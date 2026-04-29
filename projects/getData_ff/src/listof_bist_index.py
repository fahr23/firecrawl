import requests
from bs4 import BeautifulSoup
import csv
import os

def parse_bist_companies():
    # URL of the page to scrape
    url = "https://www.kap.org.tr/tr/Endeksler"

    # Send a GET request to the URL
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch data. HTTP Status Code: {response.status_code}")
        return

    # Parse the page content using BeautifulSoup
    soup = BeautifulSoup(response.content, "html.parser")

    # Find all <div> tags with class 'column-type7 wmargin'
    columns = soup.find_all("div", {"class": "column-type7 wmargin"})
    
    if not columns:
        print("Failed to find any columns on the page.")
        return

    # Loop through each column and extract the data
    for column in columns:
        # Extract the title of the column from the previous sibling div
        title_div = column.find_previous_sibling("div", {"class": "column-type1 wide vtable offset"})
        if not title_div:
            print("Failed to find title div for column.")
            continue
        title = title_div.find("div", {"class": "vcell"}).text.strip()
        
        # Find all company rows within the column
        rows = column.select("div.w-clearfix.w-inline-block.comp-row, div.w-clearfix.w-inline-block.comp-row.even")
        
        if not rows:
            print(f"Failed to find company rows in column: {title}")
            continue

        # List to store company codes and names
        company_data = []

        # Loop through the rows and extract company codes and names
        for row in rows:
            code_div = row.find("div", {"class": "comp-cell _02 vtable"})
            name_div = row.find("div", {"class": "comp-cell _03 vtable"})
            if code_div and name_div:
                code = code_div.find("a", {"class": "vcell"}).text.strip()
                name = name_div.find("a", {"class": "vcell"}).text.strip()
                company_data.append((f"{code}.IS", name))

        # Create a directory to store the CSV files if it doesn't exist
        os.makedirs('bist_companies', exist_ok=True)

        # Write the company data to a CSV file named after the column title
        filename = f'bist_companies/{title}.csv'
        with open(filename, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(['Code.IS', 'Name'])
            csvwriter.writerows(company_data)

        # Print the company data
        for code, name in company_data:
            print(f"{code}.IS, {name}")

if __name__ == "__main__":
    parse_bist_companies()