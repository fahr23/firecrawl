import os
import time
import requests
from requests.exceptions import RequestException
from extractors.text_extractor import TextExtractor


class PDFDownloader:
    def __init__(self, extractor: TextExtractor, download_path, extract_path, max_attempts=1, backoff_time=5):
        self.extractor = extractor
        self.download_path = download_path
        self.extract_path = extract_path
        self.max_attempts = max_attempts
        self.backoff_time = backoff_time
        self.headers = {'User-Agent': 'Mozilla/5.0'}


    def download_pdf(self, pdf_url, pdf_name):
        attempt = 0
        backoff_time = self.backoff_time
        pdf_path = os.path.join(self.download_path, pdf_name)
        extract_file_name = os.path.basename(pdf_name).replace('.pdf', '.txt').replace(' ', '_')
        extract_path = os.path.join(self.extract_path, extract_file_name)
        
        while attempt < self.max_attempts:
            try:
                pdf_response = requests.get(pdf_url, headers=self.headers)
                pdf_response.raise_for_status()  # Check for HTTP errors

                # Save the PDF file
                with open(pdf_path, 'wb') as pdf_file:
                    pdf_file.write(pdf_response.content)
                # Extract text and write to a .txt file
                self.extractor.extract_text(pdf_response.content, extract_path)
                return pdf_response.content
            except requests.exceptions.RequestException as e:
                print(f"Error downloading {pdf_path}: {e}")
                attempt += 1
                time.sleep(backoff_time)
                backoff_time *= 5  # Exponential backoff

        return None