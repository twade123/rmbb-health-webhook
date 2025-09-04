#!/usr/bin/env python3
"""
Wound Calculation Integration Module

Handles the integration between RMBB Health approval webhooks and the 
product wound coverage calculator. Extracts product and wound data from
RMBB Health case data and processes it through the wound coverage calculator.

This module acts as a bridge between the webhook handler and the calculator,
maintaining separation of concerns and modularity.
"""

import logging
import traceback
import re
from typing import Dict, Optional

# Import our modules
from product_wound_coverage_calculator import ProductWoundCoverageCalculator
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler


class WoundCalculationIntegration:
    """
    Integration layer between RMBB Health webhook data and wound coverage calculator.
    """
    
    def __init__(self):
        """Initialize the integration with calculator."""
        self.calculator = ProductWoundCoverageCalculator()
        self.workflow_handler = None  # Will be set externally
    
    def process_approved_case(self, case_data: Dict) -> Optional[Dict]:
        """
        Process an approved RMBB Health case for wound coverage calculation.
        
        Args:
            case_data (dict): Complete case data from RMBB Health webhook/API
            
        Returns:
            dict: Calculation results with GHL custom field updates, or None if not applicable
        """
        try:
            logging.info("🧮 Starting wound coverage processing for approved case")
            
            # Step 1: Extract product and wound information from case data
            product_info = self._extract_product_info(case_data)
            if not product_info:
                return None
            
            wound_info = self._extract_wound_info(case_data)
            if not wound_info:
                return None
            
            # Step 2: Map RMBB Health product to our product catalog
            mapped_product = self._map_rmbb_product(product_info['product_id'])
            if not mapped_product:
                return None
            
            # Step 3: Calculate optimal product size combination
            calculation_result = self.calculator.calculate_wound_coverage(
                product_name=mapped_product['name'],
                wound_size_cm2=wound_info['wound_size_cm2']
            )
            
            if not calculation_result.get('success'):
                logging.error(f"❌ Wound coverage calculation failed: {calculation_result.get('error')}")
                return None
            
            # Step 4: Enhance result with original case information
            enhanced_result = self._enhance_calculation_result(
                calculation_result, 
                product_info, 
                wound_info, 
                mapped_product
            )
            
            logging.info(f"✅ Wound coverage calculation completed successfully:")
            logging.info(f"   📊 {enhanced_result['calculation_summary']}")
            logging.info(f"   🔗 GHL field updates: {len(enhanced_result['ghl_field_updates'])}")
            
            return enhanced_result
            
        except Exception as e:
            logging.error(f"❌ Error processing approved case wound coverage: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def _extract_product_info(self, case_data: Dict) -> Optional[Dict]:
        """
        Extract product information from RMBB Health case data.
        
        Args:
            case_data (dict): Complete case data from RMBB Health
            
        Returns:
            dict: Product information or None if not found
        """
        # Try product_id first (webhook format)
        product_id = case_data.get('product_id')
        
        # If not found, try product.id (API format)
        if not product_id and 'product' in case_data:
            product_data = case_data.get('product')
            if isinstance(product_data, dict):
                product_id = product_data.get('id')
                logging.info(f"   🔄 Found product ID in product.id field: {product_id}")
        
        if not product_id:
            logging.warning("⚠️ No product_id found in case data (checked both 'product_id' and 'product.id')")
            # Print available fields for debugging
            available_fields = list(case_data.keys())
            logging.info(f"   📋 Available case fields: {available_fields}")
            if 'product' in case_data:
                product_fields = case_data.get('product', {})
                if isinstance(product_fields, dict):
                    logging.info(f"   🧬 Available product fields: {list(product_fields.keys())}")
                else:
                    logging.info(f"   🧬 Product field type: {type(product_fields)} = {product_fields}")
            return None
        
        product_info = {
            'product_id': product_id,
            'raw_case_data': case_data
        }
        
        logging.info(f"   🧬 Extracted product ID: {product_id}")
        return product_info
    
    def _extract_wound_info(self, case_data: Dict) -> Optional[Dict]:
        """
        Extract wound size information from GHL custom field rmbb_wound_size_coverage_calculator.
        
        Args:
            case_data (dict): Case data containing case_id for provider cache lookup
            
        Returns:
            dict: Wound information with numerical size in cm², or None if not found
        """
        # Get case_id for provider cache lookup
        case_id = case_data.get('case_id') or case_data.get('id')
        if not case_id:
            logging.warning("⚠️ No case_id provided for wound size lookup")
            return None
        
        # Get contact info from provider cache
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        case_mapping = provider_cache.get_case_mapping(str(case_id))
        
        if not case_mapping:
            logging.warning(f"⚠️ No case mapping found for case_id {case_id}")
            return None
        
        contact_id = case_mapping.get('contact_id')
        location_id = case_mapping.get('location_id')
        api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
        
        if not all([contact_id, api_key]):
            logging.warning(f"⚠️ Missing contact_id or api_key for case {case_id}")
            return None
        
        # Get wound size from GHL custom field
        import requests
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Version': '2021-07-28'
        }
        
        try:
            response = requests.get(f"https://rest.gohighlevel.com/v1/contacts/{contact_id}", headers=headers)
            if response.status_code == 200:
                contact_data_response = response.json().get('contact', {})
                custom_fields = contact_data_response.get('customField', [])
                
                # Find rmbb_wound_size_coverage_calculator field
                for field in custom_fields:
                    if field.get('id') == 'XQLSYwSOodHOBrqv8oz0':
                        field_value = field.get('value', '')
                        
                        if field_value:
                            # Parse wound size from custom field
                            import re
                            cm2_match = re.search(r'(\d+(?:\.\d+)?)\s*cm²?', field_value)
                            if cm2_match:
                                wound_size_cm2 = float(cm2_match.group(1))
                                
                                logging.info(f"   📏 Wound size from GHL custom field: {wound_size_cm2} cm²")
                                
                                return {
                                    'wound_size_cm2': wound_size_cm2,
                                    'wound_size_str': f"{wound_size_cm2} cm²",
                                    'total_wound_size_str': f"{wound_size_cm2} cm²",
                                    'wound_type': 'From GHL Custom Field'
                                }
                            else:
                                logging.warning(f"⚠️ Could not parse wound size from custom field: {field_value}")
                        break
                
                logging.warning(f"⚠️ No wound size data in custom field for contact {contact_id}")
            else:
                logging.warning(f"⚠️ Failed to fetch contact {contact_id}: {response.status_code}")
        
        except Exception as e:
            logging.error(f"❌ Error fetching wound size from custom field: {e}")
        
        return None
    
    def _parse_total_wound_size(self, total_wound_size_str: str) -> Optional[float]:
        """
        Parse numerical value from total wound size string.
        
        Args:
            total_wound_size_str (str): String like "12 cm2", "15.5 cm²"
            
        Returns:
            float: Numerical wound size in cm², or None if not parseable
        """
        if not total_wound_size_str:
            return None
        
        # Extract number from strings like "12 cm2", "15.5 cm²", etc.
        size_match = re.search(r'(\d+(?:\.\d+)?)', total_wound_size_str)
        if size_match:
            wound_size = float(size_match.group(1))
            logging.info(f"      📊 Parsed from total_wound_size: {wound_size} cm²")
            return wound_size
        
        return None
    
    def _calculate_from_dimensions(self, wound_size_str: str) -> Optional[float]:
        """
        Calculate wound size from dimension string.
        
        Args:
            wound_size_str (str): String like "3x4 cm", "2.5x3.5 cm"
            
        Returns:
            float: Calculated wound size in cm², or None if not parseable
        """
        if not wound_size_str:
            return None
        
        # Parse dimensions from strings like "3x4 cm", "2.5x3.5 cm"
        dimension_match = re.search(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)', wound_size_str)
        if dimension_match:
            width = float(dimension_match.group(1))
            height = float(dimension_match.group(2))
            wound_size = width * height
            logging.info(f"      🧮 Calculated from dimensions: {width}x{height} = {wound_size} cm²")
            return wound_size
        
        return None
    
    def _map_rmbb_product(self, product_id: int) -> Optional[Dict]:
        """
        Map RMBB Health product ID to our product catalog.
        
        Args:
            product_id (int): RMBB Health product ID
            
        Returns:
            dict: Product information with name, q_code, etc., or None if not found
        """
        try:
            # Product mapping from ghl_rmbb_workflow.py
            products = {
                "amniomaxx_q4239": {"name": "AmnioMaxx", "q_code": "Q4239", "dev_id": 364, "prod_id": 229, "ghl_field_id": "tOGJkZFd2ymaHGKYrVU2"},
                "palingen_q4173": {"name": "Palingen", "q_code": "Q4173", "dev_id": 373, "prod_id": 341, "ghl_field_id": "gN96ValY4BEEzUFBD6Z0"},
                "membrane_wrap_trilayer_q4205": {"name": "Membrane Wrap", "q_code": "Q4205", "dev_id": 361, "prod_id": 98, "ghl_field_id": "1hvUvoGbO7rMLSgEFoDz"},
                "amnioamp_mp_q4250": {"name": "AmnioAmp-MP", "q_code": "Q4250", "dev_id": 365, "prod_id": 230, "ghl_field_id": "f2ahSKCm3LRuN0djazBg"},
                "membrane_wrap_hydro_q4290": {"name": "Membrane Wrap H", "q_code": "Q4290", "dev_id": 362, "prod_id": 99, "ghl_field_id": "TIjFjavn2llFCwGizWj2"},
                "biovance_q4154": {"name": "Biovance", "q_code": "Q4154", "dev_id": 367, "prod_id": 232, "ghl_field_id": "nS8MzgEAKuaGNjxdPGe7"},
                "amchoplast_q4316": {"name": "Amchoplast", "q_code": "Q4316", "dev_id": 375, "prod_id": 343, "ghl_field_id": "b5h4W8FSMO1E8KSleixD"},
                "helicoll_q4164": {"name": "Helicoll", "q_code": "Q4164", "dev_id": 374, "prod_id": 342, "ghl_field_id": "lqdbhafh2zTeM23u0OMe"},
                "xcell_amnio_matrix_q4280": {"name": "Xcell Amnio Matrix", "q_code": "Q4280", "dev_id": 372, "prod_id": 237, "ghl_field_id": "49vxcOnMCVYPyDdDuH80"}
            }
            
            # Search for matching product by development or production ID
            for product_key, product_info in products.items():
                if product_info['dev_id'] == product_id or product_info['prod_id'] == product_id:
                    environment = 'development' if product_info['dev_id'] == product_id else 'production'
                    logging.info(f"   ✅ Mapped RMBB ID {product_id} ({environment}) to: {product_info['name']} ({product_info['q_code']})")
                    return product_info
            
            logging.warning(f"⚠️ Could not find product mapping for RMBB product ID: {product_id}")
            # Print available product IDs for debugging
            dev_ids = [p['dev_id'] for p in products.values()]
            prod_ids = [p['prod_id'] for p in products.values()]
            logging.info(f"   📋 Available development IDs: {dev_ids}")
            logging.info(f"   📋 Available production IDs: {prod_ids}")
            return None
            
        except Exception as e:
            logging.error(f"❌ Error mapping RMBB product ID {product_id}: {str(e)}")
            return None
    
    def _enhance_calculation_result(self, calculation_result: Dict, product_info: Dict, 
                                  wound_info: Dict, mapped_product: Dict) -> Dict:
        """
        Enhance calculation result with original case information.
        
        Args:
            calculation_result (dict): Result from wound coverage calculator
            product_info (dict): Original product information from case
            wound_info (dict): Original wound information from case
            mapped_product (dict): Mapped product information
            
        Returns:
            dict: Enhanced calculation result
        """
        # Add original case context to the calculation result
        enhanced_result = calculation_result.copy()
        enhanced_result.update({
            'original_case_data': {
                'rmbb_product_id': product_info['product_id'],
                'wound_size_str': wound_info['wound_size_str'],
                'total_wound_size_str': wound_info['total_wound_size_str'],
                'wound_type': wound_info['wound_type']
            },
            'mapped_product': {
                'rmbb_product_id': product_info['product_id'],
                'name': mapped_product['name'],
                'q_code': mapped_product['q_code'],
                'ghl_field_id': mapped_product.get('ghl_field_id', '')
            }
        })
        
        return enhanced_result


def process_webhook_case_data(case_data: Dict) -> Optional[Dict]:
    """
    Convenience function for processing case data from webhook handler.
    
    Args:
        case_data (dict): Complete case data from RMBB Health
        
    Returns:
        dict: Calculation results with GHL field updates, or None if not applicable
    """
    integration = WoundCalculationIntegration()
    return integration.process_approved_case(case_data)


if __name__ == "__main__":
    # Test the integration with sample case data
    sample_case_data = {
        "product_id": 229,  # Production ID for AmnioMaxx
        "wound_size": "4x5 cm",
        "total_wound_size": "20 cm2",
        "wound_type": "Diabetic Ulcer"
    }
    
    logging.basicConfig(level=logging.INFO)
    result = process_webhook_case_data(sample_case_data)
    
    if result:
        print("✅ Test successful!")
        print(f"📊 Calculation: {result['calculation_summary']}")
        print(f"🔗 GHL Updates: {len(result['ghl_field_updates'])} fields")
    else:
        print("❌ Test failed!")