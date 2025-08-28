#!/usr/bin/env python3
"""
Test the new GHL document upload workflow
Tests the complete flow: RMBBHealth document retrieval → GHL conversation upload
"""

import sys
import os
import logging
import traceback
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from webhook_handler import WebhookConfig
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
from services.file_service import FileService
from client import RMBBHealthClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_document_upload_workflow():
    """Test the new document upload workflow with case 53330"""
    print("🧪 Testing Document Upload Workflow")
    print("=" * 50)
    
    try:
        # Test Case: Known working case with approval document (from provider cache)
        case_id = "53330"
        contact_id = "5Qk42EBFVX3OJaxmYKOK"  # Actual contact ID from cache
        location_id = "Sqbexj54nvsxOI4V7SsD"  # Actual location ID from cache
        
        print(f"📋 Testing with:")
        print(f"   Case ID: {case_id}")
        print(f"   Contact ID: {contact_id}")
        print(f"   Location ID: {location_id}")
        print()
        
        # Step 1: Initialize FileService and retrieve documents
        print("🔍 Step 1: Retrieving documents from RMBBHealth...")
        
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        files_result = file_service.get_all_files(WebhookConfig.RMBB_TEAM_ID, case_id)
        
        if not files_result:
            print("❌ No files found for case")
            return False
            
        print(f"✅ Found {len(files_result)} files")
        for file_info in files_result:
            print(f"   📄 {file_info.get('filename', 'Unknown')} (ID: {file_info.get('id')})")
        
        # Get the first file for testing
        test_file = files_result[0]
        file_id = test_file.get('id')
        file_name = test_file.get('filename', f'document_{file_id}.pdf')
        
        print(f"\n🎯 Testing with file: {file_name}")
        
        # Step 2: Download file binary data
        print("📥 Step 2: Downloading file binary data...")
        
        file_data = file_service.view_file(WebhookConfig.RMBB_TEAM_ID, case_id, file_id)
        
        if not file_data:
            print("❌ Failed to download file data")
            return False
            
        print(f"✅ Downloaded {len(file_data)} bytes")
        
        # Step 3: Initialize GHL workflow handler
        print("🔧 Step 3: Initializing GHL workflow handler...")
        
        ghl_workflow = GHLRMBBWorkflowHandler(
            WebhookConfig.RMBB_API_KEY,
            int(WebhookConfig.RMBB_TEAM_ID),
            WebhookConfig.GHL_API_KEY
        )
        
        # Step 4: Process document upload
        print("📤 Step 4: Processing document upload workflow...")
        
        success = ghl_workflow.process_approval_document_notification(
            case_id=case_id,
            document_binary_data=file_data,
            document_name=file_name,
            contact_id=contact_id,
            location_id=location_id
        )
        
        if success:
            print("🎉 Document upload workflow completed successfully!")
            print("✅ Document should now be available in GHL conversation")
            print("✅ Workflow trigger tag should be applied to contact")
            return True
        else:
            print("❌ Document upload workflow failed")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_document_upload_workflow()
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)