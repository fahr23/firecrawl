import os
import time
import requests
import datetime
from bs4 import BeautifulSoup
from extractors.text_extractor import PDFTextExtractor
from downloaders.pdf_downloader import PDFDownloader
from database.database_manager import DatabaseManager
import psycopg2
from requests.exceptions import RequestException

def getReportwithDatabaseOps(subject_list=None):
    kap_pdf_directory = "/root/kap_pdfs"
    kap_txt_directory = "/root/kap_txts"
    kap_pdf_ek_directory = "/root/kap_pdfs_ek"
    kap_txt_ek_directory = "/root/kap_txts_ek"

    directories = [kap_pdf_directory, kap_txt_directory, kap_pdf_ek_directory, kap_txt_ek_directory]

    # Create directories if they don't exist
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    # Configuration
    download_counter_conf = 10
    wait_time = 60  # in seconds
    max_retries = 1

    # Initialize the PDF downloader and text extractor
    kap_txt_extractor = PDFTextExtractor(output_dir=kap_txt_directory)
    pdf_downloader = PDFDownloader(extractor=kap_txt_extractor, download_path=kap_pdf_directory, extract_path=kap_txt_directory)

    # Initialize the PDF downloader and text extractor for attachments
    kap_txt_ek_extractor = PDFTextExtractor(output_dir=kap_txt_ek_directory)
    pdf_downloader_ek = PDFDownloader(extractor=kap_txt_ek_extractor, download_path=kap_pdf_ek_directory, extract_path=kap_txt_ek_directory)

    # Initialize database cursor (example using psycopg2)
    db_params = {
        "host": "timescaledb",
        "database": "backtofuture",
        "user": "backtofuture",
        "password": "back2future"
    }

    db_manager = DatabaseManager(db_params)

    # Number of days before today you want to calculate
    days_before = 3  # Example: 5 days before today

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
        "subjectList": subject_list if subject_list else [],
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

    # Make the request with headers
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()

    # Iterate through data to download PDFs
    download_counter = 0  # Initialize a counter for downloads
    total_downloads = 0  # Initialize a counter for total downloads
    for item in reversed(data):
        disclosure_index = item['disclosureIndex']
        pdf_url = f"https://www.kap.org.tr/tr/BildirimPdf/{disclosure_index}"
        pdf_path = os.path.join(kap_pdf_directory, f"{disclosure_index}.pdf")
        # Check if the PDF already exists
        if not os.path.exists(pdf_path):
            print("pdfpath", pdf_path)

            # Assuming `item` is defined and contains the data to be inserted
            db_manager.insert_kap_disclosures_data((
                item.get("publishDate", ''),
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

            if item.get("attachmentCount", 0) != 0:
                print(f"Attachments found for {pdf_url}")
                url = f"https://www.kap.org.tr/tr/BildirimPopup/{disclosure_index}"
                response = requests.get(url, headers=headers)

                soup = BeautifulSoup(response.content, 'html.parser')
                attachment_links = soup.find_all('a', class_='modal-attachment type-xsmall bi-sky-black maximize')

                for attachment_link in attachment_links:
                    if 'href' in attachment_link.attrs:
                        attachment_url = f"https://www.kap.org.tr{attachment_link['href']}"

                        # Define the PDF file name
                        pdf_name = f"{disclosure_index}_{attachment_link.text.strip()}"
                        pdf_path = os.path.join(kap_pdf_ek_directory, pdf_name)

                        # Download and save the PDF
                        pdf_content = pdf_downloader_ek.download_pdf(attachment_url, pdf_path)
                        if pdf_content:
                            download_counter += 1
                            total_downloads += 1
            retries = 0
            while retries < max_retries:
                try:
                    pdf_content = pdf_downloader.download_pdf(pdf_url, pdf_path)
                    if pdf_content:
                        download_counter += 1
                        total_downloads += 1
                        break
                except RequestException as e:
                    time.sleep(wait_time)
                    retries += 1

        # Check if the download counter has reached the configured limit
        if download_counter >= download_counter_conf:
            print(f"Reached download limit of {download_counter_conf}. Waiting for {wait_time} seconds before continuing...")
            time.sleep(wait_time)
            download_counter = 0  # Reset the counter after waiting

    print(f"Total PDFs downloaded: {total_downloads}")

if __name__ == "__main__":
    getReportwithDatabaseOps(subject_list=["4028328c594bfdca01594c0af9aa0057"])  # Example: finance tables