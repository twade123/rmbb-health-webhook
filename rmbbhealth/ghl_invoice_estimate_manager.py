#!/usr/bin/env python3
"""
GHL Invoice and Estimate Manager - V1 API Integration

Handles invoice and estimate creation for RMBB Health using GoHighLevel V1 API.
Supports both predefined GHL products and custom invoice items.

Key Features:
- Create professional invoices and estimates
- Use existing GHL products or custom line items  
- Convert estimates to invoices
- Handle recurring billing
- Multi-location support
- Payment tracking integration
"""

import os
import sys
import json
import requests
import logging
import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from decimal import Decimal

# Import RMBB modules for integration
try:
    from services.provider_location_cache import get_provider_cache
except ImportError:
    # Fallback for Railway environment
    sys.path.insert(0, os.getcwd())
    from services.provider_location_cache import get_provider_cache


class GHLInvoiceEstimateManager:
    """
    Comprehensive invoice and estimate management for GHL V1 API.
    Handles both predefined products and custom invoice items.
    """
    
    def __init__(self, api_key: str, sub_account_id: str, location_id: str = None):
        """
        Initialize the invoice/estimate manager for RMBB Health.
        
        Args:
            api_key: GHL sub-account API key from Cell Products cache
            sub_account_id: GHL sub-account ID from Cell Products cache
            location_id: GHL location ID (optional, can be per-request)
        """
        self.api_key = api_key
        self.sub_account_id = sub_account_id
        self.location_id = location_id
        # Use standard GHL V1 API URL (not sub-account format for invoices)
        # The JWT token already contains the sub-account context
        self.base_url = "https://rest.gohighlevel.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # RMBB Health Service Templates
        self.rmbb_service_templates = {
            "wound_assessment": {
                "name": "Wound Care Assessment & Documentation",
                "description": "Initial wound assessment with photography and documentation",
                "price": 150.00,
                "unit": "each"
            },
            "treatment_plan": {
                "name": "Treatment Plan Development",
                "description": "Customized wound care treatment plan with product recommendations",
                "price": 200.00,
                "unit": "each"
            },
            "product_consultation": {
                "name": "Product Selection Consultation",
                "description": "Expert consultation for optimal wound care product selection",
                "price": 100.00,
                "unit": "each"
            },
            "follow_up_assessment": {
                "name": "Follow-up Assessment (10-week)",
                "description": "Wound healing progress assessment and treatment adjustment",
                "price": 125.00,
                "unit": "each"
            },
            "reorder_consultation": {
                "name": "Product Reorder Consultation",
                "description": "Assessment for reduced product quantities for healing wounds",
                "price": 75.00,
                "unit": "each"
            }
        }
    
    # ========================================
    # INVOICE MANAGEMENT
    # ========================================
    
    def create_invoice(self, contact_id: str, invoice_data: Dict, location_id: str = None) -> Dict:
        """
        Create a new invoice in GHL.
        
        Args:
            contact_id: GHL contact ID
            invoice_data: Invoice details and line items
            location_id: Override location ID if needed
            
        Returns:
            Dict: API response with invoice details
        """
        try:
            loc_id = location_id or self.location_id
            logging.info(f"📄 Creating invoice for contact {contact_id}")
            
            # Prepare invoice payload for GHL V1 API (match GHL MCP format exactly)
            payload = {
                "contactId": contact_id,
                "altId": loc_id,  # Use altId instead of locationId
                "altType": "location",  # Required field
                "title": invoice_data.get("title", "RMBB Health Services Invoice"),
                "currency": invoice_data.get("currency", "USD"),
                "issueDate": invoice_data.get("issue_date", datetime.now().isoformat()),
                "dueDate": invoice_data.get("due_date", (datetime.now() + timedelta(days=30)).isoformat()),
                "status": invoice_data.get("status", "draft"),  # draft, sent, paid, void
                "items": []
            }
            
            # Add line items (supports both custom items and GHL products)
            for item in invoice_data.get("items", []):
                invoice_item = {
                    "name": item.get("name"),
                    "description": item.get("description", ""),
                    "price": float(item.get("price", 0)),
                    "quantity": int(item.get("quantity", 1)),
                    "unit": item.get("unit", "each")
                }
                
                # If GHL product ID is provided, include it
                if item.get("product_id"):
                    invoice_item["productId"] = item.get("product_id")
                
                payload["items"].append(invoice_item)
            
            # Optional invoice settings
            if invoice_data.get("notes"):
                payload["notes"] = invoice_data["notes"]
            
            if invoice_data.get("terms"):
                payload["terms"] = invoice_data["terms"]
                
            if invoice_data.get("late_fee"):
                payload["lateFee"] = {
                    "type": invoice_data["late_fee"].get("type", "percentage"),
                    "amount": float(invoice_data["late_fee"].get("amount", 0))
                }
            
            logging.info(f"📝 Invoice payload: {json.dumps(payload, indent=2)}")
            
            # Create invoice via GHL V1 API (fixed endpoint with trailing slash)
            response = requests.post(
                f"{self.base_url}/invoices/",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logging.info(f"✅ Invoice created successfully: {result.get('id')}")
                return {
                    "success": True,
                    "invoice_id": result.get("id"),
                    "invoice_number": result.get("invoiceNumber"),
                    "total_amount": result.get("totalAmount"),
                    "status": result.get("status"),
                    "data": result
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Invoice creation failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error creating invoice: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_estimate(self, contact_id: str, estimate_data: Dict, location_id: str = None) -> Dict:
        """
        Create a new estimate/quote in GHL.
        
        Args:
            contact_id: GHL contact ID
            estimate_data: Estimate details and line items
            location_id: Override location ID if needed
            
        Returns:
            Dict: API response with estimate details
        """
        try:
            loc_id = location_id or self.location_id
            logging.info(f"📊 Creating estimate for contact {contact_id}")
            
            # Prepare estimate payload for GHL V1 API (match GHL MCP format exactly)
            payload = {
                "contactId": contact_id,
                "altId": loc_id,  # Use altId instead of locationId
                "altType": "location",  # Required field
                "title": estimate_data.get("title", "RMBB Health Services Estimate"),
                "currency": estimate_data.get("currency", "USD"),
                "issueDate": estimate_data.get("issue_date", datetime.now().isoformat()),
                "expiryDate": estimate_data.get("expiry_date", (datetime.now() + timedelta(days=30)).isoformat()),
                "status": estimate_data.get("status", "draft"),  # draft, sent, accepted, declined, invoiced
                "items": []
            }
            
            # Add line items (supports both custom items and GHL products)
            for item in estimate_data.get("items", []):
                estimate_item = {
                    "name": item.get("name"),
                    "description": item.get("description", ""),
                    "price": float(item.get("price", 0)),
                    "quantity": int(item.get("quantity", 1)),
                    "unit": item.get("unit", "each")
                }
                
                # If GHL product ID is provided, include it
                if item.get("product_id"):
                    estimate_item["productId"] = item.get("product_id")
                
                payload["items"].append(estimate_item)
            
            # Optional estimate settings
            if estimate_data.get("notes"):
                payload["notes"] = estimate_data["notes"]
            
            if estimate_data.get("terms"):
                payload["terms"] = estimate_data["terms"]
            
            logging.info(f"📝 Estimate payload: {json.dumps(payload, indent=2)}")
            
            # Create estimate via GHL V1 API (fixed endpoint - estimates under invoices path)
            response = requests.post(
                f"{self.base_url}/invoices/estimate",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logging.info(f"✅ Estimate created successfully: {result.get('id')}")
                return {
                    "success": True,
                    "estimate_id": result.get("id"),
                    "estimate_number": result.get("estimateNumber"),
                    "total_amount": result.get("totalAmount"),
                    "status": result.get("status"),
                    "data": result
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate creation failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error creating estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def convert_estimate_to_invoice(self, estimate_id: str) -> Dict:
        """
        Convert an accepted estimate to an invoice.
        
        Args:
            estimate_id: GHL estimate ID to convert
            
        Returns:
            Dict: API response with new invoice details
        """
        try:
            logging.info(f"🔄 Converting estimate {estimate_id} to invoice")
            
            response = requests.post(
                f"{self.base_url}/estimates/{estimate_id}/convert-to-invoice",
                headers=self.headers
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logging.info(f"✅ Estimate converted to invoice: {result.get('invoiceId')}")
                return {
                    "success": True,
                    "invoice_id": result.get("invoiceId"),
                    "invoice_number": result.get("invoiceNumber"),
                    "data": result
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate conversion failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error converting estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_invoice(self, invoice_id: str, send_options: Dict = None) -> Dict:
        """
        Send an invoice to the customer via email.
        
        Args:
            invoice_id: GHL invoice ID to send
            send_options: Email sending options
            
        Returns:
            Dict: API response
        """
        try:
            logging.info(f"📧 Sending invoice {invoice_id}")
            
            payload = send_options or {}
            
            response = requests.post(
                f"{self.base_url}/invoices/{invoice_id}/send",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                logging.info(f"✅ Invoice sent successfully")
                return {
                    "success": True,
                    "message": "Invoice sent successfully",
                    "data": response.json()
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Invoice sending failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error sending invoice: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_estimate(self, estimate_id: str, send_options: Dict = None) -> Dict:
        """
        Send an estimate to the customer via email.
        
        Args:
            estimate_id: GHL estimate ID to send
            send_options: Email sending options
            
        Returns:
            Dict: API response
        """
        try:
            logging.info(f"📧 Sending estimate {estimate_id}")
            
            payload = send_options or {}
            
            response = requests.post(
                f"{self.base_url}/estimates/{estimate_id}/send",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                logging.info(f"✅ Estimate sent successfully")
                return {
                    "success": True,
                    "message": "Estimate sent successfully",
                    "data": response.json()
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate sending failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error sending estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ========================================
    # RMBB HEALTH SPECIFIC WORKFLOWS
    # ========================================
    
    def create_case_approval_invoice(self, case_data: Dict, services: List[str] = None) -> Dict:
        """
        Create an invoice for an approved RMBB Health case.
        
        Args:
            case_data: Complete case data from RMBB webhook
            services: List of service types to include
            
        Returns:
            Dict: Invoice creation result
        """
        try:
            logging.info(f"🏥 Creating case approval invoice for case {case_data.get('id')}")
            
            # Default services for approved cases
            default_services = ["wound_assessment", "treatment_plan"]
            service_list = services or default_services
            
            # Build invoice items from RMBB service templates
            invoice_items = []
            for service_key in service_list:
                if service_key in self.rmbb_service_templates:
                    service = self.rmbb_service_templates[service_key]
                    invoice_items.append({
                        "name": service["name"],
                        "description": service["description"],
                        "price": service["price"],
                        "quantity": 1,
                        "unit": service["unit"]
                    })
            
            # Get contact info from case data or provider cache
            contact_id = case_data.get("contact_id")
            location_id = case_data.get("location_id")
            
            if not contact_id:
                # Try to get from provider cache
                case_id = str(case_data.get("id"))
                provider_cache = get_provider_cache()
                case_mapping = provider_cache.get_case_mapping(case_id)
                if case_mapping:
                    contact_id = case_mapping.get("contact_id")
                    location_id = case_mapping.get("location_id")
            
            if not contact_id:
                return {
                    "success": False,
                    "error": "No contact ID found for case"
                }
            
            # Prepare invoice data
            invoice_data = {
                "title": f"RMBB Health Services - Case #{case_data.get('id')}",
                "items": invoice_items,
                "notes": f"Services provided for wound care case #{case_data.get('id')}",
                "terms": "Payment due within 30 days of invoice date",
                "status": "draft"  # Start as draft, can be sent manually
            }
            
            # Add case-specific details if available
            if case_data.get("wound_size"):
                invoice_data["notes"] += f"\nWound Size: {case_data['wound_size']}"
            
            if case_data.get("product", {}).get("name"):
                invoice_data["notes"] += f"\nRecommended Product: {case_data['product']['name']}"
            
            # Create the invoice
            result = self.create_invoice(contact_id, invoice_data, location_id)
            
            if result.get("success"):
                logging.info(f"✅ Case approval invoice created: {result['invoice_id']}")
            
            return result
            
        except Exception as e:
            logging.error(f"❌ Error creating case approval invoice: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_reorder_estimate(self, case_data: Dict, wound_calculation_result: Dict) -> Dict:
        """
        Create an estimate for a 10-week reorder consultation.
        
        Args:
            case_data: Reorder case data
            wound_calculation_result: Result from wound coverage calculation
            
        Returns:
            Dict: Estimate creation result
        """
        try:
            logging.info(f"🔄 Creating reorder estimate for case {case_data.get('case_id')}")
            
            # Build estimate items
            estimate_items = []
            
            # Add reorder consultation service
            consultation_service = self.rmbb_service_templates["reorder_consultation"]
            estimate_items.append({
                "name": consultation_service["name"],
                "description": consultation_service["description"],
                "price": consultation_service["price"],
                "quantity": 1,
                "unit": consultation_service["unit"]
            })
            
            # Add follow-up assessment if needed
            if case_data.get("include_followup"):
                followup_service = self.rmbb_service_templates["follow_up_assessment"]
                estimate_items.append({
                    "name": followup_service["name"],
                    "description": followup_service["description"],
                    "price": followup_service["price"],
                    "quantity": 1,
                    "unit": followup_service["unit"]
                })
            
            contact_id = case_data.get("contact_id")
            location_id = case_data.get("location_id")
            
            # Prepare estimate data
            estimate_data = {
                "title": f"RMBB Health Reorder Services - Case #{case_data.get('case_id')}",
                "items": estimate_items,
                "notes": f"10-week reorder consultation for case #{case_data.get('case_id')}",
                "terms": "Estimate valid for 30 days",
                "status": "draft"
            }
            
            # Add wound calculation details
            if wound_calculation_result.get("success"):
                calc_summary = wound_calculation_result.get("calculation_summary", "")
                estimate_data["notes"] += f"\nNew wound coverage: {calc_summary}"
                estimate_data["notes"] += f"\nOriginal wound size reduced for healing wound"
            
            # Create the estimate
            result = self.create_estimate(contact_id, estimate_data, location_id)
            
            if result.get("success"):
                logging.info(f"✅ Reorder estimate created: {result['estimate_id']}")
            
            return result
            
        except Exception as e:
            logging.error(f"❌ Error creating reorder estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ========================================
    # UTILITY METHODS
    # ========================================
    
    def list_invoices(self, filters: Dict = None) -> Dict:
        """
        List invoices with optional filtering.
        
        Args:
            filters: Filter options (status, contact_id, date_range, etc.)
            
        Returns:
            Dict: List of invoices
        """
        try:
            params = filters or {}
            
            response = requests.get(
                f"{self.base_url}/invoices/",
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "invoices": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API error {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_estimates(self, filters: Dict = None) -> Dict:
        """
        List estimates with optional filtering.
        
        Args:
            filters: Filter options (status, contact_id, date_range, etc.)
            
        Returns:
            Dict: List of estimates
        """
        try:
            params = filters or {}
            
            response = requests.get(
                f"{self.base_url}/invoices/estimate/list",
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "estimates": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API error {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_invoice(self, invoice_id: str) -> Dict:
        """
        Get detailed invoice information.
        
        Args:
            invoice_id: GHL invoice ID
            
        Returns:
            Dict: Invoice details
        """
        try:
            response = requests.get(
                f"{self.base_url}/invoices/{invoice_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "invoice": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API error {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_estimate(self, estimate_id: str) -> Dict:
        """
        Get detailed estimate information.
        
        Args:
            estimate_id: GHL estimate ID
            
        Returns:
            Dict: Estimate details
        """
        try:
            response = requests.get(
                f"{self.base_url}/estimates/{estimate_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "estimate": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API error {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# ========================================
# HELPER FUNCTIONS
# ========================================

def create_rmbb_invoice_manager(location_id: str = None) -> GHLInvoiceEstimateManager:
    """
    Create an invoice manager instance with proper API credentials from Cell Products sub-account.
    
    Args:
        location_id: Specific location ID, or will use Cell Products cache
        
    Returns:
        GHLInvoiceEstimateManager: Configured instance
    """
    try:
        # Get API credentials from Cell Products sub-account in provider cache
        provider_cache = get_provider_cache()
        
        # Always use Cell Products sub-account data for RMBB Health
        cell_products_data = provider_cache.cache.get("cell products", {})
        api_key = cell_products_data.get("sub_account_api_key")
        default_location_id = cell_products_data.get("location_id")
        
        if not api_key:
            raise ValueError("Missing Cell Products sub-account API key in provider cache")
        
        # Extract sub-account ID from JWT token
        try:
            decoded_token = jwt.decode(api_key, options={"verify_signature": False})
            sub_account_id = decoded_token.get("sub")
            if not sub_account_id:
                raise ValueError("No 'sub' field found in JWT token")
        except Exception as e:
            raise ValueError(f"Failed to decode JWT token to extract sub-account ID: {str(e)}")
        
        # Use provided location_id or default to Cell Products location
        final_location_id = location_id or default_location_id
        
        logging.info(f"🔑 Creating invoice manager with Cell Products sub-account {sub_account_id}")
        logging.info(f"📍 Using location ID: {final_location_id}")
        
        return GHLInvoiceEstimateManager(api_key, sub_account_id, final_location_id)
        
    except Exception as e:
        logging.error(f"❌ Error creating invoice manager: {str(e)}")
        raise


# ========================================
# TESTING FUNCTIONS
# ========================================

def test_invoice_creation():
    """Test invoice creation with sample data."""
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Create manager instance
        manager = create_rmbb_invoice_manager()
        
        # Test invoice data
        test_invoice = {
            "title": "RMBB Health Test Invoice",
            "items": [
                {
                    "name": "Wound Care Assessment",
                    "description": "Initial wound assessment and documentation",
                    "price": 150.00,
                    "quantity": 1
                },
                {
                    "name": "Treatment Plan",
                    "description": "Customized wound care treatment plan",
                    "price": 200.00,
                    "quantity": 1
                }
            ],
            "notes": "Test invoice for RMBB Health integration",
            "terms": "Payment due within 30 days"
        }
        
        # Use test contact ID (replace with actual contact ID)
        test_contact_id = "9ycwwscO60MGHiTTBDzo"  # From provider cache
        
        result = manager.create_invoice(test_contact_id, test_invoice)
        
        if result.get("success"):
            print("✅ Test invoice creation successful!")
            print(f"Invoice ID: {result['invoice_id']}")
            print(f"Invoice Number: {result['invoice_number']}")
            print(f"Total Amount: ${result['total_amount']}")
        else:
            print("❌ Test invoice creation failed!")
            print(f"Error: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return {"success": False, "error": str(e)}


def test_estimate_creation():
    """Test estimate creation with sample data."""
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Create manager instance
        manager = create_rmbb_invoice_manager()
        
        # Test estimate data
        test_estimate = {
            "title": "RMBB Health Test Estimate",
            "items": [
                {
                    "name": "Wound Care Consultation",
                    "description": "Initial consultation and assessment",
                    "price": 100.00,
                    "quantity": 1
                },
                {
                    "name": "Product Recommendation",
                    "description": "Expert product selection consultation",
                    "price": 75.00,
                    "quantity": 1
                }
            ],
            "notes": "Test estimate for RMBB Health integration",
            "terms": "Estimate valid for 30 days"
        }
        
        # Use test contact ID
        test_contact_id = "9ycwwscO60MGHiTTBDzo"
        
        result = manager.create_estimate(test_contact_id, test_estimate)
        
        if result.get("success"):
            print("✅ Test estimate creation successful!")
            print(f"Estimate ID: {result['estimate_id']}")
            print(f"Estimate Number: {result['estimate_number']}")
            print(f"Total Amount: ${result['total_amount']}")
        else:
            print("❌ Test estimate creation failed!")
            print(f"Error: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("🧪 Testing GHL Invoice & Estimate Manager")
    print("=" * 50)
    
    # Test invoice creation
    print("\n📄 Testing Invoice Creation:")
    invoice_result = test_invoice_creation()
    
    print("\n📊 Testing Estimate Creation:")
    estimate_result = test_estimate_creation()
    
    if invoice_result.get("success") and estimate_result.get("success"):
        print("\n🎉 All tests passed! Invoice and estimate creation working.")
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")