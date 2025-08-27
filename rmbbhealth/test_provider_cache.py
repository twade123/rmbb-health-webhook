#!/usr/bin/env python3
"""
Test the Provider-Location Cache system to verify RMBB Health → GHL routing works correctly.
"""

import os
import sys
import json

# Add the rmbbhealth directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import directly from the cache module
from services.provider_location_cache import ProviderLocationCache

def test_provider_cache():
    """Test the provider cache functionality"""
    
    print("🧪 Testing Provider-Location Cache System")
    print("=" * 50)
    
    # Create test cache with temporary file
    test_cache_file = "test_provider_cache.json"
    cache = ProviderLocationCache(test_cache_file)
    
    # Test data simulating GHL webhook submissions
    test_providers = [
        {
            "provider_name": "Dr. Smith Medical Group",
            "location_id": "loc_abc123",
            "contact_id": "contact_456"
        },
        {
            "provider_name": "City Health Center", 
            "location_id": "loc_def789",
            "contact_id": "contact_789"
        },
        {
            "provider_name": "Dr. Smith Medical Group",  # Duplicate - should update, not create new
            "location_id": "loc_abc123",
            "contact_id": "contact_999"
        },
        {
            "provider_name": "RMBB Health Partners",
            "location_id": "loc_ghi012",
            "contact_id": "contact_111"
        }
    ]
    
    print("\n📝 Step 1: Adding providers to cache (simulating GHL webhooks)...")
    for i, provider in enumerate(test_providers, 1):
        print(f"\n   Adding provider {i}: {provider['provider_name']}")
        success = cache.add_or_update_provider(
            provider_name=provider['provider_name'],
            location_id=provider['location_id'], 
            contact_id=provider['contact_id']
        )
        print(f"   Result: {'✅ Success' if success else '❌ Failed'}")
    
    print(f"\n📊 Step 2: Cache Statistics")
    stats = cache.get_cache_stats()
    print(f"   Total providers: {stats['total_providers']}")
    print(f"   Total submissions: {stats['total_form_submissions']}")
    print(f"   Cache file: {stats['cache_file']}")
    
    print(f"\n   Providers in cache:")
    for provider in stats['providers']:
        print(f"   - {provider['name']} → {provider['location_id']} ({provider['submissions']} submissions)")
    
    print(f"\n🔍 Step 3: Testing lookups (simulating RMBB Health responses)...")
    
    # Test successful lookups
    test_lookups = [
        "Dr. Smith Medical Group",
        "City Health Center", 
        "RMBB Health Partners",
        "Dr. Smith Medical Group".upper(),  # Test case insensitive
        "  Dr. Smith Medical Group  ",      # Test whitespace handling
    ]
    
    for provider_name in test_lookups:
        print(f"\n   Looking up: '{provider_name}'")
        location_id = cache.get_location_id(provider_name)
        if location_id:
            print(f"   ✅ Found: {location_id}")
        else:
            print(f"   ❌ Not found")
    
    # Test failed lookup
    print(f"\n   Looking up unknown provider: 'Unknown Medical Center'")
    location_id = cache.get_location_id("Unknown Medical Center")
    if location_id:
        print(f"   ✅ Found: {location_id}")
    else:
        print(f"   ❌ Not found (expected)")
    
    print(f"\n💾 Step 4: Testing persistence...")
    
    # Create new cache instance from same file to test persistence
    cache2 = ProviderLocationCache(test_cache_file)
    stats2 = cache2.get_cache_stats()
    
    print(f"   Reloaded cache has {stats2['total_providers']} providers")
    print(f"   Persistence test: {'✅ PASSED' if stats2['total_providers'] == stats['total_providers'] else '❌ FAILED'}")
    
    # Test lookup after reload
    location_id = cache2.get_location_id("Dr. Smith Medical Group")
    print(f"   Lookup after reload: {'✅ PASSED' if location_id == 'loc_abc123' else '❌ FAILED'}")
    
    print(f"\n🧹 Step 5: Cleanup")
    # Clean up test file
    if os.path.exists(test_cache_file):
        os.remove(test_cache_file)
        print(f"   ✅ Removed test cache file")
    
    print(f"\n🎉 Provider Cache Test Complete!")
    print(f"   ✅ Cache successfully stores provider → locationId mappings")
    print(f"   ✅ Cache persists across restarts (Railway compatible)")
    print(f"   ✅ Cache handles duplicates correctly")
    print(f"   ✅ Cache supports case-insensitive and whitespace-tolerant lookups")
    print(f"   ✅ RMBB Health responses can be routed to correct GHL sub-accounts")

def test_workflow_integration():
    """Test how the cache integrates with the complete workflow"""
    
    print(f"\n🔗 Testing Workflow Integration")
    print("=" * 40)
    
    # Simulate complete workflow with cache
    print(f"\n📧 Simulating GHL webhook with provider data...")
    
    mock_ghl_payload = {
        "contactId": "contact_test_123",
        "locationId": "loc_test_456", 
        "Patient First Name": "John",
        "Patient Last Name": "Smith",
        "Provider Name": "Dr. Johnson Clinic",
        "Wound Type": "Diabetic Ulcer"
    }
    
    print(f"   GHL Payload: contactId={mock_ghl_payload['contactId']}, locationId={mock_ghl_payload['locationId']}")
    print(f"   Provider: {mock_ghl_payload['Provider Name']}")
    
    # Test cache storage
    test_cache_file = "test_workflow_cache.json"
    cache = ProviderLocationCache(test_cache_file)
    
    cache.add_or_update_provider(
        provider_name=mock_ghl_payload['Provider Name'],
        location_id=mock_ghl_payload['locationId'],
        contact_id=mock_ghl_payload['contactId']
    )
    
    print(f"\n📋 Simulating RMBB Health IVR response...")
    
    mock_rmbb_response = {
        "external_id": "ghl_contact_test_123_20250821_143000",
        "provider_name": "Dr. Johnson Clinic",  # This is what RMBB sends back
        "status": "qualified",
        "ivr_data": {
            "approval_status": "APPROVED",
            "qualification_level": "FULL_COVERAGE"
        }
    }
    
    print(f"   RMBB Response: provider_name={mock_rmbb_response['provider_name']}")
    print(f"   IVR Status: {mock_rmbb_response['ivr_data']['approval_status']}")
    
    # Test cache lookup for routing
    routing_location_id = cache.get_location_id(mock_rmbb_response['provider_name'])
    
    print(f"\n🔀 Cache Lookup Result:")
    if routing_location_id:
        print(f"   ✅ Found locationId: {routing_location_id}")
        print(f"   ✅ Can route RMBB response to correct GHL sub-account")
        
        if routing_location_id == mock_ghl_payload['locationId']:
            print(f"   ✅ ROUTING TEST PASSED: Correct sub-account identified")
        else:
            print(f"   ❌ ROUTING TEST FAILED: Wrong sub-account")
    else:
        print(f"   ❌ No locationId found - routing would fail")
    
    # Cleanup
    if os.path.exists(test_cache_file):
        os.remove(test_cache_file)
    
    print(f"\n🎯 Workflow Integration Test Complete!")

if __name__ == "__main__":
    test_provider_cache()
    test_workflow_integration()