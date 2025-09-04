#!/usr/bin/env python3
"""
JSON-based document processor for RMBBHealth approval documents
Processes structured JSON data from RMBB Health API instead of OCR text extraction
"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime

class DocumentProcessor:
    """
    JSON-based document processor for structured data from RMBB Health API
    Replaces OCR functionality with direct JSON data processing
    """
    
    def __init__(self):
        # Process JSON data formats from RMBB Health API
        self.supported_formats = ['json', 'case_data', 'api_response']
    
    def process_case_json_data(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process structured JSON case data from RMBB Health API
        
        Args:
            case_data: Complete case data from RMBB Health API
            
        Returns:
            dict: {
                'success': bool,
                'extracted_data': dict,
                'case_info': dict,
                'error': str (if failed)
            }
        """
        
        try:
            logging.info(f"📄 Processing JSON case data: Case ID {case_data.get('id', 'Unknown')}")
            
            # Extract structured data directly from JSON
            extracted_data = self._extract_json_structured_data(case_data)
            
            # Build case info summary
            case_info = {
                'case_id': case_data.get('id'),
                'status': case_data.get('status'),
                'external_status': case_data.get('external_status'),
                'patient_name': self._get_patient_name(case_data),
                'data_source': 'rmbb_api_json'
            }
            
            return {
                'success': True,
                'extracted_data': extracted_data,
                'case_info': case_info
            }
            
        except Exception as e:
            logging.error(f"❌ JSON processing failed: {str(e)}")
            return {
                'success': False,
                'error': f"JSON processing error: {str(e)}"
            }
    
    def _get_patient_name(self, case_data: Dict[str, Any]) -> str:
        """Extract patient name from JSON case data"""
        try:
            patient = case_data.get('patient', {})
            personal_id = patient.get('personal_identifier', {})
            first_name = personal_id.get('first', '')
            last_name = personal_id.get('last', '')
            return f"{first_name} {last_name}".strip()
        except Exception:
            return "Unknown Patient"
    
    def _extract_json_structured_data(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured data directly from RMBB Health JSON API response
        Maps to the same 5-section structure for GHL compatibility
        """
        
        # Determine document type and approval status from JSON
        document_type = self._determine_json_document_type(case_data)
        approval_status = self._determine_json_approval_status(case_data)
        
        # Initialize 5-section structure with JSON data
        extracted_data = {
            'document_type': document_type,
            'approval_status': approval_status,
            
            # Section 1: Patient/Case Info (from JSON)
            'patient_case_info': self._extract_json_patient_case_section(case_data),
            
            # Section 2: Primary Insurance Details (from JSON)
            'primary_insurance_details': self._extract_json_primary_insurance_section(case_data),
            
            # Section 3: Secondary Insurance Details (from JSON)
            'secondary_insurance_details': self._extract_json_secondary_insurance_section(case_data),
            
            # Section 4: Coverage/Decision Summary (from JSON)
            'coverage_summary_authorization': self._extract_json_coverage_section(case_data),
            
            # Section 5: Important Notes/Status (from JSON)
            'disclaimer_notes': self._extract_json_notes_section(case_data)
        }
        
        return extracted_data
    
    def _determine_json_document_type(self, case_data: Dict[str, Any]) -> str:
        """Determine document type from JSON case data"""
        status = case_data.get('status', '').upper()
        external_status = case_data.get('external_status', '').upper()
        
        if 'COMPLETE' in status:
            return 'Final Case Results'
        elif 'PROCESSING' in status or 'PENDING' in status:
            return 'Case Processing Update'
        elif 'DENIED' in status or 'REJECTED' in status:
            return 'Denial Notice'
        else:
            return 'Case Status Update'
    
    def _determine_json_approval_status(self, case_data: Dict[str, Any]) -> str:
        """Determine approval status from JSON case data"""
        status = case_data.get('status', '').upper()
        external_status = case_data.get('external_status', '').upper()
        overall_result = case_data.get('overall_insurance_result', '').upper()
        
        # Check multiple status fields for approval/denial
        all_statuses = [status, external_status, overall_result]
        
        if any('COMPLETE' in s or 'APPROVED' in s or 'AUTHORIZED' in s for s in all_statuses):
            return 'APPROVED'
        elif any('DENIED' in s or 'REJECTED' in s for s in all_statuses):
            return 'DENIED'
        elif any('PENDING' in s or 'PROCESSING' in s for s in all_statuses):
            return 'PENDING'
        else:
            return 'UNKNOWN'

    def _extract_json_patient_case_section(self, case_data: Dict[str, Any]) -> str:
        """Extract patient/case information from JSON data"""
        try:
            patient = case_data.get('patient', {})
            personal_id = patient.get('personal_identifier', {})
            address = patient.get('address', {})
            product = case_data.get('product', {})
            
            info_lines = [
                f"Patient Name: {personal_id.get('first', '')} {personal_id.get('last', '')}",
                f"Date of Birth: {patient.get('date_of_birth', '')}",
                f"Case ID: {case_data.get('management_id', case_data.get('id', ''))}",
                f"Product: {product.get('name', '')} ({product.get('hcpcs', '')})",
                f"Address: {address.get('street', '')}, {address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}",
                f"Place of Service: {case_data.get('place_of_service', '')}",
                f"Surgery Date: {case_data.get('surgery_date', '')}",
                f"Wound Size: {case_data.get('wound_size', '')}",
                f"ICD-10 Code: {case_data.get('icd_10_code', '')}"
            ]
            
            # Filter out empty lines
            info_lines = [line for line in info_lines if not line.endswith(': ')]
            
            return '\n'.join(info_lines)
            
        except Exception as e:
            logging.error(f"Error extracting patient info: {e}")
            return 'Patient information extraction failed'

    def _extract_json_primary_insurance_section(self, case_data: Dict[str, Any]) -> str:
        """Extract primary insurance information from JSON data"""
        try:
            primary_insurance = case_data.get('primary_insurance', {})
            in_network = primary_insurance.get('in_network', {})
            out_network = primary_insurance.get('out_of_network', {})
            
            info_lines = [
                f"Primary Insurance Name: {primary_insurance.get('full_name', '')}",
                f"Policy Number: {primary_insurance.get('policy_number', '')}",
                f"Group Number: {primary_insurance.get('group_number', '')}",
                f"Status: {primary_insurance.get('status', '')}",
                f"Result: {primary_insurance.get('result', '')}",
                f"PPO: {primary_insurance.get('preferred_provider_organization', '')}",
                f"HMO: {primary_insurance.get('health_maintenance_organization', '')}",
                f"In-Network Deductible: {in_network.get('deductible', '')}",
                f"In-Network Co-pay: {in_network.get('co_pay', '')}",
                f"Out-of-Network Deductible: {out_network.get('deductible', '')}",
                f"Comments: {primary_insurance.get('comments', '')}"
            ]
            
            # Filter out empty lines
            info_lines = [line for line in info_lines if not line.endswith(': ')]
            
            return '\n'.join(info_lines) if info_lines else 'Primary insurance information not available'
            
        except Exception as e:
            logging.error(f"Error extracting primary insurance: {e}")
            return 'Primary insurance extraction failed'

    def _extract_json_secondary_insurance_section(self, case_data: Dict[str, Any]) -> str:
        """Extract secondary insurance information from JSON data"""
        try:
            secondary_insurance = case_data.get('secondary_insurance', {})
            
            # Check if secondary insurance exists
            if not secondary_insurance.get('full_name'):
                return 'Secondary insurance not provided'
            
            in_network = secondary_insurance.get('in_network', {})
            out_network = secondary_insurance.get('out_of_network', {})
            
            info_lines = [
                f"Secondary Insurance Name: {secondary_insurance.get('full_name', '')}",
                f"Policy Number: {secondary_insurance.get('policy_number', '')}",
                f"Group Number: {secondary_insurance.get('group_number', '')}",
                f"Status: {secondary_insurance.get('status', '')}",
                f"Result: {secondary_insurance.get('result', '')}",
                f"PPO: {secondary_insurance.get('preferred_provider_organization', '')}",
                f"HMO: {secondary_insurance.get('health_maintenance_organization', '')}",
                f"In-Network Deductible: {in_network.get('deductible', '')}",
                f"In-Network Co-pay: {in_network.get('co_pay', '')}",
                f"Comments: {secondary_insurance.get('comments', '')}"
            ]
            
            # Filter out empty lines
            info_lines = [line for line in info_lines if not line.endswith(': ')]
            
            return '\n'.join(info_lines) if info_lines else 'Secondary insurance information not complete'
            
        except Exception as e:
            logging.error(f"Error extracting secondary insurance: {e}")
            return 'Secondary insurance extraction failed'

    def _extract_json_coverage_section(self, case_data: Dict[str, Any]) -> str:
        """Extract coverage summary and authorization details from JSON data"""
        try:
            info_lines = [
                f"Case Status: {case_data.get('status', '')}",
                f"External Status: {case_data.get('external_status', '')}",
                f"Overall Insurance Result: {case_data.get('overall_insurance_result', '')}",
                f"Coverage Summary: {case_data.get('coverage_summary', '')}",
                f"Special Instructions: {case_data.get('special_instruction', '')}",
                f"Follow-up Date: {case_data.get('follow_up_date', '')}",
                f"Close Date: {case_data.get('close_date', '')}",
                f"Last Fax Status: {case_data.get('last_fax_status', '')}"
            ]
            
            # Add primary and secondary results
            primary_result = case_data.get('primary_insurance', {}).get('result', '')
            secondary_result = case_data.get('secondary_insurance', {}).get('result', '')
            
            if primary_result:
                info_lines.append(f"Primary Insurance Result: {primary_result}")
            if secondary_result:
                info_lines.append(f"Secondary Insurance Result: {secondary_result}")
            
            # Filter out empty lines
            info_lines = [line for line in info_lines if not line.endswith(': ')]
            
            return '\n'.join(info_lines) if info_lines else 'Coverage information not available'
            
        except Exception as e:
            logging.error(f"Error extracting coverage info: {e}")
            return 'Coverage information extraction failed'

    def _extract_json_notes_section(self, case_data: Dict[str, Any]) -> str:
        """Extract important notes and disclaimer information from JSON data"""
        try:
            notes_lines = []
            
            # Add any comments from insurance
            primary_comments = case_data.get('primary_insurance', {}).get('comments', '')
            secondary_comments = case_data.get('secondary_insurance', {}).get('comments', '')
            
            if primary_comments:
                notes_lines.append(f"Primary Insurance Notes: {primary_comments}")
            if secondary_comments:
                notes_lines.append(f"Secondary Insurance Notes: {secondary_comments}")
            
            # Add physician/provider notes
            physician = case_data.get('physician', {})
            physician_comments = physician.get('comments', '')
            if physician_comments:
                notes_lines.append(f"Provider Notes: {physician_comments}")
            
            # Add case creation and tracking info
            notes_lines.extend([
                f"Case Created: {case_data.get('creation_date', '')}",
                f"Receive Date: {case_data.get('receive_date', '')}",
                f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Source: RMBB Health API (JSON)"
            ])
            
            # Filter out empty lines
            notes_lines = [line for line in notes_lines if not line.endswith(': ')]
            
            return '\n'.join(notes_lines) if notes_lines else 'No additional notes available'
            
        except Exception as e:
            logging.error(f"Error extracting notes: {e}")
            return 'Notes extraction failed'