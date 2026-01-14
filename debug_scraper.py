import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)
url = "https://www.investing.com/economic-calendar/"
response = scraper.get(url)
print(f"Status: {response.status_code}")
print(f"Content Length: {len(response.text)}")
with open("debug_investing.html", "w", encoding="utf-8") as f:
    f.write(response.text)

soup = BeautifulSoup(response.text, 'html.parser')
# Buscar cualquier tabla
tables = soup.find_all('table')
print(f"Found {len(tables)} tables")
for i, table in enumerate(tables):
    print(f"Table {i}: id={table.get('id')}, class={table.get('class')}")

# Buscar el id específico que esperábamos
target = soup.find('table', {'id': 'economicCalendarData'})
print(f"Target table found: {target is not None}")
