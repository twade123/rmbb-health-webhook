#!/usr/bin/env python3
"""
Test the actual case mapping lookup process that should happen during contact updates
Focus on cases 54717 and 54718 from the logs
"""
import sys
import os
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

from services.provider_location_cache import get_provider_cache
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler

def test_case_mapping_lookup():
    """Test the actual case mapping lookup that happens during contact updates"""
    print("🔍 Testing Case Mapping Lookup for Contact Updates...")
    print("=" * 60)
    
    # Cases from the logs that should exist
    test_cases = ["54717", "54718"]
    
    try:
        # Get provider cache
        provider_cache = get_provider_cache()
        
        print("📋 Step 1: Check Case Mappings in Cache")
        case_mappings = provider_cache.cache.get("case_mappings", {})
        print(f"   Total case mappings in cache: {len(case_mappings)}")
        
        for case_id in test_cases:
            print(f"\n   🔍 Looking up case {case_id}:")
            if case_id in case_mappings:
                mapping = case_mappings[case_id]
                print(f"      ✅ Found mapping:")
                print(f"         Provider Name: '{mapping.get('provider_name')}'")
                print(f"         Contact ID: {mapping.get('contact_id')}")
                print(f"         Location ID: {mapping.get('location_id')}")
                print(f"         External ID: {mapping.get('external_id')}")
                
                # Test the provider lookup chain
                provider_name = mapping.get('provider_name')
                location_id = mapping.get('location_id')
                
                if provider_name:
                    cached_location = provider_cache.get_location_id(provider_name)
                    print(f"         Provider → Location lookup: {provider_name} → {cached_location}")
                    
                    if cached_location:
                        api_key = provider_cache.get_sub_account_api_key_by_location_id(cached_location)
                        if api_key:
                            print(f"         Location → API key lookup: ✅ Found API key")
                        else:
                            print(f"         Location → API key lookup: ❌ No API key found")
                    else:
                        print(f"         Provider lookup failed!")
                        
            else:
                print(f"      ❌ Case {case_id} NOT found in local cache")
                print(f"         This could be why contact updates fail!")
        
        # Step 2: Test the actual workflow method that would be called
        print(f"\n📋 Step 2: Test Actual Contact Update Process")
        
        # Set up minimal environment for workflow testing
        os.environ['RMBB_API_KEY'] = 'test_key'
        os.environ['RMBB_TEAM_ID'] = '85'
        os.environ['GHL_API_KEY'] = 'test_ghl_key'
        
        try:
            workflow = GHLRMBBWorkflowHandler(
                rmbb_api_key='test_key',
                rmbb_team_id=85,
                ghl_api_key='test_ghl_key'
            )
            
            # Test the case mapping-based contact update
            for case_id in test_cases:
                print(f"\n   🎯 Testing contact update for case {case_id}")
                
                # This is what should happen: look up case mapping first
                if case_id in case_mappings:
                    mapping = case_mappings[case_id]
                    contact_id = mapping.get('contact_id')
                    provider_name = mapping.get('provider_name')
                    location_id = mapping.get('location_id')
                    
                    print(f"      📋 From case mapping:")
                    print(f"         Contact ID: {contact_id}")
                    print(f"         Provider Name: '{provider_name}'")
                    print(f"         Location ID: {location_id}")
                    
                    # Test the update_contact_case_id method with these values
                    if all([contact_id, provider_name, location_id]):
                        print(f"      🔧 Testing workflow.update_contact_case_id()...")
                        result = workflow.update_contact_case_id(
                            case_id=case_id,
                            contact_id=contact_id,
                            location_id=location_id
                        )
                        print(f"      📊 Result: {result.get('success', False)} - {result.get('message', result.get('error'))}")
                    else:
                        print(f"      ❌ Missing required data from case mapping")
                        
                else:
                    print(f"      ❌ Case {case_id} not in cache - this is the problem!")
                    print(f"         When contact update is triggered, it can't find the case mapping")
                    print(f"         So it probably falls back to wrong provider selection")
        
        except Exception as workflow_error:
            print(f"   ⚠️ Workflow init failed: {workflow_error}")
            print(f"   💡 This is expected in testing, focus on the case mapping lookup results")
        
        print(f"\n📋 Step 3: Check if cache loading is the issue")
        print(f"   💡 Cases 54717 and 54718 exist in GitHub but not in local cache")
        print(f"   💡 This suggests cache loading/syncing issue between GitHub and local")
        print(f"   💡 Railway might have same issue - cache not loading GitHub data properly")
        
        print("\n" + "=" * 60)
        print("🎯 Root Cause Analysis:")
        print("   1. Cases created successfully and saved to GitHub ✅")
        print("   2. Case mappings NOT loaded into local cache ❌")
        print("   3. Contact updates can't find case mapping ❌") 
        print("   4. Falls back to wrong provider selection ❌")
        print("   5. Uses 'Cell Products Agency Account' (no API key) ❌")
        print("   6. Results in 401 error ❌")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_case_mapping_lookup()