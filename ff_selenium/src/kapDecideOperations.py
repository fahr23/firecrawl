import requests
import time
import os
from requests.exceptions import RequestException

class PDFDownloader:
    def __init__(self, max_attempts=1, backoff_time=5):
        self.max_attempts = max_attempts
        self.backoff_time = backoff_time
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    def download_pdf(self, pdf_url, pdf_path):
        attempt = 0
        backoff_time = self.backoff_time
        while attempt < self.max_attempts:
            try:
                pdf_response = requests.get(pdf_url, headers=self.headers)
                pdf_response.raise_for_status()  # Check for HTTP errors

                # Save the PDF file
                with open(pdf_path, 'wb') as pdf_file:
                    pdf_file.write(pdf_response.content)

                print(f"Downloaded {pdf_path}")
                return pdf_response.content
            except requests.exceptions.RequestException as e:
                print(f"Error downloading {pdf_path}: {e}")
                attempt += 1
                time.sleep(backoff_time)
                backoff_time *= 2  # Double the backoff time for the next attempt
                attempt += 1
        return None

class MinioUploader:
    def __init__(self, minio_client):
        self.minio_client = minio_client

    def upload_pdf_to_minio(self, bucket_name, object_name, pdf_content):
        try:
            self.minio_client.put_object(
                bucket_name, object_name, pdf_content, len(pdf_content)
            )
            print(f"Uploaded {object_name} to Minio")
        except Exception as e:
            print(f"Error uploading {object_name} to Minio: {e}")

class DatabaseManager:
    def __init__(self, db_params):
        self.connection = psycopg2.connect(
            dbname=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"]
        )
        self.cursor = self.connection.cursor()

    def create_table(self):
            create_table_query = """
            CREATE TABLE IF NOT EXISTS kap_disclosures (
                publish_date VARCHAR(255),
                kap_title VARCHAR(255),
                is_old_kap BOOLEAN,
                disclosure_class VARCHAR(255),
                disclosure_type VARCHAR(255),
                disclosure_category VARCHAR(255),
                summary TEXT,
                subject TEXT,
                rule_type_term VARCHAR(255),
                disclosure_index INT UNIQUE,
                is_late BOOLEAN,
                stock_codes VARCHAR(255),
                has_multi_language_support BOOLEAN,
                attachment_count INT,
                createtime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updatetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            self.cursor.execute(create_table_query)
    
    def insert_data(self, data):
        insert_query = """
        INSERT INTO kap_disclosures (publish_date, kap_title, is_old_kap, disclosure_class, disclosure_type, disclosure_category, summary, subject, rule_type_term, disclosure_index, is_late, stock_codes, has_multi_language_support, attachment_count, createtime, updatetime)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (disclosure_index) DO UPDATE SET
            publish_date = EXCLUDED.publish_date,
            kap_title = EXCLUDED.kap_title,
            is_old_kap = EXCLUDED.is_old_kap,
            disclosure_class = EXCLUDED.disclosure_class,
            disclosure_type = EXCLUDED.disclosure_type,
            disclosure_category = EXCLUDED.disclosure_category,
            summary = EXCLUDED.summary,
            subject = EXCLUDED.subject,
            rule_type_term = EXCLUDED.rule_type_term,
            is_late = EXCLUDED.is_late,
            stock_codes = EXCLUDED.stock_codes,
            has_multi_language_support = EXCLUDED.has_multi_language_support,
            attachment_count = EXCLUDED.attachment_count,
            updatetime = CURRENT_TIMESTAMP
        """
        self.cursor.execute(insert_query, data)

# Example usage:
# from minio import Minio
# minio_client = Minio(...)  # Initialize Minio client
# cursor = ...  # Initialize database cursor

# Initialize classes
pdf_downloader = PDFDownloader()
# minio_uploader = MinioUploader(minio_client)

# Initialize database cursor (example using psycopg2)
import psycopg2

db_params = {
    "host": "timescaledb",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}

db_manager = DatabaseManager(db_params)

# Create table if not exists
# db_manager.create_table()
import datetime

# Number of days before today you want to calculate
days_before = 2  # Example: 5 days before today

# Calculate the current day
current_day = datetime.date.today()
before_day = current_day - datetime.timedelta(days=days_before)

url = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
payload = {
    "fromDate": before_day.strftime("%Y-%m-%d"),
    "toDate": current_day.strftime("%Y-%m-%d"),
    "year": "",
    "prd": "",
    "term": "",
    "ruleType": "",
    "bdkReview": "",
    "disclosureClass": "",
    "index": "",
    "market": "",
    "isLate": "",
    "subjectList": [],
    "mkkMemberOidList": [],
    "inactiveMkkMemberOidList": [],
    "bdkMemberOidList": [],
    "mainSector": "",
    "sector": "",
    "subSector": "",
    "memberType": "IGS",
    "fromSrc": "N",
    "srcCategory": "",
    "discIndex": []
}

# Define headers to mimic a browser request
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.kap.org.tr/",
}
# from_date = payload['fromDate'].replace("-", "")
# to_date = payload['toDate'].replace("-", "")
# folder_name = f"{from_date}to{to_date}"
base_directory = "/root/kap_pdfs"
# full_path = os.path.join(base_directory, folder_name)
full_path = os.path.join(base_directory)
# Configuration
download_counter_conf = 5
wait_time = 60  # in seconds
max_retries = 1

# Create directory if it doesn't exist
if not os.path.exists(full_path):
    os.makedirs(full_path)

# Make the request with headers
response = requests.post(url, json=payload, headers=headers)
data = response.json()

# Iterate through data to download PDFs
download_counter = 0  # Initialize a counter for downloads

for item in reversed(data):
    disclosure_index = item['disclosureIndex']
    pdf_url = f"https://www.kap.org.tr/tr/BildirimPdf/{disclosure_index}"
    pdf_path = os.path.join(full_path, f"{disclosure_index}.pdf")

    # Check if the PDF already exists
    if not os.path.exists(pdf_path):
        retries = 0
        while retries < max_retries:
            try:
                pdf_content = pdf_downloader.download_pdf(pdf_url, pdf_path)
                if pdf_content:
                    # minio_uploader.upload_pdf_to_minio("pdf", str(disclosure_index), pdf_content)
                    # db_manager.insert_data(data)
                    download_counter += 1
                    break
            except RequestException as e:
                time.sleep(wait_time)
                retries += 1


    # Check if the download counter has reached the configured limit
    if download_counter >= download_counter_conf:
        print(f"Reached download limit of {download_counter_conf}. Waiting for {wait_time} seconds before continuing...")
        time.sleep(wait_time)
        download_counter = 0  # Reset the counter after waiting
print(f"Total PDFs downloaded: {download_counter}")