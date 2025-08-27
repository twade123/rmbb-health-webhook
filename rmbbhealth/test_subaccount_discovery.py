#!/usr/bin/env python3
"""
Test script for GHL sub-account discovery solution

This script tests the new sub-account cache population functionality
that solves the missing location_id problem in RMBB Health webhooks.

Usage:
    python test_subaccount_discovery.py
"""

import os
import sys
import json
import requests
from datetime import datetime

# Add the rmbbhealth directory to Python path for imports
sys.path.insert(0, '/Users/timothywade/Jarvis/rmbbhealth')

def test_cache_population_function():
    """Test the cache population function directly"""
    
    print("🧪 Testing sub-account cache population function...")
    print("=" * 60)
    
    try:
        # Import the function from webhook_handler
        from webhook_handler import populate_subaccount_cache_from_agency
        
        print("✅ Successfully imported populate_subaccount_cache_from_agency function")
        
        # Check environment variables
        ghl_api_key = os.environ.get('GHL_API_KEY')
        if not ghl_api_key:
            print("❌ GHL_API_KEY environment variable not set")
            print("   Set it with: export GHL_API_KEY='your_agency_api_key'")
            return False
        
        print(f"✅ GHL_API_KEY configured: {ghl_api_key[:20]}...")
        
        # Test cache population
        print("\n🔄 Running cache population test...")
        result = populate_subaccount_cache_from_agency()
        
        print(f"📊 Cache population result:")
        print(json.dumps(result, indent=2))
        
        if result['success']:
            print(f"\n✅ SUCCESS: Cache populated with {result['total_locations_found']} locations")
            print(f"   🆕 New providers: {result['new_providers_added']}")
            print(f"   🔄 Updated providers: {result['existing_providers_updated']}")
            print(f"   📊 Total cached: {result['cache_stats']['total_providers']}")
            return True
        else:
            print(f"\n❌ FAILED: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_provider_cache_access():
    """Test provider cache read functionality"""
    
    print("\n🧪 Testing provider cache access...")
    print("=" * 60)
    
    try:
        from services.provider_location_cache import get_provider_cache
        
        provider_cache = get_provider_cache()
        cache_stats = provider_cache.get_cache_stats()
        
        print(f"📊 Provider cache statistics:")
        print(f"   Total providers: {cache_stats['total_providers']}")
        print(f"   Cache file: {cache_stats['cache_file']}")
        print(f"   Total submissions tracked: {cache_stats['total_form_submissions']}")
        
        if cache_stats['providers']:
            print(f"\n🏢 Sample providers in cache:")
            for i, provider in enumerate(cache_stats['providers'][:5]):  # First 5 providers
                print(f"   {i+1}. {provider['name']} → {provider['location_id']} ({provider['submissions']} submissions)")
            
            if len(cache_stats['providers']) > 5:
                print(f"   ... and {len(cache_stats['providers']) - 5} more providers")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache access test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_webhook_endpoint(base_url="http://localhost:8080"):
    """Test the webhook test endpoint (if server is running locally)"""
    
    print(f"\n🧪 Testing webhook endpoint: {base_url}")
    print("=" * 60)
    
    try:
        # Test health endpoint first
        health_response = requests.get(f"{base_url}/health", timeout=10)
        if health_response.status_code == 200:
            print("✅ Webhook server is running")
            health_data = health_response.json()
            print(f"   Service: {health_data['service']}")
            print(f"   GHL API configured: {health_data['configuration']['ghl_api_configured']}")
        else:
            print(f"⚠️ Health check returned {health_response.status_code}")
            return False
        
        # Test cache population endpoint
        cache_response = requests.get(f"{base_url}/test/populate-cache", timeout=30)
        if cache_response.status_code == 200:
            print("✅ Cache population endpoint test succeeded")
            cache_data = cache_response.json()
            if cache_data['result']['success']:
                print(f"   🆕 New providers: {cache_data['result']['new_providers_added']}")
                print(f"   🔄 Updated providers: {cache_data['result']['existing_providers_updated']}")
                print(f"   📊 Total after: {cache_data['after_stats']['total_providers']}")
            return True
        else:
            print(f"❌ Cache endpoint test failed: {cache_response.status_code}")
            if cache_response.content:
                print(f"   Error: {cache_response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️ Could not connect to webhook server (not running locally?)")
        print("   Start server with: python webhook_handler.py")
        return False
    except Exception as e:
        print(f"❌ Webhook endpoint test failed: {e}")
        return False

def main():
    """Run all tests"""
    
    print("🚀 RMBB Health Sub-Account Discovery Solution Test")
    print("=" * 60)
    print(f"📅 Test started: {datetime.now().isoformat()}")
    print()
    
    # Activate virtual environment reminder
    python_path = sys.executable
    if 'myenv' not in python_path:
        print("⚠️ WARNING: Virtual environment may not be activated")
        print("   Run: source /Users/timothywade/myenv/bin/activate")
        print()
    
    test_results = []
    
    # Test 1: Direct function test
    test_results.append(("Cache Population Function", test_cache_population_function()))
    
    # Test 2: Cache access test
    test_results.append(("Provider Cache Access", test_provider_cache_access()))
    
    # Test 3: Webhook endpoint test (optional)
    test_results.append(("Webhook Endpoint", test_webhook_endpoint()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Sub-account discovery solution is working.")
        print("\n💡 Next steps:")
        print("   1. Set GHL_API_KEY environment variable in Railway")
        print("   2. Deploy updated webhook_handler.py to Railway")
        print("   3. Test with real RMBB Health webhook data")
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        
    return passed == total

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)