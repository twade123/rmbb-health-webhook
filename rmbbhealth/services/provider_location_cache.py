# services/provider_location_cache.py
import json
import os
import threading
from datetime import datetime
from pathlib import Path

class ProviderLocationCache:
    """
    Thread-safe cache for provider name → GHL locationId mappings.
    
    HIPAA Compliant: Only stores provider name + locationId (no patient data)
    Used to route RMBB Health responses back to correct GHL sub-accounts.
    """
    
    def __init__(self, cache_file="provider_locations.json"):
        self.cache_file = Path(cache_file)
        self.cache = {}
        self.lock = threading.Lock()
        self._load_cache()
    
    def _load_cache(self):
        """Load existing cache from file if it exists"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                print(f"✅ Loaded provider cache with {len(self.cache)} providers")
            else:
                print("📝 Creating new provider location cache")
                self.cache = {}
        except Exception as e:
            print(f"⚠️ Error loading cache, starting fresh: {e}")
            self.cache = {}
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2, default=str)
            print(f"💾 Saved provider cache with {len(self.cache)} providers")
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
    
    def add_or_update_provider(self, provider_name, location_id, contact_id=None):
        """
        Add or update provider → location mapping
        
        Args:
            provider_name: Name of the healthcare provider
            location_id: GHL location ID for this provider's sub-account  
            contact_id: Optional - GHL contact ID for tracking
        """
        if not provider_name or not location_id:
            print(f"⚠️ Skipping cache update - missing provider_name or location_id")
            return False
            
        provider_key = self._normalize_provider_name(provider_name)
        
        with self.lock:
            is_new_provider = provider_key not in self.cache
            
            if is_new_provider:
                # New provider - create entry
                self.cache[provider_key] = {
                    "original_name": provider_name,
                    "location_id": location_id,
                    "first_seen": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "form_submissions": 1,
                    "sample_contact_id": contact_id  # For debugging/reference
                }
                print(f"➕ Added new provider: {provider_name} → {location_id}")
                
            else:
                # Existing provider - update last_updated and increment counter
                existing = self.cache[provider_key]
                
                # Verify location_id matches (detect potential issues)
                if existing["location_id"] != location_id:
                    print(f"⚠️ WARNING: Provider {provider_name} location changed!")
                    print(f"   Old: {existing['location_id']} → New: {location_id}")
                
                existing["location_id"] = location_id  # Update to most recent
                existing["last_updated"] = datetime.now().isoformat()
                existing["form_submissions"] += 1
                if contact_id:
                    existing["sample_contact_id"] = contact_id
                
                print(f"🔄 Updated provider: {provider_name} (submissions: {existing['form_submissions']})")
            
            self._save_cache()
            return True
    
    def get_location_id(self, provider_name):
        """
        Get GHL location ID for a provider
        
        Args:
            provider_name: Name of the healthcare provider
            
        Returns:
            str: GHL location ID, or None if provider not found
        """
        if not provider_name:
            return None
            
        provider_key = self._normalize_provider_name(provider_name)
        
        with self.lock:
            if provider_key in self.cache:
                location_id = self.cache[provider_key]["location_id"]
                print(f"🔍 Found provider {provider_name} → {location_id}")
                return location_id
            else:
                print(f"❌ Provider not found in cache: {provider_name}")
                print(f"📋 Available providers: {list(self.cache.keys())}")
                return None
    
    def _normalize_provider_name(self, provider_name):
        """
        Normalize provider name for consistent cache keys
        (handles variations in spacing, case, etc.)
        """
        if not provider_name:
            return ""
        
        # Convert to lowercase, strip whitespace, remove extra spaces
        normalized = " ".join(provider_name.lower().strip().split())
        return normalized
    
    def get_cache_stats(self):
        """Get statistics about the cache"""
        with self.lock:
            total_providers = len(self.cache)
            total_submissions = sum(p.get("form_submissions", 0) for p in self.cache.values())
            
            stats = {
                "total_providers": total_providers,
                "total_form_submissions": total_submissions,
                "cache_file": str(self.cache_file),
                "providers": []
            }
            
            for key, data in self.cache.items():
                stats["providers"].append({
                    "name": data.get("original_name", key),
                    "location_id": data.get("location_id"),
                    "submissions": data.get("form_submissions", 0),
                    "first_seen": data.get("first_seen"),
                    "last_updated": data.get("last_updated")
                })
            
            return stats
    
    def clear_cache(self):
        """Clear all cache data (use with caution)"""
        with self.lock:
            self.cache = {}
            if self.cache_file.exists():
                self.cache_file.unlink()
            print("🗑️ Provider location cache cleared")

# Singleton instance for the application
_cache_instance = None
_cache_lock = threading.Lock()

def get_provider_cache():
    """Get the global provider cache instance (singleton)"""
    global _cache_instance
    
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                # Use Railway-friendly cache file path
                cache_path = os.getenv('PROVIDER_CACHE_PATH', 'provider_locations.json')
                _cache_instance = ProviderLocationCache(cache_path)
    
    return _cache_instance