# docker volume create pgdata
# docker run -d --name backtofuturePostgre -e POSTGRES_PASSWORD=backtofuture -v pgdata:/var/lib/postgresql/data -p 5432:5432 postgres:latest

import requests
import psycopg2

from bs4 import BeautifulSoup
# Database connection parameters
# Database connection parameters
db_params = {
    "host": "timescaledb",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}
# Establish database connection
conn = psycopg2.connect(**db_params)
cur = conn.cursor()


import datetime

# Number of days before today you want to calculate
days_before = 2  # Example: 5 days before today

# Calculate the current day
current_day = datetime.date.today()

# Calculate the date for 'days_before' days before the current day
before_day = current_day - datetime.timedelta(days=days_before)

print(f"Current Day: {current_day}")
print(f"Date {days_before} Days Before: {before_day}")

# Define the URL and payload
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

from minio import Minio
from minio.error import S3Error

from io import BytesIO
from minio import Minio
from minio.error import S3Error

def upload_pdf_to_minio(bucket_name, object_name, pdf_content):
    """
    Uploads PDF content directly to a specified bucket in Minio.

    :param bucket_name: Name of the bucket to upload the file to.
    :param object_name: The object name in the bucket.
    :param pdf_content: Binary content of the PDF to be uploaded.
    """
    # Create a Minio client with the Minio server, access key, and secret key.
    minio_client = Minio(
        "minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False  # Set to False if your Minio server does not use SSL
    )

    try:
        # Make sure the bucket exists. Create it if it does not.
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # Convert binary content to a stream.
        pdf_data = BytesIO(pdf_content)
        pdf_size = len(pdf_content)

        # Use put_object to upload the PDF content.
        minio_client.put_object(
            bucket_name, object_name, pdf_data, pdf_size,
            content_type="application/pdf"
        )
        print(f"PDF content is successfully uploaded as '{object_name}' to bucket '{bucket_name}'.")
    except S3Error as exc:
        print("Error occurred:", exc)




import requests
import time
# Ensure you have the Minio client imported or defined elsewhere in your script
# from minio import Minio
# from minio.error import S3Error


def download_pdf(disclosure_index,pdf_url, pdf_path):
    attempt = 0
    max_attempts = 5
    backoff_time = 5  # Start with 5 seconds
    headers = {'User-Agent': 'Mozilla/5.0'}  # Example header, adjust as needed

    while attempt < max_attempts:
        try:
            pdf_response = requests.get(pdf_url, headers=headers)
            pdf_response.raise_for_status()  # Check for HTTP errors

            # Save the PDF file
            with open(pdf_path, 'wb') as pdf_file:
                pdf_file.write(pdf_response.content)

            print(f"Downloaded {pdf_path}")
            
            # Upload the PDF to Minio after successful download
            upload_pdf_to_minio("pdf", str(disclosure_index), pdf_response.content)
            print(f"Uploaded {pdf_path} to Minio")
            break  # Exit the loop on success
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {pdf_path}: {e}")
            time.sleep(backoff_time)
            backoff_time *= 2  # Double the backoff time for the next attempt
            attempt += 1


import os
# Create table if not exists
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
    disclosure_index INT,
    is_late BOOLEAN,
    stock_codes VARCHAR(255),
    has_multi_language_support BOOLEAN,
    attachment_count INT
)
"""
cur.execute(create_table_query)


# Insert data into the table
insert_query = """
INSERT INTO kap_disclosures (publish_date, kap_title, is_old_kap, disclosure_class, disclosure_type, disclosure_category, summary, subject, rule_type_term, disclosure_index, is_late, stock_codes, has_multi_language_support, attachment_count)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# Assuming the payload is defined as shown previously
from_date = payload['fromDate'].replace("-", "")
to_date = payload['toDate'].replace("-", "")
folder_name = f"{from_date}to{to_date}"

# Create directory if it doesn't exist
if not os.path.exists(folder_name):
    os.makedirs(folder_name)

# Iterate through data to download PDFs
import time

# Iterate through data to download PDFs
download_counter = 0  # Initialize a counter for downloads
# Make the request with headers
response = requests.post(url, json=payload, headers=headers)
# data json
data = response.json()

for item in reversed(data):
    disclosure_index = item['disclosureIndex']
    pdf_url = f"https://www.kap.org.tr/tr/BildirimPdf/{disclosure_index}"
    pdf_html_url = f"https://www.kap.org.tr/tr/Bildirim/{disclosure_index}"

    response = requests.get(pdf_html_url)
    

        
    # Initialize href_value and time_value as empty strings
    href_value = ''
    time_value = ''
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract the href value
        a_tag = soup.find('a', class_="modal-attachment type-xsmall bi-sky-black maximize")
        if a_tag:
            href_value = a_tag.get('href')
        
        # Extract the time value
        div_tag = soup.find('div', class_="type-medium bi-sky-black")
        if div_tag:
            time_value = div_tag.text.strip() 
    else:
        print("Failed to fetch the page.")
    
    
    
    # Define the path for the PDF file
    pdf_path = os.path.join(folder_name, f"{disclosure_index}.pdf")
    
    # Check if the file already exists
    if not os.path.exists(pdf_path):
        download_pdf(disclosure_index ,pdf_url, pdf_path)
        # here also download attachments there is an attachment url and counts
        cur.execute(insert_query, (
            time_value,
            item.get("kapTitle", ''),
            item.get("isOldKap", ''),
            item.get("disclosureClass", ''),
            item.get("disclosureType", ''),
            item.get("disclosureCategory", ''),
            item.get("summary", ''),
            item.get("subject", ''),
            item.get("ruleTypeTerm", ''),
            item.get("disclosureIndex", ''),
            item.get("isLate", ''),
            item.get("stockCodes", ''),
            item.get("hasMultiLanguageSupport", ''),
            item.get("attachmentCount", '')
        ))
        download_counter += 1  # Increment the counter after a successful download
        
        # Check if 10 downloads have been completed
        if download_counter >= 10:
            # Commit changes and close connection
            conn.commit()
            print("Waiting for 2 minutes after 10 downloads...")
            time.sleep(120)  # Wait for 2 minutes
            download_counter = 0  # Reset the counter
        
        # Wait for 10 seconds before the next query to reduce the chance of being blocked
        time.sleep(1)
cur.close()
conn.close()