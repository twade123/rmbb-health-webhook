# services/provider_location_cache.py
import json
import os
import threading
import requests
import base64
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
            
            # Also save to GitHub-friendly location if we can detect we're in Railway
            if '/app' in str(self.cache_file):
                self._save_to_github_format()
                # Attempt automated GitHub commit if credentials are available
                self._commit_to_github()
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
    
    def _save_to_github_format(self):
        """Save cache in a format that can be manually copied to GitHub"""
        try:
            # Create a formatted version for manual copying
            github_format = {
                "last_updated": datetime.now().isoformat(),
                "providers": {}
            }
            
            # Get global case mappings for reference
            global_case_mappings = self.cache.get("case_mappings", {})
            
            for key, data in self.cache.items():
                # Skip the global case_mappings entry
                if key == "case_mappings":
                    continue
                    
                # Build case mappings for this provider from global mappings
                provider_case_mappings = {}
                case_ids = data.get("case_ids", [])
                
                for case_id in case_ids:
                    if str(case_id) in global_case_mappings:
                        mapping = global_case_mappings[str(case_id)]
                        provider_case_mappings[str(case_id)] = {
                            "contact_id": mapping.get("contact_id"),
                            "location_id": mapping.get("location_id"),
                            "provider_name": mapping.get("provider_name"),
                            "external_id": mapping.get("external_id"),
                            "created": mapping.get("created")
                        }
                
                github_format["providers"][key] = {
                    "original_name": data.get("original_name", key),
                    "location_id": data.get("location_id"),
                    "sub_account_api_key": data.get("sub_account_api_key"),
                    "api_key_status": data.get("api_key_status", "pending_manual_entry"),
                    "case_mappings": provider_case_mappings,
                    "form_submissions": data.get("form_submissions", 0),
                    "first_seen": data.get("first_seen"),
                    "last_updated": data.get("last_updated")
                }
            
            # Print formatted JSON for manual copying
            print("🔗 GITHUB CACHE UPDATE REQUIRED:")
            print("📋 Copy the following to your GitHub provider_locations.json file:")
            print("=" * 60)
            print(json.dumps(github_format, indent=2, default=str))
            print("=" * 60)
            
        except Exception as e:
            print(f"⚠️ Error formatting for GitHub: {e}")
    
    def _commit_to_github(self):
        """Automatically commit cache to GitHub repository if credentials are available"""
        try:
            # Check for required environment variables
            github_token = os.getenv('GITHUB_TOKEN')
            repo_owner = os.getenv('GITHUB_REPO_OWNER') 
            repo_name = os.getenv('GITHUB_REPO_NAME')
            file_path = 'provider_locations.json'  # Path in repository
            
            if not all([github_token, repo_owner, repo_name]):
                print("📝 GitHub credentials not configured - using manual copy method")
                return
                
            # Create the GitHub-ready content
            github_format = {
                "last_updated": datetime.now().isoformat(),
                "providers": {}
            }
            
            global_case_mappings = self.cache.get("case_mappings", {})
            
            for key, data in self.cache.items():
                if key == "case_mappings":
                    continue
                    
                provider_case_mappings = {}
                case_ids = data.get("case_ids", [])
                
                for case_id in case_ids:
                    if str(case_id) in global_case_mappings:
                        mapping = global_case_mappings[str(case_id)]
                        provider_case_mappings[str(case_id)] = {
                            "contact_id": mapping.get("contact_id"),
                            "location_id": mapping.get("location_id"),
                            "provider_name": mapping.get("provider_name"),
                            "external_id": mapping.get("external_id"),
                            "created": mapping.get("created")
                        }
                
                github_format["providers"][key] = {
                    "original_name": data.get("original_name", key),
                    "location_id": data.get("location_id"),
                    "sub_account_api_key": data.get("sub_account_api_key"),
                    "api_key_status": data.get("api_key_status", "pending_manual_entry"),
                    "case_mappings": provider_case_mappings,
                    "form_submissions": data.get("form_submissions", 0),
                    "first_seen": data.get("first_seen"),
                    "last_updated": data.get("last_updated")
                }
            
            # Convert to JSON string
            content_json = json.dumps(github_format, indent=2, default=str)
            
            # GitHub API setup
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Get current file SHA (required for updates)
            try:
                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    current_file = response.json()
                    current_sha = current_file['sha']
                    print(f"🔍 Found existing file with SHA: {current_sha[:8]}...")
                else:
                    current_sha = None
                    print(f"📝 File doesn't exist, will create new file")
            except Exception as e:
                print(f"⚠️ Could not check existing file: {e}")
                current_sha = None
            
            # Prepare commit data
            commit_data = {
                "message": f"Update provider cache - {len(self.cache)} providers, {len(global_case_mappings)} cases",
                "content": base64.b64encode(content_json.encode()).decode(),
                "branch": "main"
            }
            
            if current_sha:
                commit_data["sha"] = current_sha
            
            # Commit to GitHub
            response = requests.put(api_url, headers=headers, json=commit_data)
            
            if response.status_code in [200, 201]:
                commit_info = response.json()
                commit_sha = commit_info['commit']['sha'][:8]
                print(f"✅ Successfully committed to GitHub!")
                print(f"🔗 Commit: {commit_sha}")
                print(f"📄 File: {file_path}")
                print(f"📊 Data: {len(github_format['providers'])} providers")
            else:
                print(f"❌ GitHub commit failed: {response.status_code}")
                print(f"📋 Response: {response.text}")
                
        except Exception as e:
            print(f"⚠️ Error committing to GitHub: {e}")
    
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
                # New provider - create entry with case tracking and API key placeholder
                self.cache[provider_key] = {
                    "original_name": provider_name,
                    "location_id": location_id,
                    "sub_account_api_key": None,  # Placeholder for manual entry
                    "api_key_status": "pending_manual_entry",  # Track API key status
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
                
                # Ensure API key fields exist (migration from old format)
                if "sub_account_api_key" not in existing:
                    existing["sub_account_api_key"] = None
                if "api_key_status" not in existing:
                    existing["api_key_status"] = "pending_manual_entry"
                
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
    
    def add_case_mapping(self, case_id, provider_name, contact_id, location_id, external_id=None):
        """
        Add RMBB Health case ID to provider mapping (MULTIPLE CASES PER PROVIDER)
        
        Args:
            case_id: RMBB Health case ID
            provider_name: Provider name for this case
            contact_id: GHL contact ID for this case
            location_id: GHL location ID for this case (needed for webhook routing)
            external_id: RMBB Health external_id for reference
        """
        if not case_id or not provider_name or not contact_id or not location_id:
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
                "location_id": location_id,
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

    def get_sub_account_api_key_by_location_id(self, location_id):
        """
        Get manually entered sub account API key for a location ID
        
        Args:
            location_id: GHL location ID
            
        Returns:
            str: Manually entered sub account API key, or None if not set
        """
        if not location_id:
            return None
            
        with self.lock:
            # Search through all providers for matching location_id
            for provider_key, provider_data in self.cache.items():
                if isinstance(provider_data, dict) and provider_data.get("location_id") == location_id:
                    api_key = provider_data.get("sub_account_api_key")
                    if api_key:
                        print(f"🔑 Found manually entered API key for location {location_id}")
                        return api_key
                    else:
                        print(f"⚠️ No API key manually entered for location {location_id} (provider: {provider_data.get('original_name')})")
                        return None
            
            print(f"❌ Location not found in cache: {location_id}")
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
            
            # Check if provider exists (without lock first)
            provider_exists = provider_key in self.cache
            
            if not provider_exists:
                # New provider - add it (add_or_update_provider handles its own locking)
                self.add_or_update_provider(
                    provider_name=business_name,
                    location_id=location_id,
                    increment_submissions=False  # Don't increment for bulk updates
                )
                stats["new_providers"] += 1
            else:
                # Existing provider - check if location_id changed
                needs_update = False
                with self.lock:
                    existing = self.cache[provider_key]
                    if existing["location_id"] != location_id:
                        needs_update = True
                    else:
                        stats["unchanged_providers"] += 1
                
                if needs_update:
                    self.add_or_update_provider(
                        provider_name=business_name,
                        location_id=location_id,
                        increment_submissions=False
                    )
                    stats["updated_providers"] += 1
        
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
                # Use absolute path to GitHub repository file for persistence
                # This ensures the cache persists in the repository where API keys can be manually added
                default_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'provider_locations.json')
                cache_path = os.getenv('PROVIDER_CACHE_PATH', default_path)
                _cache_instance = ProviderLocationCache(cache_path)
    
    return _cache_instance
