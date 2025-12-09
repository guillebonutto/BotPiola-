import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta

# Importar módulos propios
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from patterns import PatternRecognizer

# Importar estrategias
from strategy_stochastic import StrategyStochastic
from strategy_continuation import StrategyContinuation
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure

# --- Configuración ---
PAIRS = ['EURUSD_otc', 'GBPUSD_otc', 'AUDUSD_otc', 'USDCAD_otc', 'AUDCAD_otc', 'USDMXN_otc', 'USDCOP_otc']
INTERVAL = 300  # 5 minutos
LOOKBACK = 100 # Reducido para evitar timeouts

class TradingBot:
    def __init__(self, ssid):
        self.api = PocketOptionAsync(ssid)
        self.analyzer = MarketAnalyzer()
        self.pattern_recognizer = PatternRecognizer()
        
        # Estado de trading
        self.active_trade_expiry = datetime.min.replace(tzinfo=timezone.utc)
        
        # Inicializar lista de estrategias activas
        self.strategies = [
            StrategyStochastic(),
            StrategyContinuation(),
            StrategyFibonacci(),
            StrategyStructure()
        ]

    async def fetch_data(self, pair):
        """Obtiene velas y prepara el DataFrame."""
        offset = INTERVAL * LOOKBACK
        try:
            # Añadido timeout de 10 segundos
            candles = await asyncio.wait_for(self.api.get_candles(pair, INTERVAL, offset), timeout=10.0)
            df = pd.DataFrame(candles)
            if df.empty:
                print(f"  [WARN] Dataframe vacío para {pair}")
                return df
            
            # Normalizar columnas (manejar minúsculas/mayúsculas)
            df.columns = [c.lower() for c in df.columns]
            
            # Mapeo esperado
            rename_map = {'time': 'Timestamp', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low'}
            df.rename(columns=rename_map, inplace=True)
            
            # Verificar que existan las columnas críticas
            required = ['Open', 'High', 'Low', 'Close']
            if not all(col in df.columns for col in required):
                print(f"  [ERR] Columnas faltantes en {pair}. Las que hay: {df.columns.tolist()}")
                return pd.DataFrame()
                
            # Convertir Timestamp
            if 'Timestamp' in df.columns:
                 # Fix DeprecationWarning by using timezone-aware now
                 df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', utc=True)
            else:
                 # Fallback if no timestamp
                 df['Timestamp'] = pd.Timestamp.now(tz=timezone.utc)
            
            # Convertir a numeric
            for c in required:
                df[c] = pd.to_numeric(df[c])
            
            return df
            
        except asyncio.TimeoutError:
            print(f"  [WARN] Timeout obteniendo datos de {pair}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error fetching {pair}: {e}")
            return pd.DataFrame()

    async def analyze_pair(self, pair):
        """Pipeline completo de análisis para un par."""
        print(f"Analizando {pair}...")
        df = await self.fetch_data(pair)
        if df.empty:
            return None

        # 1. Análisis Fundamental (Noticias)
        news_status = self.analyzer.check_news()
        # Si hay noticias de alto impacto, podríamos decidir no operar (PENDIENTE de lógica)
        
        # 2. Análisis Técnico (Indicadores)
        df = self.analyzer.compute_indicators(df)
        
        # 3. Reconocimiento de Patrones
        df = self.pattern_recognizer.find_candlestick_patterns(df)
        df = self.pattern_recognizer.find_chart_patterns(df)
        
        # 4. Estado del Mercado
        market_state = self.analyzer.determine_market_state(df)
        # print(f"  > Estado Mercado: {market_state}")

        # 5. Consultar Estrategias
        signals = []
        for strategy in self.strategies:
            action, reason, duration = strategy.get_signal(df)
            if action in ['BUY', 'SELL']:
                print(f"  >>> SEÑAL DETECTADA en {pair} por {strategy.name}: {action} ({reason})")
                signals.append((action, duration, strategy.name))
        
        if not signals:
            return None
            
        # Sistema de Votación o Prioridad
        # Por ahora, tomamos la primera señal válida
        return signals[0]

    async def run(self):
        print("--- INICIANDO BOT DE TRADING AVANZADO ---\n")
        print("--- MODO SEGURO: Máx 1 operación simultánea ---\n")
        
        while True:
            # 0. Chequeo de Concurrencia
            now_utc = datetime.now(timezone.utc)
            if now_utc < self.active_trade_expiry:
                remaining = (self.active_trade_expiry - now_utc).total_seconds()
                print(f"[{now_utc.strftime('%H:%M:%S')}] Operación en curso. Esperando {int(remaining)}s para finalizar...")
                await asyncio.sleep(5)
                continue

            for pair in PAIRS:
                # Chequeo doble por si se tardó mucho en el loop anterior
                if datetime.now(timezone.utc) < self.active_trade_expiry:
                    break
                    
                signal = await self.analyze_pair(pair)
                
                if signal:
                    action, duration, strat_name = signal
                    print(f"EJECUTANDO ORDEN: {action} en {pair} por {duration}s. Estrategia: {strat_name}")
                    
                    try:
                        amount = 1.0 # Monto fijo por ahora
                        if action == 'BUY':
                            await self.api.buy(asset=pair, amount=amount, time=duration, check_win=False)
                        else:
                            await self.api.sell(asset=pair, amount=amount, time=duration, check_win=False)
                        
                        # Actualizar bloqueo de concurrencia
                        # Agregamos 5 segundos extra de margen de seguridad
                        self.active_trade_expiry = datetime.now(timezone.utc) + timedelta(seconds=duration + 5)
                        print(f"  >>> Bloqueando nuevas operaciones por {duration + 5} segundos.")
                        
                        # Salir del loop de pares para respetar el bloqueo inmediatamente
                        break 
                        
                    except Exception as e:
                        print(f"Error ejecutando orden: {e}")
                        
                else:
                    # print(f"Sin señal clara en {pair}")
                    pass
                
                await asyncio.sleep(2) # Pausa entre pares para no saturar
            
            print("Ciclo completado. Esperando...")
            await asyncio.sleep(10)

async def main():
    ssid = input("Introduce tu SSID de PocketOption: ").strip()
    bot = TradingBot(ssid)
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
