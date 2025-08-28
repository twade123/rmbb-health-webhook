#!/usr/bin/env python3
"""
Test script for document processing functionality
Tests the complete workflow: FileService -> DocumentProcessor -> GHL custom fields
"""

import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add current directory to path for imports
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

try:
    # Import our services
    from services.document_processor import DocumentProcessor
    from services.file_service import FileService
    from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
    
    def test_document_processing():
        """Test document processing with case 53330"""
        
        logging.info("🧪 Testing document processing with case 53330")
        
        # Test case 53330 with known HTML file (ID: 469441)
        case_id = "53330"
        
        # Test 1: FileService - get files for case
        logging.info("📋 STEP 1: Testing FileService.get_all_files()")
        
        # Setup RMBB Health client with credentials
        from client import RMBBHealthClient
        
        # Get API credentials from environment
        api_key = os.getenv('RMBB_API_KEY')
        team_id = os.getenv('RMBB_TEAM_ID')
        
        if not api_key or not team_id:
            logging.error("❌ RMBB_API_KEY and RMBB_TEAM_ID environment variables must be set")
            logging.error("   Run: export RMBB_API_KEY='your_api_key'")
            logging.error("   Run: export RMBB_TEAM_ID='your_team_id'")
            return False
        
        client = RMBBHealthClient(api_key=api_key, team_id=int(team_id))
        file_service = FileService(client)
        
        try:
            files_result = file_service.get_all_files(team_id=int(team_id), case_id=case_id)
            logging.info(f"✅ FileService returned: {files_result}")
            
            if not files_result or not isinstance(files_result, list) or len(files_result) == 0:
                logging.error("❌ No files found for case 53330")
                return False
                
            # Find the HTML file we know exists
            target_file = None
            for file_info in files_result:
                if file_info.get('id') == 469441 or 'additional-information' in file_info.get('filename', '').lower():
                    target_file = file_info
                    break
                    
            if not target_file:
                logging.error("❌ Could not find target HTML file (ID: 469441)")
                return False
                
            logging.info(f"📄 Found target file: {target_file}")
            
        except Exception as e:
            logging.error(f"❌ FileService test failed: {str(e)}")
            return False
        
        # Test 2: FileService - get file content
        logging.info("📋 STEP 2: Testing FileService.view_file()")
        
        try:
            file_content = file_service.view_file(team_id=int(team_id), case_id=case_id, file_id=target_file['id'])
            logging.info(f"✅ FileService.view_file() returned content")
            logging.info(f"📊 Content type: {type(file_content)}")
            
            if isinstance(file_content, dict) and 'link' in file_content:
                document_url = file_content['link']
                logging.info(f"🔗 Download URL obtained: {document_url[:100]}...")
            else:
                logging.error(f"❌ Unexpected file content format: {file_content}")
                return False
                
        except Exception as e:
            logging.error(f"❌ FileService.view_file() test failed: {str(e)}")
            return False
        
        # Test 3: DocumentProcessor - process document from URL
        logging.info("📋 STEP 3: Testing DocumentProcessor.process_document_from_url()")
        
        try:
            doc_processor = DocumentProcessor()
            processing_result = doc_processor.process_document_from_url(
                document_url=document_url,
                file_name=target_file['name']
            )
            
            if processing_result['success']:
                logging.info(f"✅ Document processing successful!")
                logging.info(f"📄 Document type: {processing_result['extracted_data']['document_type']}")
                logging.info(f"✅ Approval status: {processing_result['extracted_data']['approval_status']}")
                logging.info(f"📝 Text length: {processing_result['file_info']['text_length']} characters")
                logging.info(f"📋 Patient info: {processing_result['extracted_data']['patient_info']}")
                
                # Show first 200 characters of extracted text
                text_preview = processing_result['text_content'][:200] + "..."
                logging.info(f"📝 Text preview: {text_preview}")
            else:
                logging.error(f"❌ Document processing failed: {processing_result['error']}")
                return False
                
        except Exception as e:
            logging.error(f"❌ DocumentProcessor test failed: {str(e)}")
            return False
        
        # Test 4: GHL Custom Field Mapping
        logging.info("📋 STEP 4: Testing GHL custom field mapping")
        
        try:
            # Mock workflow handler for testing field mapping (without actual GHL API calls)
            workflow_handler = GHLRMBBWorkflowHandler(
                rmbb_api_key="test_key",
                rmbb_team_id=2,
                ghl_api_key="test_ghl_key"
            )
            
            # Test the mapping function
            mapped_fields = workflow_handler._map_document_data_to_ghl_fields(
                extracted_data=processing_result['extracted_data'],
                case_id=case_id,
                document_name=target_file['name']
            )
            
            logging.info(f"✅ GHL field mapping successful!")
            logging.info(f"📊 Mapped {len(mapped_fields)} custom fields")
            
            for field in mapped_fields[:5]:  # Show first 5 fields
                logging.info(f"   🔗 {field}")
                
        except Exception as e:
            logging.error(f"❌ GHL field mapping test failed: {str(e)}")
            return False
        
        logging.info("🎉 ALL TESTS PASSED! Document processing workflow is ready.")
        return True
        
    if __name__ == "__main__":
        success = test_document_processing()
        if success:
            print("\n✅ Document processing test completed successfully!")
            print("🚀 Ready to test with real webhook data")
        else:
            print("\n❌ Document processing test failed")
            print("🔍 Check the logs above for details")
            sys.exit(1)
            
except ImportError as e:
    logging.error(f"❌ Import failed: {str(e)}")
    logging.error("Make sure you're in the rmbbhealth directory and all dependencies are installed")
    sys.exit(1)