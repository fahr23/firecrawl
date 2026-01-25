import requests
import json
import os
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_URL = "https://www.kap.org.tr"
API_ENDPOINT = f"{BASE_URL}/tr/api/memberDisclosureQuery"
DOWNLOAD_DIR = "kap_reports"
DAYS_TO_LOOK_BACK = 3  # Adjust: 0 = today only, 7 = last week

# Setup Headers (Crucial: Mimics a real browser to avoid blocking)
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/tr/bildirim-sorgu",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

def get_date_string(days_ago, format_type="api"):
    """
    Returns date in required format for KAP API
    format_type: "api" for YYYY-MM-DD (recommended), "display" for DD.MM.YYYY
    """
    date = datetime.now() - timedelta(days=days_ago)
    if format_type == "api":
        return date.strftime("%Y-%m-%d")  # API format (confirmed working)
    else:
        return date.strftime("%d.%m.%Y")  # Display format

def setup_session():
    """
    Creates a requests session and visits the main page first to get cookies.
    This makes the API request look more like a real browser session.
    """
    session = requests.Session()
    
    # First, visit the main page to establish a session and get cookies
    print("[*] Establishing browser session (visiting main page)...")
    try:
        session.get(BASE_URL, headers=BROWSER_HEADERS, timeout=15)
        print("[✓] Session established, cookies received")
        time.sleep(0.5)  # Small delay to simulate human behavior
    except Exception as e:
        print(f"[!] Warning: Could not visit main page: {e}")
        print("[*] Continuing anyway...")
    
    return session

def fetch_disclosure_list(session, from_date, to_date):
    """Fetches the metadata list of reports from the API."""
    
    # This payload is reverse-engineered from the site's actual traffic
    payload = {
        "fromDate": from_date,
        "toDate": to_date,
        "year": "",
        "prd": "",
        "term": "",
        "ruleType": "",
        "bdkReview": "",
        "disclosureClass": "", # Set to "FR" if you ONLY want Financial Reports
        "index": "",
        "market": "",
        "projectedDate": "",
        "subjectList": [],
        "mkkMemberOidList": [],
        "bdkMemberOidList": [],
        "inactiveMkkMemberOidList": [],
        "fromSrc": "N",
        "srcCategory": "",
        "discIndex": []
    }

    print(f"[*] Querying API for: {from_date} - {to_date}")
    
    try:
        # Use session to maintain cookies from the initial visit
        response = session.post(API_ENDPOINT, json=payload, headers=API_HEADERS, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print(f"[!] API Request Timed Out (server may be slow)")
        return []
    except Exception as e:
        print(f"[!] API Request Failed: {e}")
        return []

def download_pdf(session, disclosure_id, title, stock_code):
    """Constructs the PDF URL and downloads the file."""
    
    # Clean filename: "STOCKCODE - Title.pdf"
    safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()[:60]
    filename = f"{stock_code}_{safe_title}_{disclosure_id}.pdf"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(filepath):
        print(f"    [Skipping] Exists: {filename}")
        return

    # The direct PDF link pattern
    pdf_url = f"{BASE_URL}/tr/BildirimPdf/{disclosure_id}"
    
    try:
        # Use session to maintain cookies
        r = session.get(pdf_url, headers=BROWSER_HEADERS, stream=True, timeout=30)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"    [Downloaded] {filename}")
        else:
            print(f"    [Failed] Status {r.status_code} for ID {disclosure_id}")
    except Exception as e:
        print(f"    [Error] Download failed: {e}")

def main():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Setup session with cookies (makes requests look more legitimate)
    session = setup_session()
    
    # Use API date format (YYYY-MM-DD) which is confirmed working
    from_date = get_date_string(DAYS_TO_LOOK_BACK, format_type="api")
    to_date = get_date_string(0, format_type="api")  # Today
    
    # 1. Get the list
    data = fetch_disclosure_list(session, from_date, to_date)
    
    if not data:
        print("No reports found or API access denied.")
        return

    print(f"[*] Found {len(data)} reports. Starting download sequence...")
    
    # 2. Iterate and Download
    for idx, item in enumerate(data, 1):
        # Extract key fields
        d_id = item.get('disclosureIndex')
        d_title = item.get('kapTitle', 'No_Title')
        stock_code = item.get('stockCodes', 'GENEL')
        
        if d_id:
            print(f"[{idx}/{len(data)}] Processing: {stock_code} - {d_title[:50]}...")
            download_pdf(session, d_id, d_title, stock_code)
            # Polite delay to prevent IP ban (simulates human behavior)
            time.sleep(0.3)

if __name__ == "__main__":
    main()
