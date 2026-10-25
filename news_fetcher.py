import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

class NewsFetcher:
    def __init__(self, cache_file="news_cache.json"):
        self.cache_file = Path(cache_file)
        self.last_fetch = None
        self.news_cache = []
        self._load_disk_cache()

    def _load_disk_cache(self):
        """Carga eventos económicos previos desde el archivo de caché local."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    events = []
                    for item in data.get("events", []):
                        events.append({
                            'time': datetime.fromisoformat(item['time']),
                            'currency': item['currency'],
                            'impact': int(item['impact']),
                            'event': item['event']
                        })
                    self.news_cache = events
                    last_str = data.get("last_fetch")
                    if last_str:
                        self.last_fetch = datetime.fromisoformat(last_str)
            except Exception:
                pass

    def _save_disk_cache(self):
        """Guarda eventos económicos en el archivo de caché local."""
        try:
            data = {
                'last_fetch': self.last_fetch.isoformat() if self.last_fetch else datetime.now().isoformat(),
                'events': [
                    {
                        'time': e['time'].isoformat(),
                        'currency': e['currency'],
                        'impact': e['impact'],
                        'event': e['event']
                    }
                    for e in self.news_cache
                ]
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _fetch_tradingview(self):
        """Obtiene el calendario económico desde la API oficial de TradingView (rápido y sin bloqueos)."""
        now_utc = datetime.now(timezone.utc)
        from_str = (now_utc - timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        to_str = (now_utc + timedelta(days=2)).strftime('%Y-%m-%dT23:59:59.000Z')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Origin': 'https://www.tradingview.com',
            'Referer': 'https://www.tradingview.com/',
        }
        params = {'from': from_str, 'to': to_str}
        
        resp = requests.get('https://economic-calendar.tradingview.com/events', headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None
            
        events = resp.json().get('result', [])
        parsed = []
        for ev in events:
            try:
                dt = datetime.fromisoformat(ev['date'].replace('Z', '+00:00'))
                local_dt = dt.astimezone().replace(tzinfo=None)
                
                # TradingView: 1 = Alto impacto, 0 = Medio/Bajo, -1 = Feriado
                raw_imp = ev.get('importance', 0)
                impact = 3 if raw_imp == 1 else (2 if raw_imp == 0 else 1)
                
                parsed.append({
                    'time': local_dt,
                    'currency': ev.get('currency', '').upper(),
                    'impact': impact,
                    'event': ev.get('title', '')
                })
            except Exception:
                continue
        return parsed

    def _fetch_forexfactory(self):
        """Fuente secundaria: Calendario semanal JSON de ForexFactory / FairEconomy."""
        url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        parsed = []
        impact_map = {'High': 3, 'Medium': 2, 'Low': 1}
        for ev in data:
            try:
                dt = datetime.fromisoformat(ev['date'])
                local_dt = dt.astimezone().replace(tzinfo=None)
                imp_str = ev.get('impact', 'Low')
                parsed.append({
                    'time': local_dt,
                    'currency': ev.get('country', '').upper(),
                    'impact': impact_map.get(imp_str, 1),
                    'event': ev.get('title', '')
                })
            except Exception:
                continue
        return parsed

    def fetch_news(self):
        """
        Obtiene las noticias económicas del día mediante proveedores de alta disponibilidad
        (TradingView API -> ForexFactory -> Caché local).
        """
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🌐 Obteniendo calendario económico...")
            
            # 1. Intentar TradingView API (Primario)
            try:
                tv_events = self._fetch_tradingview()
                if tv_events and len(tv_events) > 0:
                    self.news_cache = tv_events
                    self.last_fetch = datetime.now()
                    self._save_disk_cache()
                    print(f"✅ Se cargaron {len(tv_events)} eventos económicos (TradingView).")
                    return self.news_cache
            except Exception as e:
                pass

            # 2. Intentar ForexFactory (Secundario)
            try:
                ff_events = self._fetch_forexfactory()
                if ff_events and len(ff_events) > 0:
                    self.news_cache = ff_events
                    self.last_fetch = datetime.now()
                    self._save_disk_cache()
                    print(f"✅ Se cargaron {len(ff_events)} eventos económicos (ForexFactory).")
                    return self.news_cache
            except Exception as e:
                pass

            # 3. Usar respaldo de caché en memoria / disco
            if self.news_cache:
                print(f"ℹ️ Usando {len(self.news_cache)} eventos económicos desde la memoria caché.")
                return self.news_cache

            print("⚠️ No se pudieron obtener noticias en vivo en este momento.")
            return []

        except Exception as e:
            print(f"❌ Error en NewsFetcher: {e}")
            return self.news_cache if self.news_cache else []

    def get_upcoming_high_impact_news(self, currency_pair, window_minutes=15):
        """
        Verifica si hay noticias de alto impacto (impact >= 3) para las monedas del par en la ventana de tiempo.
        """
        if not self.news_cache or not self.last_fetch or (datetime.now() - self.last_fetch).total_seconds() > 3600:
            self.fetch_news()

        # Extraer monedas del par
        clean_pair = currency_pair.replace('_otc', '').replace('/', '')
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
    high = [n for n in news if n['impact'] >= 3]
    print(f"\n--- {len(high)} NOTICIAS DE ALTO IMPACTO ---")
    for n in high[:10]:
        print(f"{n['time'].strftime('%d/%m %H:%M')} | {n['currency']} | Impacto: {n['impact']} | {n['event']}")
