#!/usr/bin/env python3
"""
Inspect the full structure of RMBBHealth file data to see if direct download URLs are available
"""

import sys
import os
import json
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from webhook_handler import WebhookConfig
from services.file_service import FileService
from client import RMBBHealthClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def inspect_file_structure():
    """Inspect the complete file structure from RMBBHealth API"""
    
    print("🔍 Inspecting RMBBHealth File Structure")
    print("=" * 50)
    
    try:
        case_id = "53330"
        
        # Initialize RMBBHealth client
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        print(f"📋 Getting file list for case {case_id}...")
        files_result = file_service.get_all_files(WebhookConfig.RMBB_TEAM_ID, case_id)
        
        print(f"\n📊 Raw files_result type: {type(files_result)}")
        print(f"📊 Raw files_result content:")
        print(json.dumps(files_result, indent=2, default=str))
        
        if files_result:
            print(f"\n📄 Analyzing first file structure...")
            first_file = files_result[0] if isinstance(files_result, list) else files_result
            
            print(f"\n🔑 All available keys in file object:")
            if isinstance(first_file, dict):
                for key, value in first_file.items():
                    print(f"   {key}: {value} (type: {type(value).__name__})")
            else:
                print(f"   File is not a dict: {first_file}")
                
            # Check if there are any URL-like fields
            print(f"\n🔗 Looking for URL-like fields...")
            url_fields = []
            if isinstance(first_file, dict):
                for key, value in first_file.items():
                    if isinstance(value, str) and ('http' in value.lower() or 'url' in key.lower() or 'link' in key.lower()):
                        url_fields.append((key, value))
                        
            if url_fields:
                print(f"✅ Found potential URL fields:")
                for key, value in url_fields:
                    print(f"   {key}: {value}")
            else:
                print(f"❌ No obvious URL fields found")
                
        else:
            print("❌ No files found or files_result is empty")
            
    except Exception as e:
        print(f"❌ Error inspecting file structure: {str(e)}")
        import traceback
        traceback.print_exc()

def inspect_file_service_methods():
    """Check what methods are available in FileService"""
    
    print(f"\n🔧 FileService Available Methods:")
    print("=" * 50)
    
    try:
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        methods = [method for method in dir(file_service) if not method.startswith('_')]
        for method in methods:
            print(f"   📋 {method}")
            
        # Check if there are any URL-related methods
        url_methods = [m for m in methods if 'url' in m.lower() or 'link' in m.lower() or 'download' in m.lower()]
        if url_methods:
            print(f"\n🔗 URL-related methods found:")
            for method in url_methods:
                print(f"   ✅ {method}")
                
    except Exception as e:
        print(f"❌ Error inspecting FileService methods: {str(e)}")

if __name__ == "__main__":
    inspect_file_structure()
    inspect_file_service_methods()