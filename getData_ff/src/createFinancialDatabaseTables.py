# Description: Extract financial tables from PDFs and save them to a PostgreSQL database.
import pdfplumber
import pandas as pd
import psycopg2
from psycopg2 import sql
import re
import os

from database.database_manager import DatabaseManager

# Database configuration
db_params = {
    "host": "timescaledb",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}


# Main script
db_manager = DatabaseManager(db_params,schema="temelanaliz")

def camel_case(s):
    """
    Convert a string to camelCase, removing special characters and spaces.
    """
    if not s:
        return s
    
    # Mapping of Turkish characters to English equivalents
    turkish_to_english = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(turkish_to_english)
    
    s = re.sub(r'[^a-zA-Z0-9]', '', s)
    s = s.title().replace(" ", "")
    return s[0].lower() + s[1:]

def save_temel_analiz_table_to_db(table, page_num, db_manager, symbol, report_info_cleaned):
    """
    Save a table to the database, creating or updating schema as needed.
    """
    df = pd.DataFrame(table[1:], columns=table[0])
    # Normalize column names
    df.columns = [camel_case(col.strip()) if col and col.strip() else f"column_{i}" for i, col in enumerate(df.columns)]
    # print(f"Columns: {df.columns}")
    # print(f"Page {page_num}")
    # print(df)
    table_name = f"{symbol}_{report_info_cleaned}_page_{page_num}"
    db_manager.create_temel_analiz_table(table_name, df.columns)
    for _, row in df.iterrows():
        db_manager.insert_temel_analiz_data(table_name, df.columns, tuple(row))
    print(f"Saved data from page {page_num} to database.")

def has_images(page):
    """
    Check if the page contains any images or icons.
    """
    return len(page.images) > 0

def is_continuing_table(table, page):
    """
    Determine if a table is continuing from the previous page.
    If the page includes an icon picture, then the table is new.
    If the table exists but the icon picture does not exist in the page, then the table is continuing.
    """
    if has_images(page):
        return False  # New table since the page has images
    return True


pdf_directory = "/root/kap_pdfs/"

for pdf_file in os.listdir(pdf_directory):
    if pdf_file.endswith(".pdf"):
        print(f"Processing {pdf_file}")
        pdf_path = os.path.join(pdf_directory, pdf_file)
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            # Extract company name
            company_match = re.search(r"KAMUYU AYDINLATMA PLATFORMU\s+(.+?)\s+A\.Ş\.", text)
            if company_match:
                company_name = company_match.group(1)
                company_name = company_name + " A.Ş."
                
                # Select the symbol from the data_bist_stocks table based on the company name
                select_symbol_query = """
                SELECT symbol FROM data_bist_stocks WHERE company_name = %s;
                """
                db_manager.cursor.execute(select_symbol_query, (company_name,))
                result = db_manager.cursor.fetchone()
                if result:
                    symbol = result[0]
                else:
                    print(f"No symbol found for company name: {company_name}")
                    symbol = re.sub(r'\s+', '', company_name)  # Remove spaces and new lines
                    # continue  # Skip processing this PDF if no symbol is found
            
            # Extract specific text between "Finansal Rapor" and "Finansal Tablolara ilişkin Genel Açıklama"
            report_match = re.search(r"Finansal Rapor\s+(.*?)\s+Finansal Tablolara ilişkin Genel Açıklama", text, re.DOTALL)
            if report_match:
                report_info = report_match.group(1).strip()
                report_info_cleaned = re.sub(r'\s+', '', report_info)  # Remove spaces and new lines
                print(f"Report Info: {report_info_cleaned}")
            else:
                print("No report info found.")
                continue  # Skip processing this PDF if no report info is found
            
            accumulated_table = []
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if tables:
                    last_table = tables[-1]  # Take only the last table on the page
                    if is_continuing_table(last_table, page):
                        accumulated_table.extend(last_table)  # Skip headers
                    else:
                        if accumulated_table:
                            save_temel_analiz_table_to_db(accumulated_table, page_num, db_manager, symbol, report_info_cleaned)
                            accumulated_table = []
                        accumulated_table.extend(last_table)
            if accumulated_table:
                save_temel_analiz_table_to_db(accumulated_table, page_num, db_manager, symbol, report_info_cleaned)