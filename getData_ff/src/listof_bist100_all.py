import requests
from bs4 import BeautifulSoup
import csv

def parse_bist_companies():
    # URL of the page to scrape
    url = "https://www.kap.org.tr/tr/bist-sirketler"

    # Send a GET request to the URL
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch data. HTTP Status Code: {response.status_code}")
        return

    # Parse the page content using BeautifulSoup
    soup = BeautifulSoup(response.content, "html.parser")

    # Find all <div> tags with class 'comp-cell _04 vtable' and 'comp-cell _14 vtable'
    code_divs = soup.find_all("div", {"class": "comp-cell _04 vtable"})
    name_divs = soup.find_all("div", {"class": "comp-cell _14 vtable"})
    
    if not code_divs or not name_divs:
        print("Failed to find any company codes or names on the page.")
        return

    # List to store company codes and names
    company_data = []

    # Loop through the divs and extract company codes and names
    for code_div, name_div in zip(code_divs, name_divs):
        code = code_div.find("a", {"class": "vcell"}).text.strip()
        name = name_div.find("a", {"class": "vcell"}).text.strip()
        company_data.append((f"{code}.IS", name))

    # Write the company data to a CSV file
    with open('bist_companies.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(['Code.IS', 'Name'])
        csvwriter.writerows(company_data)

    # Print the company data
    for code, name in company_data:
        print(f"{code}.IS, {name}")

    # Print the count of company codes
    print(f"Total number of companies: {len(company_data)}")

if __name__ == "__main__":
    parse_bist_companies()