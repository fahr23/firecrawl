import requests
import json
import psycopg2
from datetime import datetime, timedelta
from requests.exceptions import RequestException, JSONDecodeError
from bs4 import BeautifulSoup

# Database connection parameters
# engine now support this feature beaceuse it gets other data for run
db_params = {
    "host": "timescaledb",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}

# Create a PostgreSQL database connection
conn = psycopg2.connect(**db_params)
cursor = conn.cursor()

# Create table if not exists
# cursor.execute('''
#     CREATE TABLE IF NOT EXISTS historical_price_emtia (
#         id SERIAL PRIMARY KEY,
#         date DATE NOT NULL,
#         kur_temInatkodu_D REAL,
#         kur_temInatkodu_EU REAL,
#         rfrns_AG REAL,
#         rfrns_AU REAL,
#         rfrns_PD REAL,
#         rfrns_PT REAL
#     )
# ''')

# Function to remove null values from the response content
def remove_nulls_from_content(content):
    return content.replace(b'null', b'{}')

# Function to fetch and save data for a specific date range and price type
def fetch_and_save_data():
    url = f"https://tr.tradingview.com/markets/stocks-turkey/sectorandindustry-sector/"
    print(f"url: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Referer": "https://www.borsaistanbul.com/"
    }
    retries = 3
    while retries > 0:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an HTTPError for bad responses
            if response.content and response.content.strip():
                if b"Request Rejected" in response.content or b"Please enable JavaScript" in response.content:
                    print(f"Request rejected for URL: {url}")
                    retries -= 1
                    if retries == 0:
                        return
                    continue
                cleaned_content = remove_nulls_from_content(response.content)
                soup = BeautifulSoup(cleaned_content, 'html.parser')
                sectors = soup.select('tbody tr.listRow a.tickerLinkCell-ZOeSlGQR')
                for sector in sectors:
                    print(sector.text)
                break
            else:
                print(f"No content returned for URL: {url}")
                retries -= 1
                if retries == 0:
                    return
        except (RequestException, JSONDecodeError) as e:
            print(f"Error fetching or decoding JSON data: {e}")
            retries -= 1
            if retries == 0:
                return

  

# Fetch and save data for the specified date range and price types

fetch_and_save_data()

# Close the database connection
conn.close()