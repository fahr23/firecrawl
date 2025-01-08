import psycopg2

# Database connection parameters
db_params = {
    "host": "host.docker.internal",
    "database": "backtofuture",
    "user": "postgres",
    "password": "backtofuture"
}

try:
    # Establish database connection
    conn = psycopg2.connect(**db_params)
    cur = conn.cursor()
    
    # Test query (replace 'your_table_name' with an actual table name)
    cur.execute("select * from backtofuture.dataff.kap_disclosures_info;")
    result = cur.fetchone()
    if result:
        print("Database connection test successful.")
    else:
        print("Database connection test failed.")
    
    # Close cursor and connection
    cur.close()
    conn.close()
except psycopg2.OperationalError as e:
    print(f"Database connection failed: {e}")