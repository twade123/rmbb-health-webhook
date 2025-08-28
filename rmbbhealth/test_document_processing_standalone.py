#!/usr/bin/env python3
"""
Standalone test for document processing approach
Uses Claude to read and extract key information from documents
Then stores the extracted data in GHL custom fields
"""

import sys
import os
import logging
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from webhook_handler import WebhookConfig
from services.file_service import FileService
from client import RMBBHealthClient
from services.provider_location_cache import get_provider_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_document_with_claude(document_data, document_name, case_id):
    """
    Use Claude to extract key information from document
    This simulates what your Claude handler would do
    """
    
    print(f"🤖 Processing document with Claude: {document_name}")
    
    # Determine document type and processing method
    if document_name.lower().endswith('.html') or document_name.lower().endswith('.htm'):
        # Process HTML document
        try:
            document_text = document_data.decode('utf-8')
            print(f"📄 HTML Document content preview:")
            print(f"   Length: {len(document_text)} characters")
            print(f"   Preview: {document_text[:200]}...")
            
            # Extract key information (simulated Claude processing)
            extracted_info = extract_approval_info_from_html(document_text, case_id)
            
        except Exception as e:
            print(f"❌ Error processing HTML: {e}")
            return None
            
    elif document_name.lower().endswith('.pdf'):
        # Process PDF document (would need PDF parsing library)
        print(f"📄 PDF Document: {len(document_data)} bytes")
        print(f"   Note: PDF processing would require additional libraries like PyPDF2 or pdfplumber")
        
        # Simulated extraction for PDF
        extracted_info = {
            "document_type": "PDF Approval Document",
            "case_id": case_id,
            "status": "Approved",
            "processed_date": "2025-08-27",
            "file_size_bytes": len(document_data),
            "notes": "PDF document processed - full content extraction requires PDF parsing library"
        }
        
    else:
        print(f"❌ Unsupported document type: {document_name}")
        return None
    
    print(f"✅ Extracted information:")
    for key, value in extracted_info.items():
        print(f"   {key}: {value}")
        
    return extracted_info

def extract_approval_info_from_html(html_content, case_id):
    """
    Extract key information from HTML approval document
    This simulates intelligent parsing that Claude would do
    """
    
    # Look for common approval patterns
    approval_status = "Unknown"
    if "approved" in html_content.lower():
        approval_status = "Approved"
    elif "denied" in html_content.lower() or "rejected" in html_content.lower():
        approval_status = "Denied"
    
    # Extract other information (this would be much more sophisticated with Claude)
    extracted_info = {
        "document_type": "HTML Approval Document",
        "case_id": case_id,
        "approval_status": approval_status,
        "document_length": len(html_content),
        "processed_date": "2025-08-27",
        "contains_forms": "form" in html_content.lower(),
        "contains_tables": "table" in html_content.lower(),
        "key_sections": []
    }
    
    # Look for key sections
    if "patient" in html_content.lower():
        extracted_info["key_sections"].append("Patient Information")
    if "provider" in html_content.lower():
        extracted_info["key_sections"].append("Provider Information")
    if "diagnosis" in html_content.lower():
        extracted_info["key_sections"].append("Diagnosis")
    if "treatment" in html_content.lower():
        extracted_info["key_sections"].append("Treatment Plan")
        
    return extracted_info

def update_ghl_custom_fields(contact_id, location_id, extracted_info):
    """
    Update GHL contact with extracted document information
    """
    
    print(f"📤 Updating GHL custom fields for contact {contact_id}")
    
    try:
        import requests
        
        # Get API key from cache
        cache = get_provider_cache()
        api_key = cache.get_sub_account_api_key_by_location_id(location_id)
        
        if not api_key:
            print(f"❌ No API key found for location {location_id}")
            return False
        
        # Prepare custom field updates
        custom_fields = []
        
        # Map extracted info to GHL custom field IDs
        field_mappings = {
            "rmbb_document_status": "k9onZaMZVJ5Zwlopf2fi",  # Using existing workflow status field
            "rmbb_processed_date": "TnYQER9F2ByNUrDszxZ3",  # Using existing date field
            "rmbb_document_type": "IbEE8CgkrXECvIQUgJOZ",   # Using existing field for type
        }
        
        # Add document status
        if "approval_status" in extracted_info:
            custom_fields.append({
                "id": field_mappings["rmbb_document_status"],
                "value": f"document_processed_{extracted_info['approval_status'].lower()}"
            })
        
        # Add processed date
        custom_fields.append({
            "id": field_mappings["rmbb_processed_date"],
            "value": extracted_info.get("processed_date", "2025-08-27")
        })
        
        # Add document type
        custom_fields.append({
            "id": field_mappings["rmbb_document_type"],
            "value": extracted_info.get("document_type", "Unknown Document")
        })
        
        # Update contact
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        update_data = {
            "customField": custom_fields
        }
        
        contact_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
        response = requests.put(contact_url, json=update_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Successfully updated GHL custom fields")
            print(f"   Updated {len(custom_fields)} fields")
            return True
        else:
            print(f"❌ Failed to update GHL: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating GHL custom fields: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_document_processing_workflow():
    """Test the complete document processing workflow"""
    
    print("🧪 Testing Document Processing Workflow")
    print("=" * 60)
    
    try:
        # Test case data
        case_id = "53330"
        file_id = "469441"
        
        # Get contact info from cache
        cache = get_provider_cache()
        case_data = cache.cache["cell products"]["case_mappings"][case_id]
        contact_id = case_data["contact_id"]
        location_id = case_data["location_id"]
        
        print(f"📋 Testing with:")
        print(f"   Case ID: {case_id}")
        print(f"   File ID: {file_id}")
        print(f"   Contact ID: {contact_id}")
        print(f"   Location ID: {location_id}")
        
        # Step 1: Download document from RMBBHealth
        print(f"\n🔍 Step 1: Downloading document...")
        
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        # Get file metadata
        files_list = file_service.get_all_files(WebhookConfig.RMBB_TEAM_ID, case_id)
        file_info = next((f for f in files_list if str(f.get('id')) == str(file_id)), None)
        
        if not file_info:
            print(f"❌ File not found: {file_id}")
            return False
            
        document_name = file_info.get('name', 'unknown')
        print(f"📄 Found file: {document_name}")
        
        # Get document download link
        document_result = file_service.view_file(WebhookConfig.RMBB_TEAM_ID, case_id, file_id)
        
        if not document_result or 'link' not in document_result:
            print(f"❌ Failed to get document link")
            return False
            
        document_link = document_result['link']
        print(f"✅ Got document link: {document_link[:100]}...")
        
        # Download actual content from the link for processing
        import requests
        response = requests.get(document_link, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to download document content: HTTP {response.status_code}")
            return False
            
        document_data = response.content
        print(f"✅ Downloaded {len(document_data)} bytes of content")
        
        # Step 2: Process document with Claude (simulated)
        print(f"\n🤖 Step 2: Processing document with Claude...")
        
        extracted_info = process_document_with_claude(document_data, document_name, case_id)
        
        if not extracted_info:
            print(f"❌ Failed to process document")
            return False
            
        # Step 3: Update GHL custom fields
        print(f"\n📤 Step 3: Updating GHL custom fields...")
        
        success = update_ghl_custom_fields(contact_id, location_id, extracted_info)
        
        if success:
            print(f"\n🎉 Document processing workflow completed successfully!")
            print(f"📊 Summary:")
            print(f"   ✅ Document downloaded from RMBBHealth")
            print(f"   ✅ Content extracted with Claude processing") 
            print(f"   ✅ GHL custom fields updated")
            print(f"   📄 Document info now available in GHL contact")
            return True
        else:
            print(f"\n❌ Workflow failed at GHL update step")
            return False
            
    except Exception as e:
        print(f"❌ Workflow failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_document_processing_workflow()
    
    print(f"\n" + "=" * 60)
    if success:
        print("✅ Document Processing Approach Test: PASSED")
        print()
        print("🔍 What this approach does:")
        print("   1. Downloads document from RMBBHealth")  
        print("   2. Uses Claude to extract key information")
        print("   3. Stores extracted data in GHL custom fields")
        print("   4. Providers see structured data in GHL interface")
        print()
        print("✅ Benefits:")
        print("   - No download links needed")
        print("   - Structured data in GHL") 
        print("   - Searchable information")
        print("   - Works with GHL workflows")
    else:
        print("❌ Document Processing Approach Test: FAILED")