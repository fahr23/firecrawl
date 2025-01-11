import pdfplumber
import pandas as pd
import psycopg2
from psycopg2 import sql

# Path to the PDF
pdf_path = "/root/kap_pdfs/ff.pdf"

# Database configuration
db_params = {
    "host": "timescaledb",
    "database": "backtofuture",
    "user": "backtofuture",
    "password": "back2future"
}

class DatabaseManager:
    def __init__(self, db_params, schema="temelanaliz"):
        self.connection = psycopg2.connect(
            dbname=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"]
        )
        self.cursor = self.connection.cursor()
        self.schema = schema

    def create_table(self, table_name, columns):
        columns_with_types = ", ".join([f'"{col}" TEXT' for col in columns])
        create_table_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {schema}.{table_name} (
                {columns_with_types}
            )
        """).format(
            schema=sql.Identifier(self.schema),
            table_name=sql.Identifier(table_name),
            columns_with_types=sql.SQL(columns_with_types)
        )
        self.cursor.execute(create_table_query)
        self.connection.commit()

    def add_column(self, table_name, column):
        add_column_query = sql.SQL("""
            ALTER TABLE {schema}.{table_name}
            ADD COLUMN {column} TEXT
        """).format(
            schema=sql.Identifier(self.schema),
            table_name=sql.Identifier(table_name),
            column=sql.Identifier(column)
        )
        self.cursor.execute(add_column_query)
        self.connection.commit()

    def insert_data(self, table_name, columns, data):
        columns_str = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["%s"] * len(columns))
        insert_query = sql.SQL("""
            INSERT INTO {schema}.{table_name} ({columns})
            VALUES ({placeholders})
        """).format(
            schema=sql.Identifier(self.schema),
            table_name=sql.Identifier(table_name),
            columns=sql.SQL(columns_str),
            placeholders=sql.SQL(placeholders)
        )
        try:
            self.cursor.execute(insert_query, data)
            self.connection.commit()
        except psycopg2.errors.UndefinedColumn as e:
            self.connection.rollback()
            missing_column = str(e).split('"')[1]
            self.add_column(table_name, missing_column)
            self.cursor.execute(insert_query, data)
            self.connection.commit()

import re

def camel_case(s):
    if not s:
        return s
    # Remove special characters and spaces
    s = re.sub(r'[^a-zA-Z0-9]', '', s)
    s = s.title().replace(" ", "")
    return s[0].lower() + s[1:]

# Function to clean and save data
def save_table_to_db(table, page_num, table_num, db_manager):
    # Convert to DataFrame
    df = pd.DataFrame(table[1:], columns=table[0])
    # Clean column names
    df.columns = [camel_case(col.strip()) if col and col.strip() else f"column_{i}" for i, col in enumerate(df.columns)]
    print(f"Columns: {df.columns}")
    print(f"Page {page_num}, Table {table_num}")
    print(df)
    # Create table in the database
    table_name = f"page_{page_num}_table_{table_num}"
    db_manager.create_table(table_name, df.columns)
    # Save to database
    for _, row in df.iterrows():
        data = tuple(row)
        try:
            db_manager.insert_data(table_name, df.columns, data)
        except psycopg2.errors.UndefinedColumn as e:
            missing_column = str(e).split('"')[1]
            db_manager.add_column(table_name, missing_column)
            db_manager.insert_data(table_name, df.columns, data)
    print(f"Saved data from page {page_num}, table {table_num} to database.")

# Function to check if a table is continuing from the previous page
def is_continuing_table(table):
    # Implement logic to determine if the table is continuing
    # For example, check if the first row of the table is a header or not
    return table[0][0] == ''

# Example usage
db_manager = DatabaseManager(db_params)

with pdfplumber.open(pdf_path) as pdf:
    accumulated_table = []
    for page_num, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        for table_num, table in enumerate(tables, start=1):
            if is_continuing_table(table):
                accumulated_table.extend(table[1:])  # Skip the header row
            else:
                if accumulated_table:
                    save_table_to_db(accumulated_table, page_num, table_num, db_manager)
                    accumulated_table = []
                accumulated_table.extend(table)
    if accumulated_table:
        save_table_to_db(accumulated_table, page_num, table_num, db_manager)