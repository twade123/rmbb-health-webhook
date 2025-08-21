# services/file_service.py
from ..client import RMBBHealthClient

class FileService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def upload_file(self, team_id, case_id, file_data):
        """Upload a file to a case"""
        endpoint = f"/team/{team_id}/case/{case_id}/file"
        return self.client.post(endpoint, file_data)
    
    def get_all_files(self, team_id, case_id):
        """Get all files for a case"""
        endpoint = f"/team/{team_id}/case/{case_id}/file"
        return self.client.get(endpoint)
    
    def view_file(self, team_id, case_id, file_id):
        """View a specific file"""
        endpoint = f"/team/{team_id}/case/{case_id}/file/{file_id}/view"
        return self.client.post(endpoint, {})