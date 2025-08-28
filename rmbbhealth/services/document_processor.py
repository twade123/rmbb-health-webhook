#!/usr/bin/env python3
"""
Document processor for extracting text content from RMBBHealth approval documents
Supports PDF, HTML, and DOC/DOCX files for Railway deployment
"""

import io
import logging
import requests
from typing import Optional, Dict, Any

class DocumentProcessor:
    """
    Lightweight document processor for extracting text from various file formats
    Designed for Railway deployment with minimal dependencies
    """
    
    def __init__(self):
        self.supported_extensions = ['.pdf', '.html', '.htm', '.doc', '.docx']
    
    def process_document_from_url(self, document_url: str, file_name: str) -> Dict[str, Any]:
        """
        Download and process document from RMBBHealth S3 URL
        
        Args:
            document_url: Direct S3 download URL from RMBBHealth
            file_name: Original filename to determine processing method
            
        Returns:
            dict: {
                'success': bool,
                'text_content': str,
                'extracted_data': dict,
                'file_info': dict,
                'error': str (if failed)
            }
        """
        
        try:
            logging.info(f"📄 Processing document: {file_name}")
            logging.info(f"🔗 Document URL: {document_url[:100]}...")
            
            # Download document content
            response = requests.get(document_url, timeout=30)
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f"Failed to download document: HTTP {response.status_code}"
                }
            
            document_data = response.content
            content_type = response.headers.get('content-type', '')
            
            logging.info(f"✅ Downloaded {len(document_data)} bytes, Content-Type: {content_type}")
            
            # Extract text based on file type
            text_content = self._extract_text_by_extension(document_data, file_name)
            
            if not text_content:
                return {
                    'success': False,
                    'error': f"No text content extracted from {file_name}"
                }
            
            # Extract structured data from text
            extracted_data = self._extract_structured_data(text_content, file_name)
            
            return {
                'success': True,
                'text_content': text_content,
                'extracted_data': extracted_data,
                'file_info': {
                    'name': file_name,
                    'size_bytes': len(document_data),
                    'content_type': content_type,
                    'text_length': len(text_content)
                }
            }
            
        except Exception as e:
            logging.error(f"❌ Document processing failed: {str(e)}")
            return {
                'success': False,
                'error': f"Document processing error: {str(e)}"
            }
    
    def _extract_text_by_extension(self, document_data: bytes, file_name: str) -> Optional[str]:
        """Extract text content based on file extension"""
        
        file_name_lower = file_name.lower()
        
        if file_name_lower.endswith('.pdf'):
            return self._extract_pdf_text(document_data)
        elif file_name_lower.endswith(('.html', '.htm')):
            return self._extract_html_text(document_data)
        elif file_name_lower.endswith(('.doc', '.docx')):
            return self._extract_word_text(document_data)
        else:
            logging.warning(f"⚠️ Unsupported file type: {file_name}")
            return None
    
    def _extract_pdf_text(self, pdf_data: bytes) -> str:
        """Extract text from PDF using PyPDF2"""
        try:
            import PyPDF2
            
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
            text_content = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                text_content += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            
            logging.info(f"✅ Extracted text from {len(pdf_reader.pages)} PDF pages")
            return text_content.strip()
            
        except Exception as e:
            logging.error(f"❌ PDF text extraction failed: {str(e)}")
            return None
    
    def _extract_html_text(self, html_data: bytes) -> str:
        """Extract text from HTML using BeautifulSoup"""
        try:
            from bs4 import BeautifulSoup
            
            # Decode HTML content
            html_content = html_data.decode('utf-8', errors='ignore')
            
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text_content = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text_content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text_content = ' '.join(chunk for chunk in chunks if chunk)
            
            logging.info(f"✅ Extracted {len(text_content)} characters from HTML")
            return text_content
            
        except Exception as e:
            logging.error(f"❌ HTML text extraction failed: {str(e)}")
            return None
    
    def _extract_word_text(self, doc_data: bytes) -> str:
        """Extract text from DOC/DOCX using python-docx"""
        try:
            from docx import Document
            
            doc = Document(io.BytesIO(doc_data))
            text_content = ""
            
            for paragraph in doc.paragraphs:
                text_content += paragraph.text + "\n"
            
            logging.info(f"✅ Extracted {len(text_content)} characters from Word document")
            return text_content.strip()
            
        except Exception as e:
            logging.error(f"❌ Word document text extraction failed: {str(e)}")
            return None
    
    def _extract_structured_data(self, text_content: str, file_name: str) -> Dict[str, Any]:
        """
        Extract structured data from ANY document type (approvals, denials, appeals, etc.)
        Organized into 5 main sections - adapts to document content automatically
        """
        
        # Determine document type first to guide extraction strategy
        document_type = self._determine_document_type(text_content, file_name)
        approval_status = self._determine_approval_status(text_content)
        
        # Initialize 5-section structure - adapts based on document type
        extracted_data = {
            'document_type': document_type,
            'approval_status': approval_status,
            
            # Section 1: Patient/Case Info (universal for all document types)
            'patient_case_info': self._extract_patient_case_section(text_content),
            
            # Section 2: Primary Insurance Details (universal)
            'primary_insurance_details': self._extract_primary_insurance_section(text_content),
            
            # Section 3: Secondary Insurance Details (universal)
            'secondary_insurance_details': self._extract_secondary_insurance_section(text_content),
            
            # Section 4: Coverage/Decision Summary (adapts: approval, denial, appeal info)
            'coverage_summary_authorization': self._extract_decision_summary_section(text_content, document_type),
            
            # Section 5: Important Notes/Disclaimer (universal footer content)
            'disclaimer_notes': self._extract_important_notes_section(text_content)
        }
        
        return extracted_data
    
    def _determine_document_type(self, text_content: str, file_name: str) -> str:
        """Determine the type of document based on content and filename"""
        text_upper = text_content.upper()
        file_name_upper = file_name.upper()
        
        # IVR/Verification documents
        if any(term in text_upper for term in ['INSURANCE VERIFICATION', 'IVR', 'VERIFICATION RESULTS']):
            return 'Insurance Verification'
        
        # Prior Authorization documents  
        if any(term in text_upper for term in ['PRIOR AUTH', 'AUTHORIZATION', 'PRE-AUTHORIZATION']):
            return 'Prior Authorization'
        
        # Denial documents
        if any(term in text_upper for term in ['DENIAL', 'DENIED', 'NOT COVERED', 'REJECTION', 'DECLINED']):
            return 'Denial Notice'
        
        # Appeal documents
        if any(term in text_upper for term in ['APPEAL', 'RECONSIDERATION', 'REVIEW REQUEST']):
            return 'Appeal Document'
        
        # Medical records
        if any(term in text_upper for term in ['MEDICAL RECORD', 'PATIENT CHART', 'CLINICAL NOTE']):
            return 'Medical Record'
        
        # Benefits/Coverage documents
        if any(term in text_upper for term in ['BENEFITS', 'COVERAGE', 'ELIGIBILITY']):
            return 'Benefits Information'
        
        # Filename-based detection
        if any(term in file_name_upper for term in ['IVR', 'VERIFICATION']):
            return 'Insurance Verification'
        elif any(term in file_name_upper for term in ['DENIAL', 'REJECT']):
            return 'Denial Notice'
        elif any(term in file_name_upper for term in ['APPEAL']):
            return 'Appeal Document'
        elif any(term in file_name_upper for term in ['APPROVAL', 'AUTHORIZED']):
            return 'Approval Document'
        
        # Default fallback
        return 'Healthcare Document'
        
        text_lower = text_content.lower()
        
        if 'prior authorization' in text_lower or 'pre-authorization' in text_lower:
            return 'Prior Authorization'
        elif 'approval' in text_lower or 'approved' in text_lower:
            return 'Approval Document'
        elif 'denial' in text_lower or 'denied' in text_lower:
            return 'Denial Letter'
        elif 'additional information' in text_lower or file_name.lower().startswith('additional'):
            return 'Additional Information'
        elif 'summary' in text_lower:
            return 'Summary Report'
        else:
            return 'General Document'
    
    def _extract_patient_info(self, text_content: str) -> Dict[str, str]:
        """Extract patient information using simple patterns"""
        import re
        
        patient_info = {}
        
        # Patient name patterns
        name_patterns = [
            r'patient\s*name[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'member\s*name[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                patient_info['name'] = match.group(1).strip()
                break
        
        # Date of birth patterns
        dob_patterns = [
            r'date\s*of\s*birth[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'dob[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]
        
        for pattern in dob_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                patient_info['date_of_birth'] = match.group(1).strip()
                break
        
        return patient_info
    
    def _extract_provider_info(self, text_content: str) -> Dict[str, str]:
        """Extract provider information"""
        import re
        
        provider_info = {}
        
        # Provider name patterns
        provider_patterns = [
            r'provider[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'physician[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'doctor[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]
        
        for pattern in provider_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                provider_info['name'] = match.group(1).strip()
                break
        
        return provider_info
    
    def _extract_diagnosis_info(self, text_content: str) -> Dict[str, str]:
        """Extract diagnosis codes and descriptions"""
        import re
        
        diagnosis_info = {}
        
        # ICD-10 codes
        icd10_pattern = r'([A-Z]\d{2}\.?\d*)'
        icd10_matches = re.findall(icd10_pattern, text_content)
        if icd10_matches:
            diagnosis_info['icd10_codes'] = list(set(icd10_matches))
        
        return diagnosis_info
    
    def _extract_treatment_info(self, text_content: str) -> Dict[str, str]:
        """Extract treatment and procedure information"""
        
        treatment_info = {}
        text_lower = text_content.lower()
        
        # Look for common treatments mentioned
        treatments = [
            'amniomaxx', 'palingen', 'membrane wrap', 'biovance', 
            'amchoplast', 'helicoll', 'xcell amnio matrix'
        ]
        
        found_treatments = [t for t in treatments if t in text_lower]
        if found_treatments:
            treatment_info['mentioned_treatments'] = found_treatments
        
        return treatment_info
    
    def _extract_dates(self, text_content: str) -> Dict[str, str]:
        """Extract important dates"""
        import re
        
        dates = {}
        
        # Date patterns
        date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        date_matches = re.findall(date_pattern, text_content)
        
        if date_matches:
            dates['found_dates'] = list(set(date_matches))
        
        return dates
    
    def _extract_case_info(self, text_content: str) -> Dict[str, str]:
        """Extract case numbers and authorization info"""
        import re
        
        case_info = {}
        
        # Authorization number patterns
        auth_patterns = [
            r'authorization\s*#?[:\s]*([A-Z0-9-]+)',
            r'case\s*#?[:\s]*([A-Z0-9-]+)',
            r'reference\s*#?[:\s]*([A-Z0-9-]+)',
        ]
        
        for pattern in auth_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                case_info['authorization_number'] = match.group(1).strip()
                break
        
        return case_info
    
    def _determine_approval_status(self, text_content: str) -> str:
        """Determine comprehensive approval status from any document type"""
        text_upper = text_content.upper()
        
        # APPROVED indicators (order matters - most specific first)
        approval_patterns = [
            'COVERED 100%', 'APPROVED', 'AUTHORIZED', 'VALID AND BILLABLE',
            'ELIGIBLE', 'ACCEPTED', 'COVERED', 'BENEFITS AVAILABLE'
        ]
        
        # DENIED indicators (check these FIRST - they override approvals)
        denial_patterns = [
            'NOT COVERED', 'NOT ELIGIBLE', 'NOT AUTHORIZED', 'BENEFITS NOT AVAILABLE',
            'DENIED', 'REJECTED', 'DECLINED', 'EXCLUDED'
        ]
        
        # PENDING indicators
        pending_patterns = [
            'PENDING', 'UNDER REVIEW', 'IN REVIEW', 'PROCESSING', 
            'AWAITING', 'SUBMITTED', 'RECEIVED'
        ]
        
        # Check for denial FIRST (most specific negative patterns)
        for pattern in denial_patterns:
            if pattern in text_upper:
                return 'DENIED'
        
        # Then check for approval
        for pattern in approval_patterns:
            if pattern in text_upper:
                return 'APPROVED'
                
        # Check for pending
        for pattern in pending_patterns:
            if pattern in text_upper:
                return 'PENDING'
        
        return 'UNKNOWN'
    
    def _extract_patient_case_section(self, text_content: str) -> str:
        """Extract complete patient/case info section (Green Bar 1)"""
        import re
        
        # Find the section from patient name through ICD-10 codes
        section_pattern = r'(PATIENT NAME:.*?ICD-10 DIAGNOSIS CODES:.*?)(?=PRIMARY INSURANCE|$)'
        match = re.search(section_pattern, text_content, re.IGNORECASE | re.DOTALL)
        
        if match:
            section_text = match.group(1).strip()
            
            # Clean up and format the section
            lines = [line.strip() for line in section_text.split('\n') if line.strip()]
            formatted_lines = []
            
            for line in lines:
                # Format key-value pairs nicely
                if ':' in line:
                    formatted_lines.append(line)
                else:
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
        
        # Fallback: extract individual pieces if section pattern doesn't work
        patient_case_info = []
        
        # Extract key fields individually
        field_patterns = {
            'Patient Name': r'PATIENT NAME[:\s]+([^\n\r]+)',
            'Date of Birth': r'DATE OF BIRTH[:\s]+([^\n\r]+)', 
            'Case ID': r'CASE ID[:\s]+([^\n\r]+)',
            'Date': r'(?<!OF BIRTH[:\s]{0,10})(?<!BIRTH[:\s]{0,10})DATE[:\s]+([^\n\r]+)',
            'Provider': r'PROVIDER[:\s]+([^\n\r]+)',
            'Product': r'PRODUCT[:\s]+([^\n\r]+)',
            'CPT Codes': r'CPT CODES[:\s]+([^\n\r]+)',
            'Facility': r'FACILITY[:\s]+([^\n\r]+)',
            'ICD-10 Diagnosis': r'ICD-10 DIAGNOSIS CODES[:\s]+([^\n\r]+)',
            'Place of Service': r'PLACE OF SERVICE[:\s]+([^\n\r]+)'
        }
        
        for field_name, pattern in field_patterns.items():
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                patient_case_info.append(f"{field_name}: {match.group(1).strip()}")
        
        return '\n'.join(patient_case_info) if patient_case_info else 'Patient/Case information not found'
    
    def _extract_primary_insurance_section(self, text_content: str) -> str:
        """Extract complete primary insurance section (Green Bar 2)"""
        import re
        
        # Find primary insurance section
        section_pattern = r'(PRIMARY INSURANCE NAME:.*?)(?=SECONDARY INSURANCE|COVERAGE SUMMARY|$)'
        match = re.search(section_pattern, text_content, re.IGNORECASE | re.DOTALL)
        
        if match:
            section_text = match.group(1).strip()
            
            # Clean and format the section
            lines = [line.strip() for line in section_text.split('\n') if line.strip()]
            formatted_lines = []
            
            for line in lines:
                if line and not line.isspace():
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
        
        return 'Primary insurance information not found'
    
    def _extract_secondary_insurance_section(self, text_content: str) -> str:
        """Extract complete secondary insurance section (Green Bar 3)"""
        import re
        
        # Find secondary insurance section
        section_pattern = r'(SECONDARY INSURANCE NAME:.*?)(?=COVERAGE SUMMARY|$)'
        match = re.search(section_pattern, text_content, re.IGNORECASE | re.DOTALL)
        
        if match:
            section_text = match.group(1).strip()
            
            # Clean and format the section
            lines = [line.strip() for line in section_text.split('\n') if line.strip()]
            formatted_lines = []
            
            for line in lines:
                if line and not line.isspace():
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
        
        return 'Secondary insurance information not available'
    
    def _extract_coverage_summary_section(self, text_content: str) -> str:
        """Extract complete coverage summary & authorization section (Green Bar 4)"""
        import re
        
        # Find coverage summary section
        section_pattern = r'(COVERAGE SUMMARY RESULTS.*?)(?=THIS HCPCS CODE|Documentation must support|$)'
        match = re.search(section_pattern, text_content, re.IGNORECASE | re.DOTALL)
        
        if match:
            section_text = match.group(1).strip()
            
            # Clean and format the section
            lines = [line.strip() for line in section_text.split('\n') if line.strip()]
            formatted_lines = []
            
            for line in lines:
                if line and not line.isspace():
                    formatted_lines.append(line)
            
            return '\n'.join(formatted_lines)
        
        return 'Coverage summary information not found'
    
    def _extract_disclaimer_section(self, text_content: str) -> str:
        """Extract disclaimer and important notes from bottom of document"""
        import re
        
        # Find disclaimer section - usually starts with "This authorization is not a guarantee"
        # Use more precise patterns to avoid capturing the entire document
        disclaimer_patterns = [
            r'(This authorization is not a guarantee of payment[^.]*\.)',
            r'(Documentation must support medical necessity[^.]*\.)',
            r'(HCPCS code for product[^.]*\.)',
            r'(Payment is contingent upon eligibility[^.]*\.)',
            r'(The information contained in this form[^.]*\.)',
            r'(Please call Hotline[^.]*\.)'
        ]
        
        disclaimer_parts = []
        processed_text = set()  # Track processed content to avoid duplicates
        
        for pattern in disclaimer_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                disclaimer_text = match.strip()
                if disclaimer_text and disclaimer_text not in processed_text:
                    disclaimer_parts.append(disclaimer_text)
                    processed_text.add(disclaimer_text)
        
        if disclaimer_parts:
            return '\n\n'.join(disclaimer_parts)
        
        # Fallback: look for the start of disclaimer section and take a reasonable portion
        disclaimer_start = re.search(r'(This authorization is not a guarantee.*?)PATIENT NAME:', 
                                   text_content, re.IGNORECASE | re.DOTALL)
        if disclaimer_start:
            disclaimer_text = disclaimer_start.group(1).strip()
            # Limit to first 1000 characters to avoid excessive content
            if len(disclaimer_text) > 1000:
                disclaimer_text = disclaimer_text[:1000] + '...'
            return disclaimer_text
        
        return 'Disclaimer information not found'
    
    def _extract_decision_summary_section(self, text_content: str, document_type: str) -> str:
        """Extract decision/coverage summary section - adapts based on document type"""
        
        # For IVR/Authorization documents, use the existing coverage summary method
        if document_type in ['Insurance Verification', 'Prior Authorization']:
            return self._extract_coverage_summary_section(text_content)
        
        # For denial documents, look for denial reasons and explanations
        if document_type == 'Denial Notice':
            return self._extract_denial_reasons_section(text_content)
        
        # For appeal documents, look for appeal status and decisions
        if document_type == 'Appeal Document':
            return self._extract_appeal_status_section(text_content)
        
        # Generic fallback - look for decision-related content
        return self._extract_generic_decision_section(text_content)
    
    def _extract_important_notes_section(self, text_content: str) -> str:
        """Extract important notes/disclaimer section - universal for all document types"""
        
        # Try the existing disclaimer extraction first (works well for IVR documents)
        existing_disclaimer = self._extract_disclaimer_section(text_content)
        if existing_disclaimer != 'Disclaimer information not found':
            return existing_disclaimer
        
        # Generic important notes extraction for other document types
        import re
        
        # Look for common important notes patterns
        notes_patterns = [
            r'(IMPORTANT[^.]*\.)',
            r'(NOTE[^.]*\.)',
            r'(PLEASE[^.]*\.)',
            r'(CONTACT[^.]*\.)',
            r'(For questions[^.]*\.)',
            r'(This letter[^.]*\.)',
            r'(This document[^.]*\.)'
        ]
        
        notes_parts = []
        processed_text = set()
        
        for pattern in notes_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE | re.DOTALL)
            for match in matches[:3]:  # Limit to first 3 matches per pattern
                notes_text = match.strip()
                if notes_text and len(notes_text) > 10 and notes_text not in processed_text:
                    notes_parts.append(notes_text)
                    processed_text.add(notes_text)
        
        if notes_parts:
            return '\n\n'.join(notes_parts)
        
        # Final fallback - extract last paragraph or section
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        if lines and len(lines) > 5:
            # Take last few lines as important notes
            last_section = '\n'.join(lines[-3:])
            return last_section
        
        return 'No additional notes found'
    
    def _extract_denial_reasons_section(self, text_content: str) -> str:
        """Extract denial reasons and explanations"""
        import re
        
        # Look for denial-specific content
        denial_patterns = [
            r'(DENIAL REASON[^.]*\.)',
            r'(NOT COVERED[^.]*\.)', 
            r'(REJECTED[^.]*\.)',
            r'(BENEFITS NOT AVAILABLE[^.]*\.)',
            r'(CRITERIA NOT MET[^.]*\.)'
        ]
        
        denial_parts = []
        for pattern in denial_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE | re.DOTALL)
            denial_parts.extend(matches[:2])  # Limit matches per pattern
        
        if denial_parts:
            return '\n\n'.join(denial_parts)
        
        return 'Denial details not found in structured format'
    
    def _extract_appeal_status_section(self, text_content: str) -> str:
        """Extract appeal status and decisions"""
        import re
        
        appeal_patterns = [
            r'(APPEAL STATUS[^.]*\.)',
            r'(REVIEW DECISION[^.]*\.)',
            r'(RECONSIDERATION[^.]*\.)',
            r'(APPEAL APPROVED[^.]*\.)',
            r'(APPEAL DENIED[^.]*\.)'
        ]
        
        appeal_parts = []
        for pattern in appeal_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE | re.DOTALL)
            appeal_parts.extend(matches[:2])
        
        if appeal_parts:
            return '\n\n'.join(appeal_parts)
        
        return 'Appeal information not found in structured format'
    
    def _extract_generic_decision_section(self, text_content: str) -> str:
        """Generic decision/summary extraction for unknown document types"""
        import re
        
        # Look for decision-related keywords and extract surrounding context
        decision_keywords = ['DECISION', 'DETERMINATION', 'RESULT', 'OUTCOME', 'STATUS']
        
        for keyword in decision_keywords:
            pattern = f'({keyword}[^.]*\\.)'
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            if matches:
                return '\n\n'.join(matches[:3])  # Return first 3 matches
        
        # Fallback to middle section of document (likely contains key decisions)
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        if len(lines) > 10:
            middle_start = len(lines) // 3
            middle_end = (len(lines) * 2) // 3
            middle_section = '\n'.join(lines[middle_start:middle_end])
            return middle_section[:500] + ('...' if len(middle_section) > 500 else '')
        
        return 'Decision information extracted from document body'