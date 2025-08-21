# services/status_service.py
try:
    from ..client import RMBBHealthClient
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from client import RMBBHealthClient

class StatusService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_status(self):
        """Check the API status"""
        endpoint = "/status"
        return self.client.get(endpoint)