# config.py
import os

class RMBBHealthConfig:
    BASE_URL = os.getenv('RMBB_BASE_URL', "https://connect.production.backend.rmbbhealth.com")
    API_KEY = os.getenv('RMBB_API_KEY')  # Environment variable
    TEAM_ID = os.getenv('RMBB_TEAM_ID')  # Environment variable
    
    # TBD Placeholder IDs for development/production
    TBD_PHYSICIAN_ID = os.getenv('RMBB_TBD_PHYSICIAN_ID')
    TBD_ACCOUNT_ID = os.getenv('RMBB_TBD_ACCOUNT_ID') 
    TBD_ACCOUNT_LOCATION_ID = os.getenv('RMBB_TBD_ACCOUNT_LOCATION_ID')
    
    @classmethod
    def get_team_id(cls):
        """Get team ID as integer"""
        if cls.TEAM_ID:
            try:
                return int(cls.TEAM_ID)
            except ValueError:
                raise ValueError(f"Invalid RMBB_TEAM_ID: {cls.TEAM_ID}. Must be numeric.")
        return None
    
    @classmethod
    def get_tbd_physician_id(cls):
        """Get TBD physician ID as integer"""
        if cls.TBD_PHYSICIAN_ID:
            try:
                return int(cls.TBD_PHYSICIAN_ID)
            except ValueError:
                raise ValueError(f"Invalid RMBB_TBD_PHYSICIAN_ID: {cls.TBD_PHYSICIAN_ID}. Must be numeric.")
        return None
    
    @classmethod
    def get_tbd_account_id(cls):
        """Get TBD account ID as integer"""
        if cls.TBD_ACCOUNT_ID:
            try:
                return int(cls.TBD_ACCOUNT_ID)
            except ValueError:
                raise ValueError(f"Invalid RMBB_TBD_ACCOUNT_ID: {cls.TBD_ACCOUNT_ID}. Must be numeric.")
        return None
    
    @classmethod
    def get_tbd_account_location_id(cls):
        """Get TBD account location ID as integer"""
        if cls.TBD_ACCOUNT_LOCATION_ID:
            try:
                return int(cls.TBD_ACCOUNT_LOCATION_ID)
            except ValueError:
                raise ValueError(f"Invalid RMBB_TBD_ACCOUNT_LOCATION_ID: {cls.TBD_ACCOUNT_LOCATION_ID}. Must be numeric.")
        return None