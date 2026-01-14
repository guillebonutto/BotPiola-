import cloudscraper
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import pandas as pd

class NewsFetcher:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.base_url = "https://www.investing.com/economic-calendar/"
        self.last_fetch = None
        self.news_cache = []

    def fetch_news(self):
        """Obtiene las noticias del día de Investing.com vía JSON."""
        try:
            print(f"[{datetime.now()}] 🌐 Obteniendo calendario económico (JSON)...")
            response = self.scraper.get(self.base_url)
            if response.status_code != 200:
                print(f"⚠️ Error al acceder a Investing.com: {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if not script:
                print("⚠️ No se encontró el tag __NEXT_DATA__.")
                return []

            data = json.loads(script.string)
            ec_store = data.get('props', {}).get('pageProps', {}).get('state', {}).get('economicCalendarStore', {})
            events_by_date = ec_store.get('calendarEventsByDate', {})

            all_events = []
            for date_str, events in events_by_date.items():
                for ev in events:
                    try:
                        # Convertir tiempo ISO a objeto datetime
                        # Formato: "2026-01-13T00:01:00Z"
                        event_time = datetime.fromisoformat(ev['time'].replace('Z', '+00:00'))
                        # Convertir a hora local (asumiendo que el bot corre en hora local)
                        event_time = event_time.astimezone().replace(tzinfo=None)

                        all_events.append({
                            'time': event_time,
                            'currency': ev.get('currency', ''),
                            'impact': int(ev.get('importance', 0)),
                            'event': ev.get('event', '')
                        })
                    except Exception:
                        continue

            self.news_cache = all_events
            self.last_fetch = datetime.now()
            print(f"✅ Se cargaron {len(all_events)} eventos económicos.")
            return all_events

        except Exception as e:
            print(f"❌ Error fatal en NewsFetcher: {e}")
            return []

    def get_upcoming_high_impact_news(self, currency_pair, window_minutes=15):
        """
        Verifica si hay noticias de alto impacto pronto para las monedas del par.
        """
        if not self.news_cache or (datetime.now() - self.last_fetch).total_seconds() > 3600:
            self.fetch_news()

        # Extraer monedas del par
        clean_pair = currency_pair.replace('_otc', '')
        base = clean_pair[:3]
        quote = clean_pair[3:6]
        target_currencies = [base, quote]

        now = datetime.now()
        start_window = now - timedelta(minutes=window_minutes)
        end_window = now + timedelta(minutes=window_minutes)

        high_impact_events = []
        for event in self.news_cache:
            if event['impact'] >= 3 and event['currency'] in target_currencies:
                if start_window <= event['time'] <= end_window:
                    high_impact_events.append(event)

        return high_impact_events

if __name__ == "__main__":
    fetcher = NewsFetcher()
    news = fetcher.fetch_news()
    for n in news:
        if n['impact'] >= 3:
            print(f"{n['time'].strftime('%H:%M')} | {n['currency']} | Impacto: {n['impact']} | {n['event']}")
