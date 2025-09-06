#!/usr/bin/env python3
"""
Test Wound Calculation Integration with Real Data

This test pulls actual case data from RMBB Health development environment,
processes it through the wound calculation system, and updates the correct
GHL contact as specified in the provider cache.

Case: 53330 (Cell Products - AmnioMaxx Q4239)
Contact: 9ycwwscO60MGHiTTBDzo 
Location: Sqbexj54nvsxOI4V7SsD
"""

import os
import sys
import json
import logging
from datetime import datetime

# Set up environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import our modules
from client import RMBBHealthClient
from services.case_service import CaseService
from wound_calculation_integration import WoundCalculationIntegration
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_real_wound_calculation_workflow():
    """
    Test the complete wound calculation workflow with real RMBB Health case data
    and update the actual GHL contact.
    """
    
    print("=" * 80)
    print("TESTING WOUND CALCULATION INTEGRATION WITH REAL DATA")
    print("=" * 80)
    
    # Step 1: Set up API credentials
    print("\n🔧 Step 1: Setting up API credentials...")
    
    # RMBB Health API credentials (development environment)
    rmbb_api_key = "b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0"  # Development API key
    rmbb_team_id = 85  # Development team ID
    
    # GHL API credentials from provider cache
    cell_products_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJsb2NhdGlvbl9pZCI6IlNxYmV4ajU0bnZzeE9JNFY3U3NEIiwidmVyc2lvbiI6MSwiaWF0IjoxNzUzMDI5MTMxMjU1LCJzdWIiOiI3MTJEQzhBY2NGaUo5Vmt5aFJqWCJ9.1JSN3gbOtcGBEvs-shLfBqbTKil-xXQCgMZarjBDyIU"
    
    # Test case details from provider cache
    test_case_id = "53330"
    ghl_contact_id = "9ycwwscO60MGHiTTBDzo"
    ghl_location_id = "Sqbexj54nvsxOI4V7SsD"
    
    print(f"   ✅ RMBB Health API configured (Team ID: {rmbb_team_id})")
    print(f"   ✅ GHL API configured for Cell Products")
    print(f"   ✅ Test case: {test_case_id}")
    print(f"   ✅ Target contact: {ghl_contact_id}")
    
    try:
        # Step 2: Fetch real case data from RMBB Health development API
        print(f"\n🏥 Step 2: Fetching case {test_case_id} from RMBB Health development API...")
        
        client = RMBBHealthClient(api_key=rmbb_api_key, team_id=rmbb_team_id)
        case_service = CaseService(client)
        
        case_data = case_service.get_case(test_case_id)
        
        if not case_data:
            print(f"❌ Could not fetch case {test_case_id} from RMBB Health API")
            return False
            
        print(f"   ✅ Successfully fetched case data")
        print(f"   📋 Case fields available: {list(case_data.keys())}")
        
        # Print key case information
        product_id = case_data.get('product_id')
        wound_size = case_data.get('wound_size', '')
        total_wound_size = case_data.get('total_wound_size', '')
        wound_type = case_data.get('wound_type', '')
        
        print(f"   🧬 Product ID: {product_id}")
        print(f"   📏 Wound Size: '{wound_size}'")
        print(f"   📊 Total Wound Size: '{total_wound_size}'")
        print(f"   🩹 Wound Type: '{wound_type}'")
        
        # Override wound size for testing to show meaningful calculations
        print(f"\n   🔧 TESTING: Overriding wound size from {total_wound_size} to 60 cm² for meaningful calculation")
        case_data['wound_size'] = '7.75x7.75 cm'  # Approximately 60 cm²
        case_data['total_wound_size'] = '60 cm2'
        print(f"   ✅ Updated wound size for testing: {case_data['wound_size']} = {case_data['total_wound_size']}")
        
        # Step 3: Initialize workflow handler and wound calculation integration
        print(f"\n🧮 Step 3: Initializing wound calculation system...")
        
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=rmbb_api_key,
            rmbb_team_id=rmbb_team_id,
            ghl_api_key=cell_products_api_key  # Use Cell Products sub account API key
        )
        
        # Initialize integration with the workflow handler
        integration = WoundCalculationIntegration()
        integration.workflow_handler = workflow_handler  # Set the initialized workflow handler
        
        print(f"   ✅ Wound calculation integration initialized")
        
        # Step 4: Process case through wound calculation system
        print(f"\n💊 Step 4: Processing case through wound calculation system...")
        
        calculation_result = integration.process_approved_case(case_data)
        
        if not calculation_result:
            print(f"❌ Wound calculation processing failed or not applicable")
            return False
            
        if not calculation_result.get('success'):
            print(f"❌ Wound calculation failed: {calculation_result.get('error')}")
            return False
            
        print(f"   ✅ Wound calculation successful!")
        print(f"   📊 {calculation_result['calculation_summary']}")
        print(f"   🔢 Total Coverage: {calculation_result['total_coverage_cm2']} cm²")
        print(f"   📈 Actual Waste: {calculation_result['actual_waste_percent']}%")
        print(f"   🔗 GHL Fields to update: {len(calculation_result['ghl_field_updates'])}")
        
        # Print size-specific breakdown
        print(f"\n   📋 Size-specific breakdown:")
        for field_update in calculation_result['ghl_field_updates']:
            product = field_update['product']
            size = field_update['size']
            units = field_update['units']
            cm2_per_unit = field_update['cm2_per_unit']
            total_cm2 = field_update['total_cm2']
            print(f"      • {product} {size}: {units} units ({cm2_per_unit} cm² each = {total_cm2} cm² total)")
        
        # Step 5: Update GHL contact with wound calculation results
        print(f"\n🔗 Step 5: Updating GHL contact {ghl_contact_id} with calculation results...")
        
        # Build custom fields update from wound calculation results
        custom_fields_list = []
        
        # Add wound calculation results to custom fields
        for field_update in calculation_result['ghl_field_updates']:
            custom_fields_list.append({
                "id": field_update['id'],
                "value": field_update['value']
            })
        
        # Add calculation metadata
        custom_fields_list.extend([
            {"id": "XQLSYwSOodHOBrqv8oz0", "value": f"Wound calculation: {calculation_result['calculation_summary']}"},  # rmbb_current_decision_summary
            {"id": "CWCMdJsRU4hMEDS32U4s", "value": "APPROVED"},  # rmbb_current_status
            {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "wound_calculated"},  # rmbb_workflow_status
            {"id": "4AnL32P9rjYcPjbukcok", "value": datetime.now().isoformat()},  # rmbb_ivr_received_date
        ])
        
        # Update GHL contact using direct API call
        ghl_update_result = update_ghl_contact_direct(
            contact_id=ghl_contact_id,
            location_id=ghl_location_id,
            sub_account_api_key=cell_products_api_key,
            custom_fields_update={"customField": custom_fields_list}
        )
        
        if ghl_update_result['success']:
            print(f"   ✅ Successfully updated GHL contact!")
            print(f"   📝 Updated {len(custom_fields_list)} custom fields")
        else:
            print(f"   ❌ Failed to update GHL contact: {ghl_update_result['error']}")
            return False
        
        # Step 6: Summary
        print(f"\n🎉 Step 6: Test Summary")
        print(f"   ✅ Case Data: Successfully fetched from RMBB Health (case {test_case_id})")
        print(f"   ✅ Product Mapping: {calculation_result['product_name']} ({calculation_result['q_code']})")
        print(f"   ✅ Wound Coverage: {calculation_result['wound_size_cm2']} cm² → {calculation_result['total_coverage_cm2']} cm²")
        print(f"   ✅ Waste Factor: {calculation_result['actual_waste_percent']}% (target: 15%)")
        print(f"   ✅ GHL Update: {len(calculation_result['ghl_field_updates'])} size-specific fields updated")
        print(f"   ✅ Contact Updated: {ghl_contact_id} in location {ghl_location_id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def update_ghl_contact_direct(contact_id, location_id, sub_account_api_key, custom_fields_update):
    """
    Update GHL contact custom fields using direct API v1 call with sub account API key
    """
    try:
        # GHL API v1 endpoint for contact update
        url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
        
        # Headers with sub account API key
        headers = {
            "Authorization": f"Bearer {sub_account_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # Make direct API call
        response = requests.put(url, headers=headers, json=custom_fields_update)
        
        if response.status_code == 200:
            return {"success": True, "response": response.json()}
        else:
            error_msg = f"GHL API error {response.status_code}: {response.text}"
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    success = test_real_wound_calculation_workflow()
    
    if success:
        print(f"\n🎯 TEST PASSED: Complete wound calculation workflow successful!")
        exit(0)
    else:
        print(f"\n💥 TEST FAILED: Wound calculation workflow encountered errors")
        exit(1)