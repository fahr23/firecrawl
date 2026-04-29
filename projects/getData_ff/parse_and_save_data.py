import requests
import json
import psycopg2
from datetime import datetime, timedelta
from requests.exceptions import RequestException, JSONDecodeError

# Database connection parameters
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
    CREATE TABLE IF NOT EXISTS historical_price_emtia (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL,
        kur_temInatkodu_D REAL,
        kur_temInatkodu_EU REAL,
        rfrns_AG REAL,
        rfrns_AU REAL,
        rfrns_PD REAL,
        rfrns_PT REAL
    )
''')

# Function to remove null values from the response content
def remove_nulls_from_content(content):
    return content.replace(b'null', b'{}')

# Function to fetch and save data for a specific date range and price type
def fetch_and_save_data(start_date, end_date, price_type):
    url = f"https://www.borsaistanbul.com/datfile/kmtprfrnstrh?startDate={start_date}&endDate={end_date}&priceType={price_type}"
    print(f"url: {url}")
    # Fetch the JSON response
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        if response.content and response.content.strip():
            cleaned_content = remove_nulls_from_content(response.content)
            data = json.loads(cleaned_content)
        else:
            print(f"No content returned for URL: {url}")
            return
    except (RequestException, JSONDecodeError) as e:
        print(f"Error fetching or decoding JSON data: {e}")
        return

    # Extract relevant data
    rfrnsTrh = data.get("rfrnsTrh", [])
    if rfrnsTrh is None:
        rfrnsTrh = []

    for item in rfrnsTrh:
        prc_date = item.get("prc_date")
        takasfiyat = item.get("takasfiyat")

        # Check if the date already exists in the database
        cursor.execute('SELECT id FROM historical_price_emtia WHERE date = %s', (prc_date,))
        result = cursor.fetchone()

        if result:
            # Update the existing row
            try:
                cursor.execute(f'''
                    UPDATE historical_price_emtia
                    SET rfrns_{price_type} = %s
                    WHERE date = %s
                ''', (takasfiyat, prc_date))
            except psycopg2.Error as e:
                print(f"Error updating data for {prc_date}: {e}")
                conn.rollback()
            else:
                conn.commit()
        else:
            # Insert a new row
            try:
                cursor.execute(f'''
                    INSERT INTO historical_price_emtia (date, rfrns_{price_type})
                    VALUES (%s, %s)
                ''', (prc_date, takasfiyat))
            except psycopg2.Error as e:
                print(f"Error inserting data for {prc_date}: {e}")
                conn.rollback()
            else:
                conn.commit()

# Define the date range and price types
start_date = "20240101"
end_date = "20250129"
price_types = ["AG", "AU", "PD", "PT"]

# Fetch and save data for the specified date range and price types
for price_type in price_types:
    fetch_and_save_data(start_date, end_date, price_type)

# Close the database connection
conn.close()