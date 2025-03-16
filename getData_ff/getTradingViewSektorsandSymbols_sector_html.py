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
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tradingview_sectors_tr (
        id SERIAL PRIMARY KEY,
        sector_name VARCHAR(255) NOT NULL,
        stock_symbol VARCHAR(50) NOT NULL,
        fetch_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

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
                    sector_name = sector.text
                    print(sector_name)
                    sector_url = f"https://tr.tradingview.com{sector['href']}"
                    print(sector_url)
                    sector_response = requests.get(sector_url, headers=headers)
                    sector_response.raise_for_status()
                    sector_soup = BeautifulSoup(sector_response.content, 'html.parser')
                    stocks = sector_soup.select('tbody tr.listRow')
                    for stock in stocks:
                        stock_symbol = stock.select_one('a.tickerNameBox-GrtoTeat.tickerName-GrtoTeat').text
                        stock_price = stock.select_one('td.cell-RLhfr_y4.right-RLhfr_y4').text.strip()
                        print(f"{stock_symbol}: {stock_price}")
                        
                        # Check if the entry already exists
                        cursor.execute('''
                            SELECT 1 FROM tradingview_sectors_tr WHERE sector_name = %s AND stock_symbol = %s
                        ''', (sector_name, stock_symbol))
                        
                        if cursor.fetchone() is None:
                            cursor.execute('''
                                INSERT INTO tradingview_sectors_tr (sector_name, stock_symbol)
                                VALUES (%s, %s)
                            ''', (sector_name, stock_symbol))
                        else:
                            print(f"Entry for {stock_symbol} in sector {sector_name} already exists.")
                    conn.commit()
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