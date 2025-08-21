# services/product_service.py
from client import RMBBHealthClient

class ProductService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_all_products(self, team_id):
        """Get all products for a team"""
        endpoint = f"/team/{team_id}/setting/product"
        return self.client.get(endpoint)
    
    def get_product_by_id(self, team_id, product_id):
        """Get a specific product by ID"""
        endpoint = f"/team/{team_id}/setting/product/{product_id}"
        return self.client.get(endpoint)
