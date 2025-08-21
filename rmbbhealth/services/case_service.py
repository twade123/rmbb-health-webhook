# services/case_service.py
try:
    from ..client import RMBBHealthClient
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from client import RMBBHealthClient

class CaseService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_all_cases(self, last_modified_after=None):
        """Get all cases for the team, with optional last_modified_after filter"""
        params = {}
        if last_modified_after:
            params['last_modified_after'] = last_modified_after
            
        endpoint = f"/team/{self.client.config.TEAM_ID}/case"
        return self.client.get(endpoint, params=params)
    
    def get_case(self, case_id):
        """Get a specific case by ID"""
        endpoint = f"/team/{self.client.config.TEAM_ID}/case/{case_id}"
        return self.client.get(endpoint)
    
    def create_case(self, case_data):
        """Create a new case with the format specified in rmbbhealth.txt"""
        endpoint = f"/team/{self.client.config.TEAM_ID}/case"
        return self.client.post(endpoint, case_data)
    
    def add_additional_information(self, case_id, additional_info):
        """Add additional information to a case"""
        endpoint = f"/team/{self.client.config.TEAM_ID}/case/{case_id}/additional-information"
        return self.client.post(endpoint, additional_info)