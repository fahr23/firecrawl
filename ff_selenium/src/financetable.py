import pdfplumber
import pandas as pd
import psycopg2
from psycopg2 import sql
import re

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
        """
        Create a table if it does not exist.
        """
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
        """
        Add a missing column to an existing table.
        """
        try:
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
        except psycopg2.Error as e:
            self.connection.rollback()
            print(f"Error adding column {column}: {e}")
            raise e

    def insert_data(self, table_name, columns, data):
        """
        Insert data into a table, dynamically adding missing columns if required.
        """
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
            print(f"Missing column detected: {missing_column}. Adding it to the table.")
            self.add_column(table_name, missing_column)
            self.insert_data(table_name, columns, data)

def camel_case(s):
    """
    Convert a string to camelCase, removing special characters and spaces.
    """
    if not s:
        return s
    s = re.sub(r'[^a-zA-Z0-9]', '', s)
    s = s.title().replace(" ", "")
    return s[0].lower() + s[1:]

def save_table_to_db(table, page_num, table_num, db_manager):
    """
    Save a table to the database, creating or updating schema as needed.
    """
    df = pd.DataFrame(table[1:], columns=table[0])
    # Normalize column names
    df.columns = [camel_case(col.strip()) if col and col.strip() else f"column_{i}" for i, col in enumerate(df.columns)]
    print(f"Columns: {df.columns}")
    print(f"Page {page_num}, Table {table_num}")
    print(df)
    table_name = f"page_{page_num}_table_{table_num}"
    db_manager.create_table(table_name, df.columns)
    for _, row in df.iterrows():
        db_manager.insert_data(table_name, df.columns, tuple(row))
    print(f"Saved data from page {page_num}, table {table_num} to database.")

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
    # return table[0] is not None and not any(col and col.strip() for col in table[0])

# Main script
db_manager = DatabaseManager(db_params)

with pdfplumber.open("/root/kap_pdfs/ff.pdf") as pdf:
    accumulated_table = []
    for page_num, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        if tables:
            last_table = tables[-1]  # Take only the last table on the page
            if is_continuing_table(last_table, page):
                accumulated_table.extend(last_table)  # Skip headers
            else:
                if accumulated_table:
                    save_table_to_db(accumulated_table, page_num, 1, db_manager)
                    accumulated_table = []
                accumulated_table.extend(last_table)
    if accumulated_table:
        save_table_to_db(accumulated_table, page_num, 1, db_manager)