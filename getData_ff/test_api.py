#!/usr/bin/env python3
"""Quick test to verify API connectivity"""
import requests
from datetime import datetime, timedelta

BASE_URL = "https://www.kap.org.tr"
API_ENDPOINT = f"{BASE_URL}/tr/api/memberDisclosureQuery"

def get_date_string(days_ago):
    date = datetime.now() - timedelta(days=days_ago)
    return date.strftime("%d.%m.%Y")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/tr/bildirim-sorgu",
    "X-Requested-With": "XMLHttpRequest"
}

payload = {
    "fromDate": get_date_string(3),
    "toDate": get_date_string(0),
    "year": "",
    "prd": "",
    "term": "",
    "ruleType": "",
    "bdkReview": "",
    "disclosureClass": "",
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

print(f"Testing API endpoint: {API_ENDPOINT}")
print(f"Date range: {get_date_string(3)} to {get_date_string(0)}")
print("Sending request...")

try:
    response = requests.post(API_ENDPOINT, json=payload, headers=HEADERS, timeout=60)
    print(f"✓ Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Response type: {type(data)}")
        if isinstance(data, list):
            print(f"✓ Found {len(data)} disclosures")
            if len(data) > 0:
                print(f"✓ First item sample keys: {list(data[0].keys())[:5]}")
        else:
            print(f"Response: {str(data)[:200]}")
    else:
        print(f"✗ Error response: {response.text[:500]}")
except requests.exceptions.Timeout:
    print("✗ Request timed out after 60 seconds")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
