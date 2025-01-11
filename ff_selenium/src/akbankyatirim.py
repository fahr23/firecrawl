import requests
import time
import os
import fitz  # PyMuPDF
from requests.exceptions import RequestException

class PDFTextExtractor:
    def __init__(self, output_dir="/root/akbankyatirim_txts"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def extract_text(self, pdf_content, file_name):
        temp_pdf_path = os.path.join(self.output_dir, file_name)
        with open(temp_pdf_path, "wb") as pdf_file:
            pdf_file.write(pdf_content)

        pdf_document = fitz.open(temp_pdf_path)
        pdf_text = ""
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            pdf_text += page.get_text()

        txt_file_path = os.path.join(self.output_dir, f"{os.path.splitext(file_name)[0]}.txt")
        with open(txt_file_path, "w") as txt_file:
            txt_file.write(pdf_text)
        os.remove(temp_pdf_path)
        print(f"Extracted text written to {txt_file_path}")

class PDFDownloader:
    def __init__(self, max_attempts=1, backoff_time=5):
        self.max_attempts = max_attempts
        self.backoff_time = backoff_time
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.extractor = PDFTextExtractor()

    def download_pdf(self, pdf_url, pdf_path):
        attempt = 0
        backoff_time = self.backoff_time
        while attempt < self.max_attempts:
            try:
                pdf_response = requests.get(pdf_url, headers=self.headers)
                pdf_response.raise_for_status()

                with open(pdf_path, 'wb') as pdf_file:
                    pdf_file.write(pdf_response.content)

                print(f"Downloaded {pdf_path}")
                self.extractor.extract_text(pdf_response.content, os.path.basename(pdf_path))
                return pdf_response.content
            except requests.exceptions.RequestException as e:
                print(f"Error downloading {pdf_path}: {e}")
                attempt += 1
                time.sleep(backoff_time)
                backoff_time *= 2
        return None

def download_pdfs(start_time, end_time, page_size, max_pages):
    base_directory = "/root/akbankyatirim_pdfs"
    full_path = os.path.join(base_directory)
    if not os.path.exists(full_path):
        os.makedirs(full_path)

    pdf_downloader = PDFDownloader()

    for page_no in range(1, max_pages + 1):
        url = f"https://yatirim.akbank.com/_vti_bin/AkbankYatirimciPortali/Rapor/Service.svc/Get/null/null/null/{start_time}/{end_time}/{page_no}/{page_size}"
        headers = {'Content-Type': 'application/json'}

        response = requests.get(url, headers=headers)
        data = response.json()
        for item in data['Data']['Items']:
            item_id = item['ItemID']
            pdf_url = f"https://yatirim.akbank.com/_layouts/15/AkbankYatirimciPortali/Rapor/Download.aspx?ID={item_id}"
            pdf_path = os.path.join(full_path, f"{item_id}.pdf")
            pdf_downloader.download_pdf(pdf_url, pdf_path)
        if not data['Data']['HasNextPage']:
            break

from datetime import datetime, timedelta

# Calculate today's date and the date three days ago
today = datetime.now()
three_days_ago = today - timedelta(days=3)

# Format the dates in the required format
start_time = three_days_ago.strftime("%Y%m%d%H%M%S")
end_time = today.strftime("%Y%m%d%H%M%S")

print(f"Start time: {start_time}")
print(f"End time: {end_time}")

# Example usage
page_size = 5
max_pages = 100

download_pdfs(start_time, end_time, page_size, max_pages)