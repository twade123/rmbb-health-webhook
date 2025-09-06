#!/usr/bin/env python3
"""
End-to-End Webhook Simulation Test

This test simulates a complete RMBB Health webhook approval notification
to test the entire workflow from webhook receipt through wound calculation
to GHL contact updates.

This provides the most realistic test of the production workflow.
"""

import json
import requests
import time
from datetime import datetime

def test_end_to_end_webhook_simulation():
    """
    Simulate an RMBB Health webhook call with approved case data
    to test the complete end-to-end workflow.
    """
    
    print("=" * 80)
    print("END-TO-END WEBHOOK SIMULATION TEST")
    print("=" * 80)
    
    # Step 1: Prepare webhook payload with our test case data
    print("\n🎬 Step 1: Preparing RMBB Health webhook simulation...")
    
    # Simulate webhook payload based on real case 53330 but with approval status
    # and larger wound size for meaningful calculation
    webhook_payload = {
        "case_id": "53330",
        "external_id": "ghl_contact_9ycwwscO60MGHiTTBDzo_20250827_183035_Q4239",
        
        # Case data structure (as it would come from RMBB Health API)
        "case_data": {
            "id": 53330,
            "tid": 85,
            "status": "APPROVED",  # ✅ Set to approved to trigger wound calculation
            "external_status": "APPROVED",
            "overall_insurance_result": "APPROVED",
            
            # Wound information - using larger size for meaningful calculation
            "wound_size": "8x8 cm",  # 64 cm² wound
            "total_wound_size": "64 cm2",
            "wound_type": "Diabetic Ulcer",
            
            # Product information (matches real case 53330)
            "product": {
                "id": 364,  # Development ID for AmnioMaxx
                "name": "AmnioMaxx",
                "q_code": "Q4239"
            },
            
            # Insurance information
            "primary_insurance": {
                "status": "APPROVED",
                "result": "APPROVED"
            },
            "secondary_insurance": {
                "status": "N/A",
                "result": "N/A"
            },
            
            # Patient and provider information
            "patient": {
                "first_name": "Test",
                "last_name": "Patient"
            }
        },
        
        # GHL routing information (from provider cache)
        "ghl_contact_id": "9ycwwscO60MGHiTTBDzo",
        "ghl_location_id": "Sqbexj54nvsxOI4V7SsD",
        "provider_name": "Cell Products",
        "location_id": "Sqbexj54nvsxOI4V7SsD"
    }
    
    print(f"   ✅ Prepared webhook payload:")
    print(f"      Case ID: {webhook_payload['case_id']}")
    print(f"      Status: {webhook_payload['case_data']['status']}")
    print(f"      Wound Size: {webhook_payload['case_data']['wound_size']} = {webhook_payload['case_data']['total_wound_size']}")
    print(f"      Product: {webhook_payload['case_data']['product']['name']} (ID: {webhook_payload['case_data']['product']['id']})")
    print(f"      Target Contact: {webhook_payload['ghl_contact_id']}")
    
    # Step 2: Start the webhook handler locally (if not already running)
    print(f"\n🚀 Step 2: Webhook endpoint preparation...")
    webhook_url = "http://localhost:8080/webhook/rmbb-status-update"
    print(f"   📡 Target webhook URL: {webhook_url}")
    print(f"   ⚠️ Make sure webhook handler is running: python webhook_handler.py")
    
    # Step 3: Send the webhook request
    print(f"\n📤 Step 3: Sending webhook request...")
    
    try:
        # Send POST request to webhook endpoint
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RMBB-Health-Webhook/1.0",
            "Authorization": "Bearer rmbb-health-webhook-2025"  # Default webhook auth token
        }
        
        print(f"   🔄 Sending webhook POST request...")
        response = requests.post(
            webhook_url,
            json=webhook_payload,
            headers=headers,
            timeout=30
        )
        
        print(f"   📨 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"   ✅ Webhook processed successfully!")
            
            # Step 4: Analyze the response
            print(f"\n📋 Step 4: Analyzing webhook response...")
            
            print(f"   📊 Response Summary:")
            print(f"      Status: {response_data.get('status')}")
            print(f"      Message: {response_data.get('message')}")
            print(f"      Contact Updated: {response_data.get('ghl_contact_updated')}")
            print(f"      Provider Notified: {response_data.get('provider_notified')}")
            
            # Check approval analysis
            if 'approval_analysis' in response_data:
                approval = response_data['approval_analysis']
                print(f"   🎯 Approval Analysis:")
                print(f"      Status: {approval.get('status')}")
                print(f"      Confidence: {approval.get('confidence')}")
                print(f"      Message: {approval.get('message')}")
            
            # Check wound calculation results
            if 'wound_calculation' in response_data:
                wound_calc = response_data['wound_calculation']
                print(f"   💊 Wound Calculation Results:")
                print(f"      Success: {wound_calc.get('success')}")
                print(f"      Summary: {wound_calc.get('calculation_summary')}")
                print(f"      Total Coverage: {wound_calc.get('total_coverage_cm2')} cm²")
                print(f"      Actual Waste: {wound_calc.get('actual_waste_percent')}%")
                print(f"      GHL Fields Updated: {wound_calc.get('ghl_fields_updated')}")
                
                if wound_calc.get('case_context'):
                    context = wound_calc['case_context']
                    print(f"      Original Wound: {context.get('total_wound_size_str')}")
                    print(f"      Product ID: {context.get('rmbb_product_id')}")
                
                if wound_calc.get('mapped_product'):
                    product = wound_calc['mapped_product']
                    print(f"      Mapped Product: {product.get('name')} ({product.get('q_code')})")
                
            else:
                print(f"   ⚠️ No wound calculation results in response")
            
            # Step 5: Verify GHL contact was updated
            print(f"\n🔗 Step 5: End-to-End Test Summary")
            
            success_indicators = []
            
            # Check webhook processing
            if response_data.get('status') == 'success':
                success_indicators.append("✅ Webhook processed successfully")
            else:
                success_indicators.append("❌ Webhook processing failed")
            
            # Check approval detection
            if response_data.get('approval_analysis', {}).get('status') == 'APPROVED':
                success_indicators.append("✅ Approval status detected")
            else:
                success_indicators.append("❌ Approval status not detected")
            
            # Check wound calculation
            if response_data.get('wound_calculation', {}).get('success'):
                success_indicators.append("✅ Wound calculation completed")
            else:
                success_indicators.append("❌ Wound calculation failed")
            
            # Check GHL update
            if response_data.get('ghl_contact_updated'):
                success_indicators.append("✅ GHL contact updated")
            else:
                success_indicators.append("❌ GHL contact not updated")
            
            print(f"\n   📊 Test Results:")
            for indicator in success_indicators:
                print(f"      {indicator}")
            
            all_success = all("✅" in indicator for indicator in success_indicators)
            
            if all_success:
                print(f"\n🎉 END-TO-END TEST PASSED!")
                print(f"   Complete workflow from webhook → approval detection → wound calculation → GHL update succeeded!")
                return True
            else:
                print(f"\n💥 END-TO-END TEST FAILED!")
                print(f"   Some components of the workflow did not complete successfully.")
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
        print(f"   ❌ Error during webhook test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Starting End-to-End Webhook Simulation Test...")
    print("📝 This test simulates the complete RMBB Health approval workflow:")
    print("   1. Webhook receives approval notification")
    print("   2. System detects approved status")
    print("   3. Wound calculation processes case data")
    print("   4. GHL contact is updated with size-specific fields")
    print("   5. Provider notification is sent")
    
    success = test_end_to_end_webhook_simulation()
    
    if success:
        print(f"\n🏆 All systems operational! Ready for production.")
    else:
        print(f"\n🔧 Some issues detected. Please review the output above.")
        
    exit(0 if success else 1)