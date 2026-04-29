import requests
import json
import psycopg2
from datetime import datetime, timedelta
from requests.exceptions import RequestException, JSONDecodeError



# https://www.tradingview.com/support/solutions/43000724300-sector-industry/

# Database connection parameters
# engine now support this feature beaceuse it gets other data for run
db_params = {
    "host": "localhost",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}

# Create a PostgreSQL database connection
conn = psycopg2.connect(**db_params)
cursor = conn.cursor()

# Create table if not exists
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tradingview_sectors_en (
        id SERIAL PRIMARY KEY,
        sector_name VARCHAR(255) NOT NULL,
        stock_symbol VARCHAR(50) NOT NULL,
        fetch_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Function to fetch and save data for a specific date range and price type
def fetch_and_save_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Referer": "https://www.borsaistanbul.com/"
    }
    
    sectors = [
        "Durables", "Non-Durables", "Services", "Infrastructure", "Materials", "Non-Energy Minerals", 
        "Energy Minerals", "Industrial Services", "Transportation", "Utilities", "Finance", 
        "Communications", "Miscellaneous", "Investment Trusts/Mutual Funds", "Producer Manufacturing", 
        "Process Industries", "Commercial Services", "Distribution", "Technology", "Electronic Technology", 
        "Health Technology", "Technology Services", "Health Services", "Consumer Durables", 
        "Consumer Non-Durables", "Consumer Services", "Retail Trade"
    ]
    allcount = 0
    
    for sector in sectors:
        payload = {
            "columns": [
                "name", "description", "logoid", "update_mode", "type", "typespecs", "market_cap_basic",
                "fundamental_currency_code", "close", "pricescale", "minmov", "fractional", "minmove2",
                "currency", "change", "volume", "relative_volume_10d_calc", "price_earnings_ttm",
                "earnings_per_share_diluted_ttm", "earnings_per_share_diluted_yoy_growth_ttm",
                "dividends_yield_current", "recommendation_mark"
            ],
            "filter": [
                {
                    "left": "sector",
                    "operation": "equal",
                    "right": sector
                }
            ],
            "ignore_unknown_fields": False,
            "options": {
                "lang": "tr"
            },
            "range": [0, 200],
            "sort": {
                "sortBy": "market_cap_basic",
                "sortOrder": "desc",
                "nullsFirst": False
            },
            "preset": "market_company"
        }
        api_url = "https://scanner.tradingview.com/turkey/scan?label-product=markets-screener"
        retries = 3
        while retries > 0:
            try:
                api_response = requests.post(api_url, headers=headers, json=payload)
                api_response.raise_for_status()
                data = api_response.json()
                print("sector:", sector, ":length", len(data.get("data", [])))
                total_count = len(data.get("data", []))
                for item in data.get("data", []):
                    stock_symbol = item["d"][0]
                    print(f"{sector}: {stock_symbol}")
                    cursor.execute('''
                        SELECT 1 FROM tradingview_sectors_en WHERE sector_name = %s AND stock_symbol = %s
                    ''', (sector, stock_symbol))
                    if cursor.fetchone() is None:
                        cursor.execute('''
                            INSERT INTO tradingview_sectors_en (sector_name, stock_symbol)
                            VALUES (%s, %s)
                        ''', (sector, stock_symbol))
                conn.commit()
                print(f"Total count of stocks for sector {sector}: {total_count}")
                allcount += total_count
                break
            except (RequestException, JSONDecodeError) as e:
                print(f"Error fetching or decoding JSON data for sector {sector}: {e}")
                retries -= 1
                if retries == 0:
                    return
    print(f"The total count of stocks fetched: {allcount}")
# Fetch and save data for the specified sectors
fetch_and_save_data()

# Close the database connection
conn.close()