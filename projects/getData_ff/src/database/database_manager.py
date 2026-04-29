import psycopg2
from psycopg2 import sql

class DatabaseManager:
    def __init__(self, db_params, schema="public"):
        self.connection = psycopg2.connect(
            dbname=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"]
        )
        self.cursor = self.connection.cursor()
        self.schema = schema
        self.create_kap_disclosures_table()
        

    def create_kap_disclosures_table(self):
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
        self.connection.commit()

    def insert_kap_disclosures_data(self, data):
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
        self.connection.commit()

    def create_temel_analiz_table(self, table_name, columns):
        """
        Drop the table if it exists, then create a new table.
        """
        columns_with_types = ", ".join([f'"{col}" TEXT' for col in columns])
        
        drop_table_query = sql.SQL("""
            DROP TABLE IF EXISTS {schema}.{table_name}
        """).format(
            schema=sql.Identifier(self.schema),
            table_name=sql.Identifier(table_name)
        )
        
        create_table_query = sql.SQL("""
            CREATE TABLE {schema}.{table_name} (
                {columns_with_types}
            )
        """).format(
            schema=sql.Identifier(self.schema),
            table_name=sql.Identifier(table_name),
            columns_with_types=sql.SQL(columns_with_types)
        )
        
        self.cursor.execute(drop_table_query)
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

    def insert_temel_analiz_data(self, table_name, columns, data):
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
            self.insert_temel_analiz_data(table_name, columns, data)