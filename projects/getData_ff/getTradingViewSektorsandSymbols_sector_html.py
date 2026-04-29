import requests
import psycopg2
from requests.exceptions import RequestException
from bs4 import BeautifulSoup

# Database connection parameters
# engine now support this feature beaceuse it gets other data for run
db_params = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}

TABLE_NAME = "bist_data_collector.tradingview_sectors_tr"

# Create a PostgreSQL database connection
conn = psycopg2.connect(**db_params)
cursor = conn.cursor()

# Create table if not exists
cursor.execute('''
    CREATE TABLE IF NOT EXISTS bist_data_collector.tradingview_sectors_tr (
        id SERIAL PRIMARY KEY,
        sector_name VARCHAR(255) NOT NULL,
        stock_symbol VARCHAR(50) NOT NULL,
        fetch_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

cursor.execute(
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_tradingview_sector_symbol
    ON {TABLE_NAME} (sector_name, stock_symbol)
    """
)

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
    timeout = 30
    session = requests.Session()
    while retries > 0:
        try:
            response = session.get(url, headers=headers, timeout=timeout)
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
                sectors = soup.select('a[href^="/markets/stocks-turkey/sectorandindustry-sector/"]')
                sector_links = []
                seen_hrefs = set()
                for sector in sectors:
                    href = sector.get('href', '').strip()
                    if not href:
                        continue
                    if href == '/markets/stocks-turkey/sectorandindustry-sector/':
                        continue
                    if '/industries/' in href:
                        continue
                    if href.count('/sectorandindustry-sector/') != 1:
                        continue
                    if href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    sector_links.append(sector)

                sectors = sector_links
                print(f"Found sectors: {len(sectors)}")

                total_new_rows = 0
                for sector in sectors:
                    sector_name = sector.text.strip()
                    print(sector_name)
                    sector_url = f"https://tr.tradingview.com{sector['href']}"
                    print(sector_url)
                    sector_response = session.get(sector_url, headers=headers, timeout=timeout)
                    sector_response.raise_for_status()
                    sector_soup = BeautifulSoup(sector_response.content, 'html.parser')
                    stocks = sector_soup.select('tbody tr.listRow')
                    if not stocks:
                        stocks = sector_soup.select('tr.listRow')

                    inserted_in_sector = 0
                    for stock in stocks:
                        symbol_node = stock.select_one('a[class*="tickerNameBox"][href^="/symbols/BIST-"]')
                        if symbol_node is None:
                            symbol_node = stock.select_one('a[href^="/symbols/BIST-"]')
                        if symbol_node is None:
                            continue

                        stock_symbol = symbol_node.text.strip()
                        print(stock_symbol)
                        
                        # Check if the entry already exists
                        cursor.execute('''
                            SELECT 1 FROM bist_data_collector.tradingview_sectors_tr WHERE sector_name = %s AND stock_symbol = %s
                        ''', (sector_name, stock_symbol))
                        
                        if cursor.fetchone() is None:
                            cursor.execute('''
                                INSERT INTO bist_data_collector.tradingview_sectors_tr (sector_name, stock_symbol)
                                VALUES (%s, %s)
                            ''', (sector_name, stock_symbol))
                            inserted_in_sector += 1
                            total_new_rows += 1
                        else:
                            print(f"Entry for {stock_symbol} in sector {sector_name} already exists.")

                    print(f"Inserted for {sector_name}: {inserted_in_sector}")
                    conn.commit()

                print(f"Total new rows inserted: {total_new_rows}")
                break
            else:
                print(f"No content returned for URL: {url}")
                retries -= 1
                if retries == 0:
                    return
        except RequestException as e:
            print(f"Error fetching TradingView data: {e}")
            retries -= 1
            if retries == 0:
                return

# Fetch and save data for the specified date range and price types

fetch_and_save_data()

# Close the database connection
conn.close()