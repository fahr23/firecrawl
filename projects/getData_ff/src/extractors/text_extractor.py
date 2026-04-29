import os
import fitz  # PyMuPDF
import tempfile
import re
import unicodedata
from abc import ABC, abstractmethod

class TextExtractor(ABC):
    @abstractmethod
    def extract_text(self, pdf_content, extract_path):
        pass

class PDFTextExtractor(TextExtractor):
    def __init__(self, output_dir="/root/kap_txts"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def normalize_text(self, text):
        # Normalize unicode characters
        text = unicodedata.normalize('NFKD', text)
        # Replace specific unwanted characters or sequences
        text = text.replace("൴", "i")
        # Remove other unwanted characters using regex
        text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Replace non-ASCII characters with space
        text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with a single space
        return text.strip()

    def extract_text(self, pdf_content, file_name):
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write the PDF content to a temporary file
            temp_pdf_path = os.path.join(temp_dir, os.path.basename(file_name))
            with open(temp_pdf_path, "wb") as pdf_file:
                pdf_file.write(pdf_content)

            # Open the PDF file
            with fitz.open(temp_pdf_path) as pdf_document:
                # Extract text from the PDF
                pdf_text = ""
                for page_num in range(len(pdf_document)):
                    page = pdf_document.load_page(page_num)
                    pdf_text += page.get_text()

                # Write the extracted text to a .txt file
                txt_file_path = os.path.join(self.output_dir, f"{os.path.splitext(file_name)[0]}.txt")
                with open(txt_file_path, "w", encoding="utf-8") as txt_file:
                    txt_file.write(pdf_text)
