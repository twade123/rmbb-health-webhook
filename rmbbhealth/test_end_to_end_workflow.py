#!/usr/bin/env python3
"""
End-to-End Workflow Test for RMBB Health + GHL Integration

This test simulates the complete workflow:
1. GHL form submission webhook (triggers cache refresh)
2. Case creation in RMBB Health
3. Case mapping added to cache
4. RMBB Health status update webhook
5. GHL contact update using case_id mapping

Uses REAL API credentials for comprehensive testing.
"""

import requests
import json
import time
from datetime import datetime
import sys
import os

# Add the rmbbhealth directory to Python path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

from services.provider_location_cache import get_provider_cache
from services.case_service import CaseService
from services.patient_service import PatientService
from client import RMBBHealthClient

class EndToEndWorkflowTest:
    def __init__(self):
        # Real API credentials
        self.ghl_api_key = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2NzRhMjM2OGE0MjVjOTI1ZGNjOTM5OTkiLCJqdGkiOiJiZWUzY2FhZS00MjQzLTRhZTUtYWRjNi1iMzUxNDE5YmUzOGIiLCJpYXQiOjE3MjQ2MTMzODEsIm5iZiI6MTcyNDYxMzM4MSwiZXhwIjoxNzI3MjA1MzgxLCJzdWIiOiJ1c2VyIiwic2NvcGVzIjpbImNhbGVuZGFycy5yZWFkb25seSIsImNhbGVuZGFycy53cml0ZSIsImNhbXBhaWducy5yZWFkb25seSIsImNvbXBhbmllcy5yZWFkb25seSIsImNvbXBhbmllcy53cml0ZSIsImNvbnRhY3RzLnJlYWRvbmx5IiwiY29udGFjdHMud3JpdGUiLCJjb252ZXJzYXRpb25zLnJlYWRvbmx5IiwiY29udmVyc2F0aW9ucy53cml0ZSIsImNvdXJzZXMucmVhZG9ubHkiLCJjb3Vyc2VzLndyaXRlIiwiZm9ybXMucmVhZG9ubHkiLCJmb3Jtcy53cml0ZSIsImZ1bm5lbHMucmVhZG9ubHkiLCJsaW5rcy5yZWFkb25seSIsImxpbmtzLndyaXRlIiwibG9jYXRpb25zLnJlYWRvbmx5IiwibG9jYXRpb25zLndyaXRlIiwibWVkaWEucmVhZG9ubHkiLCJtZWRpYS53cml0ZSIsIm9wcG9ydHVuaXRpZXMucmVhZG9ubHkiLCJvcHBvcnR1bml0aWVzLndyaXRlIiwicGlwZWxpbmVzLnJlYWRvbmx5IiwicGlwZWxpbmVzLndyaXRlIiwicHJvZHVjdHMucmVhZG9ubHkiLCJwcm9kdWN0cy53cml0ZSIsInN1cnZleXMucmVhZG9ubHkiLCJzdXJ2ZXlzLndyaXRlIiwidXNlcnMucmVhZG9ubHkiLCJ1c2Vycy53cml0ZSIsIndvcmtmbG93cy5yZWFkb25seSIsIndvcmtmbG93cy53cml0ZSIsInRyaWdnZXJzLndyaXRlIl0sImxvY2F0aW9uSWQiOiJTcWJleGo1NG52c3hPSTRWN1NzRCJ9.PjHV5sqZ4ShbTf0JaWgRuBt--zRg2o4rqOGsXesDRBA"
        self.rmbb_api_key = "b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0"
        self.rmbb_team_id = "85"
        
        # Test location and webhook URLs
        self.webhook_base = "http://localhost:8080"
        self.test_location_id = "Sqbexj54nvsxOI4V7SsD"  # Cell Products
        
        # Initialize services
        self.rmbb_client = RMBBHealthClient()
        self.case_service = CaseService(self.rmbb_client)
        self.patient_service = PatientService(self.rmbb_client)
        self.provider_cache = get_provider_cache()
        
        print("🚀 End-to-End Workflow Test Initialized")
        print(f"   Webhook Base: {self.webhook_base}")
        print(f"   Test Location: {self.test_location_id}")
        print(f"   RMBB Team ID: {self.rmbb_team_id}")
    
    def step_1_simulate_ghl_webhook(self):
        """
        STEP 1: Simulate GHL form submission webhook
        This should trigger cache refresh BEFORE any processing
        """
        print("\n" + "="*80)
        print("STEP 1: Simulating GHL Form Submission Webhook")
        print("="*80)
        
        # Use real contact ID created in GHL for testing
        contact_id = "0L8CuPLnCi5xQhbcuPUs"
        test_payload = {
            "contactId": contact_id,
            "locationId": self.test_location_id,
            "firstName": "John",
            "lastName": "Doe", 
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@test.com",
            "email_address": "john.doe@test.com",
            "phone": "+1234567890",
            "phone_number": "+1234567890",
            "dateOfBirth": "1990-01-01",
            "date_of_birth": "1990-01-01",
            "provider_name": "Cell Products",
            "insurance_type": "Medicare",
            "patient_first_name": "John",
            "patient_last_name": "Doe",
            "patient_date_of_birth": "1990-01-01",
            "patient_phone": "+1234567890",
            "patient_email": "john.doe@test.com",
            # REQUIRED ADDRESS FIELDS for RMBB Health API
            "street_address": "123 Test Street",
            "city": "Las Vegas",
            "state": "NV",
            "zip_code": "89101",
            # Add some common fields from actual GHL webhooks
            "wound_type": "Diabetic Foot Ulcer",
            "wound_size": "2x3cm",
            "product_biovance": "true",
            "product_amniomaxx": "false",
            "product_palingen": "false",
            # Required insurance fields for RMBB Health API
            "primary_insurance_name": "MEDICARE PART B",
            "primary_policy_number": "POL123456",
            "secondary_insurance_name": "AARP MEDICARE SUPPLEMENT PLAN F",
            "secondary_policy_number": "POL654321",
            # Required medical fields for case creation
            "icd_10_code": "E11.621",
            "cpt_surgery_code": "12345",
            "expected_date_of_service": "2023-04-01",
            "facility_type": "Physician Office - 11"
        }
        
        try:
            # Send webhook to our Flask app
            response = requests.post(
                f"{self.webhook_base}/webhook/ghl-rmbb-qualification",
                json=test_payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.ghl_api_key}"
                },
                timeout=30
            )
            
            print(f"✅ GHL Webhook Response: {response.status_code}")
            print(f"📄 Response Body: {response.text[:500]}")
            
            if response.status_code == 200:
                response_data = response.json()
                if "case_id" in response_data:
                    print(f"🎯 Case Created: {response_data['case_id']}")
                    return response_data['case_id']
                    
        except Exception as e:
            print(f"❌ Error in GHL webhook: {e}")
            return None
    
    def step_2_verify_cache_updated(self):
        """
        STEP 2: Verify provider cache was refreshed and updated
        """
        print("\n" + "="*80)
        print("STEP 2: Verifying Provider Cache Update")
        print("="*80)
        
        cache_stats = self.provider_cache.get_cache_stats()
        print(f"📊 Cache Stats:")
        print(f"   Total Providers: {cache_stats['total_providers']}")
        print(f"   Total Cases: {cache_stats['total_cases']}")
        print(f"   Total Submissions: {cache_stats['total_form_submissions']}")
        
        # Check if Cell Products is in cache
        cell_products_id = self.provider_cache.get_location_id("Cell Products")
        if cell_products_id:
            print(f"✅ Cell Products found in cache: {cell_products_id}")
            return True
        else:
            print("❌ Cell Products NOT found in cache")
            return False
    
    def step_3_verify_case_mapping(self, case_id):
        """
        STEP 3: Verify case ID was mapped to provider in cache
        """
        if not case_id:
            print("\n❌ STEP 3 SKIPPED: No case_id from previous step")
            return False
            
        print("\n" + "="*80)
        print(f"STEP 3: Verifying Case Mapping for Case {case_id}")
        print("="*80)
        
        case_mapping = self.provider_cache.get_case_mapping(case_id)
        if case_mapping:
            print(f"✅ Case mapping found:")
            print(f"   Case ID: {case_mapping['case_id']}")
            print(f"   Provider: {case_mapping['provider_name']}")
            print(f"   Location ID: {case_mapping.get('location_id')}")
            print(f"   Contact ID: {case_mapping['contact_id']}")
            print(f"   External ID: {case_mapping.get('external_id')}")
            return True
        else:
            print(f"❌ Case mapping NOT found for case {case_id}")
            return False
    
    def step_4_simulate_rmbb_status_webhook(self, case_id):
        """
        STEP 4: Simulate RMBB Health status update webhook
        This should use case_id mapping for routing
        """
        if not case_id:
            print("\n❌ STEP 4 SKIPPED: No case_id from previous step")
            return False
            
        print("\n" + "="*80)
        print(f"STEP 4: Simulating RMBB Health Status Update for Case {case_id}")
        print("="*80)
        
        # Get case mapping for external_id and provider_name
        case_mapping = self.provider_cache.get_case_mapping(case_id)
        if not case_mapping:
            print(f"❌ No case mapping found for case {case_id}")
            return False
            
        # Create RMBB status update payload (official format from RMBB Health)
        status_payload = {
            "case_id": int(case_id),
            "team_id": 85,
            "status": "UNDER_REVIEW",
            "external_id": case_mapping['external_id'],
            "provider_name": case_mapping['provider_name']
        }
        
        try:
            # Send status webhook to our Flask app (with authentication)
            response = requests.post(
                f"{self.webhook_base}/webhook/rmbb-status-update",
                json=status_payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer rmbb-health-webhook-2025"
                },
                timeout=30
            )
            
            print(f"✅ RMBB Status Webhook Response: {response.status_code}")
            print(f"📄 Response Body: {response.text[:500]}")
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"🎯 Status Update Processed: {response_data.get('message', 'Success')}")
                return True
                
        except Exception as e:
            print(f"❌ Error in RMBB status webhook: {e}")
            return False
    
    def step_5_verify_ghl_contact_update(self, case_id):
        """
        STEP 5: Verify GHL contact was updated with status information
        """
        if not case_id:
            print("\n❌ STEP 5 SKIPPED: No case_id from previous step")
            return False
            
        print("\n" + "="*80)
        print(f"STEP 5: Verifying GHL Contact Update for Case {case_id}")
        print("="*80)
        
        # Get case mapping to find contact
        case_mapping = self.provider_cache.get_case_mapping(case_id)
        if not case_mapping:
            print(f"❌ Cannot verify - case mapping not found")
            return False
        
        contact_id = case_mapping['contact_id']
        location_id = case_mapping['location_id']
        
        try:
            # Check GHL contact for updated custom fields
            headers = {
                'Authorization': f'Bearer {self.ghl_api_key}',
                'Content-Type': 'application/json',
                'Version': '2021-07-28'
            }
            
            response = requests.get(
                f"https://services.leadconnectorhq.com/contacts/{contact_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                contact_data = response.json()
                custom_fields = contact_data.get('contact', {}).get('customFields', [])
                
                print(f"✅ Contact found in GHL: {contact_id}")
                print(f"📋 Custom fields count: {len(custom_fields)}")
                
                # Look for RMBB status fields
                rmbb_fields = [field for field in custom_fields if 'rmbb' in field.get('fieldKey', '').lower()]
                if rmbb_fields:
                    print(f"🎯 RMBB status fields found:")
                    for field in rmbb_fields[:5]:  # Show first 5
                        print(f"   {field.get('fieldKey')}: {field.get('fieldValue')}")
                    return True
                else:
                    print(f"⚠️ No RMBB status fields found in contact")
                    return False
            else:
                print(f"❌ Error fetching contact: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error verifying GHL contact: {e}")
            return False
    
    def run_complete_test(self):
        """
        Run the complete end-to-end workflow test
        """
        print("🧪 Starting Complete End-to-End Workflow Test")
        print("This will test the entire integration with REAL API data")
        print("-" * 80)
        
        results = {
            "step_1_ghl_webhook": False,
            "step_2_cache_updated": False,
            "step_3_case_mapping": False,
            "step_4_rmbb_status": False,
            "step_5_ghl_update": False,
            "case_id": None
        }
        
        # Step 1: GHL webhook (creates case and refreshes cache)
        case_id = self.step_1_simulate_ghl_webhook()
        results["case_id"] = case_id
        results["step_1_ghl_webhook"] = bool(case_id)
        
        # Step 2: Verify cache was updated
        results["step_2_cache_updated"] = self.step_2_verify_cache_updated()
        
        # Step 3: Verify case mapping exists
        results["step_3_case_mapping"] = self.step_3_verify_case_mapping(case_id)
        
        # Step 4: RMBB status webhook (uses case_id mapping)
        results["step_4_rmbb_status"] = self.step_4_simulate_rmbb_status_webhook(case_id)
        
        # Step 5: Verify GHL contact was updated
        results["step_5_ghl_update"] = self.step_5_verify_ghl_contact_update(case_id)
        
        # Final Results
        print("\n" + "="*80)
        print("FINAL TEST RESULTS")
        print("="*80)
        
        total_steps = len([k for k in results.keys() if k.startswith('step_')])
        passed_steps = sum([1 for k, v in results.items() if k.startswith('step_') and v])
        
        print(f"📊 Overall Results: {passed_steps}/{total_steps} steps passed")
        print(f"🎯 Case ID Generated: {results['case_id']}")
        
        for step, passed in results.items():
            if step.startswith('step_'):
                status = "✅ PASS" if passed else "❌ FAIL"
                step_name = step.replace('step_', '').replace('_', ' ').title()
                print(f"   {step_name}: {status}")
        
        if passed_steps == total_steps:
            print("\n🎉 END-TO-END TEST SUCCESSFUL!")
            print("   All workflow components are working correctly")
        else:
            print(f"\n⚠️ TEST PARTIAL SUCCESS: {passed_steps}/{total_steps} steps passed")
            print("   Review failed steps above for issues")
        
        return results

def main():
    """Main test execution"""
    test = EndToEndWorkflowTest()
    
    print("⚡ Starting Flask webhook server check...")
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            print("✅ Flask server is running")
        else:
            print("⚠️ Flask server responded but may have issues")
    except:
        print("❌ Flask server not running - start webhook_handler.py first")
        print("   Run: python webhook_handler.py")
        return
    
    # Run the complete test
    results = test.run_complete_test()
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"end_to_end_test_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    main()