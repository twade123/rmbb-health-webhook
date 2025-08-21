# client.py
import requests
try:
    from .config import RMBBHealthConfig
except ImportError:
    from config import RMBBHealthConfig

class RMBBHealthClient:
    def __init__(self, api_key=None, team_id=None):
        self.config = RMBBHealthConfig()
        
        if api_key:
            self.config.API_KEY = api_key
        
        if team_id:
            self.config.TEAM_ID = team_id
            
        self.session = requests.Session()
        
    def get_headers(self):
        """Return headers with authentication token as shown in rmbbhealth.txt"""
        if not self.config.API_KEY:
            raise ValueError("API key is not configured")
            
        return {
            "Authorization": f"Bearer {self.config.API_KEY}",
            "Content-Type": "application/json"
        }
    
    def get(self, endpoint, params=None):
        """Make a GET request to the API"""
        url = f"{self.config.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.get_headers(), params=params)
        return response.json()
    
    def post(self, endpoint, data=None):
        """Make a POST request to the API"""
        url = f"{self.config.BASE_URL}{endpoint}"
        response = requests.post(url, headers=self.get_headers(), json=data)
        return response.json()