# GHL → RMBB Health Field Mapping Analysis

## 🔍 Current Issues Found

### ❌ **Critical Issues**
1. **Hardcoded Default Values**: Many RMBB fields use hardcoded defaults instead of GHL data
2. **Missing Required Fields**: Some RMBB required fields not extracted from GHL
3. **Incorrect external_id Format**: Not using the format needed for webhook routing

### ❌ **Specific Field Issues**

#### **Patient Creation - ✅ GOOD**
- ✅ `personal_identifier` → Properly mapped from GHL
- ✅ `address` → Properly mapped from GHL  
- ✅ `communication_information` → Properly mapped from GHL
- ✅ `date_of_birth` → Properly mapped from GHL

#### **Case Creation - ⚠️ NEEDS FIXING**
- ❌ `account_location_id`: Hardcoded `682` → Should map from GHL locationId
- ❌ `physician_id`: Hardcoded `1960` → Should map from provider name
- ❌ `external_id`: Wrong format → Should be `ghl_contact_{contactId}_{timestamp}`
- ❌ `product_id`: Hardcoded `31` → Should map from treatment/wound type
- ❌ `product_cpt_code`: Hardcoded `67890` → Should map from treatment type

## ✅ **Required GHL Form Fields**

### **Patient Information (Working)**
```
✅ Patient First Name / first_name
✅ Patient Last Name / last_name  
✅ Patient Email / email
✅ Patient Phone / phone
✅ Patient Date of Birth / dob
✅ Patient Address / address
✅ Patient City / city
✅ Patient State / state
✅ Patient Zip Code / zip_code
```

### **Provider Information (Partially Working)**
```
✅ Provider Name / provider_name (for cache)
❌ Provider ID (need mapping table)
❌ Account Location ID (need mapping from locationId)
```

### **Medical Information (Partially Working)**
```
✅ Wound Type / wound_type
✅ Wound Size / wound_size  
✅ Surgery Date / surgery_date
✅ ICD-10 Code / icd_10_code
✅ CPT Surgery Code / cpt_surgery_code
❌ Product ID (need mapping from wound type)
❌ Product CPT Code (need mapping from treatment)
❌ Place of Service (need proper mapping)
```

### **Insurance Information (Working)**
```
✅ Primary Insurance / primary_insurance
✅ Primary Policy Number / policy_number
✅ Secondary Insurance / secondary_insurance  
✅ Secondary Policy Number / secondary_policy
```

### **Missing Optional Fields**
```
❌ Is In Skilled Nursing Facility (boolean)
❌ Is In Surgical Nursing Facility (boolean)
❌ Prior Authorization Number
❌ Insurance Type (Original Medicare, Supplement, etc.)
❌ Insurance Participating Status
❌ PPO/HMO Status
```

## 🔧 **Recommended Fixes**

### **1. Fix external_id Format**
Current: `ghl_{timestamp}`
Needed: `ghl_contact_{contactId}_{timestamp}`

### **2. Add Provider/Location Mapping**
Need mapping tables for:
- Provider Name → physician_id
- GHL locationId → account_location_id  
- Wound Type → product_id + product_cpt_code

### **3. Add Missing GHL Form Fields**
Add extraction for:
- Facility type questions
- Insurance details (type, PPO, etc.)
- Prior authorization info

### **4. Remove Hardcoded Defaults**
Replace hardcoded values with proper mappings or form fields.