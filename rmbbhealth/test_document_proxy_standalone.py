#!/usr/bin/env python3
"""
Standalone test for document proxy approach
Creates a simple Flask server that proxies documents from RMBBHealth
"""

import sys
import os
import logging
from flask import Flask, Response, request
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

# Create Flask app
app = Flask(__name__)

@app.route('/documents/<case_id>/<file_id>/download')
def download_document(case_id, file_id):
    """
    Proxy document downloads from RMBBHealth
    Test URL: http://localhost:5001/documents/53330/469441/download
    """
    try:
        print(f"📥 Document download request - Case: {case_id}, File: {file_id}")
        
        # Initialize RMBBHealth client
        rmbb_client = RMBBHealthClient(
            api_key=WebhookConfig.RMBB_API_KEY,
            team_id=int(WebhookConfig.RMBB_TEAM_ID)
        )
        file_service = FileService(client=rmbb_client)
        
        # Get document binary data
        print(f"🔍 Fetching document from RMBBHealth...")
        document_data = file_service.view_file(WebhookConfig.RMBB_TEAM_ID, case_id, file_id)
        
        if not document_data:
            print(f"❌ Document not found")
            return "Document not found", 404
            
        # Get file metadata
        files_list = file_service.get_all_files(WebhookConfig.RMBB_TEAM_ID, case_id)
        file_info = next((f for f in files_list if str(f.get('id')) == str(file_id)), None)
        
        # Determine filename and content type
        if file_info:
            filename = file_info.get('name', f'document_{file_id}')
            print(f"📄 File info: {file_info}")
        else:
            filename = f'rmbb_case_{case_id}_file_{file_id}'
            
        # Determine content type
        content_type = 'application/pdf'
        if filename.lower().endswith('.html') or filename.lower().endswith('.htm'):
            content_type = 'text/html'
            
        print(f"✅ Streaming document: {filename} ({len(document_data)} bytes, {content_type})")
        
        # Create response
        response = Response(
            document_data,
            mimetype=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(document_data)),
            }
        )
        
        return response
        
    except Exception as e:
        print(f"❌ Download failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Download failed: {str(e)}", 500

@app.route('/test')
def test_endpoint():
    """Test endpoint to verify server is running"""
    return f"""
    <h1>Document Proxy Test Server</h1>
    <p>Server is running!</p>
    
    <h2>Test Document Download</h2>
    <p>Case 53330, File 469441 (HTML file):</p>
    <a href="/documents/53330/469441/download" target="_blank">
        📄 Download RMBBHealth Document
    </a>
    
    <h2>How it works:</h2>
    <ol>
        <li>Click the link above</li>
        <li>Server fetches document from RMBBHealth API</li>
        <li>Document streams directly to your browser</li>
        <li>No files stored on our server</li>
    </ol>
    """

if __name__ == '__main__':
    print("🧪 Starting Document Proxy Test Server")
    print("=" * 50)
    print("📡 Server will run on: http://localhost:5001")
    print("🔗 Test URL: http://localhost:5001/test")
    print("📄 Direct download: http://localhost:5001/documents/53330/469441/download")
    print()
    print("Press Ctrl+C to stop")
    
    app.run(host='localhost', port=5001, debug=True)