import asyncio
import pandas as pd
import html
from datetime import datetime, timezone, timedelta
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from patterns import PatternRecognizer
from telegram_bot import TelegramNotifier
from strategy_stochastic import StrategyStochastic
from strategy_continuation import StrategyContinuation
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure
from trade_logger import trade_logger
from feedback_db import FeedbackDB
import uuid
import json
from pathlib import Path

# --- Configuración ---
PAIRS = ['EURUSD_otc', 'GBPUSD_otc', 'AUDUSD_otc', 'USDCAD_otc', 'AUDCAD_otc', 'USDMXN_otc', 'USDCOP_otc']
INTERVAL = 300  # 5 minutos
LOOKBACK = 300 # Aumentado a 300 para cubrir SMA 200
VERBOSE = True # Modo Depuración: Imprimir todas las razones de HOLD
VERBOSE_TELEGRAM = True # Enviar reporte de DEBUG a Telegram (Resumen por ciclo)

class TradingBot:
    def __init__(self, ssid, telegram_token=None, telegram_chat_id=None, telegram_owner_id=None):
        self.api = PocketOptionAsync(ssid)
        self.analyzer = MarketAnalyzer()
        self.pattern_recognizer = PatternRecognizer()
        self.notifier = TelegramNotifier(
            telegram_token, 
            telegram_chat_id, 
            telegram_owner_id,
            get_balance_callback=self.get_balance
        )
        
        # Estado de trading
        self.active_trade_expiry = datetime.min.replace(tzinfo=timezone.utc)
        
        # Inicializar lista de estrategias activas
        self.strategies = [
            StrategyStochastic(),
            StrategyContinuation(),
            StrategyFibonacci(),
            StrategyStructure()
        ]
        
        # Base de datos de feedback y mantenimiento
        self.db = FeedbackDB()
        self.db.maintain()
        
        # Inteligencia Artificial (Filtros Históricos)
        self.intelligence = self._load_intelligence()

        # --- GESTIÓN DE RIESGO ---
        self.daily_stop_loss = -15.0  # Parar si perdemos $15 en la sesión
        self.daily_take_profit = 10.0 # Asegurar ganancias si ganamos $10
        self.session_profit = 0.0
        self.strategy_fails = {}      # Seguimiento de rachas negativas por sesión

    def _load_intelligence(self):
        """Carga el mapa de confianza generado por analyze_best_times.py."""
        try:
            path = Path('trading_intelligence.json')
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"🧠 Inteligencia de trading cargada (Actualizada: {data.get('last_update', 'N/A')})")
                    return data
        except Exception as e:
            print(f"⚠️ Error cargando inteligencia: {e}")
        return None

    def is_allowed_by_ai(self, pair, strategy):
        """Verifica si la IA aprueba esta operación basada en el historial y racha."""
        if not self.intelligence:
            return True, "No intelligence data"
            
        current_hour = datetime.now().hour
        
        # 1. Filtro de Racha Negativa (Session)
        if self.strategy_fails.get(strategy, 0) >= 3:
            return False, f"Estrategia en racha negativa (Session Fails: {self.strategy_fails[strategy]})"

        # 2. Verificar Zonas de Riesgo por Hora/Par
        for zone in self.intelligence.get('risk_zones', []):
            if zone['hour'] == current_hour and zone['pair'] == pair:
                return False, f"Zona de Riesgo (Histórico WR: {zone['win_rate']*100:.1f}%)"
        
        # 3. Filtro de Rendimiento Histórico por Estrategia
        for s_stats in self.intelligence.get('strategy_performance', []):
            if s_stats['strategy'] == strategy and s_stats['win_rate'] < 0.48:
                return False, f"Bajo rendimiento histórico ({s_stats['win_rate']*100:.1f}% WR)"

        return True, "Approved"

    async def get_balance(self):
        """Obtiene el balance actual de la cuenta."""
        try:
            return await self.api.balance()
        except Exception as e:
            print(f"[Bot] Error obteniendo balance: {e}")
            return "Error"

    async def fetch_data(self, pair):
        """Obtiene velas y prepara el DataFrame."""
        offset = INTERVAL * LOOKBACK
        try:
            # Añadido timeout de 20 segundos total
            print(f"  [DEBUG] Fetching {pair} (Chunk 1)...")
            candles = await asyncio.wait_for(self.api.get_candles(pair, INTERVAL, offset), timeout=10.0)
            
            # Paginación si faltan datos (Límite API suele ser ~150)
            if len(candles) > 0 and len(candles) < 200:
                print(f"  [DEBUG] {pair}: Got {len(candles)} candles. Keys: {list(candles[0].keys())}")
                
                try:
                    # Detectar clave de tiempo (puede ser 'time', 'Time', 'timestamp')
                    time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
                    
                    if not time_key:
                        print(f"  [WARN] No time key found in candle data for {pair}")
                    else:
                        # Asumimos orden ascendente [Oldest ... Newest]
                        # ERROR FIX: Castear a int porque el API requiere entero, y a veces viene como float
                        oldest_time = int(candles[0][time_key])
                        print(f"  [DEBUG] Fetching Chunk 2 (Previous) ending at {oldest_time}...")
                        
                        # Pedimos otro bloque terminando en el tiempo más viejo del bloque 1
                        chunk2 = await asyncio.wait_for(
                            self.api.get_candles_advanced(pair, INTERVAL, offset, oldest_time), 
                            timeout=10.0
                        )
                        print(f"  [DEBUG] {pair}: Chunk 2 got {len(chunk2)} candles.")
                        
                        # Combinar: Chunk2 (Viejo) + Chunk1 (Nuevo)
                        full_data = chunk2 + candles
                        
                        # Usar la misma clave para de-duplicar
                        seen = set()
                        candles = []
                        for c in full_data:
                            # Asegurar que el chunk2 tenga la misma key (debería)
                            tk = next((k for k in c.keys() if k.lower() in ['time', 'timestamp', 'date']), time_key)
                            t_val = c.get(tk)
                            
                            if t_val is not None and t_val not in seen:
                                candles.append(c)
                                seen.add(t_val)
                        
                        # Re-ordenar por tiempo
                        candles.sort(key=lambda x: x.get(time_key, 0))
                        print(f"  [DEBUG] {pair}: Total combined candles: {len(candles)}")
                    
                except Exception as e:
                    print(f"  [WARN] Failed fetching chunk 2 for {pair}: {e}")
                    # Continuamos con lo que tenemos por si acaso
            
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
            return pd.DataFrame()
        except Exception as e:
            print(f"Error fetching {pair}: {e}")
            return pd.DataFrame()

    async def analyze_pair(self, pair):
        """Pipeline completo de análisis para un par."""
        print(f"Analizando {pair}...")
        
        # --- NUEVO FORMATO DE MENSAJE: Cabecera del Par ---
        cycle_log = f"\n🔹 <b>{pair}</b>"
        
        df = await self.fetch_data(pair)
        if df.empty:
            return None, {}, cycle_log + "\n   ⚠️ <i>Sin datos disponibles</i>"

        # 1. Análisis Fundamental (Noticias)
        news_status = self.analyzer.check_news()
        
        # 2. Análisis Técnico (Indicadores)
        df = self.analyzer.compute_indicators(df)
        
        # 3. Reconocimiento de Patrones
        df = self.pattern_recognizer.find_candlestick_patterns(df)
        df = self.pattern_recognizer.find_chart_patterns(df)
        
        # 4. Estado del Mercado
        market_state = self.analyzer.determine_market_state(df)

        # 5. Consultar Estrategias
        signals = []
        strategy_logs = []
        
        for strategy in self.strategies:
            action, reason, duration = strategy.get_signal(df)
            
            # Sanitizar textos para Telegram (escapar <, >, &)
            safe_reason = html.escape(str(reason)) if reason else ""
            safe_strat_name = html.escape(strategy.name)
            
            if action in ['BUY', 'SELL']:
                print(f"  >>> SEÑAL DETECTADA en {pair} por {strategy.name}: {action} ({reason})")
                signals.append((action, duration, strategy.name))
                # Formato lista indentada
                strategy_logs.append(f"   🔥 <b>{action}</b>: {safe_strat_name}\n      <i>{safe_reason}</i>")
            elif VERBOSE:
                print(f"  [{strategy.name}] HOLD: {reason}")
                # Simplificamos "HOLD" para no llenar pantalla, solo icono y texto
                strategy_logs.append(f"   ⏱ {safe_reason}")
        
        if strategy_logs:
            # Unir con saltos de línea
            cycle_log += "\n" + "\n".join(strategy_logs)
        else:
            cycle_log += "\n   <i>Sin señales</i>"  

        # Sistema de Votación y Resolución de Conflictos
        latest_candle = df.iloc[-1].to_dict()

        if not signals:
            return None, latest_candle, cycle_log

        # Separar señales de COMPRA y VENTA
        buy_signals = [s for s in signals if s[0] == 'BUY']
        sell_signals = [s for s in signals if s[0] == 'SELL']

        # 1. Chequeo de Conflicto (Si hay señales opuestas, NO operamos)
        if buy_signals and sell_signals:
            print(f"  [ALERTA] Conflicto de estrategias en {pair}: {len(buy_signals)} BUY vs {len(sell_signals)} SELL. Operación cancelada por seguridad.")
            return None, latest_candle, cycle_log + "\n   ⛔ <b>CONFLICTO DE ESTRATEGIAS</b>"

        # 2. Ejecución por Consenso
        if buy_signals:
            print(f"  >>> CONSENSO DE COMPRA ({len(buy_signals)} estrategias coinciden).")
            return buy_signals[0], latest_candle, cycle_log
            
        if sell_signals:
            print(f"  >>> CONSENSO DE VENTA ({len(sell_signals)} estrategias coinciden).")
            return sell_signals[0], latest_candle, cycle_log
            
        return signals[0], latest_candle, cycle_log

    async def run(self):
        print("--- INICIANDO BOT DE TRADING AVANZADO ---\n")
        print("--- MODO SEGURO: Máx 1 operación simultánea ---\n")
        if self.notifier.token:
            print("--- TELEGRAM ACTIVADO ---\n")
            await self.notifier.send_message("🤖 **Bot Iniciado**\nListo para operar.")
            # Iniciar el listener en segundo plano
            asyncio.create_task(self.notifier.start_listening())
        
        while True:
            # 0. Chequeo de Concurrencia y Riesgo
            now_utc = datetime.now(timezone.utc)
            
            # --- CONTROL DE RIESGO DIARIO ---
            if self.session_profit <= self.daily_stop_loss:
                msg = f"🛑 <b>STOP LOSS ALCANZADO:</b> ${self.session_profit:.2f}. Deteniendo operaciones por hoy."
                print(msg)
                await self.notifier.send_message(msg)
                break # Sale del bot
            
            if self.session_profit >= self.daily_take_profit:
                msg = f"🎯 <b>TAKE PROFIT ALCANZADO:</b> ${self.session_profit:.2f}. Asegurando ganancias."
                print(msg)
                await self.notifier.send_message(msg)
                break

            if now_utc < self.active_trade_expiry:
                remaining = (self.active_trade_expiry - now_utc).total_seconds()
                print(f"[{now_utc.strftime('%H:%M:%S')}] Operación en curso. Esperando {int(remaining)}s para finalizar...")
                await asyncio.sleep(5)
                continue
            
            cycle_report = []
            for pair in PAIRS:
                # Chequeo doble por si se tardó mucho en el loop anterior
                if datetime.now(timezone.utc) < self.active_trade_expiry:
                    break
                    
                signal, latest_data, log_msg = await self.analyze_pair(pair)
                cycle_report.append(log_msg)
                
                if signal:
                    action, duration, strat_name = signal
                    
                    # --- FILTRO IA ---
                    allowed, reason = self.is_allowed_by_ai(pair, strat_name)
                    if not allowed:
                        print(f"  [AI FILTER] Operación bloqueada: {reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>IA BLOCK:</b> {reason}"
                        continue

                    print(f"EJECUTANDO ORDEN: {action} en {pair} por {duration}s. Estrategia: {strat_name}")
                    
                    try:
                        amount = 1.0 # Monto fijo por ahora
                        trade_id = str(uuid.uuid4())[:8]

                        # --- BLOQUEO PROACTIVO (Antes de la API) ---
                        # Bloqueamos el bot por la duración del trade + 10s de margen
                        self.active_trade_expiry = datetime.now(timezone.utc) + timedelta(seconds=duration + 10)
                        print(f"  [LOCK] Bot bloqueado hasta {self.active_trade_expiry.strftime('%H:%M:%S')} UTC")

                        # --- LOGGING PREVIO ---
                        trade_data = {
                            'timestamp': datetime.now(timezone(timedelta(hours=-3))),
                            'trade_id': trade_id,
                            'pair': pair,
                            'timeframe': INTERVAL,
                            'decision': action,
                            'pattern_detected': strat_name, # Usamos el nombre de la estrategia
                            'price': latest_data.get('Close', 0),
                            'ema': latest_data.get('EMA_20', 0), 
                            'rsi': latest_data.get('RSI', 0), 
                            'atr': latest_data.get('ATR', 0),
                            'result': 'PENDING',
                            'expiry_time': duration,
                            # Agregar más campos si analyzer los provee en df
                        }
                        trade_logger.log_trade(trade_data)
                        
                        # Notificar Apertura
                        await self.notifier.notify_open(pair, action, strat_name, duration, amount)

                        # Ejecutar orden y ESPERAR resultado (check_win=True)
                        # Nota: Si check_win=True bloquea por 'duration', el bot confirma el resultado.
                        trade_result = None
                        if action == 'BUY':
                             trade_result = await self.api.buy(asset=pair, amount=amount, time=duration, check_win=True)
                        else:
                             trade_result = await self.api.sell(asset=pair, amount=amount, time=duration, check_win=True)
                        
                        # Procesar Resultado
                        # El API retorna (trade_id, details_dict)
                        is_win = False
                        profit = 0.0
                        
                        if isinstance(trade_result, tuple) and len(trade_result) == 2:
                            _, details = trade_result
                            is_win = details.get('result') == 'win'
                            profit = details.get('profit', 0.0)
                        else:
                            # Fallback por si cambia la API
                             print(f"  [WARN] Formato de resultado inesperado: {trade_result}")
                             is_win = False
                             profit = -amount
                        
                        print(f"  >>> Resultado Operación: {'GANADA' if is_win else 'PERDIDA'}")
                        await self.notifier.notify_close(pair, profit, is_win)

                        # --- ACTUALIZAR MÉTRICAS DE SESIÓN ---
                        self.session_profit += profit
                        if is_win:
                            self.strategy_fails[strat_name] = 0 # Reset racha
                        else:
                            self.strategy_fails[strat_name] = self.strategy_fails.get(strat_name, 0) + 1

                        # --- ACTUALIZAR LOG CSV ---
                        trade_logger.update_trade_result(
                            trade_id=trade_id,
                            result='WIN' if is_win else 'LOSS',
                            profit_loss=profit
                        )

                        # --- GUARDAR EN BASE DE DATOS SQL (Restaurado) ---
                        try:
                            timeframe_str = f"{duration // 60}min" if duration >= 60 else f"{duration}seg"
                            trade_db_data = {
                                'trade_id': trade_id,
                                'pair': pair,
                                'action': action,
                                'strategy': strat_name,
                                'timeframe': timeframe_str,
                                'amount': amount,
                                'open_price': latest_data.get('Close', 0), # Estimado de la vela
                                'close_price': latest_data.get('Close', 0) + (profit if is_win else -amount), # Estimado
                                'result': 'win' if is_win else 'loss',
                                'profit': profit,
                                'telegram_message_id': None # Se actualizará si hay feedback manual
                            }
                            self.db.save_trade(trade_db_data)
                            print(f"  [DB] Operación {trade_id} guardada en feedback.db")
                        except Exception as db_e:
                            print(f"  [WARN] Error guardando en DB: {db_e}")

                        # Salir del loop de pares para respetar el bloqueo inmediatamente
                        break 
                        
                    except Exception as e:
                        print(f"Error ejecutando orden: {e}")
                        await self.notifier.send_message(f"⚠️ Error ejecutando orden en {pair}: {e}")
                        
                else:
                    # print(f"Sin señal clara en {pair}")
                    pass
                
                await asyncio.sleep(2) # Pausa entre pares para no saturar
            
            # --- Mantenimiento Periódico (Una vez al día) ---
            if datetime.now().hour == 0 and datetime.now().minute < 5:
                self.db.maintain()
                # trade_logger.cleanup_old_logs() # Desactivado por pedido del usuario
            
            # --- Reporte Telegram (Al final del ciclo) ---
            if VERBOSE_TELEGRAM and cycle_report and self.notifier.token:
                header = "📊 <b>Reporte de Ciclo</b>\n\n"
                full_report = "\n".join(cycle_report)
                
                # Telegram tiene un límite de 4096 caracteres
                MAX_LEN = 4000 
                if len(header + full_report) > MAX_LEN:
                    # Enviar por partes si es muy largo
                    parts = []
                    current_part = header
                    for line in cycle_report:
                        if len(current_part + line) + 1 > MAX_LEN:
                            parts.append(current_part)
                            current_part = line
                        else:
                            current_part += "\n" + line
                    parts.append(current_part)
                    
                    for p in parts:
                        try:
                            await self.notifier.send_message(p)
                            await asyncio.sleep(1) # Evitar flood
                        except Exception as e:
                            print(f"Error enviando parte del reporte: {e}")
                else:
                    try:
                        await self.notifier.send_message(header + full_report)
                    except Exception as e:
                        print(f"Error enviando reporte Telegram: {e}")

            print("Ciclo completado. Esperando...")
            await asyncio.sleep(10)

async def main():
    # Intentar cargar desde config.json
    config = {}
    config_path = Path('config.json')
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print("✅ Configuración cargada desde config.json")
        except Exception as e:
            print(f"⚠️ Error leyendo config.json: {e}")

    ssid = config.get('ssid') or input("Introduce tu SSID de PocketOption: ").strip()
    tg_token = config.get('telegram_token') or input("Introduce tu Token de Telegram (Enter para omitir): ").strip()
    tg_chat = config.get('telegram_chat_id') or input("Introduce tu Chat ID de Telegram (Enter para omitir): ").strip()
    tg_owner = config.get('telegram_owner_id') or input("Introduce tu Telegram Owner ID (opcional, usa coma para varios): ").strip()
    
    bot = TradingBot(ssid, tg_token, tg_chat, tg_owner)
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
