# RMBB Health Integration - Production Webhook System

## Overview
Complete production webhook system that processes GoHighLevel (GHL) form submissions through RMBB Health API for IVR qualification and returns results to the correct GHL sub-account. This is a working production system, not an example.

## Architecture - Two Independent Webhook Flows
```
Flow 1: GHL Form → /webhook/ghl-rmbb-qualification → Submit to RMBB Health → Cache Provider → END

Flow 2: RMBB IVR Result → /webhook/rmbb-status-update → Lookup Provider Cache → Update GHL Contact → Notify Provider → END
```

**Important**: These are two SEPARATE webhook flows handled by the SAME Railway app with different endpoints.

## Claude SDK Deployment with Railway MCP + GitHub MCP

### 🚀 Quick Deployment Commands for Claude SDK

Use these commands in Claude Code with your Railway MCP and GitHub MCP:

#### 1. Deploy to GitHub
```
Create a new GitHub repository called "rmbb-health-webhook" and push this code:
- Create repository with README
- Push all files from /Users/timothywade/Jarvis/rmbbhealth/ 
- Set repository to private
- Add .gitignore for Python projects
```

#### 2. Deploy to Railway
```
Create a new Railway project:
- Connect to the GitHub repository "rmbb-health-webhook"
- Set runtime to Python
- Enable auto-deploy from main branch
- Set the environment variables below
- Deploy and get the production URL
```

## Railway Environment Variables

### Development Environment Variables (Start with these for testing)
```bash
RMBB_API_KEY=b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0
RMBB_TEAM_ID=85
RMBB_PHYSICIAN_ID=8077
RMBB_ACCOUNT_ID=2921
RMBB_ACCOUNT_LOCATION_ID=4195
GHL_API_KEY=your_development_ghl_api_key
GHL_BASE_URL=https://rest.gohighlevel.com/v1
WEBHOOK_AUTH_TOKEN=rmbb-health-webhook-2025
```

### Production Environment Variables (Switch when ready for live)
```bash
RMBB_API_KEY=08u6Avws1Qp4mzkSV81GgzdOe54mWqNQ
RMBB_TEAM_ID=59
RMBB_PHYSICIAN_ID=8077
RMBB_ACCOUNT_ID=2921
RMBB_ACCOUNT_LOCATION_ID=4195
GHL_API_KEY=your_production_ghl_api_key
GHL_BASE_URL=https://rest.gohighlevel.com/v1
WEBHOOK_AUTH_TOKEN=rmbb-health-webhook-2025
```

## Deployment Process

### Phase 1: Development Deployment & Testing
1. **Deploy with Development Variables** (Start here)
   ```bash
   RMBB_API_KEY=b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0
   RMBB_TEAM_ID=85
   # Other variables stay the same
   ```
   
2. **Test the system** with development API key
   - Send test GHL webhooks 
   - Verify RMBB Health API calls work
   - Check provider cache functionality
   - Confirm webhook responses

3. **Monitor Railway logs** for any errors or issues

### Phase 2: Production Switch (After successful testing)
1. **Update ONLY these 2 variables** in Railway dashboard:
   ```bash
   RMBB_API_KEY=08u6Avws1Qp4mzkSV81GgzdOe54mWqNQ  # Switch to production
   RMBB_TEAM_ID=59                                  # Switch to production
   ```

2. **Keep all other variables the same** (physician, account, location stay 8077, 2921, 4195)

3. **Test production deployment** with real GHL forms

### Critical Notes
- ✅ **Physician/Account/Location values are identical** for dev and production
- ✅ **Only API Key and Team ID change** between environments  
- ✅ **Always test with development first** before switching to production
- ✅ **Railway auto-deploys** when you change environment variables

## Testing & Verification

### 1. Test Complete Workflow (Local)
```bash
cd rmbbhealth
python test_complete_workflow.py
```
**Tests**: Environment variables, field mapping, provider cache, webhook endpoints

### 2. Verify Railway Deployment
```bash
python test_railway_deployment.py  
```
**Tests**: Railway environment configuration, runtime setup, deployment readiness

### 3. Manual Testing Steps

#### Phase 1: Development Testing
1. **Deploy with development variables** to Railway
2. **Run deployment verification**: `python test_railway_deployment.py`
3. **Test webhook endpoint**: Send POST to `/webhook/ghl-rmbb-qualification`
4. **Check Railway logs** for successful RMBB Health API calls
5. **Verify provider cache** functionality

#### Phase 2: Production Testing  
1. **Switch to production variables** (API Key + Team ID only)
2. **Re-run verification**: `python test_railway_deployment.py`
3. **Test with real GHL form** submissions
4. **Monitor RMBB Health** for actual patient/case creation
5. **Verify webhook responses** update GHL contacts

### 4. Expected Test Results
✅ **All environment variables set correctly**  
✅ **GHL fields map to RMBB Health format**
✅ **Biologic products extract correctly** (Q codes as product_id)
✅ **CPT code is "15271-8"** for all biologic products
✅ **Provider cache routes correctly** for webhook responses
✅ **Real RMBB Health API calls** (no mock responses)

### 3. Webhook Endpoints
- **GHL Form Submissions**: `POST /webhook/ghl-rmbb-qualification`
- **RMBB Health Status Updates**: `POST /webhook/rmbb-status-update`
- **Test Endpoint**: `GET/POST /webhook/test`  
- **Health Check**: `GET /health`

## Local Development

### Setup
```bash
cd rmbbhealth
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python webhook_handler.py
```

### Testing
```bash
# Health check
curl http://localhost:8080/health

# Test endpoint
curl http://localhost:8080/webhook/test

# Mock webhook
curl -X POST http://localhost:8080/webhook/ghl-rmbb-qualification \
  -H "Content-Type: application/json" \
  -d '{"contactId":"test123", "Patient First Name":"John", "Patient Last Name":"Smith"}'
```

## Production Data Flow - Two Independent Webhook Flows

### 📧 Flow 1: GHL Form Submission → RMBB Health Submission
**Endpoint**: `POST /webhook/ghl-rmbb-qualification`

1. **GHL Webhook Processing**
   - Receive POST webhook from GHL form submission
   - Extract `contactId`, `locationId`, and provider name from payload
   - Map GHL form fields to RMBB Health patient/medical data

2. **Provider-Location Caching**
   - Cache provider name → locationId mapping for later routing
   - Store initial tracking data in GHL contact custom fields
   - Create unique `external_id` for RMBB case linking

3. **RMBB Health Submission** 
   - Transform GHL data to RMBB patient format (name, address, contact info)
   - Create RMBB patient via Patient API
   - Transform medical data to RMBB case format (wound info, insurance, diagnosis)
   - Create RMBB case with `external_id` linking back to GHL contact

4. **Workflow Completion**
   - Update GHL contact with "submitted, awaiting IVR" status
   - **Flow ends here** - wait for RMBB Health webhook

### 📋 Flow 2: RMBB Health IVR Result → GHL Update
**Endpoint**: `POST /webhook/rmbb-status-update`

1. **RMBB Health Webhook Processing**
   - Receive POST webhook from RMBB Health with IVR results
   - Extract `external_id`, provider name, and IVR qualification data

2. **Provider-Location Lookup**
   - Use provider name to lookup cached locationId
   - Extract GHL contact ID from `external_id`

3. **GHL Contact Update**
   - Update original GHL contact with IVR qualification results
   - Store qualification details (coverage level, prior auth, etc.)

4. **Provider Notification**
   - Send provider notification to correct sub-account using cached locationId
   - **Flow ends here** - complete bidirectional workflow

**Key**: Both flows use the same provider cache for HIPAA-compliant routing without external data storage.

## Multi-Tenant Routing
- Uses `locationId` to route notifications to correct sub-account
- Uses `contactId` to update the exact contact that submitted form
- No cross-contamination between different providers/locations

## HIPAA Compliance
- ✅ All patient data stored in GHL (HIPAA compliant platform)
- ✅ No external database storage
- ✅ Data flows through → never stored elsewhere
- ✅ RMBB Health uses `external_id` to link back to GHL contact

## File Structure
```
rmbbhealth/
├── webhook_handler.py      # Main Flask webhook server (Railway entry point)
├── ghl_rmbb_workflow.py   # Complete GHL ↔ RMBB Health workflow handler
├── __init__.py            # Package initialization with service exports
├── client.py              # RMBB Health API client
├── config.py              # Configuration settings
├── services/              # RMBB Health API services
│   ├── __init__.py        # Service module initialization
│   ├── case_service.py    # Case management and IVR polling
│   ├── patient_service.py # Patient creation and management
│   ├── account_service.py # Account and location services
│   ├── file_service.py    # File upload services
│   ├── note_service.py    # Case notes services
│   ├── product_service.py # Product services
│   ├── status_service.py  # Status and health checks
│   └── provider_location_cache.py # Provider→LocationId cache (HIPAA compliant routing)
├── requirements.txt       # Python dependencies for Railway
├── railway.json           # Railway deployment configuration
└── README.md             # Production documentation
```

## Monitoring & Logs
- Railway provides automatic logging dashboard
- Health check endpoint for uptime monitoring
- Error handling with GHL contact status updates
- Comprehensive logging for debugging

## Production Usage

### GHL Form Configuration
Configure your GHL form to send webhooks to:
```
POST https://your-railway-app.railway.app/webhook/ghl-rmbb-qualification
```

### Required GHL Form Fields
The webhook handler captures these exact field names from GHL form submissions:

#### Patient Information
```
patient_first_name
patient_last_name
patient_dob
patient_street_address
patient_city
patient_state
patient_zip_code
```

#### Insurance Information
```
patient_primary_insurance
patient_primary_insurance_#
patient_secondary_insurance
patient_secondary_insurance_#
```

#### Medical & Facility Information
```
facility_type
facility_npi_#
expected_date_of_service
icd_-_10_diagnosis_code(s)
(Provider ) email
```

#### Biologic Products (Provider selects products and enters cm2)
```
amniomaxx_(q4239)_units/cm2
palingen_(q4173)_units/cm2
membrane_wrap_tri-layer_(q4344)_units/cm2
amnioamp-mp_(q4250)_units/cm2
membrane_wrap_hydro_(q4290)_units/cm2
biovance_(q4154)_units/cm2
amchoplast_(q4316)_units/cm2
helicoll_(q4164)_units/cm2
xcell_amnio_matrix_(q4280)_units/cm2
```

**Important**: Provider fills in cm2 values for selected biologic products. The system automatically:
- Maps product selection to RMBB Health product_id (Q4239, Q4173, etc.)
- Uses cm2 values for wound_size and total_wound_size
- Sets product_cpt_code to "15271-8" for all biologic products

### 🔄 Provider-Location Cache System
**CRITICAL HIPAA-Compliant Solution**: The system maintains a persistent cache mapping provider names to GHL locationIds to route RMBB Health responses back to the correct sub-accounts.

**How It Works:**
1. **GHL Form Submission**: Extracts provider name + locationId, stores mapping in cache
2. **RMBB Health Response**: Uses provider name to lookup locationId from cache
3. **GHL Update**: Routes results to correct sub-account using cached locationId

**Cache Features:**
- ✅ **HIPAA Compliant**: Only stores provider name + locationId (no patient data)
- ✅ **Persistent**: Survives Railway restarts via JSON file storage
- ✅ **Thread-Safe**: Handles concurrent webhook calls
- ✅ **Auto-Append**: Never deletes entries, prevents duplicates
- ✅ **Debugging**: Cache statistics and lookup logs for troubleshooting

**Cache File Location**: `provider_locations.json` (Railway persistent storage)

### 📋 RMBB Health Webhook Configuration
**IMPORTANT**: Provide these details to RMBB Health to enable instant status updates:

**Webhook Endpoint:**
```
POST https://your-railway-app.railway.app/webhook/rmbb-status-update
```

**Authentication:**
```
Authorization: Bearer rmbb-health-webhook-2025
Content-Type: application/json
```

**Expected Payload Format:**
```json
{
  "external_id": "ghl_contact_{contactId}_{timestamp}",
  "case_id": "rmbb_case_id",
  "provider_name": "Dr. Smith Medical Group",
  "status": "qualified",
  "patient_name": "John Smith",
  "ivr_data": {
    "approval_status": "APPROVED",
    "qualification_level": "FULL_COVERAGE",
    "prior_authorization_number": "PA123456789",
    "effective_date": "2025-08-21",
    "coverage_percentage": 100
  },
  "processed_at": "2025-08-21T15:30:00Z"
}
```

**Webhook Benefits:**
- ✅ **Instant delivery** of IVR qualification results (no polling delays)
- ✅ **Reduced API calls** and Railway resource usage
- ✅ **Real-time patient notifications** via GHL
- ✅ **Automatic provider routing** using cached locationId mappings

### Production Deployment Checklist
- ✅ Set Railway environment variables (API keys, team ID)
- ✅ Set `DEBUG=false` in Railway environment variables
- ✅ Use strong `WEBHOOK_AUTH_TOKEN` for security
- ✅ Configure GHL form webhook to Railway URL
- ✅ **Configure RMBB Health webhook** (provide endpoint and auth details above)
- ✅ Test with real API keys and form submissions
- ✅ Monitor Railway logs for webhook deliveries
- ✅ Verify IVR qualification responses update GHL contacts correctly
- ✅ Test provider cache routing with multiple sub-accounts
