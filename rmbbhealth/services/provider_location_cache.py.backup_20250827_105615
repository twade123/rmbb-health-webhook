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
    
    def add_or_update_provider(self, provider_name, location_id, contact_id=None, increment_submissions=True):
        """
        Add or update provider → location mapping (INCREMENTAL ONLY - NO DELETION)
        
        Args:
            provider_name: Name of the healthcare provider
            location_id: GHL location ID for this provider's sub-account  
            contact_id: Optional - GHL contact ID for tracking
            increment_submissions: Whether to increment form submission counter
        """
        if not provider_name or not location_id:
            print(f"⚠️ Skipping cache update - missing provider_name or location_id")
            return False
            
        provider_key = self._normalize_provider_name(provider_name)
        
        with self.lock:
            is_new_provider = provider_key not in self.cache
            
            if is_new_provider:
                # New provider - create entry with case tracking
                self.cache[provider_key] = {
                    "original_name": provider_name,
                    "location_id": location_id,
                    "first_seen": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "form_submissions": 1 if increment_submissions else 0,
                    "case_ids": [],  # Track all RMBB Health case IDs for this provider
                    "sample_contact_id": contact_id
                }
                print(f"➕ Added NEW provider: {provider_name} → {location_id}")
                
            else:
                # Existing provider - INCREMENTAL update only
                existing = self.cache[provider_key]
                
                # Ensure case_ids exists (migration from old format)
                if "case_ids" not in existing:
                    existing["case_ids"] = []
                
                # Check for location_id changes (potential issue detection)
                if existing["location_id"] != location_id:
                    print(f"⚠️ WARNING: Provider {provider_name} location changed!")
                    print(f"   Old: {existing['location_id']} → New: {location_id}")
                    existing["location_id"] = location_id  # Update to most recent
                
                # Increment submission counter only if requested
                if increment_submissions:
                    existing["form_submissions"] = existing.get("form_submissions", 0) + 1
                
                # Update timestamps and contact info
                existing["last_updated"] = datetime.now().isoformat()
                if contact_id:
                    existing["sample_contact_id"] = contact_id
                
                submissions = existing.get("form_submissions", 0)
                cases = len(existing.get("case_ids", []))
                print(f"🔄 Updated provider: {provider_name} ({submissions} submissions, {cases} cases)")
            
            self._save_cache()
            return True
    
    def add_case_mapping(self, case_id, provider_name, contact_id, external_id=None):
        """
        Add RMBB Health case ID to provider mapping (MULTIPLE CASES PER PROVIDER)
        
        Args:
            case_id: RMBB Health case ID
            provider_name: Provider name for this case
            contact_id: GHL contact ID for this case
            external_id: RMBB Health external_id for reference
        """
        if not case_id or not provider_name or not contact_id:
            print(f"⚠️ Missing required data for case mapping")
            return False
            
        provider_key = self._normalize_provider_name(provider_name)
        
        with self.lock:
            # Ensure provider exists in cache
            if provider_key not in self.cache:
                print(f"⚠️ Provider {provider_name} not in cache - cannot add case mapping")
                return False
            
            # Ensure case_ids list exists
            if "case_ids" not in self.cache[provider_key]:
                self.cache[provider_key]["case_ids"] = []
            
            # Add case ID if not already present (avoid duplicates)
            case_ids = self.cache[provider_key]["case_ids"]
            if str(case_id) not in case_ids:
                case_ids.append(str(case_id))
                print(f"📋 Added case {case_id} to provider {provider_name} (total: {len(case_ids)} cases)")
            else:
                print(f"⚠️ Case {case_id} already exists for provider {provider_name}")
            
            # Store detailed case mapping in separate section
            if "case_mappings" not in self.cache:
                self.cache["case_mappings"] = {}
                
            self.cache["case_mappings"][str(case_id)] = {
                "case_id": str(case_id),
                "provider_name": provider_name,
                "provider_key": provider_key,
                "contact_id": contact_id,
                "external_id": external_id,
                "created": datetime.now().isoformat()
            }
            
            self._save_cache()
            return True
    
    def get_case_mapping(self, case_id):
        """
        Get provider and contact info for a case ID
        
        Args:
            case_id: RMBB Health case ID
            
        Returns:
            dict: Case mapping with provider_name, contact_id, location_id
        """
        with self.lock:
            case_mappings = self.cache.get("case_mappings", {})
            mapping = case_mappings.get(str(case_id))
            
            if mapping:
                # Add location_id to the mapping
                provider_key = mapping.get("provider_key")
                if provider_key and provider_key in self.cache:
                    mapping["location_id"] = self.cache[provider_key]["location_id"]
                
                print(f"🔍 Found case mapping: {case_id} → {mapping['provider_name']} → {mapping.get('location_id')}")
                return mapping
            else:
                print(f"❌ Case mapping not found: {case_id}")
                return None

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
    
    def incremental_provider_update(self, ghl_locations):
        """
        Incrementally update providers list - NO DELETION, only add/update new ones
        
        Args:
            ghl_locations: List of GHL location objects from agency API
            
        Returns:
            dict: Update statistics
        """
        stats = {
            "locations_processed": len(ghl_locations),
            "new_providers": 0,
            "updated_providers": 0,
            "unchanged_providers": 0
        }
        
        for location in ghl_locations:
            location_id = location.get('id')
            business_name = location.get('businessName') or location.get('name', '')
            
            if not location_id or not business_name:
                continue
                
            provider_key = self._normalize_provider_name(business_name)
            
            with self.lock:
                if provider_key not in self.cache:
                    # New provider - add it
                    self.add_or_update_provider(
                        provider_name=business_name,
                        location_id=location_id,
                        increment_submissions=False  # Don't increment for bulk updates
                    )
                    stats["new_providers"] += 1
                else:
                    # Existing provider - check if location_id changed
                    existing = self.cache[provider_key]
                    if existing["location_id"] != location_id:
                        # Location changed - update it
                        self.add_or_update_provider(
                            provider_name=business_name,
                            location_id=location_id,
                            increment_submissions=False
                        )
                        stats["updated_providers"] += 1
                    else:
                        # No changes
                        stats["unchanged_providers"] += 1
        
        print(f"📊 Incremental update: +{stats['new_providers']} new, ~{stats['updated_providers']} updated, ={stats['unchanged_providers']} unchanged")
        return stats

    def get_cache_stats(self):
        """Get comprehensive statistics about the cache"""
        with self.lock:
            # Handle both old and new cache format
            providers = {k: v for k, v in self.cache.items() if isinstance(v, dict) and "location_id" in v}
            case_mappings = self.cache.get("case_mappings", {})
            
            total_providers = len(providers)
            total_submissions = sum(p.get("form_submissions", 0) for p in providers.values())
            total_cases = len(case_mappings)
            
            stats = {
                "total_providers": total_providers,
                "total_form_submissions": total_submissions,
                "total_cases": total_cases,
                "cache_file": str(self.cache_file),
                "providers": []
            }
            
            for key, data in providers.items():
                case_count = len(data.get("case_ids", []))
                stats["providers"].append({
                    "name": data.get("original_name", key),
                    "location_id": data.get("location_id"),
                    "submissions": data.get("form_submissions", 0),
                    "cases": case_count,
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