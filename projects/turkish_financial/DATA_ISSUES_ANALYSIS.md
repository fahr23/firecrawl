# Data Issues Analysis & Solutions

## Problems Identified

### 1. KAP Reports Table
**Issue:** All records have NULL values for `report_date`, `title`, `report_type`
**Root Cause:**
- KAP API endpoints (`/tr/api/memberDisclosureQuery?member=CODE`) are returning 500 error pages
- The scraper is saving error page content instead of actual report data
- LLM extraction is failing or not configured
- No fallback parsing mechanism

**Current Data:**
- 10 records in database
- All have `data` field with error page content
- All have NULL for date, title, type
- All marked as `extracted: false`

### 2. TradingView Tables
**Issue:** Both `tradingview_sectors_tr` and `tradingview_industry_tr` are empty
**Root Cause:**
- LLM extraction is returning 0 sectors/industries
- No data is being saved because extraction fails
- No fallback mechanism if LLM extraction fails

**Current Data:**
- 0 records in both tables

### 3. Sentiment Table
**Issue:** `kap_report_sentiment` is empty
**Root Cause:**
- No sentiment analysis has been run
- Or sentiment analysis is failing due to missing LLM configuration

**Current Data:**
- 0 records

## Solutions Needed

### Immediate Fixes:

1. **Add HTML Parsing Fallback for KAP**
   - Parse HTML directly using BeautifulSoup if LLM extraction fails
   - Extract report dates, titles from HTML structure
   - Handle error pages by skipping them

2. **Add HTML Parsing Fallback for TradingView**
   - Parse HTML tables/lists directly
   - Extract sector/industry data from page structure
   - Save data even if LLM extraction fails

3. **Improve Error Detection**
   - Better detection of error pages
   - Skip error pages instead of saving them
   - Log warnings when error pages are encountered

4. **Add Manual Data Entry Option**
   - Allow manual correction of parsed data
   - Provide API endpoints to update report metadata

## Recommended Actions

1. ✅ Fixed schema isolation (tables now in correct schema)
2. ✅ Fixed missing sentiment table
3. ⚠️ **TODO:** Add HTML parsing fallbacks
4. ⚠️ **TODO:** Improve error page detection
5. ⚠️ **TODO:** Test with working KAP/TradingView pages
6. ⚠️ **TODO:** Add data validation before saving
