#!/usr/bin/env python3
"""
Complete RMBB Health Integration Test Suite
Tests the entire GHL → RMBB Health → GHL workflow with Railway environment variables
"""

import os
import json
import requests
from datetime import datetime

def test_environment_variables():
    """Test that all required Railway environment variables are set"""
    print("🔧 Testing Railway Environment Variables...")
    
    required_vars = [
        'RMBB_API_KEY',
        'RMBB_TEAM_ID', 
        'RMBB_PHYSICIAN_ID',
        'RMBB_ACCOUNT_ID',
        'RMBB_ACCOUNT_LOCATION_ID',
        'GHL_API_KEY',
        'GHL_BASE_URL',
        'WEBHOOK_AUTH_TOKEN'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # Mask sensitive values in output
            if 'API_KEY' in var or 'TOKEN' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"  ✅ {var}: {display_value}")
    
    if missing_vars:
        print(f"  ❌ Missing variables: {', '.join(missing_vars)}")
        return False
    
    print("  ✅ All environment variables are set!")
    return True

def test_ghl_webhook_payload():
    """Test GHL webhook payload with all required fields"""
    print("\n📦 Testing GHL Webhook Payload Processing...")
    
    # Sample GHL webhook payload with all required fields
    test_payload = {
        "contactId": "test_contact_123",
        "locationId": "test_location_456",
        
        # Patient Information
        "patient_first_name": "John",
        "patient_last_name": "Smith", 
        "patient_dob": "1985-03-15",
        "patient_street_address": "123 Main Street",
        "patient_city": "Anytown",
        "patient_state": "CA",
        "patient_zip_code": "12345",
        
        # Insurance Information
        "patient_primary_insurance": "Medicare Part B",
        "patient_primary_insurance_#": "POL123456",
        "patient_secondary_insurance": "AARP Supplement",
        "patient_secondary_insurance_#": "POL654321",
        
        # Medical & Facility Information
        "facility_type": "Physician Office",
        "facility_npi_#": "1234567890",
        "expected_date_of_service": "2025-08-25",
        "icd_-_10_diagnosis_code(s)": "E11.621",
        "(Provider ) email": "provider@example.com",
        
        # Biologic Product Selection (Provider selects one)
        "amniomaxx_(q4239)_units/cm2": "5.2",  # Selected product
        "palingen_(q4173)_units/cm2": "",      # Not selected
        "biovance_(q4154)_units/cm2": "",      # Not selected
        # ... other products empty
    }
    
    print(f"  📋 Test payload has {len(test_payload)} fields")
    print(f"  🧬 Selected biologic: amniomaxx (Q4239) - 5.2 cm2")
    
    return test_payload

def test_field_mapping():
    """Test that GHL fields map correctly to RMBB Health format"""
    print("\n🔄 Testing Field Mapping...")
    
    from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
    
    # Initialize handler with environment variables
    try:
        handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=os.getenv('RMBB_API_KEY'),
            rmbb_team_id=int(os.getenv('RMBB_TEAM_ID')),
            ghl_api_key=os.getenv('GHL_API_KEY')
        )
        print("  ✅ Workflow handler initialized with Railway variables")
    except Exception as e:
        print(f"  ❌ Failed to initialize handler: {e}")
        return False
    
    # Test payload processing
    test_payload = test_ghl_webhook_payload()
    
    try:
        # Extract and transform patient data
        patient_data = handler.extract_patient_data(test_payload)
        print(f"  ✅ Patient data extracted: {patient_data['first_name']} {patient_data['last_name']}")
        
        # Test biologic product extraction
        product_info = handler.extract_selected_biologic_product(patient_data)
        if product_info['primary_product']:
            product = product_info['primary_product']
            print(f"  ✅ Selected product: {product['name']} ({product['product_id']}) - {product['cm2']} cm2")
        else:
            print("  ❌ No biologic product detected")
            return False
        
        # Test RMBB Health data transformation
        rmbb_patient_data = handler.transform_patient_data(patient_data)
        rmbb_case_data = handler.transform_case_data(patient_data, 99999)  # Mock patient ID for test
        
        print(f"  ✅ RMBB Patient data: {rmbb_patient_data['personal_identifier']['first']}")
        print(f"  ✅ RMBB Case data:")
        print(f"    - Team ID: {rmbb_case_data['tid']}")
        print(f"    - Physician ID: {rmbb_case_data['physician_id']}")
        print(f"    - Account Location ID: {rmbb_case_data['account_location_id']}")
        print(f"    - Product ID: {rmbb_case_data['product_id']}")
        print(f"    - Product CPT Code: {rmbb_case_data['product_cpt_code']}")
        print(f"    - Wound Size: {rmbb_case_data['wound_size']}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Field mapping test failed: {e}")
        return False

def test_webhook_endpoints():
    """Test webhook endpoints are accessible"""
    print("\n🌐 Testing Webhook Endpoints...")
    
    base_url = os.getenv('RAILWAY_URL', 'http://localhost:8080')
    
    endpoints_to_test = [
        '/health',
        '/webhook/test'
    ]
    
    for endpoint in endpoints_to_test:
        try:
            url = f"{base_url}{endpoint}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"  ✅ {endpoint}: {response.status_code}")
            else:
                print(f"  ⚠️ {endpoint}: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"  ❌ {endpoint}: Connection failed - {e}")

def test_provider_cache():
    """Test provider-location cache functionality"""
    print("\n📋 Testing Provider-Location Cache...")
    
    from rmbbhealth.services.provider_location_cache import ProviderLocationCache
    
    try:
        cache = ProviderLocationCache()
        
        # Test cache operations
        test_provider = "Dr. Test Provider"
        test_location = "test_location_123"
        test_contact = "test_contact_456"
        
        # Add provider to cache
        cache.add_or_update_provider(test_provider, test_location, test_contact)
        print(f"  ✅ Added provider to cache: {test_provider}")
        
        # Lookup provider
        cached_location = cache.get_location_id(test_provider)
        if cached_location == test_location:
            print(f"  ✅ Cache lookup successful: {cached_location}")
        else:
            print(f"  ❌ Cache lookup failed: expected {test_location}, got {cached_location}")
            return False
        
        # Test cache statistics
        stats = cache.get_cache_stats()
        print(f"  ✅ Cache stats: {stats['total_providers']} providers")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Provider cache test failed: {e}")
        return False

def run_complete_test_suite():
    """Run the complete test suite"""
    print("=" * 80)
    print("🚀 RMBB Health Integration - Complete Test Suite")
    print("=" * 80)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Field Mapping", test_field_mapping), 
        ("Provider Cache", test_provider_cache),
        ("Webhook Endpoints", test_webhook_endpoints)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_function in tests:
        try:
            if test_function():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
        
        print("-" * 40)
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests PASSED! System is ready for deployment.")
        return True
    else:
        print("⚠️ Some tests FAILED. Check configuration and try again.")
        return False

if __name__ == "__main__":
    success = run_complete_test_suite()
    exit(0 if success else 1)