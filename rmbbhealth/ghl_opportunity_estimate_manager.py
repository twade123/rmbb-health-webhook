#!/usr/bin/env python3
"""
GHL Opportunity-Based Estimate Manager for RMBB Health

Creates estimates as GHL Opportunities for provider approval workflow:
1. wound_calculation_integration.py outputs product combinations  
2. Creates opportunity with product order details
3. Provider receives estimate for approval in their sub-account
4. Approved estimates convert to invoices/billing

This replaces the non-working GHL invoice API with native opportunity functionality.
"""

import os
import sys
import json
import requests
import logging
import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

# Import RMBB modules for integration
try:
    from services.provider_location_cache import get_provider_cache
    from wound_calculation_integration import WoundCalculationIntegration
    from product_pricing import ProductPricingManager
except ImportError:
    # Fallback for Railway environment
    sys.path.insert(0, os.getcwd())
    from services.provider_location_cache import get_provider_cache
    from wound_calculation_integration import WoundCalculationIntegration
    from product_pricing import ProductPricingManager


class GHLOpportunityEstimateManager:
    """
    Opportunity-based estimate system for RMBB Health provider workflow.
    Uses GHL opportunities as estimates for internal provider approval.
    """
    
    def __init__(self, api_key: str, sub_account_id: str, location_id: str = None):
        """
        Initialize the opportunity-based estimate manager.
        
        Args:
            api_key: GHL sub-account API key from Cell Products cache
            sub_account_id: GHL sub-account ID from Cell Products cache  
            location_id: GHL location ID
        """
        self.api_key = api_key
        self.sub_account_id = sub_account_id
        self.location_id = location_id
        self.base_url = "https://rest.gohighlevel.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # RMBB Health Pipeline Configuration
        self.rmbb_pipeline_config = {
            "pipeline_name": "RMBB Health Orders",
            "stages": [
                {"name": "Draft Order", "order": 1},
                {"name": "Pending Provider Approval", "order": 2}, 
                {"name": "Provider Approved", "order": 3},
                {"name": "Provider Declined", "order": 4},
                {"name": "Invoiced/Billed", "order": 5}
            ]
        }
        
        # Initialize pricing manager
        self.pricing_manager = ProductPricingManager()
        
        # Provider discount configuration
        self.provider_discount_percentage = 65  # Provider pays 65% of product cost to Cell Products
        
        # Custom field IDs for insurance and wound data
        self.insurance_field_id = "FoqW1DyrjW6WtsoPflFZ"  # rmbb_current_insurance_info
        self.wound_size_field_id = "XQLSYwSOodHOBrqv8oz0"  # rmbb_wound_size_coverage_calculator
    
    def create_wound_product_estimate(self, case_data: Dict, wound_calculation_result: Dict) -> Dict:
        """
        Create an opportunity-based estimate from wound calculation results using correct GHL V1 pipeline API.
        
        Args:
            case_data: Complete case data from RMBB webhook/API
            wound_calculation_result: Output from wound_calculation_integration.py
            
        Returns:
            Dict: Opportunity creation result with estimate details
        """
        try:
            logging.info(f"🔄 Creating wound product estimate for case {case_data.get('id')}")
            
            # Extract contact info
            contact_id = case_data.get("contact_id")
            if not contact_id:
                return {"success": False, "error": "No contact ID found for case"}
            
            # Step 1: Get or create RMBB Health pipeline
            pipeline_result = self._get_or_create_rmbb_pipeline()
            if not pipeline_result.get("success"):
                return pipeline_result
            
            pipeline_id = pipeline_result["pipeline_id"]
            draft_stage_id = pipeline_result["draft_stage_id"]
            
            # Step 2: Process wound calculation results into order items
            order_items = self._process_wound_calculation_to_order(wound_calculation_result)
            if not order_items:
                return {"success": False, "error": "No valid order items from wound calculation"}
            
            # Step 2.5: Get insurance coverage and provider discount from contact data
            insurance_coverage_pct = self.get_insurance_coverage_percentage(contact_id)
            provider_discount_pct = self.get_provider_discount_from_tags(contact_id)
            
            logging.info(f"📊 Insurance coverage: {insurance_coverage_pct}%")
            logging.info(f"🏷️ Provider discount: {provider_discount_pct}%")
            
            # Calculate financial breakdown
            total_product_cost = sum([item["total_price"] for item in order_items])
            insurance_reimbursement = total_product_cost * (insurance_coverage_pct / 100)
            cell_products_invoice = total_product_cost * (provider_discount_pct / 100)
            provider_revenue = insurance_reimbursement - cell_products_invoice
            provider_margin_pct = (provider_revenue / total_product_cost) * 100
            
            logging.info(f"💰 Financial Breakdown:")
            logging.info(f"   Total Product Cost: ${total_product_cost:.2f}")
            logging.info(f"   Insurance Reimbursement: ${insurance_reimbursement:.2f} ({insurance_coverage_pct}%)")
            logging.info(f"   Cell Products Invoice: ${cell_products_invoice:.2f} ({provider_discount_pct}%)")
            logging.info(f"   Provider Revenue: ${provider_revenue:.2f} ({provider_margin_pct:.1f}% margin)")
            
            # Use total product cost for opportunity value (what insurance sees)
            total_value = total_product_cost
            
            # Step 3: Create detailed opportunity that looks like a proper estimate/order
            # Build detailed title with product breakdown
            product_summary = ", ".join([f"{item['quantity']}x {item['product_size']}" for item in order_items])
            
            opportunity_data = {
                "title": f"ESTIMATE #{case_data.get('id')}: {product_summary} - ${total_value:.2f}",
                "contactId": contact_id,
                "stageId": draft_stage_id,
                "status": "open",
                "monetaryValue": total_value,
                "source": "wound_calculation_system",
                "companyName": f"RMBB Health - {wound_calculation_result.get('original_wound_size')}cm² wound",
                # Removed tags to prevent overwriting contact tags
            }
            
            # If we have contact details from case_data, override them for better display
            if case_data.get("patient_name"):
                opportunity_data["name"] = case_data["patient_name"]
            
            if case_data.get("patient_email"):
                opportunity_data["email"] = case_data["patient_email"]
                
            if case_data.get("patient_phone"):
                opportunity_data["phone"] = case_data["patient_phone"]
            
            logging.info(f"📝 Opportunity payload: {json.dumps(opportunity_data, indent=2)}")
            logging.info(f"🔗 Creating in pipeline {pipeline_id} at stage {draft_stage_id}")
            
            # Create opportunity via correct GHL V1 pipeline API
            response = requests.post(
                f"{self.base_url}/pipelines/{pipeline_id}/opportunities/",
                headers=self.headers,
                json=opportunity_data
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                opportunity_id = result.get("id")
                
                logging.info(f"✅ Estimate opportunity created: {opportunity_id}")
                
                # Step 4: Add detailed notes with revenue breakdown
                notes_result = self._add_detailed_notes(
                    pipeline_id, 
                    opportunity_id, 
                    case_data, 
                    order_items, 
                    wound_calculation_result,
                    {
                        "insurance_coverage_pct": insurance_coverage_pct,
                        "insurance_reimbursement": insurance_reimbursement,
                        "cell_products_invoice": cell_products_invoice,
                        "provider_revenue": provider_revenue,
                        "provider_margin_pct": provider_margin_pct,
                        "provider_discount_pct": provider_discount_pct
                    }
                )
                
                return {
                    "success": True,
                    "opportunity_id": opportunity_id,
                    "pipeline_id": pipeline_id,
                    "stage_id": draft_stage_id,
                    "estimate_total": total_value,
                    "order_items": order_items,
                    "case_id": case_data.get('id'),
                    "data": result,
                    "notes_added": notes_result.get("success", False),
                    # Add revenue calculations to response
                    "financial_breakdown": {
                        "total_product_cost": total_product_cost,
                        "insurance_coverage_pct": insurance_coverage_pct,
                        "insurance_reimbursement": insurance_reimbursement,
                        "cell_products_invoice": cell_products_invoice,
                        "provider_revenue": provider_revenue,
                        "provider_margin_pct": provider_margin_pct
                    }
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate opportunity creation failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logging.error(f"❌ Error creating wound product estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _process_wound_calculation_to_order(self, wound_calculation_result: Dict) -> List[Dict]:
        """
        Convert wound calculation results to order items with pricing.
        
        Args:
            wound_calculation_result: Results from wound_calculation_integration.py
            
        Returns:
            List of order items with pricing
        """
        try:
            order_items = []
            
            # Get the size combinations from calculation result
            product_combinations = wound_calculation_result.get("size_combination", {})
            
            # Get product name from mapped product info
            mapped_product = wound_calculation_result.get("mapped_product", {})
            product_name = mapped_product.get("name", "Unknown")
            
            for size, size_info in product_combinations.items():
                quantity = size_info.get('units', 0)
                if quantity > 0:
                    # Use pricing manager to get accurate pricing
                    unit_price = self.pricing_manager.get_product_price(product_name, size)
                    
                    # Fallback to area-based pricing if specific product price not found
                    if unit_price is None:
                        unit_price = self.pricing_manager.calculate_size_price_by_area(size)
                        logging.info(f"   📐 Using area-based pricing for {product_name} {size}: ${unit_price:.2f}")
                    else:
                        logging.info(f"   💰 Using product pricing for {product_name} {size}: ${unit_price:.2f}")
                    
                    total_price = unit_price * quantity
                    
                    order_item = {
                        "product_name": product_name,
                        "product_size": size,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_price": total_price,
                        "description": f"{product_name} {size} cm² wound graft - {quantity} units"
                    }
                    order_items.append(order_item)
            
            return order_items
            
        except Exception as e:
            logging.error(f"❌ Error processing wound calculation to order: {str(e)}")
            return []
    
    def _get_or_create_rmbb_pipeline(self) -> Dict:
        """
        Get existing RMBB Health pipeline or create it if it doesn't exist.
        
        Returns:
            Dict: Pipeline details with stage IDs
        """
        try:
            logging.info("🔍 Getting RMBB Health pipeline...")
            
            # First, get all existing pipelines
            response = requests.get(
                f"{self.base_url}/pipelines/",
                headers=self.headers
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get pipelines: {response.status_code} {response.text}"
                }
            
            pipelines_data = response.json()
            pipelines = pipelines_data.get("pipelines", [])
            
            # Look for existing RMBB Health pipeline or use IVR Processing pipeline
            rmbb_pipeline = None
            ivr_pipeline = None
            
            for pipeline in pipelines:
                if pipeline.get("name") == "RMBB Health Orders":
                    rmbb_pipeline = pipeline
                    break
                elif pipeline.get("name") == "IVR Processing":
                    ivr_pipeline = pipeline
            
            # Use RMBB Health pipeline if exists, otherwise use IVR Processing pipeline  
            target_pipeline = rmbb_pipeline or ivr_pipeline
            
            if target_pipeline:
                # Pipeline exists, extract stage IDs
                stages = target_pipeline.get("stages", [])
                stage_map = {stage.get("name"): stage.get("id") for stage in stages}
                
                if rmbb_pipeline:
                    logging.info(f"✅ Found RMBB Health pipeline: {target_pipeline['id']}")
                    # Use dedicated RMBB stages
                    return {
                        "success": True,
                        "pipeline_id": target_pipeline["id"],
                        "draft_stage_id": stage_map.get("Draft Order"),
                        "pending_stage_id": stage_map.get("Pending Provider Approval"),
                        "approved_stage_id": stage_map.get("Provider Approved"),
                        "declined_stage_id": stage_map.get("Provider Declined"),
                        "invoiced_stage_id": stage_map.get("Invoiced/Billed"),
                        "stages": stage_map
                    }
                else:
                    logging.info(f"✅ Using IVR Processing pipeline for estimates: {target_pipeline['id']}")
                    # Map IVR stages to estimate workflow
                    return {
                        "success": True,
                        "pipeline_id": target_pipeline["id"],
                        "draft_stage_id": stage_map.get("IVR Decision - Approved"),  # Draft estimate
                        "pending_stage_id": stage_map.get("IVR - Authorization Required"),  # Pending approval
                        "approved_stage_id": stage_map.get("IVR Appeal Resolved - Approved"),  # Provider approved
                        "declined_stage_id": stage_map.get("IVR Decision - Disapproved"),  # Provider declined
                        "invoiced_stage_id": stage_map.get("IVR Appeal Resolved - Denied"),  # Temp for invoiced
                        "stages": stage_map,
                        "using_ivr_pipeline": True
                    }
            else:
                return {
                    "success": False,
                    "error": "No suitable pipeline found. Need either 'RMBB Health Orders' or 'IVR Processing' pipeline."
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting RMBB pipeline: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_provider_discount_from_tags(self, contact_id: str) -> float:
        """
        Get provider discount percentage from contact tags (60% or 65%).
        
        Args:
            contact_id: GHL contact ID
            
        Returns:
            float: Provider discount percentage (60 or 65)
        """
        try:
            # Get contact details
            response = requests.get(
                f"{self.base_url}/contacts/{contact_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                contact_data = response.json().get('contact', {})
                tags = contact_data.get('tags', [])
                
                # Look for discount percentage tags
                for tag in tags:
                    if tag in ['60%', '65%']:
                        percentage = int(tag.replace('%', ''))
                        logging.info(f"🏷️ Found provider discount tag: {percentage}%")
                        return float(percentage)
                
                logging.warning(f"⚠️ No discount percentage tag found for contact {contact_id}")
                return None
            else:
                logging.error(f"❌ Failed to get contact tags for {contact_id}: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"❌ Error getting provider discount from tags for {contact_id}: {str(e)}")
            return None
    
    def get_wound_size_from_calculator(self, contact_id: str) -> str:
        """
        Get wound size (cm²) from rmbb_wound_size_coverage_calculator custom field.
        
        Args:
            contact_id: GHL contact ID
            
        Returns:
            str: Wound size in cm² format (e.g., "23 cm²") or "N/A"
        """
        try:
            # Get contact details
            response = requests.get(
                f"{self.base_url}/contacts/{contact_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                contact_data = response.json().get('contact', {})
                custom_fields = contact_data.get('customField', [])
                
                # Find wound size coverage calculator field
                for field in custom_fields:
                    if field.get('id') == self.wound_size_field_id:
                        field_value = field.get('value', '')
                        
                        if field_value:
                            # Extract wound size using regex patterns
                            import re
                            
                            # Look for "Total: XX cm²" pattern first (most accurate)
                            total_match = re.search(r'Total:\s*(\d+)\s*cm²', field_value)
                            if total_match:
                                return f"{total_match.group(1)} cm²"
                            
                            # Fallback: Look for any "XX cm²" pattern
                            cm2_match = re.search(r'(\d+)\s*cm²', field_value)
                            if cm2_match:
                                return f"{cm2_match.group(1)} cm²"
                        
                        break
                
                logging.warning(f"⚠️ No wound size data found in rmbb_wound_size_coverage_calculator field for contact {contact_id}")
                return "N/A cm²"
            else:
                logging.error(f"❌ Failed to get contact {contact_id}: {response.status_code}")
                return "N/A cm²"
                
        except Exception as e:
            logging.error(f"❌ Error getting wound size for {contact_id}: {str(e)}")
            return "N/A cm²"
    
    def get_insurance_coverage_percentage(self, contact_id: str) -> float:
        """
        Extract insurance coverage percentage from contact's custom field.
        
        Args:
            contact_id: GHL contact ID
            
        Returns:
            float: Insurance coverage percentage (0-100)
        """
        try:
            # Get contact details
            response = requests.get(
                f"{self.base_url}/contacts/{contact_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                contact_data = response.json().get('contact', {})
                custom_fields = contact_data.get('customField', [])
                
                # Find insurance field
                for field in custom_fields:
                    if field.get('id') == self.insurance_field_id:
                        insurance_data = field.get('value', '')
                        
                        # Parse coverage percentage from insurance data
                        if 'COVERED 100%' in insurance_data:
                            return 100.0
                        elif 'COVERED' in insurance_data and '%' in insurance_data:
                            import re
                            pct_match = re.search(r'COVERED (\d+)%', insurance_data)
                            if pct_match:
                                return float(pct_match.group(1))
                        
                        # Default assumption if coverage found but no percentage specified
                        if 'COVERED' in insurance_data:
                            return 80.0  # Conservative default
                        
                        break
                
                logging.warning(f"⚠️ No insurance coverage data found for contact {contact_id}")
                return 80.0  # Default assumption
            else:
                logging.error(f"❌ Failed to get contact {contact_id}: {response.status_code}")
                return 80.0  # Default assumption
                
        except Exception as e:
            logging.error(f"❌ Error getting insurance coverage for {contact_id}: {str(e)}")
            return 80.0  # Default assumption
    
    def _add_detailed_notes(self, pipeline_id: str, opportunity_id: str, case_data: Dict, order_items: List[Dict], wound_calc: Dict, financial_data: Dict = None) -> Dict:
        """
        Add detailed order breakdown notes to the contact using the proper contact notes API.
        
        Returns:
            Dict: Update result
        """
        try:
            # Get contact ID from the opportunity first
            contact_id = case_data.get("contact_id")
            if not contact_id:
                logging.warning("⚠️ No contact_id found in case_data - cannot add notes")
                return {"success": False, "error": "No contact_id found"}
            
            # Build the detailed notes content with financial breakdown
            notes_body = self._build_order_details_notes(contact_id, case_data, order_items, wound_calc, financial_data)
            
            # Create note using proper contact notes API (POST /v1/contacts/{contactId}/notes/)
            notes_data = {
                "body": notes_body,
                # userId is optional - omitting it will use the API key owner as the creator
            }
            
            response = requests.post(
                f"{self.base_url}/contacts/{contact_id}/notes/",
                headers=self.headers,
                json=notes_data
            )
            
            if response.status_code in [200, 201]:
                note_result = response.json()
                logging.info(f"✅ Added detailed estimate note to contact {contact_id}")
                logging.info(f"   Note ID: {note_result.get('id')}")
                return {"success": True, "note_id": note_result.get('id')}
            else:
                logging.warning(f"⚠️ Failed to create contact note: {response.status_code} {response.text}")
                return {"success": False, "error": f"Contact notes API error {response.status_code}: {response.text}"}
                
        except Exception as e:
            logging.error(f"❌ Error adding contact notes: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _build_order_details_notes(self, contact_id: str, case_data: Dict, order_items: List[Dict], wound_calc: Dict, financial_data: Dict = None) -> str:
        """
        Build detailed notes for the opportunity with order breakdown.
        Uses proper line breaks and formatting that works in GHL notes.
        
        Returns:
            Formatted notes string for provider review
        """
        try:
            # Use actual line breaks, not escaped ones
            notes = []
            notes.append("=========================================")
            notes.append("           ESTIMATE DETAILS")
            notes.append("=========================================")
            notes.append("")
            
            # Estimate header
            estimate_date = datetime.now().strftime("%B %d, %Y")
            notes.append(f"Estimate Date: {estimate_date}")
            notes.append(f"Case ID: #{case_data.get('id')}")
            wound_size = wound_calc.get('wound_size_cm2', 'N/A')
            notes.append(f"Wound Size: {wound_size} cm²")
            notes.append("")
            
            # Line items section - simplified formatting for better readability
            notes.append("LINE ITEMS:")
            notes.append("-" * 40)
            
            total_cost = 0
            for item in order_items:
                product_name = item.get('product_name', 'Product')
                size = item['product_size']
                desc = f"{product_name} {size} cm² Graft"
                qty = item['quantity']
                price = item['unit_price']
                total = item['total_price']
                
                notes.append(f"{desc}")
                notes.append(f"  Quantity: {qty} units")
                notes.append(f"  Unit Price: ${price:,.2f}")
                notes.append(f"  Total: ${total:,.2f}")
                notes.append("")
                total_cost += total
            
            notes.append("-" * 40)
            notes.append(f"TOTAL PRODUCT COST: ${total_cost:,.2f}")
            notes.append("")
            
            # Add financial breakdown if available
            if financial_data:
                notes.append("=========================================")
                notes.append("         REVENUE BREAKDOWN")
                notes.append("=========================================")
                notes.append("")
                
                insurance_coverage = financial_data.get("insurance_coverage_pct", 0)
                insurance_reimbursement = financial_data.get("insurance_reimbursement", 0)
                cell_products_invoice = financial_data.get("cell_products_invoice", 0)
                provider_revenue = financial_data.get("provider_revenue", 0)
                provider_margin = financial_data.get("provider_margin_pct", 0)
                provider_discount = financial_data.get("provider_discount_pct", 65)
                
                notes.append(f"Insurance Coverage: {insurance_coverage:.1f}%")
                notes.append(f"Insurance Reimbursement: ${insurance_reimbursement:,.2f}")
                notes.append("")
                notes.append(f"Cell Products Invoice ({provider_discount:.0f}%): ${cell_products_invoice:,.2f}")
                notes.append(f"Provider Revenue: ${provider_revenue:,.2f}")
                notes.append(f"Provider Profit Margin: {provider_margin:.1f}%")
                notes.append("")
                
                if provider_margin > 30:
                    pass  # Remove the excellent margin text
                elif provider_margin > 15:
                    pass  # Remove the good margin text
                else:
                    notes.append("🔴 LOW MARGIN - Review coverage/pricing")
                notes.append("")
            
            # Technical details
            if wound_calc.get("calculation_summary"):
                notes.append("TECHNICAL CALCULATION:")
                notes.append(f"• {wound_calc['calculation_summary']}")
                notes.append("")
            
            # Provider instructions
            notes.append("PROVIDER ACTION REQUIRED:")
            notes.append("• Review estimate details above")
            notes.append("• Approve or decline this product order")
            notes.append("• Approved orders will be processed for billing")
            notes.append("")
            notes.append("Contact Cell Products support for questions.")
            
            # Join with actual newlines, not escaped ones
            return "\n".join(notes)
            
        except Exception as e:
            logging.error(f"❌ Error building order notes: {str(e)}")
            return f"RMBB Product Order - Case #{case_data.get('id')}"
    
    def approve_estimate(self, pipeline_id: str, opportunity_id: str, approval_notes: str = None) -> Dict:
        """
        Approve an estimate opportunity (move to approved stage).
        
        Args:
            pipeline_id: GHL pipeline ID
            opportunity_id: GHL opportunity ID
            approval_notes: Optional approval notes
            
        Returns:
            Dict: Update result
        """
        try:
            logging.info(f"✅ Approving estimate opportunity {opportunity_id}")
            
            # Get pipeline stages to find approved stage ID
            pipeline_result = self._get_or_create_rmbb_pipeline()
            if not pipeline_result.get("success"):
                return pipeline_result
                
            approved_stage_id = pipeline_result["approved_stage_id"]
            if not approved_stage_id:
                return {"success": False, "error": "No 'Provider Approved' stage found in pipeline"}
            
            # Update opportunity status and stage using pipeline API
            update_data = {
                "status": "won",
                "stageId": approved_stage_id
            }
            
            # Use the status-specific endpoint
            response = requests.put(
                f"{self.base_url}/pipelines/{pipeline_id}/opportunities/{opportunity_id}/status",
                headers=self.headers,
                json=update_data
            )
            
            if response.status_code == 200:
                # Add approval notes separately
                if approval_notes:
                    notes_data = {
                        "title": f"APPROVED - Ready for Billing",
                        "notes": f"APPROVED by provider - {approval_notes}"
                    }
                    requests.put(
                        f"{self.base_url}/pipelines/{pipeline_id}/opportunities/{opportunity_id}",
                        headers=self.headers,
                        json=notes_data
                    )
                
                logging.info(f"✅ Estimate approved successfully")
                return {
                    "success": True,
                    "message": "Estimate approved - ready for invoicing",
                    "opportunity_id": opportunity_id,
                    "stage": "Provider Approved"
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate approval failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            logging.error(f"❌ Error approving estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def decline_estimate(self, pipeline_id: str, opportunity_id: str, decline_reason: str = None) -> Dict:
        """
        Decline an estimate opportunity.
        
        Args:
            pipeline_id: GHL pipeline ID
            opportunity_id: GHL opportunity ID
            decline_reason: Reason for decline
            
        Returns:
            Dict: Update result
        """
        try:
            logging.info(f"❌ Declining estimate opportunity {opportunity_id}")
            
            # Get pipeline stages to find declined stage ID
            pipeline_result = self._get_or_create_rmbb_pipeline()
            if not pipeline_result.get("success"):
                return pipeline_result
                
            declined_stage_id = pipeline_result["declined_stage_id"]
            if not declined_stage_id:
                return {"success": False, "error": "No 'Provider Declined' stage found in pipeline"}
            
            update_data = {
                "status": "lost",  # Mark as lost/declined
                "stageId": declined_stage_id
            }
            
            response = requests.put(
                f"{self.base_url}/pipelines/{pipeline_id}/opportunities/{opportunity_id}/status",
                headers=self.headers,
                json=update_data
            )
            
            if response.status_code == 200:
                # Add decline notes separately
                if decline_reason:
                    notes_data = {
                        "title": f"DECLINED - {decline_reason}",
                        "notes": f"DECLINED by provider - {decline_reason}"
                    }
                    requests.put(
                        f"{self.base_url}/pipelines/{pipeline_id}/opportunities/{opportunity_id}",
                        headers=self.headers,
                        json=notes_data
                    )
                
                logging.info(f"✅ Estimate declined successfully")
                return {
                    "success": True,
                    "message": "Estimate declined",
                    "opportunity_id": opportunity_id,
                    "stage": "Provider Declined"
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Estimate decline failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            logging.error(f"❌ Error declining estimate: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_estimate_details(self, opportunity_id: str) -> Dict:
        """
        Get detailed estimate information.
        
        Args:
            opportunity_id: GHL opportunity ID
            
        Returns:
            Dict: Estimate details
        """
        try:
            response = requests.get(
                f"{self.base_url}/opportunities/{opportunity_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                opportunity_data = response.json()
                return {
                    "success": True,
                    "estimate": opportunity_data
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
    
    def list_pending_estimates(self, contact_id: str = None) -> Dict:
        """
        List pending estimates (open opportunities) from RMBB Health pipeline.
        
        Args:
            contact_id: Filter by specific contact
            
        Returns:
            Dict: List of pending estimates
        """
        try:
            # Get RMBB Health pipeline
            pipeline_result = self._get_or_create_rmbb_pipeline()
            if not pipeline_result.get("success"):
                return pipeline_result
            
            pipeline_id = pipeline_result["pipeline_id"]
            
            # Get opportunities from RMBB pipeline
            params = {
                "status": "open",
                "limit": 50
            }
            
            response = requests.get(
                f"{self.base_url}/pipelines/{pipeline_id}/opportunities",
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                opportunities_data = response.json()
                opportunities = opportunities_data.get("opportunities", [])
                
                # Filter by contact if specified
                if contact_id:
                    opportunities = [opp for opp in opportunities if opp.get("contact", {}).get("id") == contact_id]
                
                return {
                    "success": True,
                    "estimates": opportunities,
                    "total": len(opportunities),
                    "pipeline_id": pipeline_id
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

def create_rmbb_opportunity_manager(location_id: str = None) -> GHLOpportunityEstimateManager:
    """
    Create opportunity manager instance with Cell Products sub-account credentials.
    
    Args:
        location_id: Specific location ID, or will use Cell Products cache
        
    Returns:
        GHLOpportunityEstimateManager: Configured instance
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
        
        logging.info(f"🔑 Creating opportunity manager with Cell Products sub-account {sub_account_id}")
        logging.info(f"📍 Using location ID: {final_location_id}")
        
        return GHLOpportunityEstimateManager(api_key, sub_account_id, final_location_id)
        
    except Exception as e:
        logging.error(f"❌ Error creating opportunity manager: {str(e)}")
        raise


# ========================================
# TESTING FUNCTIONS
# ========================================

def test_wound_product_estimate():
    """Test creating an estimate from wound calculation results."""
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Create manager instance
        manager = create_rmbb_opportunity_manager()
        
        # Mock case data (similar to real RMBB webhook data)
        test_case_data = {
            "id": "53330",  # Real case ID from our testing
            "contact_id": "9ycwwscO60MGHiTTBDzo",  # Our test contact
            "product_id": 230,  # AmnioAmp-MP production ID
            "wound_size": "4x5 cm",
            "total_wound_size": "20 cm2",
            "wound_type": "Diabetic Ulcer",
            "status": "approved"
        }
        
        # Use actual wound calculation integration to get real product mapping
        from wound_calculation_integration import WoundCalculationIntegration
        integration = WoundCalculationIntegration()
        
        # Process the case data through the real wound calculation system
        test_wound_calc = integration.process_approved_case(test_case_data)
        
        if not test_wound_calc:
            print("❌ Could not process case data through wound calculation integration")
            return {"success": False, "error": "Wound calculation failed"}
        
        # Create the estimate opportunity
        result = manager.create_wound_product_estimate(test_case_data, test_wound_calc)
        
        if result.get("success"):
            print("✅ Test estimate creation successful!")
            print(f"Opportunity ID: {result['opportunity_id']}")
            print(f"Estimate Total: ${result['estimate_total']:.2f}")
            print(f"Order Items: {len(result['order_items'])} products")
            print()
            print("📦 Order Breakdown:")
            for item in result['order_items']:
                print(f"  • {item['quantity']}x {item['product_size']} @ ${item['unit_price']:.2f} = ${item['total_price']:.2f}")
        else:
            print("❌ Test estimate creation failed!")
            print(f"Error: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("🧪 Testing GHL Opportunity-Based Estimate Manager")
    print("=" * 60)
    
    # Test opportunity-based estimate creation
    print("📋 Testing Wound Product Estimate Creation:")
    estimate_result = test_wound_product_estimate()
    
    if estimate_result.get("success"):
        print("\\n🎉 Opportunity-based estimate system working!")
        print("\\nNext steps:")
        print("1. Provider sees opportunity in their GHL dashboard")
        print("2. Provider can approve/decline the product order")
        print("3. Approved orders can be converted to invoices/billing")
    else:
        print("\\n⚠️ Test failed. Check the output above for details.")
