import cloudscraper
from bs4 import BeautifulSoup
import json
from datetime import datetime

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)
url = "https://www.investing.com/economic-calendar/"
response = scraper.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
script = soup.find('script', id='__NEXT_DATA__')

if script:
    data = json.loads(script.string)
    # Guardar para inspección
    with open("next_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    print("✅ __NEXT_DATA__ extraído y guardado en next_data.json")
    
    # Intentar encontrar los eventos en el JSON
    # La estructura suele ser props -> pageProps -> initialData o similar
    try:
        # Esto es un ejemplo, la ruta real puede variar
        # props -> pageProps -> state -> ecEvents (o algo así)
        print("Estructura de llaves en props.pageProps:")
        print(data.get('props', {}).get('pageProps', {}).keys())
    except Exception as e:
        print(f"Error inspeccionando JSON: {e}")
else:
    print("❌ No se encontró el tag __NEXT_DATA__")
