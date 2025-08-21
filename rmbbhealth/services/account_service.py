# services/account_service.py
from ..client import RMBBHealthClient

class AccountService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_all_accounts(self, team_id):
        """Get all accounts for a team"""
        endpoint = f"/team/{team_id}/account"
        return self.client.get(endpoint)
    
    def get_account_by_id(self, team_id, account_id):
        """Get a specific account by ID"""
        endpoint = f"/team/{team_id}/account/{account_id}"
        return self.client.get(endpoint)
    
    def get_all_locations(self, team_id, account_id):
        """Get all locations for an account"""
        endpoint = f"/team/{team_id}/account/{account_id}/location"
        return self.client.get(endpoint)
    
    def get_location_by_id(self, team_id, account_id, location_id):
        """Get a specific location by ID"""
        endpoint = f"/team/{team_id}/account/{account_id}/location/{location_id}"
        return self.client.get(endpoint)
    
    def get_all_contacts(self, team_id):
        """Get all contacts for a team"""
        endpoint = f"/team/{team_id}/contact"
        return self.client.get(endpoint)
    
    def get_contact_by_id(self, team_id, contact_id):
        """Get a specific contact by ID"""
        endpoint = f"/team/{team_id}/contact/{contact_id}"
        return self.client.get(endpoint)