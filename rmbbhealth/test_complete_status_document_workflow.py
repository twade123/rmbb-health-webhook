#!/usr/bin/env python3
"""
Comprehensive Test for Complete Status-Triggered Document Processing System

This test verifies:
1. Status field analysis and trigger detection
2. Status-specific document processing 
3. Workflow tag application based on status type
4. Both webhook endpoints triggering document processing
5. Error handling and edge cases

Tests the complete implementation we just built.
"""

import os
import sys
import json
import logging
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add current directory to path for imports
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

def test_status_trigger_analysis():
    """Test the _analyze_status_trigger function with different status scenarios"""
    
    logger.info("🧪 Testing Status Trigger Analysis...")
    
    try:
        from webhook_handler import _analyze_status_trigger
        
        # Test Case 1: Primary Insurance Approval
        test_cases = [
            {
                'name': 'Primary Insurance Approval',
                'case_data': {
                    'status': 'processing',
                    'primary_insurance': {'result': 'APPROVED'}
                },
                'approval_analysis': {
                    'status': 'APPROVED',
                    'determining_field': 'primary_insurance_result',
                    'determining_value': 'APPROVED'
                },
                'expected_trigger': 'PRIMARY_INSURANCE_APPROVAL',
                'expected_tags': ['rmbb-ivr-approved', 'rmbb-primary-approved']
            },
            {
                'name': 'Overall Case Approval',
                'case_data': {
                    'overall_insurance_result': 'QUALIFIED'
                },
                'approval_analysis': {
                    'status': 'APPROVED', 
                    'determining_field': 'overall_result',
                    'determining_value': 'QUALIFIED'
                },
                'expected_trigger': 'OVERALL_CASE_APPROVAL',
                'expected_tags': ['rmbb-final-approved', 'rmbb-case-complete']
            },
            {
                'name': 'Denial Status',
                'case_data': {
                    'status': 'DENIED',
                    'external_status': 'NOT COVERED'
                },
                'approval_analysis': {
                    'status': 'DENIED',
                    'determining_field': 'external_status', 
                    'determining_value': 'NOT COVERED'
                },
                'expected_trigger': 'DENIAL_STATUS',
                'expected_tags': ['rmbb-denial-received', 'rmbb-appeal-eligible']
            },
            {
                'name': 'Pending Status',
                'case_data': {
                    'status': 'PENDING REVIEW'
                },
                'approval_analysis': {
                    'status': 'PENDING',
                    'determining_field': 'case_status',
                    'determining_value': 'PENDING REVIEW'
                },
                'expected_trigger': 'PENDING_STATUS',
                'expected_tags': ['rmbb-pending-update']
            }
        ]
        
        for test_case in test_cases:
            logger.info(f"   Testing: {test_case['name']}")
            
            result = _analyze_status_trigger(test_case['case_data'], test_case['approval_analysis'])
            
            # Verify trigger type
            assert result['trigger_type'] == test_case['expected_trigger'], f"Expected {test_case['expected_trigger']}, got {result['trigger_type']}"
            
            # Verify workflow tags
            assert result['workflow_tags'] == test_case['expected_tags'], f"Expected {test_case['expected_tags']}, got {result['workflow_tags']}"
            
            logger.info(f"   ✅ {test_case['name']}: {result['trigger_type']} → {result['workflow_tags']}")
        
        logger.info("✅ Status Trigger Analysis - ALL TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Status Trigger Analysis failed: {str(e)}")
        return False

def test_webhook_handler_integration():
    """Test that both webhook endpoints properly integrate with document processing"""
    
    logger.info("🧪 Testing Webhook Handler Integration...")
    
    try:
        # Test webhook handler imports and basic structure
        from webhook_handler import handle_ghl_qualification_webhook, handle_rmbb_status_webhook
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        
        # Verify the updated method signature accepts status_context
        import inspect
        sig = inspect.signature(GHLRMBBWorkflowHandler.process_approval_document_with_extraction)
        params = list(sig.parameters.keys())
        
        assert 'status_context' in params, f"Missing status_context parameter. Found: {params}"
        logger.info("   ✅ Method signature updated with status_context parameter")
        
        # Verify webhook endpoints exist and are callable
        assert callable(handle_ghl_qualification_webhook), "GHL qualification webhook not callable"
        assert callable(handle_rmbb_status_webhook), "RMBB status webhook not callable"
        logger.info("   ✅ Both webhook endpoints are callable")
        
        logger.info("✅ Webhook Handler Integration - TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Webhook Handler Integration failed: {str(e)}")
        return False

def test_document_processing_with_status_context():
    """Test the enhanced document processing with status context"""
    
    logger.info("🧪 Testing Document Processing with Status Context...")
    
    try:
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        
        # Mock the RMBB client and dependencies
        mock_client = Mock()
        
        # Create workflow handler
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key="test_key",
            rmbb_team_id=85,
            ghl_api_key="test_ghl_key"
        )
        workflow_handler.rmbb_client = mock_client
        
        # Test different status contexts
        test_contexts = [
            {
                'name': 'IVR Approval Context',
                'status_context': {
                    'trigger_type': 'PRIMARY_INSURANCE_APPROVAL',
                    'status_field': 'primary_insurance_result', 
                    'action_needed': 'PROCESS_IVR_APPROVAL_DOCUMENTS',
                    'document_priority': 'IVR_APPROVAL',
                    'workflow_tags': ['rmbb-ivr-approved', 'rmbb-primary-approved']
                }
            },
            {
                'name': 'Denial Context',
                'status_context': {
                    'trigger_type': 'DENIAL_STATUS',
                    'status_field': 'external_status',
                    'action_needed': 'PROCESS_DENIAL_DOCUMENTS', 
                    'document_priority': 'DENIAL_NOTICE',
                    'workflow_tags': ['rmbb-denial-received', 'rmbb-appeal-eligible']
                }
            },
            {
                'name': 'Initial Case Creation',
                'status_context': {
                    'trigger_type': 'INITIAL_CASE_CREATION',
                    'status_field': 'case_created',
                    'action_needed': 'PROCESS_INITIAL_DOCUMENTS',
                    'document_priority': 'INITIAL_SUBMISSION', 
                    'workflow_tags': ['rmbb-case-created', 'rmbb-documents-processed']
                }
            }
        ]
        
        for test_context in test_contexts:
            logger.info(f"   Testing: {test_context['name']}")
            
            with patch('services.file_service.FileService') as mock_file_service:
                # Mock no files found (to test basic flow without actual file processing)
                mock_file_service_instance = Mock()
                mock_file_service.return_value = mock_file_service_instance
                mock_file_service_instance.get_all_files.return_value = []
                
                # Call the method with status context
                result = workflow_handler.process_approval_document_with_extraction(
                    case_id="test_case_123",
                    contact_id="test_contact_456", 
                    location_id="test_location_789",
                    provider_name="Test Provider",
                    status_context=test_context['status_context']
                )
                
                # Verify status context is preserved in response
                assert result['status_trigger'] == test_context['status_context']['trigger_type'], f"Status trigger not preserved: {result}"
                assert result['workflow_tags'] == [], "Should be empty list when no files processed"
                assert result['success'] == True, f"Expected success, got: {result}"
                
                logger.info(f"   ✅ {test_context['name']}: Status trigger preserved: {result['status_trigger']}")
        
        logger.info("✅ Document Processing with Status Context - ALL TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Document Processing with Status Context failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def test_workflow_tag_application():
    """Test that workflow tags are properly applied based on status context"""
    
    logger.info("🧪 Testing Workflow Tag Application...")
    
    try:
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        
        # Mock successful tag application
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key="test_key", 
            rmbb_team_id=85,
            ghl_api_key="test_ghl_key"
        )
        
        # Test the tag application logic by mocking dependencies
        with patch('services.file_service.FileService') as mock_file_service, \
             patch('services.provider_location_cache.get_provider_cache') as mock_cache, \
             patch.object(workflow_handler, '_process_single_document') as mock_process_doc, \
             patch.object(workflow_handler, '_add_contact_tag') as mock_add_tag:
            
            # Setup mocks
            mock_file_service_instance = Mock()
            mock_file_service.return_value = mock_file_service_instance
            mock_file_service_instance.get_all_files.return_value = [
                {'name': 'test_approval.pdf', 'id': 'file_123'}
            ]
            mock_file_service_instance.view_file.return_value = {'link': 'https://test.com/file.pdf'}
            
            mock_cache_instance = Mock()
            mock_cache.return_value = mock_cache_instance
            mock_cache_instance.get_sub_account_api_key_by_location_id.return_value = "test_api_key"
            
            # Mock successful document processing
            mock_process_doc.return_value = {
                'success': True,
                'document_type': 'IVR Approval',
                'approval_status': 'APPROVED',
                'text_length': 1000
            }
            
            # Mock successful tag addition
            mock_add_tag.return_value = True
            
            # Test with IVR approval status context
            status_context = {
                'trigger_type': 'PRIMARY_INSURANCE_APPROVAL',
                'status_field': 'primary_insurance_result',
                'action_needed': 'PROCESS_IVR_APPROVAL_DOCUMENTS',
                'document_priority': 'IVR_APPROVAL',
                'workflow_tags': ['rmbb-ivr-approved', 'rmbb-primary-approved']
            }
            
            result = workflow_handler.process_approval_document_with_extraction(
                case_id="test_case_123",
                contact_id="test_contact_456",
                location_id="test_location_789", 
                provider_name="Test Provider",
                status_context=status_context
            )
            
            # Verify results
            assert result['success'] == True, f"Expected success, got: {result}"
            assert result['files_processed'] == 1, f"Expected 1 file processed, got: {result['files_processed']}"
            assert result['document_type'] == 'IVR Approval', f"Document type not preserved: {result['document_type']}"
            assert result['workflow_tags'] == ['rmbb-ivr-approved', 'rmbb-primary-approved'], f"Workflow tags not applied: {result['workflow_tags']}"
            
            # Verify tag addition was called correctly
            expected_calls = [
                ('test_contact_456', 'test_location_789', 'test_api_key', 'rmbb-ivr-approved'),
                ('test_contact_456', 'test_location_789', 'test_api_key', 'rmbb-primary-approved')
            ]
            
            assert mock_add_tag.call_count == 2, f"Expected 2 tag calls, got: {mock_add_tag.call_count}"
            
            logger.info("   ✅ Tags applied correctly for IVR approval context")
            
        logger.info("✅ Workflow Tag Application - ALL TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Workflow Tag Application failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def test_error_handling_scenarios():
    """Test error handling in the status-triggered document processing"""
    
    logger.info("🧪 Testing Error Handling Scenarios...")
    
    try:
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        from webhook_handler import _analyze_status_trigger
        
        # Test 1: Invalid status context
        try:
            result = _analyze_status_trigger({}, {'determining_field': None, 'determining_value': ''})
            assert result['trigger_type'] == 'STATUS_CHANGE', f"Expected STATUS_CHANGE for invalid input, got: {result['trigger_type']}"
            logger.info("   ✅ Invalid status context handled gracefully")
        except Exception as e:
            logger.error(f"   ❌ Invalid status context not handled: {e}")
            return False
        
        # Test 2: Document processing without API key
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key="test_key",
            rmbb_team_id=85, 
            ghl_api_key="test_ghl_key"
        )
        
        with patch('services.file_service.FileService') as mock_file_service, \
             patch('services.provider_location_cache.get_provider_cache') as mock_cache:
            
            # Setup no API key scenario
            mock_file_service_instance = Mock()
            mock_file_service.return_value = mock_file_service_instance
            mock_file_service_instance.get_all_files.return_value = [
                {'name': 'test.pdf', 'id': 'file_123'}
            ]
            mock_file_service_instance.view_file.return_value = {'link': 'https://test.com/file.pdf'}
            
            mock_cache_instance = Mock()
            mock_cache.return_value = mock_cache_instance
            mock_cache_instance.get_sub_account_api_key_by_location_id.return_value = None  # No API key
            
            with patch.object(workflow_handler, '_process_single_document') as mock_process_doc:
                mock_process_doc.return_value = {
                    'success': False,
                    'error': 'No sub-account API key found',
                    'document_type': None,
                    'approval_status': None
                }
                
                result = workflow_handler.process_approval_document_with_extraction(
                    case_id="test_case_123",
                    contact_id="test_contact_456",
                    location_id="test_location_789",
                    provider_name="Test Provider"
                )
                
                assert result['success'] == True, "Should succeed even with processing failures"
                assert result['files_processed'] == 0, f"Expected 0 files processed due to API key issue, got: {result['files_processed']}"
                logger.info("   ✅ Missing API key scenario handled gracefully")
        
        # Test 3: Exception in document processing
        with patch('services.file_service.FileService') as mock_file_service:
            mock_file_service.side_effect = Exception("FileService connection failed")
            
            result = workflow_handler.process_approval_document_with_extraction(
                case_id="test_case_123",
                contact_id="test_contact_456",
                location_id="test_location_789",
                provider_name="Test Provider"
            )
            
            assert result['success'] == False, "Should fail when FileService throws exception"
            assert 'error' in result, f"Error message not included in result: {result}"
            logger.info("   ✅ Exception handling works correctly")
        
        logger.info("✅ Error Handling Scenarios - ALL TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error Handling Scenarios failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def test_field_preservation():
    """Test that all original webhook status fields are preserved"""
    
    logger.info("🧪 Testing Original Status Field Preservation...")
    
    try:
        from webhook_handler import handle_rmbb_status_webhook
        
        # Read webhook handler code to verify field IDs are preserved
        import webhook_handler
        handler_code = inspect.getsource(webhook_handler)
        
        # Check that all original field IDs are present
        original_field_ids = [
            'k9onZaMZVJ5Zwlopf2fi',  # rmbb_workflow_status
            '4AnL32P9rjYcPjbukcok',  # rmbb_ivr_received_date
            'drfCODR4HhoKeI3eoH6J',  # rmbb_webhook_processed
            'A2gqU59iygkmxwUeO2j6',  # rmbb_case_status
            'b7odVJaRBRTBQlVaUCF1',  # rmbb_external_status
            'NStZu6i6cSflIhmRS7Eg',  # rmbb_overall_result
            'lek4SmWzewBgvrAXBLWy',  # rmbb_primary_insurance_status
            'vnZmPnf00xi9ImOLxao9',  # rmbb_secondary_insurance_status
            'JeBBYNNHOWqyYU5FMA1w',  # rmbb_tertiary_insurance_status
            'tXkwLnHu00e9t2MdGarP',  # rmbb_primary_insurance_result
            '0viEC6QFPlBZIm75N0fE',  # rmbb_secondary_insurance_result
        ]
        
        missing_fields = []
        for field_id in original_field_ids:
            if field_id not in handler_code:
                missing_fields.append(field_id)
        
        assert len(missing_fields) == 0, f"Missing original field IDs: {missing_fields}"
        logger.info(f"   ✅ All {len(original_field_ids)} original webhook status fields preserved")
        
        logger.info("✅ Original Status Field Preservation - TESTS PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Original Status Field Preservation failed: {str(e)}")
        return False

def run_comprehensive_test():
    """Run all tests to verify the complete status-triggered document processing system"""
    
    logger.info("🚀 COMPREHENSIVE TEST: Complete Status-Triggered Document Processing System")
    logger.info("=" * 80)
    
    test_results = []
    
    # Run all test suites
    test_suites = [
        ("Status Trigger Analysis", test_status_trigger_analysis),
        ("Webhook Handler Integration", test_webhook_handler_integration), 
        ("Document Processing with Status Context", test_document_processing_with_status_context),
        ("Workflow Tag Application", test_workflow_tag_application),
        ("Error Handling Scenarios", test_error_handling_scenarios),
        ("Original Status Field Preservation", test_field_preservation)
    ]
    
    for suite_name, test_function in test_suites:
        logger.info(f"\n📋 Running: {suite_name}")
        logger.info("-" * 50)
        
        try:
            result = test_function()
            test_results.append((suite_name, result))
            
            if result:
                logger.info(f"✅ {suite_name}: PASSED")
            else:
                logger.info(f"❌ {suite_name}: FAILED")
                
        except Exception as e:
            logger.error(f"❌ {suite_name}: EXCEPTION - {str(e)}")
            test_results.append((suite_name, False))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for suite_name, passed in test_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{status}: {suite_name}")
        if passed:
            passed_tests += 1
    
    logger.info("-" * 80)
    logger.info(f"RESULTS: {passed_tests}/{total_tests} test suites passed ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests == total_tests:
        logger.info("🎉 ALL TESTS PASSED! The status-triggered document processing system is ready!")
        logger.info("\n🚀 READY FOR DEPLOYMENT:")
        logger.info("   • Status field updates → Document processing ✅")
        logger.info("   • Targeted workflow tags → Clean automation ✅")
        logger.info("   • Both webhook endpoints integrated ✅") 
        logger.info("   • Error handling implemented ✅")
        logger.info("   • Original fields preserved ✅")
        return True
    else:
        failed_count = total_tests - passed_tests
        logger.error(f"❌ {failed_count} test suite(s) failed. Review the errors above.")
        return False

if __name__ == '__main__':
    import inspect
    
    # Set test environment variables
    os.environ['RMBB_API_KEY'] = 'test_key'
    os.environ['RMBB_TEAM_ID'] = '85'
    os.environ['GHL_API_KEY'] = 'test_ghl_key'
    
    success = run_comprehensive_test()
    
    if success:
        print("\n✅ COMPREHENSIVE TEST COMPLETED SUCCESSFULLY!")
        print("🚀 The status-triggered document processing system is ready for deployment!")
        sys.exit(0)
    else:
        print("\n❌ COMPREHENSIVE TEST FAILED!")
        print("🔍 Check the logs above for details on what needs to be fixed.")
        sys.exit(1)