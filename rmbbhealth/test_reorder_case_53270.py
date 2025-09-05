#!/usr/bin/env python3
"""
Test GHL Reorder System with Case 53270

This test simulates a GHL reorder webhook request for case 53270
using PalinGen as the approved product with a new smaller wound size.

Test Scenario:
- Original case: 53270 (PalinGen - Q4173)
- Original wound: Assume 20 cm² (will be overridden)
- New wound size: 12 cm² (healing wound, smaller)
- Expected: Clear old fields, calculate new PalinGen combinations, apply reorder tag
"""

import json
import requests
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_reorder_case_53270():
    """
    Test the complete reorder workflow for case 53270
    """
    
    print("=" * 80)
    print("GHL REORDER SYSTEM TEST - CASE 53270")
    print("=" * 80)
    
    print("\\n📋 Test Case Details:")
    print(f"   Case ID: 53270")
    print(f"   Contact ID: QPRoC5cRrXs8EMVFNGdX")
    print(f"   Approved Product: PalinGen (Q4173)")
    print(f"   New Wound Size: 12 cm² (smaller healing wound)")
    print(f"   Provider: Cell Products")
    print(f"   Location: Sqbexj54nvsxOI4V7SsD")
    
    # Step 1: Prepare reorder webhook payload
    print("\\n🔄 Step 1: Preparing GHL reorder webhook payload...")
    
    reorder_payload = {
        "case_id": "53270",
        "contact_id": "QPRoC5cRrXs8EMVFNGdX", 
        "new_wound_size": "12"  # 12 cm²
    }
    
    print(f"   ✅ Payload prepared:")
    print(f"      Case ID: {reorder_payload['case_id']}")
    print(f"      Contact ID: {reorder_payload['contact_id']}")
    print(f"      New Wound Size: {reorder_payload['new_wound_size']} cm²")
    
    # Step 2: Send reorder webhook request
    print("\\n📤 Step 2: Sending reorder webhook request...")
    
    webhook_url = "http://localhost:8080/webhook/ghl-reorder"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GHL-Reorder-Test/1.0"
    }
    
    try:
        print(f"   🔄 Sending POST to {webhook_url}")
        response = requests.post(
            webhook_url,
            json=reorder_payload,
            headers=headers,
            timeout=30
        )
        
        print(f"   📨 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"   ✅ Reorder processed successfully!")
            
            # Step 3: Analyze reorder results
            print("\\n📊 Step 3: Analyzing reorder results...")
            
            print(f"   🎯 REORDER SUMMARY:")
            print(f"      Status: {response_data.get('status')}")
            print(f"      Message: {response_data.get('message')}")
            print(f"      New Wound Size: {response_data.get('new_wound_size_cm2')} cm²")
            
            # Check reorder calculation
            if 'reorder_calculation' in response_data:
                calc = response_data['reorder_calculation']
                print(f"   📐 WOUND CALCULATION:")
                print(f"      Product: {calc.get('product_name')}")
                print(f"      Summary: {calc.get('calculation_summary')}")
                print(f"      Total Coverage: {calc.get('total_coverage_cm2')} cm²")
                print(f"      Actual Waste: {calc.get('actual_waste_percent')}%")
                print(f"      GHL Fields Updated: {calc.get('ghl_fields_updated')}")
            
            # Check field clearing and tag application
            print(f"   🧹 FIELD MANAGEMENT:")
            print(f"      Fields Cleared: {response_data.get('fields_cleared', 0)}")
            print(f"      Contact Updated: {response_data.get('ghl_contact_updated')}")
            print(f"      Reorder Tag Applied: {response_data.get('reorder_tag_applied')}")
            
            # Step 4: Verify success indicators
            print("\\n✅ Step 4: Verifying reorder success...")
            
            success_indicators = []
            
            if response_data.get('status') == 'success':
                success_indicators.append("✅ Webhook processing succeeded")
            else:
                success_indicators.append("❌ Webhook processing failed")
            
            if response_data.get('fields_cleared', 0) > 0:
                success_indicators.append(f"✅ {response_data.get('fields_cleared')} fields cleared")
            else:
                success_indicators.append("❌ No fields were cleared")
            
            if response_data.get('ghl_contact_updated'):
                success_indicators.append("✅ GHL contact updated with new sizes")
            else:
                success_indicators.append("❌ GHL contact not updated")
            
            if response_data.get('reorder_tag_applied'):
                success_indicators.append("✅ 'rmbb-re-order' tag applied")
            else:
                success_indicators.append("❌ Reorder tag not applied")
            
            print(f"   📋 Success Verification:")
            for indicator in success_indicators:
                print(f"      {indicator}")
            
            all_success = all("✅" in indicator for indicator in success_indicators)
            
            if all_success:
                print(f"\\n🎉 REORDER TEST PASSED!")
                print(f"   Case 53270 successfully reordered with PalinGen for 12 cm² wound")
                print(f"   System ready for 10-week reorder workflow")
                return True
            else:
                print(f"\\n💥 REORDER TEST FAILED!")
                print(f"   Some components did not complete successfully")
                return False
                
        else:
            print(f"   ❌ Webhook request failed: {response.status_code}")
            print(f"   📄 Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Could not connect to webhook handler at {webhook_url}")
        print(f"   💡 Make sure the webhook handler is running:")
        print(f"      cd /Users/timothywade/Jarvis/rmbbhealth")
        print(f"      source /Users/timothywade/myenv/bin/activate")
        print(f"      python webhook_handler.py")
        return False
        
    except Exception as e:
        print(f"   ❌ Error during reorder test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Testing GHL Reorder System with Case 53270...")
    print("📝 This test validates the complete reorder workflow:")
    print("   1. Lookup approved product from provider cache")
    print("   2. Create reorder case data with new wound size")
    print("   3. Clear existing product custom fields")
    print("   4. Calculate new optimal size combinations")
    print("   5. Update GHL contact with new product fields")
    print("   6. Apply 'rmbb-re-order' tag for workflow trigger")
    
    success = test_reorder_case_53270()
    
    if success:
        print(f"\\n🏆 All reorder systems operational! Ready for 10-week reorder workflow.")
    else:
        print(f"\\n🔧 Some issues detected. Please review the output above.")
        
    exit(0 if success else 1)