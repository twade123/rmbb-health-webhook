#!/usr/bin/env python3
"""
Railway Deployment Verification Script
Tests Railway environment variable configuration and deployment readiness
"""

import os
import sys
import json
from datetime import datetime

def test_railway_environment():
    """Test Railway-specific environment configuration"""
    print("🚂 Testing Railway Environment Configuration...")
    
    # Test required environment variables with Railway-specific checks
    railway_vars = {
        # Development Environment (Phase 1)
        'RMBB_API_KEY': 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0',  # Expected dev value
        'RMBB_TEAM_ID': '85',  # Expected dev value
        
        # Production Constants (same for dev and prod)
        'RMBB_PHYSICIAN_ID': '8077',
        'RMBB_ACCOUNT_ID': '2921', 
        'RMBB_ACCOUNT_LOCATION_ID': '4195',
        
        # GHL Configuration
        'GHL_BASE_URL': 'https://rest.gohighlevel.com/v1',
        'WEBHOOK_AUTH_TOKEN': 'rmbb-health-webhook-2025'
    }
    
    print("  Checking environment variable configuration...")
    
    # Check if using development or production
    current_api_key = os.getenv('RMBB_API_KEY', '').strip()
    current_team_id = os.getenv('RMBB_TEAM_ID', '').strip()
    
    if current_api_key == railway_vars['RMBB_API_KEY'] and current_team_id == railway_vars['RMBB_TEAM_ID']:
        print("  ✅ DEVELOPMENT environment detected")
        environment = "development"
    elif current_api_key == '08u6Avws1Qp4mzkSV81GgzdOe54mWqNQ' and current_team_id == '59':
        print("  ✅ PRODUCTION environment detected")
        environment = "production"
    else:
        print(f"  ❌ UNKNOWN environment - API key/Team ID don't match expected values")
        print(f"      Current API Key: {current_api_key[:8]}...{current_api_key[-4:] if len(current_api_key) > 8 else 'SHORT'}")
        print(f"      Current Team ID: {current_team_id}")
        return False
    
    # Verify constant values are correct for both environments
    constants_correct = True
    for var_name in ['RMBB_PHYSICIAN_ID', 'RMBB_ACCOUNT_ID', 'RMBB_ACCOUNT_LOCATION_ID']:
        expected = railway_vars[var_name]
        actual = os.getenv(var_name, '').strip()
        
        if actual != expected:
            print(f"  ❌ {var_name}: Expected '{expected}', got '{actual}'")
            constants_correct = False
        else:
            print(f"  ✅ {var_name}: {actual}")
    
    if not constants_correct:
        return False
    
    # Check GHL configuration
    ghl_api_key = os.getenv('GHL_API_KEY', '').strip()
    if not ghl_api_key or ghl_api_key.startswith('your_'):
        print(f"  ⚠️ GHL_API_KEY: Not set or using placeholder value")
        print(f"      You need to set your actual GHL API key in Railway")
    else:
        print(f"  ✅ GHL_API_KEY: {ghl_api_key[:8]}...{ghl_api_key[-4:]}")
    
    return True

def test_railway_runtime():
    """Test Railway runtime environment"""
    print("\n⚙️ Testing Railway Runtime Environment...")
    
    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  ✅ Python Version: {python_version}")
    
    # Check Railway-specific environment variables
    railway_env_vars = [
        'PORT',
        'RAILWAY_ENVIRONMENT', 
        'RAILWAY_PROJECT_ID',
        'RAILWAY_SERVICE_ID'
    ]
    
    for var in railway_env_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {value}")
        else:
            print(f"  ⚠️ {var}: Not set (may be normal in local testing)")
    
    # Test port configuration
    port = int(os.getenv('PORT', 8080))
    print(f"  ✅ Server Port: {port}")
    
    return True

def test_deployment_readiness():
    """Test if the deployment is ready"""
    print("\n🚀 Testing Deployment Readiness...")
    
    try:
        # Test imports
        from rmbbhealth import RMBBHealthClient
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        from rmbbhealth.services.provider_location_cache import ProviderLocationCache
        print("  ✅ All required modules import successfully")
        
        # Test client initialization with Railway environment variables
        client = RMBBHealthClient()
        print("  ✅ RMBB Health client initializes successfully")
        
        # Test workflow handler initialization
        handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=os.getenv('RMBB_API_KEY'),
            rmbb_team_id=int(os.getenv('RMBB_TEAM_ID')),
            ghl_api_key=os.getenv('GHL_API_KEY')
        )
        print("  ✅ Workflow handler initializes successfully")
        
        # Test provider cache
        cache = ProviderLocationCache()
        print("  ✅ Provider cache initializes successfully")
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Initialization error: {e}")
        return False

def generate_deployment_report():
    """Generate a deployment status report"""
    print("\n📋 Generating Deployment Report...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "environment": {
            "rmbb_api_key": os.getenv('RMBB_API_KEY', '')[:8] + '...',
            "rmbb_team_id": os.getenv('RMBB_TEAM_ID', ''),
            "rmbb_physician_id": os.getenv('RMBB_PHYSICIAN_ID', ''),
            "rmbb_account_id": os.getenv('RMBB_ACCOUNT_ID', ''),
            "rmbb_account_location_id": os.getenv('RMBB_ACCOUNT_LOCATION_ID', ''),
            "ghl_api_key_set": bool(os.getenv('GHL_API_KEY', '').strip()),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "port": os.getenv('PORT', '8080')
        },
        "railway_vars": {
            var: bool(os.getenv(var)) for var in [
                'RAILWAY_ENVIRONMENT', 
                'RAILWAY_PROJECT_ID', 
                'RAILWAY_SERVICE_ID'
            ]
        }
    }
    
    print(f"  📄 Deployment report generated")
    return report

def run_railway_verification():
    """Run complete Railway deployment verification"""
    print("=" * 80)
    print("🚂 RMBB Health - Railway Deployment Verification")
    print("=" * 80)
    
    tests = [
        ("Railway Environment", test_railway_environment),
        ("Railway Runtime", test_railway_runtime),
        ("Deployment Readiness", test_deployment_readiness)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_function in tests:
        try:
            if test_function():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
        
        print("-" * 40)
    
    # Generate report
    report = generate_deployment_report()
    
    print(f"\n📊 Verification Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Railway deployment is READY!")
        print("\n📋 Next Steps:")
        print("  1. Deploy to Railway with development variables")
        print("  2. Test with GHL webhook calls")
        print("  3. Switch to production variables when ready")
        return True
    else:
        print("⚠️ Railway deployment has issues. Fix configuration and retry.")
        return False

if __name__ == "__main__":
    success = run_railway_verification()
    exit(0 if success else 1)