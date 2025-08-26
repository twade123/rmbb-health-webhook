# services/note_service.py
from client import RMBBHealthClient

class NoteService:
    def __init__(self, client=None):
        self.client = client or RMBBHealthClient()
    
    def get_all_notes(self, team_id, case_id):
        """Get all notes for a case"""
        endpoint = f"/team/{team_id}/case/{case_id}/note"
        return self.client.get(endpoint)
    
    def get_note_by_id(self, team_id, case_id, note_id):
        """Get a specific note by ID"""
        endpoint = f"/team/{team_id}/case/{case_id}/note/{note_id}"
        return self.client.get(endpoint)
    
    def create_note(self, team_id, case_id, note_data):
        """Create a new note for a case"""
        endpoint = f"/team/{team_id}/case/{case_id}/note"
        return self.client.post(endpoint, note_data)