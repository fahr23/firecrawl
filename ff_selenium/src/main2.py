import requests
from bs4 import BeautifulSoup

def main():
    # URL to fetch
    url = "https://www.kap.org.tr/tr/Bildirim/1307324"
    
    # Send a GET request
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract the href value
        a_tag = soup.find('a', class_="modal-attachment type-xsmall bi-sky-black maximize")
        if a_tag:
            href_value = a_tag.get('href')
            print(f"PDF Link: https://www.kap.org.tr{href_value}")
        else:
            print("PDF link not found.")
        
        # Extract the time value
        div_tag = soup.find('div', class_="type-medium bi-sky-black")
        if div_tag:
            time_value = div_tag.text
            print(f"Time Value: {time_value}")
        else:
            print("Time value not found.")
    else:
        print("Failed to fetch the page.")

if __name__ == "__main__":
    main()