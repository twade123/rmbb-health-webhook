# services/patient_service.py
from client import RMBBHealthClient

class PatientService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_all_patients(self, team_id, personal_identifier_last=None, personal_identifier_first=None, date_of_birth=None):
        """Get all patients for a team with optional filtering"""
        endpoint = f"/team/{team_id}/patient"
        params = {}
        if personal_identifier_last:
            params["personal_identifier_last"] = personal_identifier_last
        if personal_identifier_first:
            params["personal_identifier_first"] = personal_identifier_first
        if date_of_birth:
            params["date_of_birth"] = date_of_birth
        return self.client.get(endpoint, params if params else None)
    
    def get_patient_by_id(self, team_id, patient_id):
        """Get a specific patient by ID"""
        endpoint = f"/team/{team_id}/patient/{patient_id}"
        return self.client.get(endpoint)
    
    def create_patient(self, team_id, patient_data):
        """Create a new patient"""
        endpoint = f"/team/{team_id}/patient"
        return self.client.post(endpoint, patient_data)