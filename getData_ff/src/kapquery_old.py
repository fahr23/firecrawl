# docker volume create pgdata
# docker run -d --name backtofuturePostgre -e POSTGRES_PASSWORD=backtofuture -v pgdata:/var/lib/postgresql/data -p 5432:5432 postgres:latest

import requests
import psycopg2


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

# Define the URL and payload
url = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
payload = {
    "fromDate": "2024-07-03",
    "toDate": "2024-07-04",
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

# Make the HTTP POST request
response = requests.post(url, json=payload)
data = response.json()

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
for item in data:
    cur.execute(insert_query, (
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

# Commit changes and close connection
conn.commit()
cur.close()
conn.close()