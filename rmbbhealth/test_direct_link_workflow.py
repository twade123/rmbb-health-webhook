#!/usr/bin/env python3
"""
Test the complete direct link workflow
Tests the new simplified approach: RMBBHealth S3 link → GHL contact notes
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
from services.provider_location_cache import get_provider_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_direct_link_workflow():
    """Test the complete direct link workflow"""
    print("🧪 Testing Direct Link Workflow")
    print("=" * 60)
    
    try:
        # Test Case: Known working case with approval document
        case_id = "53330"
        
        # Get contact info from cache
        cache = get_provider_cache()
        case_data = cache.cache["cell products"]["case_mappings"][case_id]
        contact_id = case_data["contact_id"]
        location_id = case_data["location_id"]
        
        print(f"📋 Testing with:")
        print(f"   Case ID: {case_id}")
        print(f"   Contact ID: {contact_id}")
        print(f"   Location ID: {location_id}")
        print()
        
        # Step 1: Get file list from RMBBHealth
        print("🔍 Step 1: Getting files from RMBBHealth...")
        
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
            print(f"   📄 {file_info.get('name', 'Unknown')} (ID: {file_info.get('id')})")
        
        # Step 2: Get direct download link
        test_file = files_result[0]
        file_id = test_file.get('id')
        file_name = test_file.get('name', f'document_{file_id}')
        
        print(f"\n🔗 Step 2: Getting direct download link for: {file_name}")
        
        view_result = file_service.view_file(WebhookConfig.RMBB_TEAM_ID, case_id, file_id)
        
        if not view_result or 'link' not in view_result:
            print("❌ Failed to get download link")
            return False
            
        download_link = view_result['link']
        print(f"✅ Got direct S3 link: {download_link[:100]}...")
        
        # Step 3: Process with GHL workflow handler
        print(f"\n📤 Step 3: Processing with GHL workflow handler...")
        
        ghl_workflow = GHLRMBBWorkflowHandler(
            WebhookConfig.RMBB_API_KEY,
            int(WebhookConfig.RMBB_TEAM_ID),
            WebhookConfig.GHL_API_KEY
        )
        
        success = ghl_workflow.process_approval_document_notification(
            case_id=case_id,
            document_link=download_link,
            document_name=file_name,
            contact_id=contact_id,
            location_id=location_id
        )
        
        if success:
            print("🎉 Direct link workflow completed successfully!")
            print()
            print("✅ What happened:")
            print("   1. ✅ Got file list from RMBBHealth API")
            print("   2. ✅ Got direct S3 download link (no file download!)")
            print("   3. ✅ Added link to GHL contact notes")  
            print("   4. ✅ Added workflow trigger tag to contact")
            print()
            print("🔍 Provider Experience:")
            print("   1. Provider gets notification in GHL")
            print("   2. Provider opens contact and sees notes")
            print("   3. Provider clicks link → Document opens from RMBBHealth S3")
            print("   4. Provider can view/download as needed")
            print()
            print("💡 Benefits of this approach:")
            print("   ✅ No file storage on Railway")
            print("   ✅ No memory usage for large files") 
            print("   ✅ Direct access from secure RMBBHealth servers")
            print("   ✅ Links work immediately")
            print("   ✅ Simple and reliable")
            return True
        else:
            print("❌ Direct link workflow failed")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()
        return False

def test_link_accessibility():
    """Test that the direct link is actually accessible"""
    print("\n🌐 Testing Link Accessibility")
    print("=" * 40)
    
    try:
        # Get the link from our previous test
        case_id = "53330"
        file_id = "469441"
        
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        view_result = file_service.view_file(WebhookConfig.RMBB_TEAM_ID, case_id, file_id)
        
        if view_result and 'link' in view_result:
            download_link = view_result['link']
            print(f"🔗 Testing link: {download_link[:100]}...")
            
            # Try to access the link
            import requests
            response = requests.head(download_link, timeout=10)  # HEAD request to check accessibility
            
            print(f"📊 Link status: HTTP {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Link is accessible!")
                
                # Get content info
                content_length = response.headers.get('content-length')
                content_type = response.headers.get('content-type')
                
                if content_length:
                    print(f"📏 File size: {int(content_length)} bytes")
                if content_type:
                    print(f"📄 Content type: {content_type}")
                    
                return True
            else:
                print(f"❌ Link not accessible: HTTP {response.status_code}")
                return False
        else:
            print("❌ Could not get download link")
            return False
            
    except Exception as e:
        print(f"❌ Link test failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Test the complete workflow
    workflow_success = test_direct_link_workflow()
    
    # Test link accessibility
    link_success = test_link_accessibility()
    
    print("\n" + "=" * 60)
    print("🧪 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    if workflow_success:
        print("✅ Direct Link Workflow: PASSED")
    else:
        print("❌ Direct Link Workflow: FAILED")
        
    if link_success:
        print("✅ Link Accessibility: PASSED") 
    else:
        print("❌ Link Accessibility: FAILED")
        
    if workflow_success and link_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n🚀 Ready for deployment!")
        print("The direct link approach is working perfectly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed.")
        sys.exit(1)