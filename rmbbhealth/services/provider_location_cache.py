# services/provider_location_cache.py
import json
import os
import threading
import requests
import base64
from datetime import datetime
from pathlib import Path

class HierarchicalProviderCache:
    """
    Thread-safe hierarchical cache for provider name → GHL locationId mappings.

    NEW ARCHITECTURE: Isolated sub-account files prevent data corruption
    - Each sub-account gets its own JSON file with cases
    - Master registry tracks all sub-accounts without case data
    - Atomic operations: changes to one provider can't affect others

    BACKWARD COMPATIBILITY: All existing method signatures preserved
    """

    def __init__(self, cache_file="provider_locations.json"):
        # New hierarchical structure
        self.base_dir = Path(os.path.dirname(cache_file))
        self.cache_dir = self.base_dir / "provider_cache"
        self.sub_accounts_dir = self.cache_dir / "sub_accounts"
        self.master_registry_file = self.cache_dir / "master_registry.json"
        self.sync_metadata_file = self.cache_dir / "sync_metadata.json"

        # Legacy compatibility - still support old cache_file parameter
        self.legacy_cache_file = Path(cache_file)

        # Thread safety
        self.lock = threading.Lock()

        # In-memory cache for performance
        self.master_registry = {}
        self.sub_account_cache = {}  # Loaded on-demand

        # Initialize directory structure
        self._ensure_directory_structure()

        # Load or migrate data
        self._load_or_migrate_cache()

    def _ensure_directory_structure(self):
        """Create hierarchical directory structure if it doesn't exist"""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.sub_accounts_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"⚠️ Error creating directory structure: {e}")

    def _load_or_migrate_cache(self):
        """Load existing hierarchical cache or migrate from legacy format"""
        try:
            # Try to load hierarchical structure first
            if self.master_registry_file.exists():
                self._load_hierarchical_cache()
                print(f"✅ Loaded hierarchical cache: {len(self.master_registry.get('sub_accounts', {}))} sub-accounts")
            elif self.legacy_cache_file.exists():
                # Migration from legacy format
                print("🔄 Migrating from legacy cache format...")
                self._migrate_from_legacy_format()
                print("✅ Migration completed")
            else:
                # Initialize new structure
                self._initialize_empty_cache()
                print("✅ Initialized new hierarchical cache")
        except Exception as e:
            print(f"⚠️ Error loading cache, starting fresh: {e}")
            self._initialize_empty_cache()

    def _load_hierarchical_cache(self):
        """Load the master registry"""
        try:
            with open(self.master_registry_file, 'r') as f:
                self.master_registry = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading master registry: {e}")
            self._initialize_empty_cache()

    def _migrate_from_legacy_format(self):
        """Migrate existing provider_locations.json to hierarchical structure"""
        try:
            with open(self.legacy_cache_file, 'r') as f:
                legacy_data = json.load(f)

            # Initialize master registry
            self.master_registry = {
                "last_updated": datetime.now().isoformat(),
                "total_sub_accounts": 0,
                "agency_info": {},
                "sub_accounts": {},
                "discovery_metadata": {
                    "auto_discovery_enabled": True,
                    "last_ghl_agency_sync": legacy_data.get("last_updated"),
                    "locations_discovered_count": 0,
                    "sync_frequency": "on_webhook",
                    "sync_errors": []
                }
            }

            # Handle GitHub format vs direct cache format
            providers_data = {}
            global_case_mappings = {}

            if 'providers' in legacy_data:
                # GitHub format
                providers_data = legacy_data['providers']
                global_case_mappings = legacy_data.get('case_mappings', {})
            else:
                # Direct cache format - separate providers from case_mappings
                for key, data in legacy_data.items():
                    if key == "case_mappings":
                        global_case_mappings = data
                    elif isinstance(data, dict) and "location_id" in data:
                        providers_data[key] = data

            # Migrate each provider to individual files
            for provider_key, provider_data in providers_data.items():
                try:
                    # Create sub-account entry in master registry
                    is_agency = provider_data.get("location_id") == "10SapwdFnQK3Kwqp5ecv"
                    account_type = "agency" if is_agency else "sub_account"

                    self.master_registry["sub_accounts"][provider_key] = {
                        "display_name": provider_data.get("original_name", provider_key),
                        "normalized_key": provider_key,
                        "location_id": provider_data.get("location_id"),
                        "account_type": account_type,
                        "status": "active",
                        "data_file": f"{provider_key}.json" if not is_agency else None,
                        "api_key_status": provider_data.get("api_key_status", "pending_manual_entry"),
                        "first_seen": provider_data.get("first_seen"),
                        "last_updated": provider_data.get("last_updated"),
                        "form_submissions": provider_data.get("form_submissions", 0),
                        "case_count": len(provider_data.get("case_ids", []))
                    }

                    # For agency account, store in master registry
                    if is_agency:
                        self.master_registry["agency_info"] = {
                            "agency_name": provider_data.get("original_name"),
                            "agency_location_id": provider_data.get("location_id"),
                            "api_key_status": provider_data.get("api_key_status"),
                            "created": provider_data.get("first_seen")
                        }
                        continue

                    # Create individual sub-account file
                    sub_account_data = {
                        "provider_info": {
                            "original_name": provider_data.get("original_name"),
                            "normalized_key": provider_key,
                            "location_id": provider_data.get("location_id"),
                            "sub_account_api_key": provider_data.get("sub_account_api_key"),
                            "api_key_status": provider_data.get("api_key_status", "pending_manual_entry")
                        },
                        "statistics": {
                            "form_submissions": provider_data.get("form_submissions", 0),
                            "first_seen": provider_data.get("first_seen"),
                            "last_updated": provider_data.get("last_updated"),
                            "case_ids": provider_data.get("case_ids", [])
                        },
                        "case_mappings": {}
                    }

                    # Add case mappings for this provider
                    case_ids = provider_data.get("case_ids", [])
                    for case_id in case_ids:
                        if str(case_id) in global_case_mappings:
                            sub_account_data["case_mappings"][str(case_id)] = global_case_mappings[str(case_id)]

                    # Also include provider-specific case mappings
                    if "case_mappings" in provider_data:
                        sub_account_data["case_mappings"].update(provider_data["case_mappings"])

                    # Add remaining global case mappings that belong to this provider
                    for case_id, case_data in global_case_mappings.items():
                        if case_data.get("provider_key") == provider_key:
                            sub_account_data["case_mappings"][case_id] = case_data

                    # Save individual sub-account file
                    sub_account_file = self.sub_accounts_dir / f"{provider_key}.json"
                    with open(sub_account_file, 'w') as f:
                        json.dump(sub_account_data, f, indent=2, default=str)

                except Exception as e:
                    print(f"⚠️ Error migrating provider {provider_key}: {e}")
                    continue

            self.master_registry["total_sub_accounts"] = len(self.master_registry["sub_accounts"])

            # Save master registry
            self._save_master_registry()

            # Initialize sync metadata
            self._initialize_sync_metadata()

            # Backup legacy file
            backup_file = f"{self.legacy_cache_file}.backup_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(self.legacy_cache_file, backup_file)
            print(f"✅ Legacy file backed up to: {backup_file}")

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            self._initialize_empty_cache()

    def _initialize_empty_cache(self):
        """Initialize empty cache structure"""
        self.master_registry = {
            "last_updated": datetime.now().isoformat(),
            "total_sub_accounts": 0,
            "agency_info": {},
            "sub_accounts": {},
            "discovery_metadata": {
                "auto_discovery_enabled": True,
                "last_ghl_agency_sync": None,
                "locations_discovered_count": 0,
                "sync_frequency": "on_webhook",
                "sync_errors": []
            }
        }
        self._save_master_registry()
        self._initialize_sync_metadata()

    def _initialize_sync_metadata(self):
        """Initialize sync metadata tracking"""
        sync_metadata = {
            "sync_history": {
                "last_successful_sync": None,
                "last_sync_attempt": None,
                "consecutive_successful_syncs": 0,
                "consecutive_failed_syncs": 0,
                "total_syncs_performed": 0
            },
            "ghl_api_status": {
                "agency_api_key_valid": True,
                "last_api_response_code": None,
                "api_rate_limit_remaining": None,
                "locations_endpoint_accessible": True
            },
            "sync_configuration": {
                "auto_sync_enabled": True,
                "sync_trigger": "webhook_request",
                "preserve_existing_data": True,
                "backup_before_sync": True,
                "max_sync_retries": 3
            },
            "change_detection": {
                "new_sub_accounts_detected": [],
                "modified_sub_accounts": [],
                "removed_sub_accounts": [],
                "location_id_changes": []
            },
            "performance_metrics": {
                "average_sync_duration_ms": 0,
                "last_sync_duration_ms": 0,
                "cache_file_sizes_bytes": {}
            }
        }

        try:
            with open(self.sync_metadata_file, 'w') as f:
                json.dump(sync_metadata, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Error initializing sync metadata: {e}")

    def _save_master_registry(self):
        """Save master registry to file"""
        try:
            self.master_registry["last_updated"] = datetime.now().isoformat()
            with open(self.master_registry_file, 'w') as f:
                json.dump(self.master_registry, f, indent=2, default=str)
        except Exception as e:
            print(f"❌ Error saving master registry: {e}")

    def _load_sub_account_data(self, provider_key):
        """Load individual sub-account data on demand"""
        if provider_key in self.sub_account_cache:
            return self.sub_account_cache[provider_key]

        try:
            sub_account_file = self.sub_accounts_dir / f"{provider_key}.json"
            if sub_account_file.exists():
                with open(sub_account_file, 'r') as f:
                    data = json.load(f)
                    self.sub_account_cache[provider_key] = data
                    return data
            else:
                return None
        except Exception as e:
            print(f"⚠️ Error loading sub-account {provider_key}: {e}")
            return None

    def _save_sub_account_data(self, provider_key, data):
        """Save individual sub-account data"""
        try:
            # Update in-memory cache
            self.sub_account_cache[provider_key] = data

            # Save to file
            sub_account_file = self.sub_accounts_dir / f"{provider_key}.json"
            with open(sub_account_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            # Update master registry statistics
            if provider_key in self.master_registry.get("sub_accounts", {}):
                self.master_registry["sub_accounts"][provider_key]["last_updated"] = datetime.now().isoformat()
                self.master_registry["sub_accounts"][provider_key]["case_count"] = len(data.get("case_mappings", {}))
                self._save_master_registry()
                
            # CRITICAL: Commit to GitHub for Railway persistence
            # Only attempt if we're in Railway environment (has /app path)
            if '/app' in str(self.cache_dir):
                self._commit_provider_file_to_github(provider_key)
                # Also commit updated master registry
                self._commit_master_registry_to_github()

        except Exception as e:
            print(f"❌ Error saving sub-account {provider_key}: {e}")

    def _normalize_provider_name(self, provider_name):
        """Normalize provider name for consistent cache keys"""
        if not provider_name:
            return ""
        return " ".join(provider_name.lower().strip().split())

    def add_or_update_provider(self, provider_name, location_id, contact_id=None, increment_submissions=True):
        """
        Add or update provider → location mapping (ISOLATED - NO CROSS-CONTAMINATION)

        BACKWARD COMPATIBLE: Same method signature as before
        NEW BEHAVIOR: Each provider gets isolated file, cannot corrupt others
        """
        if not provider_name or not location_id:
            print(f"⚠️ Skipping cache update - missing provider_name or location_id")
            return False

        provider_key = self._normalize_provider_name(provider_name)

        with self.lock:
            # Check if provider exists in master registry
            is_new_provider = provider_key not in self.master_registry.get("sub_accounts", {})

            if is_new_provider:
                # Create new sub-account entry in master registry
                is_agency = location_id == "10SapwdFnQK3Kwqp5ecv"
                account_type = "agency" if is_agency else "sub_account"

                self.master_registry.setdefault("sub_accounts", {})[provider_key] = {
                    "display_name": provider_name,
                    "normalized_key": provider_key,
                    "location_id": location_id,
                    "account_type": account_type,
                    "status": "active",
                    "data_file": f"{provider_key}.json" if not is_agency else None,
                    "api_key_status": "pending_manual_entry",
                    "first_seen": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "form_submissions": 1 if increment_submissions else 0,
                    "case_count": 0
                }

                # For agency account, don't create sub-account file
                if is_agency:
                    self.master_registry["agency_info"] = {
                        "agency_name": provider_name,
                        "agency_location_id": location_id,
                        "api_key_status": "uses_railway_ghl_api_key",
                        "created": datetime.now().isoformat()
                    }
                    self._save_master_registry()
                    return True

                # Create new sub-account file
                sub_account_data = {
                    "provider_info": {
                        "original_name": provider_name,
                        "normalized_key": provider_key,
                        "location_id": location_id,
                        "sub_account_api_key": None,
                        "api_key_status": "pending_manual_entry"
                    },
                    "statistics": {
                        "form_submissions": 1 if increment_submissions else 0,
                        "first_seen": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "case_ids": []
                    },
                    "case_mappings": {}
                }

                self._save_sub_account_data(provider_key, sub_account_data)
                self.master_registry["total_sub_accounts"] += 1
                self._save_master_registry()

            else:
                # Update existing provider - ISOLATED update
                existing_registry = self.master_registry["sub_accounts"][provider_key]

                # Check for location_id changes (potential issue detection)
                if existing_registry["location_id"] != location_id:
                    print(f"⚠️ WARNING: Provider {provider_name} location changed!")
                    print(f"   Old: {existing_registry['location_id']} → New: {location_id}")
                    existing_registry["location_id"] = location_id

                # Update submission counter in master registry
                if increment_submissions:
                    existing_registry["form_submissions"] = existing_registry.get("form_submissions", 0) + 1

                existing_registry["last_updated"] = datetime.now().isoformat()

                # Update sub-account file if it exists
                if existing_registry.get("data_file"):
                    sub_account_data = self._load_sub_account_data(provider_key)
                    if sub_account_data:
                        # Update statistics in isolated file
                        if increment_submissions:
                            sub_account_data["statistics"]["form_submissions"] = sub_account_data["statistics"].get("form_submissions", 0) + 1
                        sub_account_data["statistics"]["last_updated"] = datetime.now().isoformat()
                        if contact_id:
                            sub_account_data["statistics"]["sample_contact_id"] = contact_id

                        # Update location_id if changed
                        if sub_account_data["provider_info"]["location_id"] != location_id:
                            sub_account_data["provider_info"]["location_id"] = location_id

                        self._save_sub_account_data(provider_key, sub_account_data)

                self._save_master_registry()

            return True

    def add_case_mapping(self, case_id, provider_name, contact_id, location_id, external_id=None, product_info=None):
        """
        Add RMBB Health case ID to provider mapping (ISOLATED PER PROVIDER)

        BACKWARD COMPATIBLE: Same method signature
        NEW BEHAVIOR: Case stored in individual provider file - cannot corrupt other providers
        """
        if not case_id or not provider_name or not contact_id or not location_id:
            print(f"⚠️ Missing required data for case mapping")
            return False

        provider_key = self._normalize_provider_name(provider_name)

        with self.lock:
            # Ensure provider exists in master registry
            if provider_key not in self.master_registry.get("sub_accounts", {}):
                print(f"⚠️ Provider {provider_name} not in cache - cannot add case mapping")
                return False

            # Load individual provider data
            sub_account_data = self._load_sub_account_data(provider_key)
            if not sub_account_data:
                print(f"⚠️ Sub-account data not found for {provider_name}")
                return False

            # Add case ID to statistics if not already present
            case_ids = sub_account_data["statistics"].setdefault("case_ids", [])
            if str(case_id) not in case_ids:
                case_ids.append(str(case_id))

            # Store case mapping in ISOLATED provider file
            case_mapping_data = {
                "case_id": str(case_id),
                "provider_name": provider_name,
                "provider_key": provider_key,
                "contact_id": contact_id,
                "location_id": location_id,
                "external_id": external_id,
                "created": datetime.now().isoformat()
            }

            # Add product information for reorder system
            if product_info:
                case_mapping_data["approved_product"] = {
                    "name": product_info.get("name"),
                    "product_id": product_info.get("product_id"),
                    "q_code": product_info.get("q_code"),
                    "saved_at": datetime.now().isoformat()
                }

            # Store in provider's isolated case mappings
            sub_account_data.setdefault("case_mappings", {})[str(case_id)] = case_mapping_data

            # Save to isolated provider file
            self._save_sub_account_data(provider_key, sub_account_data)

            return True

    def get_case_mapping(self, case_id):
        """
        Get provider and contact info for a case ID

        BACKWARD COMPATIBLE: Same return format
        NEW BEHAVIOR: Searches across isolated provider files
        """
        with self.lock:
            # Search through all sub-accounts for the case
            for provider_key, registry_info in self.master_registry.get("sub_accounts", {}).items():
                if not registry_info.get("data_file"):
                    continue  # Skip agency accounts

                sub_account_data = self._load_sub_account_data(provider_key)
                if not sub_account_data:
                    continue

                case_mappings = sub_account_data.get("case_mappings", {})
                if str(case_id) in case_mappings:
                    mapping = case_mappings[str(case_id)]
                    # Ensure location_id is included
                    if "location_id" not in mapping:
                        mapping["location_id"] = sub_account_data["provider_info"]["location_id"]
                    return mapping

            print(f"❌ Case mapping not found: {case_id}")
            return None

    def get_location_id(self, provider_name):
        """
        Get GHL location ID for a provider

        BACKWARD COMPATIBLE: Same method signature and return value
        """
        if not provider_name:
            return None

        provider_key = self._normalize_provider_name(provider_name)

        with self.lock:
            sub_accounts = self.master_registry.get("sub_accounts", {})
            if provider_key in sub_accounts:
                location_id = sub_accounts[provider_key]["location_id"]
                return location_id
            else:
                print(f"❌ Provider not found: {provider_name}")
                return None

    def get_sub_account_api_key_by_location_id(self, location_id):
        """
        Get manually entered sub account API key for a location ID

        BACKWARD COMPATIBLE: Same method signature and return value
        NEW BEHAVIOR: Searches across isolated provider files
        """
        if not location_id:
            return None

        with self.lock:
            # Search through all sub-accounts for matching location_id
            for provider_key, registry_info in self.master_registry.get("sub_accounts", {}).items():
                if registry_info.get("location_id") == location_id:
                    if not registry_info.get("data_file"):
                        # Agency account - no API key stored in file
                        return None

                    sub_account_data = self._load_sub_account_data(provider_key)
                    if sub_account_data:
                        api_key = sub_account_data["provider_info"].get("sub_account_api_key")
                        if api_key:
                            return api_key
                        else:
                            print(f"⚠️ No API key manually entered for location {location_id} (provider: {registry_info.get('display_name')})")
                            return None

            print(f"❌ Location not found in cache: {location_id}")
            return None

    def incremental_provider_update(self, ghl_locations):
        """
        Incrementally update providers list - ISOLATED updates prevent corruption

        BACKWARD COMPATIBLE: Same method signature and return format
        NEW BEHAVIOR: Updates only master registry, preserves all existing case data
        """
        stats = {
            "locations_processed": len(ghl_locations),
            "new_providers": 0,
            "updated_providers": 0,
            "unchanged_providers": 0
        }

        with self.lock:
            start_time = datetime.now()

            for location in ghl_locations:
                location_id = location.get('id')
                business_name = location.get('businessName') or location.get('name', '')

                if not location_id or not business_name:
                    continue

                provider_key = self._normalize_provider_name(business_name)
                sub_accounts = self.master_registry.setdefault("sub_accounts", {})

                if provider_key not in sub_accounts:
                    # New provider - add to master registry only
                    is_agency = location_id == "10SapwdFnQK3Kwqp5ecv"
                    account_type = "agency" if is_agency else "sub_account"

                    sub_accounts[provider_key] = {
                        "display_name": business_name,
                        "normalized_key": provider_key,
                        "location_id": location_id,
                        "account_type": account_type,
                        "status": "active",
                        "data_file": f"{provider_key}.json" if not is_agency else None,
                        "api_key_status": "pending_manual_entry",
                        "first_seen": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "form_submissions": 0,
                        "case_count": 0
                    }

                    stats["new_providers"] += 1

                    # For new sub-accounts (not agency), create empty file
                    if not is_agency:
                        sub_account_data = {
                            "provider_info": {
                                "original_name": business_name,
                                "normalized_key": provider_key,
                                "location_id": location_id,
                                "sub_account_api_key": None,
                                "api_key_status": "pending_manual_entry"
                            },
                            "statistics": {
                                "form_submissions": 0,
                                "first_seen": datetime.now().isoformat(),
                                "last_updated": datetime.now().isoformat(),
                                "case_ids": []
                            },
                            "case_mappings": {}
                        }
                        self._save_sub_account_data(provider_key, sub_account_data)

                else:
                    # Existing provider - check for location_id changes
                    existing = sub_accounts[provider_key]
                    if existing["location_id"] != location_id:
                        print(f"⚠️ WARNING: Provider {business_name} location changed!")
                        print(f"   Old: {existing['location_id']} → New: {location_id}")
                        existing["location_id"] = location_id
                        existing["last_updated"] = datetime.now().isoformat()

                        # Also update location_id in individual provider file
                        if existing.get("data_file"):
                            sub_account_data = self._load_sub_account_data(provider_key)
                            if sub_account_data:
                                sub_account_data["provider_info"]["location_id"] = location_id
                                sub_account_data["statistics"]["last_updated"] = datetime.now().isoformat()
                                self._save_sub_account_data(provider_key, sub_account_data)

                        stats["updated_providers"] += 1
                    else:
                        stats["unchanged_providers"] += 1

            # Update master registry totals and metadata
            self.master_registry["total_sub_accounts"] = len(sub_accounts)
            self.master_registry["discovery_metadata"].update({
                "last_ghl_agency_sync": datetime.now().isoformat(),
                "locations_discovered_count": len(ghl_locations),
                "new_accounts_found_last_sync": stats["new_providers"]
            })

            self._save_master_registry()

            # Update sync metadata
            try:
                sync_duration = (datetime.now() - start_time).total_seconds() * 1000
                self._update_sync_metadata(sync_duration, True)
            except Exception as e:
                print(f"⚠️ Error updating sync metadata: {e}")

            return stats

    def _update_sync_metadata(self, duration_ms, success):
        """Update sync performance and status metadata"""
        try:
            if not self.sync_metadata_file.exists():
                self._initialize_sync_metadata()

            with open(self.sync_metadata_file, 'r') as f:
                sync_metadata = json.load(f)

            # Update sync history
            sync_metadata["sync_history"]["last_sync_attempt"] = datetime.now().isoformat()
            if success:
                sync_metadata["sync_history"]["last_successful_sync"] = datetime.now().isoformat()
                sync_metadata["sync_history"]["consecutive_successful_syncs"] += 1
                sync_metadata["sync_history"]["consecutive_failed_syncs"] = 0
            else:
                sync_metadata["sync_history"]["consecutive_failed_syncs"] += 1

            sync_metadata["sync_history"]["total_syncs_performed"] += 1

            # Update performance metrics
            sync_metadata["performance_metrics"]["last_sync_duration_ms"] = duration_ms
            total_syncs = sync_metadata["sync_history"]["total_syncs_performed"]
            current_avg = sync_metadata["performance_metrics"].get("average_sync_duration_ms", 0)
            sync_metadata["performance_metrics"]["average_sync_duration_ms"] = \
                ((current_avg * (total_syncs - 1)) + duration_ms) / total_syncs

            # Save updated metadata
            with open(self.sync_metadata_file, 'w') as f:
                json.dump(sync_metadata, f, indent=2, default=str)

        except Exception as e:
            print(f"⚠️ Error updating sync metadata: {e}")

    def get_cache_stats(self):
        """
        Get comprehensive statistics about the cache

        BACKWARD COMPATIBLE: Same return format
        NEW BEHAVIOR: Aggregates stats across all isolated provider files
        """
        with self.lock:
            # Get stats from master registry
            sub_accounts = self.master_registry.get("sub_accounts", {})

            total_providers = len([sa for sa in sub_accounts.values() if sa.get("account_type") == "sub_account"])
            total_submissions = sum(sa.get("form_submissions", 0) for sa in sub_accounts.values())
            total_cases = sum(sa.get("case_count", 0) for sa in sub_accounts.values())

            stats = {
                "total_providers": total_providers,
                "total_form_submissions": total_submissions,
                "total_cases": total_cases,
                "cache_file": str(self.master_registry_file),
                "providers": []
            }

            # Build provider list from master registry
            for key, registry_info in sub_accounts.items():
                if registry_info.get("account_type") == "agency":
                    continue  # Skip agency account in provider list

                stats["providers"].append({
                    "name": registry_info.get("display_name", key),
                    "location_id": registry_info.get("location_id"),
                    "submissions": registry_info.get("form_submissions", 0),
                    "cases": registry_info.get("case_count", 0),
                    "first_seen": registry_info.get("first_seen"),
                    "last_updated": registry_info.get("last_updated")
                })

            return stats

    def get_approved_product(self, case_id):
        """
        Get approved product information for a case ID

        BACKWARD COMPATIBLE: Same method signature and return format
        NEW BEHAVIOR: Searches across isolated provider files
        """
        with self.lock:
            mapping = self.get_case_mapping(case_id)
            if mapping and "approved_product" in mapping:
                return mapping["approved_product"]
            else:
                print(f"⚠️ No approved product found for case {case_id}")
                return None

    def clear_cache(self):
        """
        Clear all cache data (use with caution)

        BACKWARD COMPATIBLE: Same behavior
        NEW BEHAVIOR: Clears hierarchical structure
        """
        with self.lock:
            try:
                # Clear in-memory caches
                self.master_registry = {}
                self.sub_account_cache = {}

                # Remove all sub-account files
                if self.sub_accounts_dir.exists():
                    for file_path in self.sub_accounts_dir.glob("*.json"):
                        file_path.unlink()

                # Remove master registry and sync metadata
                if self.master_registry_file.exists():
                    self.master_registry_file.unlink()
                if self.sync_metadata_file.exists():
                    self.sync_metadata_file.unlink()

                # Reinitialize
                self._initialize_empty_cache()
                print("🗑️ Provider location cache cleared")

            except Exception as e:
                print(f"❌ Error clearing cache: {e}")

    def _commit_master_registry_to_github(self):
        """Commit master registry to GitHub for Railway persistence"""
        try:
            # Check for required environment variables
            github_token = os.getenv('GITHUB_TOKEN')
            repo_owner = os.getenv('GITHUB_REPO_OWNER') 
            repo_name = os.getenv('GITHUB_REPO_NAME')
            
            if not all([github_token, repo_owner, repo_name]):
                return False
                
            file_path = 'rmbbhealth/provider_cache/master_registry.json'
            
            # GitHub API setup
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Get current file SHA (required for updates)
            current_sha = None
            try:
                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    current_file = response.json()
                    current_sha = current_file['sha']
            except Exception:
                pass  # File doesn't exist, will create new
            
            # Prepare commit data
            content_json = json.dumps(self.master_registry, indent=2, default=str)
            commit_data = {
                "message": f"Update master registry - {len(self.master_registry.get('sub_accounts', {}))} providers",
                "content": base64.b64encode(content_json.encode()).decode(),
                "branch": "main"
            }
            
            if current_sha:
                commit_data["sha"] = current_sha
            
            # Commit to GitHub
            response = requests.put(api_url, headers=headers, json=commit_data)
            
            if response.status_code in [200, 201]:
                print(f"✅ Master registry committed to GitHub")
                return True
            else:
                print(f"❌ GitHub master registry commit failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"⚠️ Error committing master registry to GitHub: {e}")
            return False

    def _commit_provider_file_to_github(self, provider_key):
        """Commit individual provider file to GitHub for Railway persistence"""
        try:
            # Check for required environment variables
            github_token = os.getenv('GITHUB_TOKEN')
            repo_owner = os.getenv('GITHUB_REPO_OWNER') 
            repo_name = os.getenv('GITHUB_REPO_NAME')
            
            if not all([github_token, repo_owner, repo_name]):
                return False
                
            # Load provider data
            sub_account_data = self._load_sub_account_data(provider_key)
            if not sub_account_data:
                return False
                
            file_path = f'rmbbhealth/provider_cache/sub_accounts/{provider_key}.json'
            
            # GitHub API setup
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Get current file SHA (required for updates)
            current_sha = None
            try:
                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    current_file = response.json()
                    current_sha = current_file['sha']
            except Exception:
                pass  # File doesn't exist, will create new
            
            # Prepare commit data
            content_json = json.dumps(sub_account_data, indent=2, default=str)
            case_count = len(sub_account_data.get("case_mappings", {}))
            commit_data = {
                "message": f"Update {provider_key} - {case_count} cases",
                "content": base64.b64encode(content_json.encode()).decode(),
                "branch": "main"
            }
            
            if current_sha:
                commit_data["sha"] = current_sha
            
            # Commit to GitHub
            response = requests.put(api_url, headers=headers, json=commit_data)
            
            if response.status_code in [200, 201]:
                print(f"✅ Provider {provider_key} committed to GitHub")
                return True
            else:
                print(f"❌ GitHub provider commit failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"⚠️ Error committing provider {provider_key} to GitHub: {e}")
            return False

    def _commit_hierarchical_cache_to_github(self):
        """Commit both master registry and all provider files to GitHub"""
        try:
            # Only commit if we're in Railway environment
            if '/app' not in str(self.cache_dir):
                return True  # Skip in development
                
            success = True
            
            # Commit master registry
            if not self._commit_master_registry_to_github():
                success = False
            
            # Commit all provider files
            for provider_key in self.master_registry.get("sub_accounts", {}):
                registry_info = self.master_registry["sub_accounts"][provider_key]
                if registry_info.get("data_file"):  # Skip agency accounts
                    if not self._commit_provider_file_to_github(provider_key):
                        success = False
            
            return success
            
        except Exception as e:
            print(f"⚠️ Error committing hierarchical cache to GitHub: {e}")
            return False


# BACKWARD COMPATIBILITY: Keep the original class name as alias
ProviderLocationCache = HierarchicalProviderCache

# Singleton instance for the application (BACKWARD COMPATIBLE)
_cache_instance = None
_cache_lock = threading.Lock()

def get_provider_cache():
    """Get the global provider cache instance (singleton) - BACKWARD COMPATIBLE"""
    global _cache_instance

    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                # Use absolute path to GitHub repository file for persistence
                default_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'provider_locations.json')
                cache_path = os.getenv('PROVIDER_CACHE_PATH', default_path)
                _cache_instance = HierarchicalProviderCache(cache_path)

    return _cache_instance
