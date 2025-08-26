#!/usr/bin/env python3
"""
Test RMBB Health using our EXACT workflow files - not recreating the process
"""
import sys
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
import json

def test_workflow_data_transformation():
    """Test using our actual workflow transformation methods"""
    print("🧪 Testing RMBB Health Using Our Workflow Files")
    print("=" * 60)
    
    # Initialize our actual workflow with required parameters
    workflow = GHLRMBBWorkflowHandler(
        rmbb_api_key='b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0',
        rmbb_team_id=85,
        ghl_api_key='eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2NzRhMjM2OGE0MjVjOTI1ZGNjOTM5OTkiLCJqdGkiOiJiZWUzY2FhZS00MjQzLTRhZTUtYWRjNi1iMzUxNDE5YmUzOGIiLCJpYXQiOjE3MjQ2MTMzODEsIm5iZiI6MTcyNDYxMzM4MSwiZXhwIjoxNzI3MjA1MzgxLCJzdWIiOiJ1c2VyIiwic2NvcGVzIjpbImNhbGVuZGFycy5yZWFkb25seSIsImNhbGVuZGFycy53cml0ZSIsImNhbXBhaWducy5yZWFkb25seSIsImNvbXBhbmllcy5yZWFkb25seSIsImNvbXBhbmllcy53cml0ZSIsImNvbnRhY3RzLnJlYWRvbmx5IiwiY29udGFjdHMud3JpdGUiLCJjb252ZXJzYXRpb25zLnJlYWRvbmx5IiwiY29udmVyc2F0aW9ucy53cml0ZSIsImNvdXJzZXMucmVhZG9ubHkiLCJjb3Vyc2VzLndyaXRlIiwiZm9ybXMucmVhZG9ubHkiLCJmb3Jtcy53cml0ZSIsImZ1bm5lbHMucmVhZG9ubHkiLCJsaW5rcy5yZWFkb25seSIsImxpbmtzLndyaXRlIiwibG9jYXRpb25zLnJlYWRvbmx5IiwibG9jYXRpb25zLndyaXRlIiwibWVkaWEucmVhZG9ubHkiLCJtZWRpYS53cml0ZSIsIm9wcG9ydHVuaXRpZXMucmVhZG9ubHkiLCJvcHBvcnR1bml0aWVzLndyaXRlIiwicGlwZWxpbmVzLnJlYWRvbmx5IiwicGlwZWxpbmVzLndyaXRlIiwicHJvZHVjdHMucmVhZG9ubHkiLCJwcm9kdWN0cy53cml0ZSIsInN1cnZleXMucmVhZG9ubHkiLCJzdXJ2ZXlzLndyaXRlIiwidXNlcnMucmVhZG9ubHkiLCJ1c2Vycy53cml0ZSIsIndvcmtmbG93cy5yZWFkb25seSIsIndvcmtmbG93cy53cml0ZSIsInRyaWdnZXJzLndyaXRlIl0sImxvY2F0aW9uSWQiOiJTcWJleGo1NG52c3hPSTRWN1NzRCJ9.PjHV5sqZ4ShbTf0JaWgRuBt--zRg2o4rqOGsXesDRBA'
    )
    
    # Use the EXACT same test payload that our end-to-end test uses
    test_webhook_payload = {
        "contactId": "0L8CuPLnCi5xQhbcuPUs",
        "locationId": "Sqbexj54nvsxOI4V7SsD",
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@test.com",
        "email_address": "john.doe@test.com",
        "phone": "+1234567890",
        "phone_number": "+1234567890",
        "dateOfBirth": "1990-01-01",
        "date_of_birth": "1990-01-01",
        "provider_name": "Cell Products",
        "insurance_type": "Medicare",
        "first_name": "John",
        "last_name": "Doe", 
        "patient_first_name": "John",
        "patient_last_name": "Doe",
        "patient_date_of_birth": "1990-01-01",
        "patient_phone": "+1234567890",
        "patient_email": "john.doe@test.com",
        "street_address": "123 Test Street",
        "city": "Las Vegas",
        "state": "NV",
        "zip_code": "89101",
        "wound_type": "Diabetic Foot Ulcer",
        "wound_size": "2x3cm",
        "biovance_q4154": "6",  # Use actual cm2 value instead of boolean
        "primary_insurance_name": "MEDICARE PART B",
        "primary_policy_number": "POL123456",
        "secondary_insurance_name": "AARP MEDICARE SUPPLEMENT PLAN F",
        "secondary_policy_number": "POL654321",
        "icd_10_code": "E11.621",
        "cpt_surgery_code": "12345",
        "expected_date_of_service": "2023-04-01",
        "facility_type": "Physician Office - 11"
    }
    
    print("📦 Testing with our workflow's transform methods...")
    
    # Step 1: Transform using our workflow's patient transformation
    print("\n🏥 Step 1: Transform patient data using workflow method")
    try:
        patient_data = workflow.transform_patient_data(test_webhook_payload)
        print("✅ Patient transformation successful")
        print(f"📋 Patient Data:")
        print(json.dumps(patient_data, indent=2))
        
        # Step 2: Create patient using our workflow's patient service
        print(f"\n👤 Step 2: Create patient using workflow's patient service")
        patient_response = workflow.patient_service.create_patient(85, patient_data)
        print(f"📊 Patient Response: {patient_response}")
        
        if 'id' in patient_response:
            patient_id = patient_response['id']
            print(f"✅ Patient created successfully: {patient_id}")
            
            # Step 3: Transform case data using our workflow method
            print(f"\n📋 Step 3: Transform case data using workflow method")
            case_data = workflow.transform_case_data(test_webhook_payload, patient_id)
            print("✅ Case transformation successful")
            print(f"📋 Case Data:")
            print(json.dumps(case_data, indent=2))
            
            # Step 4: Create case using our workflow's case service
            print(f"\n🏥 Step 4: Create case using workflow's case service")
            case_response = workflow.case_service.create_case(case_data)
            print(f"📊 Case Response: {case_response}")
            
            if 'id' in case_response:
                case_id = case_response['id']
                print(f"✅ SUCCESS! Case created: {case_id}")
                print(f"🎉 Our workflow files work perfectly!")
                return True
            else:
                print(f"❌ Case creation failed: {case_response}")
                return False
        else:
            print(f"❌ Patient creation failed: {patient_response}")
            return False
            
    except Exception as e:
        print(f"❌ Error in workflow test: {e}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_workflow_data_transformation()
    
    if success:
        print(f"\n🎉 WORKFLOW FILES TEST: SUCCESS!")
        print("Our workflow transformation and services work correctly")
    else:
        print(f"\n❌ WORKFLOW FILES TEST: FAILED")
        print("Issue found in our workflow transformation or services")