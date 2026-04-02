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

# --- Configuración (Valores por defecto, se sobrescriben con config.json) ---
DEFAULT_CONFIG = {
    "pairs": ['EURUSD_otc', 'GBPUSD_otc', 'AUDUSD_otc', 'USDCAD_otc', 'AUDCAD_otc', 'USDMXN_otc', 'USDCOP_otc'],
    "interval": 300,
    "lookback": 400,
    "verbose": True,
    "verbose_telegram": True,
    "amount": 1.0,
    "daily_stop_loss": -15.0,
    "daily_take_profit": 10.0
}

class TradingBot:
    def __init__(self, ssid, telegram_token=None, telegram_chat_id=None, telegram_owner_id=None, config=None):
        self.api = PocketOptionAsync(ssid)
        self.analyzer = MarketAnalyzer()
        self.pattern_recognizer = PatternRecognizer()
        self.notifier = TelegramNotifier(
            telegram_token, 
            telegram_chat_id, 
            telegram_owner_id,
            get_balance_callback=self.get_balance
        )
        
        # Configuración dinámica
        self.config = config or DEFAULT_CONFIG
        self.pairs = self.config.get('pairs', DEFAULT_CONFIG['pairs'])
        self.interval = self.config.get('interval', DEFAULT_CONFIG['interval'])
        self.lookback = self.config.get('lookback', DEFAULT_CONFIG['lookback'])
        self.verbose = self.config.get('verbose', DEFAULT_CONFIG['verbose'])
        self.verbose_telegram = self.config.get('verbose_telegram', DEFAULT_CONFIG['verbose_telegram'])
        self.amount = self.config.get('amount', DEFAULT_CONFIG['amount'])
        
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
        self.daily_stop_loss = self.config.get('daily_stop_loss', DEFAULT_CONFIG['daily_stop_loss'])
        self.daily_take_profit = self.config.get('daily_take_profit', DEFAULT_CONFIG['daily_take_profit'])
        self.session_profit = 0.0
        self.session_profit = 0.0
        self.strategy_fails = {}      # Seguimiento de rachas negativas por sesión
        self.consecutive_losses = {}  # Seguimiento de Martingala por par {pair: count}
        
        # --- MTF CACHE ---
        self.mtf_cache = {} # { (pair, interval): (timestamp, dataframe) }
        self.api_semaphore = asyncio.Semaphore(3) # Máximo 3 peticiones simultáneas a la API

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
        # 1. Filtro de Racha Negativa (Session)
        if self.strategy_fails.get(strategy, 0) >= 3:
            return False, f"Estrategia en racha negativa (Session Fails: {self.strategy_fails[strategy]})"

        # 2. Filtro por Feedback Reciente (Dinámico)
        try:
            recent_trades = self.db.get_all_trades(limit=20)
            bad_feedback_count = 0
            for t in recent_trades:
                # Si hay feedback negativo o mención de volatilidad/falso positivo
                fb = str(t.get('feedback_text', '')).lower()
                if t['strategy'] == strategy and ('mal' in fb or 'volatilidad' in fb or 'falso' in fb):
                    bad_feedback_count += 1
            
            if bad_feedback_count >= 2:
                return False, f"Feedback negativo reciente ({bad_feedback_count} alertas)"
        except Exception as e:
            print(f"⚠️ Error en filtro de feedback: {e}")

        # 3. Filtro de Inteligencia Estática (trading_intelligence.json)
        if not self.intelligence:
            return True, "Approved (No intelligence data)"
            
        current_hour = datetime.now().hour
        
        # Filtro de Rendimiento Histórico por Estrategia
        for s_stats in self.intelligence.get('strategy_performance', []):
            if s_stats['strategy'] == strategy and s_stats['win_rate'] < 0.48:
                return False, f"Bajo rendimiento histórico ({s_stats['win_rate']*100:.1f}% WR)"

        # MODO ESTRICTO: Solo operar si el par y la hora están en las zonas de confianza (>70% WR)
        in_confidence_zone = False
        for zone in self.intelligence.get('confidence_zones', []):
            if zone['hour'] == current_hour and zone['pair'] == pair:
                in_confidence_zone = True
                break
                
        if not in_confidence_zone:
            return False, f"No es horario óptimo para {pair} (solo zonas >70% WR)"

        return True, "Approved"

    async def get_balance(self):
        """Obtiene el balance actual de la cuenta."""
        try:
            balance = await self.api.balance()
            if balance == -1.0:
                print("[Bot] ❌ ERROR: SSID Inválido o Expirado (Balance: -1.0)")
                return "SSID Expirado"
            return balance
        except Exception as e:
            print(f"[Bot] Error obteniendo balance: {e}")
            return "Error"

    async def calculate_trade_amount(self, pair):
        """Calcula el monto de la operación según la gestión de riesgo."""
        mm_config = self.config.get('money_management', {})
        mode = mm_config.get('mode', 'fixed')
        
        # 1. Modo Fijo (Default)
        amount = mm_config.get('fixed_amount', self.amount)
        
        # 2. Interés Compuesto (% del balance)
        if mode == 'compound':
            balance = await self.get_balance()
            if isinstance(balance, (int, float)):
                pct = mm_config.get('compound_percentage', 0.01)
                amount = balance * pct
                amount = max(1.0, round(amount, 2)) # Mínimo $1
                
        # 3. Martingala (Multiplicador tras pérdida)
        elif mode == 'martingale':
            losses = self.consecutive_losses.get(pair, 0)
            max_steps = mm_config.get('martingale_max_steps', 3)
            multiplier = mm_config.get('martingale_multiplier', 2.0)
            
            if losses > 0 and losses <= max_steps:
                amount = amount * (multiplier ** losses)
                print(f"  [MARTINGALE] {pair}: {losses} losses. Increasing amount to ${amount:.2f}")
            elif losses > max_steps:
                print(f"  [MARTINGALE] {pair}: Max steps reached ({max_steps}). Resetting to base amount.")
                self.consecutive_losses[pair] = 0
                
        return amount

    async def fetch_data(self, pair, interval=None):
        """Obtiene velas y prepara el DataFrame con reintentos."""
        target_interval = interval if interval else self.interval
        offset = target_interval * self.lookback
        
        for attempt in range(2): # Hasta 2 intentos
            async with self.api_semaphore:
                try:
                    if self.verbose: print(f"  [DEBUG] Fetching {pair} @ {target_interval}s {'(Retry '+str(attempt)+')' if attempt > 0 else '(Chunk 1)'}...")
                    candles = await asyncio.wait_for(self.api.get_candles(pair, target_interval, offset), timeout=25.0)
                    
                    if 0 < len(candles) < 200:
                        try:
                            time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
                            if time_key:
                                oldest_time = int(candles[0][time_key])
                                if self.verbose: print(f"  [DEBUG] Fetching Chunk 2 (Previous) ending at {oldest_time}...")
                                
                                chunk2 = await asyncio.wait_for(
                                    self.api.get_candles_advanced(pair, target_interval, offset, oldest_time), 
                                    timeout=20.0
                                )
                                
                                full_data = chunk2 + candles
                                seen = set()
                                candles = []
                                for c in full_data:
                                    tk = next((k for k in c.keys() if k.lower() in ['time', 'timestamp', 'date']), time_key)
                                    t_val = c.get(tk)
                                    if t_val is not None and t_val not in seen:
                                        candles.append(c)
                                        seen.add(t_val)
                                
                                candles.sort(key=lambda x: x.get(time_key, 0))
                        except Exception as e:
                            if self.verbose: print(f"  [WARN] Failed fetching chunk 2 for {pair}: {repr(e)}")

                    df = pd.DataFrame(candles)
                    if df.empty: 
                        if attempt == 0: continue # Reintentar si vino vacío
                        return df
                    
                    df.columns = [c.lower() for c in df.columns]
                    rename_map = {'time': 'Timestamp', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low'}
                    df.rename(columns=rename_map, inplace=True)
                    
                    required = ['open', 'high', 'low', 'close'] # Usar minúsculas por si acaso
                    # Asegurar que las columnas requeridas existen (renombradas o no)
                    if not all(col.capitalize() in df.columns for col in required):
                         return pd.DataFrame()
                    
                    # Normalizar a mayúsculas para el resto del bot
                    df.rename(columns={c: c.capitalize() for c in required if c in df.columns}, inplace=True)

                    if 'timestamp' in df.columns:
                        df['Timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
                    elif 'Timestamp' in df.columns:
                         df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', utc=True)
                    else:
                        df['Timestamp'] = pd.Timestamp.now(tz=timezone.utc)
                    
                    for c in ['Open', 'High', 'Low', 'Close']:
                        df[c] = pd.to_numeric(df[c])
                    
                    return df

                except asyncio.TimeoutError:
                    if self.verbose: print(f"  [TIMEOUT] {pair} @ {target_interval}s attempt {attempt+1} timed out.")
                    if attempt == 0:
                        await asyncio.sleep(2) # Esperar un poco antes de reintentar
                        continue
                    return pd.DataFrame()
                except Exception as e:
                    print(f"Error fetching {pair} (Attempt {attempt+1}): {e}")
                    if attempt == 0: continue
                    return pd.DataFrame()
        
        return pd.DataFrame()

    async def analyze_pair(self, pair):
        """Pipeline completo de análisis para un par."""
        print(f"Analizando {pair}...")
        
        # --- NUEVO FORMATO DE MENSAJE: Cabecera del Par ---
        cycle_log = f"\n🔹 <b>{pair}</b>"
        
        df = await self.fetch_data(pair)
        if df.empty:
            return None, {}, cycle_log + "\n   ⚠️ <b>Sin datos disponibles</b> (Error de conexión o API)"

        # --- ANÁLISIS MULTI-TIMEFRAME (MTF) ---
        mtf_settings = self.config.get('mtf_settings', {})
        if mtf_settings.get('enabled', True):
            macro_int = mtf_settings.get('macro_interval', 3600)
            meso_int = mtf_settings.get('meso_interval', 900)
            
            # Actualizar Cache si es necesario
            df_1h = await self.get_cached_mtf(pair, macro_int, 1800) # 30 min
            df_15m = await self.get_cached_mtf(pair, meso_int, 600)  # 10 min
            
            context, context_msg = self.analyzer.get_market_context(df, df_15m, df_1h)
            
            if context == 'CONFLICT':
                return None, {}, cycle_log + f"\n   ⚠️ <b>HOLD (MTF Conflict)</b>\n      <i>{context_msg}</i>"
            
            # Usar variable local para evitar condiciones de carrera en ejecución paralela
            market_context = context
            cycle_log += f"\n   🌐 <b>Contexto:</b> {context}"
        else:
            market_context = 'NEUTRAL'

        # 1. Análisis Fundamental (Noticias)
        news_status, news_msg = self.analyzer.check_news(pair, window_minutes=self.config.get('news_window', 15))
        if news_status == 'HIGH_IMPACT':
            return None, {}, cycle_log + f"\n   ⚠️ <b>HOLD (Noticias)</b>\n      <i>{news_msg}</i>"

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
            # --- FILTRO DE RÉGIMEN DE MERCADO ---
            # Si el mercado está en TENDENCIA, evitamos estrategias de REVERSIÓN
            if 'TRENDING' in market_state and getattr(strategy, 'type', '') == 'REVERSION':
                if self.verbose: print(f"  [REGIME] Skipping {strategy.name} (Reversion) in Trending Market")
                strategy_logs.append(f"   🛡️ <b>{strategy.name}</b>: Saltada (Mercado en Tendencia)")
                continue
            
            # Si el mercado está LATERAL, evitamos estrategias de TENDENCIA
            if market_state == 'SIDEWAYS' and getattr(strategy, 'type', '') == 'TREND':
                if self.verbose: print(f"  [REGIME] Skipping {strategy.name} (Trend) in Sideways Market")
                strategy_logs.append(f"   🛡️ <b>{strategy.name}</b>: Saltada (Mercado Lateral)")
                continue

            action, reason, duration = strategy.get_signal(df)
            
            # Sanitizar textos para Telegram (escapar <, >, &)
            safe_reason = html.escape(str(reason)) if reason else ""
            safe_strat_name = html.escape(strategy.name)
            
            if action in ['BUY', 'SELL']:
                # --- FILTRO DE CONTEXTO MTF ---
                if market_context != 'NEUTRAL':
                    if action == 'BUY' and 'SELL' in market_context:
                        strategy_logs.append(f"   🛡️ <b>{action} BLOQUEADO</b> (Tendencia Bajista)")
                        continue
                    if action == 'SELL' and 'BUY' in market_context:
                        strategy_logs.append(f"   🛡️ <b>{action} BLOQUEADO</b> (Tendencia Alcista)")
                        continue

                print(f"  >>> SEÑAL DETECTADA en {pair} por {strategy.name}: {action} ({reason})")
                signals.append((action, duration, strategy.name))
                # Formato lista indentada
                strategy_logs.append(f"   🔥 <b>{action}</b>: {safe_strat_name}\n      <i>{safe_reason}</i>")
            if self.verbose:
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
            conflict_msg = f"⚔️ <b>CONFLICTO:</b> {len(buy_signals)} BUY vs {len(sell_signals)} SELL"
            print(f"  [ALERTA] {conflict_msg} en {pair}. Operación cancelada.")
            return None, latest_candle, cycle_log + f"\n   ⛔ {conflict_msg}"

        # 2. Ejecución por Consenso
        if buy_signals:
            print(f"  >>> CONSENSO DE COMPRA ({len(buy_signals)} estrategias coinciden).")
            return buy_signals[0], latest_candle, cycle_log
            
        if sell_signals:
            print(f"  >>> CONSENSO DE VENTA ({len(sell_signals)} estrategias coinciden).")
            return sell_signals[0], latest_candle, cycle_log
            
        return signals[0], latest_candle, cycle_log

    async def get_cached_mtf(self, pair, interval, ttl_seconds):
        """Obtiene datos de MTF usando un sistema de cache simple."""
        now = datetime.now().timestamp()
        cache_key = (pair, interval)
        
        if cache_key in self.mtf_cache:
            ts, df = self.mtf_cache[cache_key]
            if now - ts < ttl_seconds:
                return df
        
        # Si no está en cache o expiró, descargar
        df = await self.fetch_data(pair, interval)
        if not df.empty:
            self.mtf_cache[cache_key] = (now, df)
        return df

    async def run(self):
        print("--- INICIANDO BOT DE TRADING AVANZADO ---\n")
        print("--- MODO SEGURO: Máx 1 operación simultánea ---\n")
        if self.notifier.token:
            print("--- TELEGRAM ACTIVADO ---\n")
            await self.notifier.send_message("🤖 **Bot Iniciado**\nListo para operar.")
            # Iniciar el listener en segundo plano
            asyncio.create_task(self.notifier.start_listening())
        
        while True:
            # 0. Verificación de Conexión (SSID)
            balance = await self.get_balance()
            if balance == "SSID Expirado":
                print("🛑 El bot no puede continuar sin un SSID válido. Por favor, actualiza config.json.")
                if self.notifier.token:
                    await self.notifier.send_message("🛑 <b>ERROR CRÍTICO:</b> El SSID ha expirado o es inválido. Por favor, actualiza la configuración.")
                break # Detener el bot

            # 1. Chequeo de Concurrencia y Riesgo
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
            # --- ANÁLISIS EN PARALELO ---
            tasks = [self.analyze_pair(pair) for pair in self.pairs]
            results = await asyncio.gather(*tasks)
            
            for i, (signal, latest_data, log_msg) in enumerate(results):
                pair = self.pairs[i]
                cycle_report.append(log_msg)
                
                if signal:
                    # Si ya hay una operación en curso (por un par anterior en este mismo ciclo), ignorar
                    if datetime.now(timezone.utc) < self.active_trade_expiry:
                        continue

                    action, duration, strat_name = signal
                    
                    # --- FILTRO IA ---
                    allowed, reason = self.is_allowed_by_ai(pair, strat_name)
                    if not allowed:
                        print(f"  [AI FILTER] Operación bloqueada: {reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>IA BLOCK:</b> {reason}"
                        continue

                    print(f"EJECUTANDO ORDEN: {action} en {pair} por {duration}s. Estrategia: {strat_name}")
                    
                    try:
                        amount = await self.calculate_trade_amount(pair)
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
                            'timeframe': self.interval,
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
                        await self.notifier.notify_close(pair, profit, is_win, trade_id=trade_id)

                        # --- ACTUALIZAR MÉTRICAS DE SESIÓN ---
                        self.session_profit += profit
                        if is_win:
                            self.strategy_fails[strat_name] = 0 # Reset racha
                            self.consecutive_losses[pair] = 0   # Reset Martingala
                        else:
                            self.strategy_fails[strat_name] = self.strategy_fails.get(strat_name, 0) + 1
                            self.consecutive_losses[pair] = self.consecutive_losses.get(pair, 0) + 1

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
            if self.verbose_telegram and cycle_report and self.notifier.token:
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

import os
try:
    from aiohttp import web
except ImportError:
    web = None

async def main():
    # 1. Intentar cargar configuración desde Variables de Entorno (Modo Nube)
    config = {}
    env_config = os.getenv('BOT_CONFIG')
    
    if env_config:
        try:
            config = json.loads(env_config)
            print("🌐 Configuración cargada desde Variable de Entorno (BOT_CONFIG)")
        except Exception as e:
            print(f"⚠️ Error parseando BOT_CONFIG: {e}")
    
    # 2. Si no hay en env, intentar desde config.json (Modo Local)
    if not config:
        config_path = Path('config.json')
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print("🏠 Configuración cargada desde config.json")
            except Exception as e:
                print(f"⚠️ Error leyendo config.json: {e}")

    # 3. Extraer valores (Sin inputs para evitar que la nube se bloquee)
    ssid = config.get('ssid')
    tg_token = config.get('telegram_token')
    tg_chat = config.get('telegram_chat_id')
    tg_owner = config.get('telegram_owner_id')
    
    if not ssid:
        print("❌ CRÍTICO: No se encontró SSID en config.json ni en las variables de entorno.")
        return

    # 4. Servidor Web Minimalista (Keep-alive para Koyeb/Render)
    if web:
        async def handle(request):
            return web.Response(text="Bot is running!")

        app = web.Application()
        app.router.add_get('/', handle)
        port = int(os.getenv("PORT", 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        asyncio.create_task(site.start())
        print(f"📡 Servidor keep-alive iniciado en puerto {port}")

    # 5. Iniciar el Bot
    bot = TradingBot(ssid, tg_token, tg_chat, tg_owner, config=config.get('trading', config))
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")
