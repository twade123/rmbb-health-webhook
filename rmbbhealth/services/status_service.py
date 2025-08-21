# services/status_service.py
from client import RMBBHealthClient

class StatusService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_status(self):
        """Check the API status"""
        endpoint = "/status"
        return self.client.get(endpoint)
