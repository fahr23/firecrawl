from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
import time

url = "https://tr.tradingview.com/markets/cryptocurrencies/prices-all/"

options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)
driver.get(url)
time.sleep(5)  # Wait for JS to load content

soup = BeautifulSoup(driver.page_source, "html.parser")
driver.quit()

symbols = []
for a_tag in soup.find_all("a", class_="tickerNameBox-GrtoTeat tickerName-GrtoTeat"):
    if a_tag.has_attr("href"):
        match = re.search(r'/symbols/([A-Z0-9]+)/', a_tag["href"])
        if match:
            symbols.append(match.group(1))

symbols = sorted(set(symbols))

formatted = 'fetch_instruments_symbols_from_db = [\n'
formatted += ',\n'.join(f'"{s}"' for s in symbols)
formatted += '\n]'

print(formatted)