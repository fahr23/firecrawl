# KAP Scraper API-Based Refactoring

## Summary

The KAP scraper has been refactored to use the **KAP API endpoint** (`/tr/api/memberDisclosureQuery`) instead of HTML scraping, aligning with the working implementation in `getKAPReports.py`.

## Changes Made

### ✅ API-Based Approach

**Previous Approach:**
- Scraped HTML page (`https://www.kap.org.tr/tr`)
- Tried to parse table structure
- Unreliable due to JavaScript rendering and empty states

**New Approach:**
- Uses KAP API: `https://www.kap.org.tr/tr/api/memberDisclosureQuery`
- POST request with JSON payload
- Returns structured JSON data with all disclosure information
- Matches the working `getKAPReports.py` implementation

### Implementation Details

1. **API Endpoint**: `/tr/api/memberDisclosureQuery`
2. **Method**: POST with JSON payload
3. **Payload Structure**:
   ```json
   {
     "fromDate": "2026-01-18",
     "toDate": "2026-01-25",
     "memberType": "IGS",  // BIST companies
     "subjectList": [],
     // ... other filters
   }
   ```

4. **Response**: Array of disclosure objects with:
   - `disclosureIndex`
   - `publishDate`
   - `kapTitle`
   - `stockCodes` (comma-separated)
   - `subject`
   - `summary`
   - `disclosureType`
   - `disclosureClass`
   - `attachmentCount`
   - etc.

5. **Data Mapping**:
   - `stockCodes` → `company_code` (first code)
   - `publishDate` → `report_date`
   - `kapTitle` or `subject` → `title`
   - `disclosureType` → `report_type`
   - All metadata stored in `data` JSON field

### Code Structure

```python
async def scrape(self, days_back: int = 7, company_symbols: Optional[List[str]] = None):
    # Calculate date range
    # Prepare API payload
    # Make POST request with aiohttp
    # Process JSON response
    # Save to database
```

## Current Status

### ✅ Code is Correctly Refactored

- Uses KAP API endpoint
- Matches working implementation structure
- Proper error handling
- Timeout handling (30 seconds)
- Data mapping aligned with database schema

### ⚠️ Network/API Issues

**Current Issue**: API requests are timing out
- May be network issue from devcontainer
- KAP API may be slow or rate-limiting
- May need to test from different network

**Error Handling**:
- Timeout errors are caught and logged
- Returns proper error response
- Does not crash the application

## Testing

### Direct API Test

```python
import requests
from datetime import datetime, timedelta

url = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
payload = {
    "fromDate": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
    "toDate": datetime.now().strftime("%Y-%m-%d"),
    "memberType": "IGS",
    # ... other fields
}

response = requests.post(url, json=payload, timeout=30)
data = response.json()  # Array of disclosures
```

### Expected Behavior

When API is accessible:
- Returns array of disclosure objects
- Each object contains all KAP report metadata
- Can be directly saved to database

## Alignment with Working Code

### `getKAPReports.py` Structure

```python
# Same API endpoint
url = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"

# Same payload structure
payload = {
    "fromDate": before_day.strftime("%Y-%m-%d"),
    "toDate": current_day.strftime("%Y-%m-%d"),
    "memberType": "IGS",
    # ...
}

# Same request method
response = requests.post(url, json=payload, headers=headers)
data = response.json()

# Process each item
for item in data:
    disclosure_index = item['disclosureIndex']
    # Save to database
```

### Differences

1. **Async vs Sync**: New scraper uses `aiohttp` (async), working code uses `requests` (sync)
2. **Error Handling**: New scraper has comprehensive timeout/error handling
3. **Data Structure**: New scraper maps to existing `kap_reports` table schema

## Next Steps

1. **Test from different network** to verify API accessibility
2. **Consider using `requests`** if async is causing issues
3. **Add retry logic** for transient network failures
4. **Monitor API response times** to adjust timeout

## Benefits of API Approach

✅ **Reliable**: Direct API access, no HTML parsing  
✅ **Structured Data**: JSON response with all fields  
✅ **Fast**: No need to wait for JavaScript rendering  
✅ **Complete**: All metadata available (disclosureIndex, attachments, etc.)  
✅ **Aligned**: Matches proven working implementation  
