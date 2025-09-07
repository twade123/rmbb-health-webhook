#!/usr/bin/env python3
"""
Debug provider name lookup to identify the 401 API error cause
"""
import sys
import os
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

from services.provider_location_cache import get_provider_cache

def debug_provider_lookup():
    """Debug provider name lookup to find the mismatch"""
    print("🔍 Debugging Provider Lookup for API Key Issues...")
    print("=" * 60)
    
    try:
        # Get provider cache
        provider_cache = get_provider_cache()
        print(f"📊 Total providers in cache: {len(provider_cache.cache)}")
        
        # Show all provider entries
        print("\n📋 All Provider Entries:")
        for key, data in provider_cache.cache.items():
            if key == "case_mappings":
                continue
            
            original_name = data.get("original_name", key)
            location_id = data.get("location_id")
            api_key_status = data.get("api_key_status", "unknown")
            sub_account_key = data.get("sub_account_api_key")
            
            print(f"   🏥 Key: '{key}'")
            print(f"      Original Name: '{original_name}'")
            print(f"      Location ID: {location_id}")
            print(f"      API Key Status: {api_key_status}")
            print(f"      Has Sub-Account Key: {'Yes' if sub_account_key else 'No'}")
            if sub_account_key:
                print(f"      Sub-Account Key: {sub_account_key[:30]}...")
            print()
        
        # Test specific lookups that might be failing
        test_names = [
            "Cell Products",
            "cell products",
            "CELL PRODUCTS", 
            "Cell Products Agency Account",
            "cell products agency account"
        ]
        
        print("🔍 Testing Provider Name Lookups:")
        for name in test_names:
            print(f"\n   Testing: '{name}'")
            
            # Test location_id lookup
            location_id = provider_cache.get_location_id(name)
            print(f"      get_location_id() → {location_id}")
            
            if location_id:
                # Test API key lookup
                api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
                if api_key:
                    print(f"      get_sub_account_api_key_by_location_id() → {api_key[:30]}...")
                else:
                    print(f"      get_sub_account_api_key_by_location_id() → None")
            else:
                print(f"      No location_id found - can't test API key lookup")
        
        # Check case mappings for recent cases
        print(f"\n📋 Recent Case Mappings:")
        case_mappings = provider_cache.cache.get("case_mappings", {})
        
        recent_cases = ["54717", "54718"]  # From your logs
        for case_id in recent_cases:
            if case_id in case_mappings:
                mapping = case_mappings[case_id]
                print(f"   Case {case_id}:")
                print(f"      Provider Name: '{mapping.get('provider_name')}'")
                print(f"      Provider Key: '{mapping.get('provider_key')}'") 
                print(f"      Location ID: {mapping.get('location_id')}")
                print(f"      Contact ID: {mapping.get('contact_id')}")
            else:
                print(f"   Case {case_id}: Not found in cache")
        
        print("\n" + "=" * 60)
        print("🎯 Analysis Complete - Look for mismatches above!")
        
    except Exception as e:
        print(f"❌ Debug failed: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_provider_lookup()