#!/usr/bin/env python3
"""
Test Provider Cache API Key Fixes - Real Data Validation

This script tests the fixes to ensure:
1. Provider cache API key lookup works correctly
2. Contact updates use the right API keys 
3. Race condition delays prevent 401 errors
4. All provider names are properly normalized

Run this BEFORE updating Railway deployment.
"""

import os
import sys
import json
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    # Import our fixed workflow handler
    from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
    from services.provider_location_cache import get_provider_cache
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the rmbbhealth directory")
    sys.exit(1)

def test_provider_cache_loading():
    """Test 1: Verify provider cache loads correctly"""
    print("\n" + "="*60)
    print("TEST 1: Provider Cache Loading")
    print("="*60)
    
    try:
        provider_cache = get_provider_cache()
        
        if not provider_cache:
            print("❌ Provider cache is empty or None")
            return False
        
        # Use cache object methods to get stats
        stats = provider_cache.get_cache_stats()
        print(f"✅ Loaded provider cache with {stats.get('total_providers', 0)} providers")
        
        # Check for Cell Products specifically using cache methods
        location_id = provider_cache.get_location_id("Cell Products")
        if location_id:
            api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
            print(f"✅ Found Cell Products provider:")
            print(f"   📍 Location ID: {location_id}")
            print(f"   🔑 Has API Key: {'Yes' if api_key else 'No'}")
            return True
        else:
            print(f"❌ Cell Products not found in cache")
            # Show available providers by accessing internal cache
            with provider_cache.lock:
                cache_data = provider_cache.cache
                providers = [key for key in cache_data.keys() if key != "case_mappings"]
                print(f"🔍 Available providers: {providers}")
            return False
        
    except Exception as e:
        print(f"❌ Error loading provider cache: {e}")
        return False

def test_provider_header_lookup():
    """Test 2: Test provider-specific header generation"""
    print("\n" + "="*60)
    print("TEST 2: Provider Header Lookup")
    print("="*60)
    
    # Create workflow handler instance
    workflow = GHLRMBBWorkflowHandler(
        rmbb_api_key="test_key",
        rmbb_team_id="85",
        ghl_api_key="test_ghl_key"
    )
    
    try:
        # Test with Cell Products (should find cached API key)
        print("🔍 Testing with 'Cell Products' provider name:")
        headers_result = workflow._get_provider_headers("Cell Products ")  # Note: with trailing space
        
        if isinstance(headers_result, tuple):
            headers, location_id = headers_result
            auth_header = headers.get("Authorization", "")
            
            if "Bearer eyJ" in auth_header:  # JWT token starts with eyJ
                print(f"✅ Found cached API key for Cell Products")
                print(f"   📍 Location ID: {location_id}")
                print(f"   🔑 API Key: {auth_header[:50]}...")
                return True
            else:
                print(f"❌ No cached API key found for Cell Products")
                print(f"   🔑 Using: {auth_header[:50]}...")
                return False
        else:
            print(f"❌ Unexpected header result format: {type(headers_result)}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing provider headers: {e}")
        return False

def test_provider_name_normalization():
    """Test 3: Test provider name normalization edge cases"""
    print("\n" + "="*60)
    print("TEST 3: Provider Name Normalization")
    print("="*60)
    
    workflow = GHLRMBBWorkflowHandler(
        rmbb_api_key="test_key",
        rmbb_team_id="85",
        ghl_api_key="test_ghl_key"
    )
    
    test_cases = [
        "Cell Products",       # Exact match
        "Cell Products ",      # Trailing space
        " Cell Products",      # Leading space
        " Cell Products ",     # Both spaces
        "CELL PRODUCTS",       # All caps
        "cell products",       # All lowercase
    ]
    
    success_count = 0
    
    for test_name in test_cases:
        try:
            print(f"🔍 Testing: '{test_name}'")
            headers_result = workflow._get_provider_headers(test_name)
            
            if isinstance(headers_result, tuple):
                headers, location_id = headers_result
                auth_header = headers.get("Authorization", "")
                
                if "Bearer eyJ" in auth_header:
                    print(f"   ✅ Found API key")
                    success_count += 1
                else:
                    print(f"   ❌ No API key found")
            else:
                print(f"   ❌ No API key found")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n📊 Normalization Test Results: {success_count}/{len(test_cases)} passed")
    return success_count == len(test_cases)

def test_location_to_provider_lookup():
    """Test 4: Test location_id to provider name lookup"""
    print("\n" + "="*60)
    print("TEST 4: Location to Provider Lookup")
    print("="*60)
    
    workflow = GHLRMBBWorkflowHandler(
        rmbb_api_key="test_key",
        rmbb_team_id="85",
        ghl_api_key="test_ghl_key"
    )
    
    try:
        # Get expected location_id from cache using cache methods
        provider_cache = get_provider_cache()
        expected_location_id = provider_cache.get_location_id("Cell Products")
        
        if not expected_location_id:
            print("❌ No location_id found for Cell Products in cache")
            return False
        
        print(f"🔍 Testing lookup for location_id: {expected_location_id}")
        
        # Test the lookup
        provider_name = workflow._get_provider_name_by_location(expected_location_id)
        
        if provider_name:
            print(f"✅ Found provider: {provider_name}")
            return True
        else:
            print(f"❌ No provider found for location_id: {expected_location_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing location lookup: {e}")
        return False

def test_mock_contact_update():
    """Test 5: Mock contact update with timing and provider context"""
    print("\n" + "="*60)
    print("TEST 5: Mock Contact Update (Timing Test)")
    print("="*60)
    
    workflow = GHLRMBBWorkflowHandler(
        rmbb_api_key="test_key",
        rmbb_team_id="85",
        ghl_api_key="test_ghl_key"
    )
    
    # Mock contact update data
    test_contact_id = "5Qk42EBFVX3OJaxmYKOK"  # Same as in your log
    test_update_data = {
        "customFields": [
            {"key": "test_field", "value": "test_value"}
        ]
    }
    
    try:
        print(f"🔍 Testing contact update with delay...")
        print(f"   📧 Contact ID: {test_contact_id}")
        print(f"   👤 Provider: Cell Products")
        print(f"   ⏱️ Adding 3-second delay")
        
        start_time = datetime.now()
        
        # This will do the timing delay and get provider headers, but not actually call GHL
        # (since we're using test API keys, the verification will fail gracefully)
        result = workflow.update_ghl_contact(
            test_contact_id,
            test_update_data,
            provider_name="Cell Products",
            add_delay=True
        )
        
        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()
        
        print(f"   ⏱️ Total time: {elapsed:.1f} seconds")
        
        if elapsed >= 3.0:
            print(f"✅ Delay mechanism working (took {elapsed:.1f}s)")
            return True
        else:
            print(f"❌ Delay not working properly (only took {elapsed:.1f}s)")
            return False
            
    except Exception as e:
        print(f"❌ Error testing contact update: {e}")
        return False

def main():
    """Run all tests and report results"""
    print("🧪 RMBB HEALTH PROVIDER CACHE FIX VALIDATION")
    print("=" * 60)
    print("Testing fixes before Railway deployment...")
    
    tests = [
        ("Provider Cache Loading", test_provider_cache_loading),
        ("Provider Header Lookup", test_provider_header_lookup), 
        ("Provider Name Normalization", test_provider_name_normalization),
        ("Location to Provider Lookup", test_location_to_provider_lookup),
        ("Mock Contact Update Timing", test_mock_contact_update),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n📊 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED - Ready for Railway deployment!")
        return 0
    else:
        print(f"\n⚠️ {len(results) - passed} tests failed - DO NOT deploy yet!")
        return 1

if __name__ == "__main__":
    sys.exit(main())