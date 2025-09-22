#!/usr/bin/env python3
"""
Automatic Field Mapping Service for New GHL Sub-Accounts

Automatically extracts custom field definitions from new sub-accounts and maps
the 96 critical RMBB fields to their correct field IDs.

This service is called by the provider_location_cache.py when new sub-accounts
are discovered to ensure immediate webhook compatibility.
"""

import requests
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from difflib import SequenceMatcher


class AutoFieldMapper:
    """
    Automatically maps critical RMBB fields for new GHL sub-accounts
    """

    # The 96 critical fields that must be mapped for webhook functionality
    CRITICAL_FIELDS = {
        # RMBB Workflow Fields (28 fields)
        "rmbb_workflow_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_received_date": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_webhook_processed": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_case_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_external_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_overall_result": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_primary_insurance_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_secondary_insurance_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_tertiary_insurance_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_primary_insurance_result": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_secondary_insurance_result": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_current_patient_info": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_current_insurance_info": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_current_notes": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_current_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_patient_data": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_primary_insurance": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_secondary_insurance": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_coverage_summary": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_ivr_authorization_info": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_document_history": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_case_summary": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_total_documents": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_approval_status": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_wound_size_coverage_calculator": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "RMBB Case ID": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_current_decision_summary": {"category": "workflow", "required": True, "data_type": "TEXT"},
        "rmbb_external_id": {"category": "workflow", "required": True, "data_type": "TEXT"},

        # Product Conversion Fields (9 fields)
        "AmnioMaxx (Q4239) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "AmnioAmp-MP (Q4250) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Membrane Wrap Hydro (Q4290) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Membrane Wrap (Q4205) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Biovance (Q4154) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "XCell Amnio Matrix (Q4280) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Palingen (Q4173) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Amchoplast (Q4316) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},
        "Helicoll (Q4164) Units/CM2": {"category": "conversion", "required": True, "data_type": "NUMERICAL"},

        # Individual Product Inventory Fields (59 fields)
        # AmnioMaxx Products
        "AmnioMaxx 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 2x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 3x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioMaxx 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # AmnioAmp-MP Products
        "AmnioAmp-MP 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioAmp-MP 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioAmp-MP 2x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioAmp-MP 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioAmp-MP 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "AmnioAmp-MP 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Palingen Products
        "Palingen 1x1 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Palingen 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Palingen 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Palingen 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Palingen 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Membrane Wrap Products
        "Membrane Wrap 1x1 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Membrane Wrap Q2 Products
        "Membrane Wrap Q2 1x1 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap Q2 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap Q2 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap Q2 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap Q2 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap Q2 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Membrane Wrap H Products
        "Membrane Wrap H 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap H 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap H 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap H 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Membrane Wrap H 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Xcell Amnio Matrix Products
        "Xcell Amnio Matrix 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Xcell Amnio Matrix 2x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Xcell Amnio Matrix 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Xcell Amnio Matrix 4x7 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Simplimax Products
        "Simplimax 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Simplimax 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Simplimax 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Simplimax 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Simplimax 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Derm Maxx Products
        "Derm Maxx 1x1 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Derm Maxx 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Derm Maxx 2x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Derm Maxx 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Derm Maxx 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Derm Maxx 5x10 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Dermabind-FM Products
        "Dermabind-FM 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Dermabind-FM 3x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Dermabind-FM 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Dermabind-FM 6.5x6.5 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},

        # Esano ACA Products
        "Esano ACA 2x2 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Esano ACA 2x3 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Esano ACA 4x4 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Esano ACA 4x6 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
        "Esano ACA 4x8 Units": {"category": "inventory", "required": False, "data_type": "NUMERICAL"},
    }

    def __init__(self):
        """Initialize the auto field mapper"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def extract_and_map_fields(self, location_id: str, api_key: str) -> Dict:
        """
        Main entry point: Extract all custom fields and map the 96 critical ones

        Args:
            location_id: GHL location ID
            api_key: GHL API key for the sub-account

        Returns:
            Dict with field mappings and statistics
        """
        try:
            self.logger.info(f"🔄 Starting field mapping for location {location_id}")

            # 1. Extract all custom field definitions
            field_definitions = self._get_custom_field_definitions(location_id, api_key)
            if not field_definitions:
                return self._create_error_result("Failed to retrieve custom field definitions")

            # 2. Map the critical fields
            mapping_result = self._map_critical_fields(field_definitions)

            # 3. Create final result
            result = {
                "status": "success",
                "field_mappings": mapping_result["mapped_fields"],
                "statistics": {
                    "total_fields_in_account": len(field_definitions),
                    "critical_fields_mapped": mapping_result["mapped_count"],
                    "critical_fields_missing": len(mapping_result["missing_fields"]),
                    "mapping_success_rate": round((mapping_result["mapped_count"] / len(self.CRITICAL_FIELDS)) * 100, 1),
                    "mapping_date": datetime.now().isoformat()
                },
                "missing_fields": mapping_result["missing_fields"],
                "recommendations": self._generate_recommendations(mapping_result)
            }

            self.logger.info(f"✅ Field mapping complete: {mapping_result['mapped_count']}/{len(self.CRITICAL_FIELDS)} fields mapped")
            return result

        except Exception as e:
            self.logger.error(f"❌ Field mapping failed: {e}")
            return self._create_error_result(str(e))

    def _get_custom_field_definitions(self, location_id: str, api_key: str) -> List[Dict]:
        """Get all custom field definitions from GHL API"""
        try:
            url = "https://rest.gohighlevel.com/v1/custom-fields/"
            headers = {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                field_data = response.json()
                custom_fields = field_data.get('customFields', [])
                self.logger.info(f"📋 Retrieved {len(custom_fields)} custom field definitions")
                return custom_fields
            else:
                self.logger.error(f"❌ GHL API error {response.status_code}: {response.text}")
                return []

        except Exception as e:
            self.logger.error(f"❌ Error retrieving custom fields: {e}")
            return []

    def _map_critical_fields(self, field_definitions: List[Dict]) -> Dict:
        """Map the 96 critical fields using multi-tier matching algorithm"""
        mapped_fields = {}
        missing_fields = []

        for field_name, config in self.CRITICAL_FIELDS.items():
            field_id = self._find_field_match(field_name, field_definitions, config)

            if field_id:
                mapped_fields[field_name] = field_id
            else:
                missing_fields.append({
                    "field_name": field_name,
                    "category": config["category"],
                    "required": config["required"],
                    "data_type": config["data_type"]
                })

        return {
            "mapped_fields": mapped_fields,
            "mapped_count": len(mapped_fields),
            "missing_fields": missing_fields
        }

    def _find_field_match(self, target_field: str, field_definitions: List[Dict], config: Dict) -> Optional[str]:
        """Find matching field using multi-tier algorithm"""

        # Tier 1: Exact name match
        exact_match = self._find_exact_match(target_field, field_definitions)
        if exact_match:
            return exact_match

        # Tier 2: Fuzzy name matching (for minor variations)
        fuzzy_match = self._find_fuzzy_match(target_field, field_definitions)
        if fuzzy_match:
            return fuzzy_match

        # Tier 3: Pattern matching for product fields
        if config["category"] == "inventory":
            pattern_match = self._find_product_pattern_match(target_field, field_definitions)
            if pattern_match:
                return pattern_match

        return None

    def _find_exact_match(self, target_field: str, field_definitions: List[Dict]) -> Optional[str]:
        """Find exact name match"""
        for field in field_definitions:
            if field.get('name', '').strip() == target_field.strip():
                return field.get('id')
        return None

    def _find_fuzzy_match(self, target_field: str, field_definitions: List[Dict], threshold: float = 0.9) -> Optional[str]:
        """Find fuzzy match for renamed or similar fields"""
        best_match = None
        best_ratio = 0

        for field in field_definitions:
            field_name = field.get('name', '').strip()
            ratio = SequenceMatcher(None, target_field.lower(), field_name.lower()).ratio()

            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = field.get('id')

        return best_match

    def _find_product_pattern_match(self, target_field: str, field_definitions: List[Dict]) -> Optional[str]:
        """Find product fields using pattern matching"""
        # Extract product name and size from target field
        # Example: "AmnioMaxx 2x2 Units" -> product="AmnioMaxx", size="2x2"
        parts = target_field.split()
        if len(parts) < 3 or "Units" not in target_field:
            return None

        product_name = parts[0]
        size = parts[1] if len(parts) > 1 else ""

        # Look for fields containing both product name and size
        for field in field_definitions:
            field_name = field.get('name', '').strip()
            if (product_name.lower() in field_name.lower() and
                size in field_name and
                "Units" in field_name and
                "Units/CM2" not in field_name):  # Exclude conversion fields
                return field.get('id')

        return None

    def _generate_recommendations(self, mapping_result: Dict) -> List[str]:
        """Generate recommendations based on mapping results"""
        recommendations = []

        missing_required = [f for f in mapping_result["missing_fields"] if f["required"]]
        if missing_required:
            recommendations.append(
                f"⚠️ {len(missing_required)} critical workflow fields are missing and should be created in GHL"
            )

        success_rate = mapping_result["mapped_count"] / len(self.CRITICAL_FIELDS) * 100
        if success_rate < 80:
            recommendations.append(
                "⚠️ Low mapping success rate - manual review recommended"
            )
        elif success_rate >= 95:
            recommendations.append(
                "✅ Excellent mapping success - webhook should work immediately"
            )

        return recommendations

    def _create_error_result(self, error_message: str) -> Dict:
        """Create standardized error result"""
        return {
            "status": "error",
            "error": error_message,
            "field_mappings": {},
            "statistics": {
                "total_fields_in_account": 0,
                "critical_fields_mapped": 0,
                "critical_fields_missing": len(self.CRITICAL_FIELDS),
                "mapping_success_rate": 0,
                "mapping_date": datetime.now().isoformat()
            },
            "missing_fields": [],
            "recommendations": ["❌ Field mapping failed - manual intervention required"]
        }


# Convenience function for provider cache integration
def auto_map_fields_for_new_provider(location_id: str, api_key: str) -> Dict:
    """
    Convenience function for provider cache to auto-map fields for new sub-accounts

    Args:
        location_id: GHL location ID
        api_key: GHL API key

    Returns:
        Dict with field mappings ready to add to provider JSON
    """
    mapper = AutoFieldMapper()
    return mapper.extract_and_map_fields(location_id, api_key)


if __name__ == "__main__":
    # Test with Integrated Wound Care
    test_location_id = "uyNJLBsVOLYr6PBVUeB4"
    test_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJsb2NhdGlvbl9pZCI6InV5TkpMQnNWT0xZcjZQQlZVZUI0IiwidmVyc2lvbiI6MSwiaWF0IjoxNzU3OTQyMjc0MzI1LCJzdWIiOiI3MTJEQzhBY2NGaUo5Vmt5aFJqWCJ9.o5F-84m6xDzqpdpnfWA6TwWRWsDv9NC998JyHZy5y74"

    print("🧪 Testing Auto Field Mapper...")
    result = auto_map_fields_for_new_provider(test_location_id, test_api_key)

    print(f"📊 Results:")
    print(f"   Status: {result['status']}")
    print(f"   Fields mapped: {result['statistics']['critical_fields_mapped']}/96")
    print(f"   Success rate: {result['statistics']['mapping_success_rate']}%")

    if result['missing_fields']:
        print(f"   Missing fields: {len(result['missing_fields'])}")