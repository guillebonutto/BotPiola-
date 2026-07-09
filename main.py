import asyncio
import pandas as pd
import html
import os
from datetime import datetime, timezone, timedelta
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from patterns import PatternRecognizer
from telegram_bot import TelegramNotifier
from strategy_stochastic import StrategyStochastic
from strategy_continuation import StrategyContinuation
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure
from strategy_expert_vision import StrategyExpertVision
from strategy_alpha_convergence import StrategyAlphaConvergence
from strategy_wavetrend_keltner import StrategyWaveTrendKeltner

from trade_logger import trade_logger
from feedback_db import FeedbackDB
import uuid
import json
from pathlib import Path
from analyze_best_times import analyze_logs

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    print("[WARN] [AI Validator] google-generativeai no instalado. Validacion en tiempo real desactivada.")

# --- Configuración (Valores por defecto, se sobrescriben con config.json) ---
DEFAULT_CONFIG = {
    "pairs": ['EURUSD_otc', 'GBPUSD_otc', 'AUDUSD_otc', 'USDCAD_otc', 'AUDCAD_otc', 'USDMXN_otc', 'USDCOP_otc'],
    "interval": 300,
    "intervals": [300],
    "lookback": 400,
    "verbose": True,
    "verbose_telegram": True,
    "amount": 1.0,
    "daily_stop_loss": -15.0,
    "daily_take_profit": 10.0
}

class TradingBot:
    def __init__(self, ssid, telegram_token=None, telegram_chat_id=None, telegram_owner_id=None, config=None, root_config=None, config_path='config.json'):
        self.config_path = config_path
        self.root_config = root_config or {}
        self.broker = self.root_config.get('broker', 'pocketoption')
        
        # Configurar logger dinámicamente según configuración
        logger_suffix = Path(self.config_path).stem
        if logger_suffix == "config":
            logger_suffix = "pocketoption"
        trade_logger.configure(
            filename_pattern=f"trades_{logger_suffix}_{{date}}.csv",
            config_path=self.config_path
        )
        
        if self.broker == 'alpaca':
            alpaca_key = self.root_config.get('alpaca_key_id') or (config or {}).get('alpaca_key_id')
            alpaca_secret = self.root_config.get('alpaca_secret_key') or (config or {}).get('alpaca_secret_key')
            alpaca_paper = self.root_config.get('alpaca_paper', True)
            from broker_alpaca import AlpacaAdapter
            self.api = AlpacaAdapter(alpaca_key, alpaca_secret, paper=alpaca_paper, config=config)
            print(f"[OK] [Alpaca] Conectado en modo {'Paper' if alpaca_paper else 'Live'}.")
        else:
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
        self.intervals = self.config.get('intervals', [self.interval])
        self.lookback = self.config.get('lookback', DEFAULT_CONFIG['lookback'])
        self.verbose = self.config.get('verbose', DEFAULT_CONFIG['verbose'])
        self.verbose_telegram = self.config.get('verbose_telegram', DEFAULT_CONFIG['verbose_telegram'])
        self.amount = self.config.get('amount', DEFAULT_CONFIG['amount'])
        
        # Estado de trading
        self.active_trade_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self.active_trade_expiry_dict = {} # Expiración por par (para Alpaca concurrente)
        self.gemini_cache = {} # Cache de veredictos de la IA por vela para evitar re-análisis redundantes y 429s
        
        # Inicializar lista de estrategias activas
        is_alpaca = self.broker == 'alpaca'
        all_strategies = [
            StrategyStochastic(bypass_filter=is_alpaca),
            StrategyFibonacci(bypass_filter=is_alpaca),
            StrategyStructure(),
            StrategyExpertVision(bypass_filter=is_alpaca),
            StrategyAlphaConvergence(bypass_filter=is_alpaca),
            StrategyWaveTrendKeltner(bypass_filter=is_alpaca)
        ]
        
        enabled_list = self.config.get('enabled_strategies')
        if enabled_list is not None:
            self.strategies = [s for s in all_strategies if s.name in enabled_list]
            print(f"[Bot] Estrategias activas filtradas: {[s.name for s in self.strategies]}")
        else:
            self.strategies = all_strategies

        
        # Base de datos de feedback y mantenimiento
        db_stem = Path(self.config_path).stem
        db_name = f"feedback_{db_stem}.db" if db_stem != "config" else "feedback.db"
        self.db = FeedbackDB(db_name)
        self.db.maintain()
        
        # Inteligencia Artificial (Filtros Históricos)
        self.intelligence = self._load_intelligence()
        self.thresholds = self._load_thresholds()
        self.whitelist = self._load_whitelist()

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

        # --- VALIDADOR IA EN TIEMPO REAL (Gemini) ---
        self.use_gemini_live = self.config.get('use_gemini_live', True)
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    root_cfg = json.load(f)
                    if 'use_gemini_live' in root_cfg:
                        self.use_gemini_live = root_cfg['use_gemini_live']
                    elif 'trading' in root_cfg and 'use_gemini_live' in root_cfg['trading']:
                        self.use_gemini_live = root_cfg['trading']['use_gemini_live']
        except Exception:
            pass

        gemini_key = self.config.get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
        if not gemini_key:
            try:
                if Path(self.config_path).exists():
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        gemini_key = json.load(f).get('gemini_api_key')
            except Exception:
                pass

        self.ai_validator = None
        if not self.use_gemini_live:
            print("[INFO] [AI Validator] Gemini Live desactivado por configuración. Usando Filtro Técnico Local de Seguridad (Opción B).")
        elif _GENAI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.ai_validator = genai.GenerativeModel(
                    model_name='gemini-2.5-flash',
                    system_instruction=(
                        "Eres un validador experto de señales de trading en opciones binarias (PocketOption). "
                        "Tu única función es analizar snapshots de indicadores técnicos y decidir si una "
                        "operación es segura o no. Siempre respondes con un JSON estrictamente válido. "
                        "No das consejos generales, no explicas tu razonamiento fuera del JSON, "
                        "no permites operaciones en condiciones de mercado extremas o con indicadores contradictorios. "
                        "Tu prioridad es proteger el capital del trader."
                    )
                )
                print("[OK] [AI Validator] Gemini conectado. Validación en tiempo real ACTIVA.")
            except Exception as e:
                print(f"[WARN] [AI Validator] Error iniciando Gemini: {e}. Validación desactivada, usando Filtro Técnico Local.")
        else:
            if not gemini_key:
                print("[INFO] [AI Validator] Agrega 'gemini_api_key' a config.json para activar la validación IA en tiempo real.")

        # Iniciar monitor de posiciones en segundo plano para Alpaca
        if self.broker == 'alpaca':
            asyncio.create_task(self.monitor_alpaca_trades())

    async def monitor_alpaca_trades(self):
        """Monitorea en segundo plano las operaciones de Alpaca y actualiza resultados."""
        print("[Alpaca Monitor] Iniciado.")
        import sqlite3
        while True:
            try:
                if self.broker != 'alpaca':
                    break
                    
                # closed_deals() devolverá una lista de trades cerrados en el último escaneo
                closed = await self.api.closed_deals()
                for matched in closed:
                    placed_id = matched.get('id')
                    profit = float(matched.get('profit', 0.0))
                    is_win = matched.get('result') == 'win'
                    pair = matched.get('asset') # ej: EURUSD
                    
                    print(f"[Alpaca Monitor] Se detectó cierre de posición para {pair} (ID: {placed_id}). Profit: ${profit:.2f}")
                    
                    # Actualizar en la base de datos SQL
                    try:
                        conn = sqlite3.connect(self.db.db_path)
                        cursor = conn.cursor()
                        # Buscar si existe un registro PENDING con este trade_id
                        cursor.execute("SELECT trade_id, strategy, amount FROM trades WHERE trade_id = ?", (str(placed_id),))
                        row = cursor.fetchone()
                        
                        if row:
                            db_trade_id = row[0]
                            strat_name = row[1]
                            amount = row[2]
                            
                            # Actualizar el registro
                            cursor.execute("""
                                UPDATE trades 
                                SET result = ?, profit = ?, close_price = open_price + ?
                                WHERE trade_id = ?
                            """, ('win' if is_win else 'loss', profit, profit / amount if amount > 0 else 0, db_trade_id))
                            conn.commit()
                            
                            # Actualizar CSV
                            trade_logger.update_trade_result(
                                trade_id=db_trade_id,
                                result='WIN' if is_win else 'LOSS',
                                profit_loss=profit
                            )
                            
                            # Actualizar métricas de sesión
                            self.session_profit += profit
                            if is_win:
                                self.strategy_fails[strat_name] = 0
                                self.consecutive_losses[pair] = 0
                            else:
                                self.strategy_fails[strat_name] = self.strategy_fails.get(strat_name, 0) + 1
                                self.consecutive_losses[pair] = self.consecutive_losses.get(pair, 0) + 1
                                
                            # Liberar bloqueo del par
                            if pair in self.active_trade_expiry_dict:
                                self.active_trade_expiry_dict[pair] = datetime.min.replace(tzinfo=timezone.utc)
                                print(f"[Alpaca Monitor] Bloqueo liberado para {pair}.")
                                
                            print(f"[Alpaca Monitor] DB y CSV actualizados para {db_trade_id}. Notificando en Telegram...")
                            await self.notifier.notify_close(pair, profit, is_win, trade_id=db_trade_id)
                            
                            # Re-aprender en tiempo real
                            try:
                                analyze_logs(config_path=self.config_path)
                                from analyze_best_times import generate_dynamic_threshold_matrix
                                generate_dynamic_threshold_matrix(config_path=self.config_path)
                                self.intelligence = self._load_intelligence()
                                self.thresholds = self._load_thresholds()
                            except Exception as intel_e:
                                print(f"[Alpaca Monitor] Error actualizando inteligencia: {intel_e}")
                        else:
                            print(f"[Alpaca Monitor] [WARN] No se encontró el trade {placed_id} en la base de datos.")
                        conn.close()
                    except Exception as db_e:
                        print(f"[Alpaca Monitor] Error actualizando base de datos para {placed_id}: {db_e}")
                        
            except Exception as e:
                print(f"[Alpaca Monitor] Error en ciclo de monitoreo: {e}")
                
            await asyncio.sleep(20) # Escanear cada 20 segundos

    def reload_config(self):
        """Recarga la configuración desde config.json en tiempo real."""
        try:
            path = Path(self.config_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    new_config = json.load(f)
                    trading_config = new_config.get('trading', {})
                    
                    # Actualizar parámetros dinámicos de trading
                    self.pairs = trading_config.get('pairs', self.pairs)
                    self.interval = trading_config.get('interval', self.interval)
                    self.intervals = trading_config.get('intervals', [self.interval])
                    self.lookback = trading_config.get('lookback', self.lookback)
                    self.verbose = trading_config.get('verbose', self.verbose)
                    self.verbose_telegram = trading_config.get('verbose_telegram', self.verbose_telegram)
                    self.amount = trading_config.get('amount', self.amount)
                    self.daily_stop_loss = trading_config.get('daily_stop_loss', self.daily_stop_loss)
                    self.daily_take_profit = trading_config.get('daily_take_profit', self.daily_take_profit)
                    
                    self.config = trading_config
                    
                # Recargar inteligencia estática en memoria
                self.intelligence = self._load_intelligence()
                self.thresholds = self._load_thresholds()
                
        except Exception as e:
            print(f"[WARN] [Config] Error al recargar configuracion dinamica: {e}")

    def _load_intelligence(self):
        """Carga el mapa de confianza generado por analyze_best_times.py."""
        try:
            stem = Path(self.config_path).stem
            suffix = f"_{stem}" if stem != "config" else ""
            filename = f"trading_intelligence{suffix}.json"
            path = Path(filename)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"[INFO] Inteligencia de trading cargada ({filename}, Actualizada: {data.get('last_update', 'N/A')})")
                    return data
        except Exception as e:
            print(f"[WARN] Error cargando inteligencia: {e}")
        return None

    def _load_whitelist(self):
        """Carga la whitelist de combinaciones par-estrategia-temporalidad probadas."""
        try:
            path = Path("whitelist_combinations.json")
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    whitelist_set = {
                        (item["pair"], item["strategy"], int(item["interval"]))
                        for item in data
                    }
                    print(f"[INFO] Whitelist de combinaciones de backtesting cargada: {len(whitelist_set)} configuraciones permitidas.")
                    return whitelist_set
        except Exception as e:
            print(f"[WARN] Error cargando whitelist_combinations.json: {e}")
        return None

    def _load_thresholds(self):
        """Carga la matriz de umbrales dinámicos generada por analyze_best_times.py."""
        try:
            stem = Path(self.config_path).stem
            suffix = f"_{stem}" if stem != "config" else ""
            filename = f"strategy_thresholds{suffix}.json"
            path = Path(filename)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"[INFO] Matriz de umbrales dinámicos cargada con éxito ({filename}).")
                    return data
        except Exception as e:
            print(f"[WARN] Error cargando umbrales dinámicos: {e}")
        return {}

    def is_allowed_by_ai(self, pair, strategy, interval):
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
            print(f"[WARN] Error en filtro de feedback: {e}")

        # 3. Filtro de Inteligencia Estática (trading_intelligence.json)
        # DESACTIVADO TEMPORALMENTE por pedido del usuario para operar basándose únicamente en análisis técnico (Opción 3).
        return True, "Approved (Filtros históricos de IA desactivados)"
            
        # Obtener la hora actual en GMT-3 (coincidiendo con los logs y la base de datos de inteligencia)
        tz_gmt3 = timezone(timedelta(hours=-3))
        current_hour = datetime.now(tz_gmt3).hour
        
        # Filtro de Rendimiento Histórico General por Estrategia
        min_overall_wr = 0.43 if self.broker == 'alpaca' else 0.51
        for s_stats in self.intelligence.get('strategy_performance', []):
            if s_stats['strategy'] == strategy:
                overall_count = s_stats['count']
                overall_win_rate = s_stats['win_rate']
                if overall_count >= 15 and overall_win_rate < min_overall_wr:
                    return False, f"Bajo rendimiento histórico general ({overall_win_rate*100:.1f}% WR)"

        # Filtro Matricial Dinámico: Verificar si el par-estrategia supera su umbral dinámico de win rate
        pair_strat_stats = None
        for ps_stats in self.intelligence.get('pair_strategy_performance', []):
            if ps_stats['pair'] == pair and ps_stats['strategy'] == strategy:
                pair_strat_stats = ps_stats
                break
                
        if pair_strat_stats:
            count = pair_strat_stats['count']
            win_rate = pair_strat_stats['win_rate']
            
            # Obtener umbral dinámico (default a 0.45 si es alpaca, 0.55 si no está registrado)
            default_thresh = 0.45 if self.broker == 'alpaca' else 0.55
            threshold = default_thresh
            if self.thresholds and strategy in self.thresholds and pair in self.thresholds[strategy]:
                threshold = self.thresholds[strategy][pair]
                
            if count >= 15 and win_rate < threshold:
                return False, f"Rendimiento de {strategy} en {pair} ({win_rate*100:.1f}% WR) por debajo del umbral dinámico ({threshold*100:.1f}% WR)"

        # FILTRO DE HORARIO EXCLUYENTE (Zonas de Riesgo): Bloquear de inmediato si la hora y par están en la zona de pérdidas históricas
        in_risk_zone = False
        for zone in self.intelligence.get('risk_zones', []):
            if zone['hour'] == current_hour and zone['pair'] == pair:
                in_risk_zone = True
                break
                
        if in_risk_zone:
            return False, f"Bloqueado por Zona de Riesgo Horaria para {pair} en la hora {current_hour} (Historial perdedor)"

        return True, "Approved"

    async def get_mtf_alignment_score(self, pair, action):
        """
        Calcula un score de alineación MTF (M15, M5, M1) de 0 a 60.
        M15: +30 si está alineado con la dirección de la señal
        M5: +20 si está alineado
        M1: +10 si está alineado
        """
        try:
            # Obtener dataframes de cache o descargas rápidas
            df_15m = await self.get_cached_mtf(pair, 900, 300) # 15m
            df_5m = await self.get_cached_mtf(pair, 300, 60)   # 5m
            df_1m = await self.get_cached_mtf(pair, 60, 20)    # 1m
            
            score = 0
            details = {}

            # Helper local para determinar la tendencia
            def calc_trend(df, ema_window=20):
                if df is None or df.empty or len(df) < max(ema_window, 14) + 1:
                    return 'NEUTRAL'
                from ta.trend import EMAIndicator
                from ta.momentum import RSIIndicator
                close = df['Close']
                ema = EMAIndicator(close, window=ema_window).ema_indicator().iloc[-1]
                rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
                last_close = close.iloc[-1]
                if last_close > ema and rsi > 50:
                    return 'BULLISH'
                elif last_close < ema and rsi < 50:
                    return 'BEARISH'
                return 'NEUTRAL'

            trend_15m = calc_trend(df_15m, ema_window=50) # M15 usa EMA50
            trend_5m = calc_trend(df_5m, ema_window=20)   # M5 usa EMA20
            trend_1m = calc_trend(df_1m, ema_window=20)   # M1 usa EMA20

            details['trend_15m'] = trend_15m
            details['trend_5m'] = trend_5m
            details['trend_1m'] = trend_1m

            target = 'BULLISH' if action == 'BUY' else 'BEARISH'

            if trend_15m == target:
                score += 30
            if trend_5m == target:
                score += 20
            if trend_1m == target:
                score += 10

            return score, details
        except Exception as e:
            print(f"[WARN] Error calculando score MTF: {e}")
            return 0, {}

    def local_risk_fallback(self, snapshot):
        """
        Filtro técnico local estricto de respaldo cuando la API de Gemini falla,
        está rate-limited, o está completamente desactivada (Opción B).
        Aplica reglas básicas de capital para evitar entrar en señales de alto riesgo.
        """
        action = snapshot.get("action")
        rsi = snapshot.get("rsi", 50)
        stoch_k = snapshot.get("stoch_k", 50)
        close = snapshot.get("close", 0)
        ema_20 = snapshot.get("ema_20", 0)
        atr = snapshot.get("atr", 0)
        mtf = snapshot.get("multi_timeframe", {})
        
        # 1. Agotamiento Extremo (RSI / Stochastic)
        if action == "BUY":
            if rsi > 70:
                return False, "Bloqueo Local: Agotamiento alcista extremo (RSI > 70)"
            if stoch_k > 90:
                return False, "Bloqueo Local: Agotamiento alcista extremo (Stoch_K > 90)"
        elif action == "SELL":
            if rsi < 30:
                return False, "Bloqueo Local: Agotamiento bajista extremo (RSI < 30)"
            if stoch_k < 10:
                return False, "Bloqueo Local: Agotamiento bajista extremo (Stoch_K < 10)"

        # 2. Cuchillo cayendo / Subida vertical (Fuerte momentum en contra)
        # Si compramos pero el precio está cayendo con fuerza por debajo de la EMA 20
        # (Close muy por debajo de EMA 20 y RSI es bajo)
        if action == "BUY":
            if close < ema_20 and (ema_20 - close) > (1.8 * atr) and rsi < 38:
                return False, f"Bloqueo Local: Falling Knife (Precio demasiado lejos de EMA 20, RSI={rsi})"
        elif action == "SELL":
            if close > ema_20 and (close - ema_20) > (1.8 * atr) and rsi > 62:
                return False, f"Bloqueo Local: Rising Knife (Precio demasiado lejos de EMA 20, RSI={rsi})"

        # 3. Alineación Mínima de Tendencia MTF
        # Evitar operar a contra-tendencia total en H1 y M15
        h1_trend = mtf.get("1h_trend", "NEUTRAL")
        m15_trend = mtf.get("15m_trend", "NEUTRAL")
        
        if action == "BUY":
            if h1_trend == "BEARISH" and m15_trend == "BEARISH":
                return False, "Bloqueo Local: Contra-tendencia absoluta en H1 y M15 (BEARISH)"
        elif action == "SELL":
            if h1_trend == "BULLISH" and m15_trend == "BULLISH":
                return False, "Bloqueo Local: Contra-tendencia absoluta en H1 y M15 (BULLISH)"

        return True, "Aprobado Local: Filtros técnicos básicos correctos"

    async def validate_signal_with_ai(self, pair, action, strategy_name, latest_candle, rich_ctx):
        """
        Valida una señal de trading contra Gemini o mediante Filtro Local ANTES de ejecutar la operación.
        Envía un snapshot compacto y con contexto completo de régimen y timeframes.
        Retorna (approved: bool, reason: str, confidence: int, snapshot: dict)
        """
        # Obtener el tipo de estrategia dinámicamente
        strat_type = "TREND"
        for strat in self.strategies:
            if strat.name == strategy_name:
                strat_type = getattr(strat, 'type', 'TREND')
                break

        # Snapshot ultra-completo con contexto de régimen real de mercado
        snapshot = {
            "pair": pair,
            "action": action,
            "strategy": strategy_name,
            "strategy_type": strat_type,
            "mss_signal": "Cambio de Estructura" in strategy_name,
            "market_state": rich_ctx.get("market_state", "UNKNOWN") if isinstance(rich_ctx, dict) else "UNKNOWN",
            "regime": rich_ctx.get("regime", "NEUTRAL") if isinstance(rich_ctx, dict) else "NEUTRAL",
            "multi_timeframe": rich_ctx.get("multi_timeframe", {
                "1h_trend": "NEUTRAL",
                "15m_trend": "NEUTRAL"
            }) if isinstance(rich_ctx, dict) else {
                "1h_trend": "NEUTRAL",
                "15m_trend": "NEUTRAL"
            },
            "hour_utc": datetime.now(timezone.utc).hour,
            "close": round(latest_candle.get('Close', 0), 5),
            "rsi": round(latest_candle.get('RSI', 50), 2),
            "ema_20": round(latest_candle.get('EMA_20', 0), 5),
            "ema_50": round(latest_candle.get('EMA_50', 0), 5),
            "sma_200": round(latest_candle.get('SMA_200', 0), 5),
            "macd": round(latest_candle.get('MACD', 0), 6),
            "macd_signal": round(latest_candle.get('MACD_Signal', 0), 6),
            "stoch_k": round(latest_candle.get('Stoch_K', 50), 2),
            "stoch_d": round(latest_candle.get('Stoch_D', 50), 2),
            "atr": round(latest_candle.get('ATR', 0), 6),
            "session_profit_usd": round(self.session_profit, 2),
        }

        # --- SISTEMA DE CACHE POR VELA ---
        candle_ts = latest_candle.get('Timestamp') or latest_candle.get('timestamp') or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        cache_key = (pair, strategy_name, action, str(candle_ts))
        
        if cache_key in self.gemini_cache:
            approved, reason, confidence, cached_snapshot = self.gemini_cache[cache_key]
            print(f"  [AI Cache Hit] Reutilizando veredicto para {pair} {strategy_name}: {'[APPROVED]' if approved else '[BLOCKED]'} -- Confianza: {confidence}% | Razón: {reason}")
            return approved, reason, confidence, cached_snapshot

        # Si Gemini está desactivado por configuración (Opción B) o no disponible, usar el Filtro Local de Seguridad
        if not self.use_gemini_live or not self.ai_validator:
            local_approved, local_reason = self.local_risk_fallback(snapshot)
            confidence = 100
            print(f"  [Filtro Local] {'[APPROVED]' if local_approved else '[BLOCKED]'} -- {local_reason}")
            fallback_res = (local_approved, local_reason, confidence, snapshot)
            self.gemini_cache[cache_key] = fallback_res
            return fallback_res

        prompt = f"""Eres un filtro inteligente de riesgo extremo para un bot de opciones binarias (PocketOption). Analiza esta señal y responde SOLO con un objeto JSON.

SEÑAL PROPUESTA Y CONTEXTO COMPLETO:
{json.dumps(snapshot, indent=2)}

REGLAS CRÍTICAS PARA TU ROL (FILTRO DE RIESGO Y CUIDADO DEL CAPITAL):
1. Analiza el contexto de régimen de mercado ('market_state') y la tendencia en múltiples timeframes ('multi_timeframe').
2. BLOQUEA la señal si detectas alguna de las siguientes situaciones de alto riesgo técnico:
   - "Cuchillo Cayendo" (Falling Knife): Señal de COMPRA (BUY) cuando el precio está cayendo con fuerza (ej. Close muy por debajo de la EMA 20 y RSI < 38) sin confirmación de giro o soporte.
   - "Subida Vertical" (Rising Knife): Señal de VENTA (SELL) cuando el precio está subiendo con fuerza (ej. Close muy por encima de la EMA 20 y RSI > 62) sin confirmación de resistencia.
   - Contra-Tendencia Absoluta: Ir en contra de la tendencia principal ('1h_trend') en mercados con fuerte direccionalidad (TRENDING_UP / TRENDING_DOWN).
   - Agotamiento Extremo: Señales de COMPRA con RSI > 75 o Stoch_K > 95, o señales de VENTA con RSI < 25 o Stoch_K < 5, ya que hay alta probabilidad de retroceso inmediato (mortal para opciones de 5 minutos).
   - Consolidación sin Volumen (Chop Market): Rango muy estrecho o ATR plano donde el precio oscila sin dirección clara, aumentando falsos breakouts.
3. Si el contexto técnico muestra alineación de tendencias, soporte/resistencia respetados y osciladores saliendo de zonas de sobrecompra/sobreventa de manera saludable, tu veredicto debe ser APPROVED.

Devuelve SOLO este JSON, sin explicaciones ni formato markdown fuera del bloque:
{{"decision": "APPROVED" o "BLOCKED", "confidence": 1-100, "reason": "Una línea concisa en español explicando el riesgo crítico si bloqueas, o por qué se aprueba"}}"""

        try:
            response = await asyncio.to_thread(
                self.ai_validator.generate_content, prompt
            )
            raw = response.text.strip()
            # Limpiar markdown si viene con ```json
            if '```' in raw:
                raw = raw.split('```')[1].replace('json', '').strip()
                if '```' in raw:
                    raw = raw.split('```')[0].strip()

            result = json.loads(raw)
            decision = result.get('decision', 'APPROVED')
            confidence = result.get('confidence', 50)
            reason = result.get('reason', 'Sin razón')

            approved = decision == 'APPROVED'
            msg = f"IA [{confidence}%]: {reason}"
            print(f"  [AI Validator] {'[APPROVED]' if approved else '[BLOCKED]'} -- {msg}")
            
            # Guardar en cache
            self.gemini_cache[cache_key] = (approved, reason, confidence, snapshot)
            
            # Limpiar entradas antiguas si el tamaño excede 500 para evitar consumos de memoria
            if len(self.gemini_cache) > 500:
                keys = list(self.gemini_cache.keys())
                for k in keys[:250]:
                    self.gemini_cache.pop(k, None)
                    
            return approved, reason, confidence, snapshot

        except Exception as e:
            err_reason = f"Error en validación: {e}"
            print(f"  [AI Validator] Error: {e}. Activando Filtro Técnico Local de Seguridad.")
            local_approved, local_reason = self.local_risk_fallback(snapshot)
            fallback_res = (local_approved, f"Fallback (API Error: {e}) -> {local_reason}", 50, snapshot)
            self.gemini_cache[cache_key] = fallback_res
            return fallback_res

    async def get_balance(self):
        """Obtiene el balance actual de la cuenta."""
        try:
            balance = await self.api.balance()
            if balance == -1.0:
                print("[Bot] [ERR] ERROR: SSID Invalido o Expirado (Balance: -1.0)")
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
                    df.attrs['pair'] = pair
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

    async def analyze_pair(self, pair, interval):
        """Pipeline completo de análisis para un par y temporalidad."""
        timeframe_name = f"{interval // 60}m" if interval >= 60 else f"{interval}s"
        print(f"Analizando {pair} ({timeframe_name})...")
        
        # --- NUEVO FORMATO DE MENSAJE: Cabecera del Par ---
        cycle_log = f"\n🔹 <b>{pair} ({timeframe_name})</b>"
        
        # Inicializar contexto rico de mercado por defecto
        rich_ctx = {
            "market_state": "UNKNOWN",
            "regime": "NEUTRAL",
            "multi_timeframe": {
                "1h_trend": "NEUTRAL",
                "15m_trend": "NEUTRAL"
            }
        }
        
        df = await self.fetch_data(pair, interval)
        if df.empty:
            return None, {}, cycle_log + "\n   ⚠️ <b>Sin datos disponibles</b> (Error de conexión o API)", rich_ctx

        # --- ANÁLISIS MULTI-TIMEFRAME (MTF) ---
        mtf_settings = self.config.get('mtf_settings', {})
        macro_trend = 'NEUTRAL'
        meso_trend = 'NEUTRAL'
        if mtf_settings.get('enabled', True):
            macro_int = mtf_settings.get('macro_interval', 3600)
            meso_int = mtf_settings.get('meso_interval', 900)
            
            # Actualizar Cache si es necesario
            df_1h = await self.get_cached_mtf(pair, macro_int, 1800) # 30 min
            df_15m = await self.get_cached_mtf(pair, meso_int, 600)  # 10 min
            
            context, context_msg = self.analyzer.get_market_context(df, df_15m, df_1h)
            macro_trend = self.analyzer.get_trend(df_1h, 'macro')
            meso_trend = self.analyzer.get_trend(df_15m, 'meso')
            
            # Actualizar rich_ctx
            rich_ctx["regime"] = context
            rich_ctx["multi_timeframe"]["1h_trend"] = macro_trend
            rich_ctx["multi_timeframe"]["15m_trend"] = meso_trend
            
            if context == 'CONFLICT':
                return None, {}, cycle_log + f"\n   ⚠️ <b>HOLD (MTF Conflict)</b>\n      <i>{context_msg}</i>", rich_ctx
            
            market_context = context
            cycle_log += f"\n   🌐 <b>Contexto:</b> {context}"
        else:
            market_context = 'NEUTRAL'

        # 1. Análisis Fundamental (Noticias)
        news_status, news_msg = self.analyzer.check_news(pair, window_minutes=self.config.get('news_window', 15))
        if news_status == 'HIGH_IMPACT':
            return None, {}, cycle_log + f"\n   ⚠️ <b>HOLD (Noticias)</b>\n      <i>{news_msg}</i>", rich_ctx

        # 2. Análisis Técnico (Indicadores)
        df = self.analyzer.compute_indicators(df)
        
        # 3. Reconocimiento de Patrones
        df = self.pattern_recognizer.find_candlestick_patterns(df)
        df = self.pattern_recognizer.find_chart_patterns(df)
        
        # 4. Estado del Mercado
        market_state = self.analyzer.determine_market_state(df)
        rich_ctx["market_state"] = market_state
        
        # --- REGIME HARD LOCK (Early Return) ---
        if market_state == 'SIDEWAYS':
            return None, {}, cycle_log + f"\n   🛡️ <b>HOLD (Regime Hard Lock: {market_state})</b>\n      <i>Evitando operar en consolidaciones de bajo rango (chop market).</i>", rich_ctx
        elif market_state == 'VOLATILE':
            return None, {}, cycle_log + f"\n   🛡️ <b>HOLD (Regime Hard Lock: {market_state})</b>\n      <i>Evitando operar en condiciones de volatilidad extrema descontrolada.</i>", rich_ctx

        # 5. Consultar Estrategias
        signals = []
        strategy_logs = []
        
        # --- CONFIGURACIÓN DE ACTIVACIÓN DE ESTRATEGIAS SEGÚN RÉGIMEN (Strategy Router) ---
        allowed_types = []
        if self.broker == 'alpaca':
            if market_state in ['TRENDING_UP', 'TRENDING_DOWN', 'NEUTRAL']:
                allowed_types = ['TREND', 'REVERSION']
            else:
                allowed_types = []
        else:
            if market_state in ['TRENDING_UP', 'TRENDING_DOWN']:
                allowed_types = ['TREND']
            elif market_state == 'SIDEWAYS':
                # Evitamos operar por completo en consolidaciones de bajo rango (chop market)
                allowed_types = []
            elif market_state == 'VOLATILE':
                # Protegemos el capital evitando operaciones durante volatilidad descontrolada
                allowed_types = []
            elif market_state == 'NEUTRAL':
                # En transiciones o mercados sin tendencia, permitimos solo reversión
                allowed_types = ['REVERSION']
            else:
                allowed_types = []

        for strategy in self.strategies:
            strat_type = getattr(strategy, 'type', 'TREND')
            if strat_type not in allowed_types:
                if self.verbose: 
                    print(f"  [REGIME] Saltando {strategy.name} ({strat_type}) por incompatibilidad con regimen {market_state}")
                strategy_logs.append(f"   🛡️ <b>{strategy.name}</b>: Incompatible con {market_state}")
                continue

            action, reason, _ = strategy.get_signal(df)
            duration = interval
            
            # Sanitizar textos para Telegram (escapar <, >, &)
            safe_reason = html.escape(str(reason)) if reason else ""
            safe_strat_name = html.escape(strategy.name)
            
            if action in ['BUY', 'SELL']:
                # --- FILTRO DE CONTEXTO MTF ---
                # Las estrategias de tipo REVERSION no se filtran por la tendencia mayor MTF, ya que operan rebotes
                if market_context != 'NEUTRAL' and strat_type == 'TREND':
                    if action == 'BUY' and 'SELL' in market_context:
                        strategy_logs.append(f"   🛡️ <b>{action} BLOQUEADO</b> (Tendencia Bajista)")
                        continue
                    if action == 'SELL' and 'BUY' in market_context:
                        strategy_logs.append(f"   🛡️ <b>{action} BLOQUEADO</b> (Tendencia Alcista)")
                        continue

                print(f"  >>> SENAL DETECTADA en {pair} por {strategy.name}: {action} ({reason})")
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
            return None, latest_candle, cycle_log, rich_ctx

        # Separar señales de COMPRA y VENTA
        buy_signals = [s for s in signals if s[0] == 'BUY']
        sell_signals = [s for s in signals if s[0] == 'SELL']

        # 1. Chequeo de Conflicto (Si hay señales opuestas, NO operamos)
        if buy_signals and sell_signals:
            conflict_msg = f"⚔️ <b>CONFLICTO:</b> {len(buy_signals)} BUY vs {len(sell_signals)} SELL"
            print(f"  [ALERTA] {conflict_msg} en {pair}. Operacion cancelada.")
            return None, latest_candle, cycle_log + f"\n   ⛔ {conflict_msg}", rich_ctx

        # 2. Ejecución por Consenso
        if buy_signals:
            print(f"  >>> CONSENSO DE COMPRA ({len(buy_signals)} estrategias coinciden).")
            return buy_signals[0], latest_candle, cycle_log, rich_ctx
            
        if sell_signals:
            print(f"  >>> CONSENSO DE VENTA ({len(sell_signals)} estrategias coinciden).")
            return sell_signals[0], latest_candle, cycle_log, rich_ctx
            
        return signals[0], latest_candle, cycle_log, rich_ctx

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
        print("--- MODO SEGURO: Max 1 operacion simultanea ---\n")
        if self.notifier.token:
            print("--- TELEGRAM ACTIVADO ---\n")
            await self.notifier.send_message("🤖 **Bot Iniciado**\nListo para operar.")
            # Iniciar el listener en segundo plano si está habilitado
            if self.config.get('telegram_listen', True):
                asyncio.create_task(self.notifier.start_listening())
            else:
                print("--- TELEGRAM LISTENER DESACTIVADO PARA EVITAR CONFLICTOS EN GETUPDATES ---")
        
        while True:
            # 0. Detectar señal de reinicio externa
            restart_path = Path('restart.signal')
            if restart_path.exists():
                print("\n[INFO] Senal de reinicio detectada. Apagando el bot...")
                try:
                    restart_path.unlink()
                except Exception:
                    pass
                import sys
                sys.exit(5)

            # 0. Recargar configuración dinámicamente al inicio del ciclo
            self.reload_config()

            
            # 0. Verificación de Conexión (SSID o Credenciales)
            balance = await self.get_balance()
            if self.broker == 'alpaca' and isinstance(balance, (int, float)):
                try:
                    with open('alpaca_status.json', 'w', encoding='utf-8') as sf:
                        json.dump({
                            'balance': balance,
                            'last_updated': datetime.now(timezone.utc).isoformat()
                        }, sf)
                except Exception as sf_err:
                    print(f"[Alpaca Status] Error escribiendo status compartido: {sf_err}")

            if balance == "Network Error":
                print("[WARN] Error temporal de red al consultar balance. Reintentando en el próximo ciclo...")
                await asyncio.sleep(10)
                continue
            elif balance == "SSID Expirado" or (self.broker == 'alpaca' and balance == -1.0):
                msg = "[ERR] El bot no puede continuar sin credenciales de Alpaca válidas." if self.broker == 'alpaca' else "[ERR] El bot no puede continuar sin un SSID válido. Por favor, actualiza config.json."
                print(msg)
                if self.notifier.token:
                    await self.notifier.send_message(f"🛑 <b>ERROR CRÍTICO:</b> {msg}")
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

            if self.broker != 'alpaca' and now_utc < self.active_trade_expiry:
                remaining = (self.active_trade_expiry - now_utc).total_seconds()
                print(f"[{now_utc.strftime('%H:%M:%S')}] Operacion en curso. Esperando {int(remaining)}s para finalizar...")
                await asyncio.sleep(5)
                continue
            
            cycle_report = []
            # --- ANÁLISIS SECUENCIAL CON DELAY PARA EVITAR TIMEOUTS ---
            results = []
            pairs_with_tf = self.config.get('pairs_with_timeframe')
            if pairs_with_tf:
                for pair, interval in pairs_with_tf.items():
                    res = await self.analyze_pair(pair, interval)
                    results.append((pair, interval, res))
                    await asyncio.sleep(0.3)
            else:
                for pair in self.pairs:
                    for interval in self.intervals:
                        res = await self.analyze_pair(pair, interval)
                        results.append((pair, interval, res))
                        await asyncio.sleep(0.3)
            
            for pair, interval, (signal, latest_data, log_msg, ctx) in results:
                cycle_report.append(log_msg)
                
                if signal:
                    # Si ya hay una operación en curso (por un par anterior en este mismo ciclo), ignorar
                    if self.broker == 'alpaca':
                        if datetime.now(timezone.utc) < self.active_trade_expiry_dict.get(pair, datetime.min.replace(tzinfo=timezone.utc)):
                            continue
                    else:
                        if datetime.now(timezone.utc) < self.active_trade_expiry:
                            continue
 
                    action, duration, strat_name = signal
                    
                    # --- FILTRO DE WHITELIST DE BACKTESTING ---
                    # DESACTIVADO TEMPORALMENTE por pedido del usuario para operar basándose únicamente en análisis técnico.
                    # if self.whitelist is not None:
                    #     # Mapear el nombre del par para compatibilidad con la whitelist (que usa nombres de PocketOption OTC)
                    #     pair_mapped = pair
                    #     if not pair.endswith('_otc'):
                    #         if len(pair) == 6 and not pair.startswith('#'):
                    #             pair_mapped = f"{pair}_otc"
                    #         else:
                    #             pair_mapped = f"#{pair}_otc"
                    #     
                    #     sig_key = (pair_mapped, strat_name, int(interval))
                    #     if sig_key not in self.whitelist:
                    #         print(f"  [WHITELIST FILTER] Señal bloqueada: {pair} (mapeado a {pair_mapped}) | {strat_name} | {interval}s no está en la whitelist de backtesting.")
                    #         cycle_report[-1] += f"\n   🚫 <b>WHITELIST BLOCK:</b> {strat_name} no permitida en {pair} ({interval}s)"
                    #         continue
                    pass
                            
                    # --- FILTRO IA HISTÓRICO (trading_intelligence.json) ---
                    allowed, reason = self.is_allowed_by_ai(pair, strat_name, interval)
                    if not allowed:
                        print(f"  [AI FILTER] Operacion bloqueada: {reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>IA BLOCK:</b> {reason}"
                        continue

 
                    # --- VALIDADOR IA EN TIEMPO REAL (Gemini Live) ---
                    ai_ok, ai_reason, ai_confidence, ai_snapshot = await self.validate_signal_with_ai(
                        pair, action, strat_name, latest_data, ctx
                    )
                    if not ai_ok:
                        print(f"  [AI Live] Senal rechazada por Gemini (Confianza {ai_confidence}%): {ai_reason}")
                        cycle_report[-1] += f"\n   🤖 <b>GEMINI BLOCK:</b> {html.escape(ai_reason)}"
                        
                        # Guardar registro del trade bloqueado para análisis
                        try:
                            trade_id = f"blk_{str(uuid.uuid4())[:5]}"
                            close_val = latest_data.get('Close', 0)
                            ema20_val = latest_data.get('EMA_20', 0)
                            distance_ema20 = close_val - ema20_val
                            
                            trade_context = {
                                "indicators": {
                                    "price": close_val,
                                    "ema20": ema20_val,
                                    "ema50": latest_data.get('EMA_50', 0),
                                    "sma200": latest_data.get('SMA_200', 0),
                                    "distance_ema20": distance_ema20,
                                    "rsi": latest_data.get('RSI', 0),
                                    "stoch_k": latest_data.get('Stoch_K', 0),
                                    "stoch_d": latest_data.get('Stoch_D', 0),
                                    "atr": latest_data.get('ATR', 0),
                                    "macd": latest_data.get('MACD', 0),
                                    "macd_signal": latest_data.get('MACD_Signal', 0)
                                },
                                "market_state": ctx.get("market_state", "UNKNOWN") if isinstance(ctx, dict) else "UNKNOWN",
                                "regime": ctx.get("regime", "NEUTRAL") if isinstance(ctx, dict) else "NEUTRAL",
                                "mtf_alignment": {
                                    "score": 0,
                                    "details": {}
                                },
                                "gemini_validation": {
                                    "approved": False,
                                    "confidence": ai_confidence,
                                    "reason": ai_reason
                                }
                            }
                            
                            notes_json = json.dumps(trade_context)
                            trade_data = {
                                'timestamp': datetime.now(timezone(timedelta(hours=-3))),
                                'trade_id': trade_id,
                                'pair': pair,
                                'timeframe': duration,
                                'decision': action,
                                'pattern_detected': strat_name,
                                'price': close_val,
                                'ema': ema20_val, 
                                'rsi': latest_data.get('RSI', 0), 
                                'atr': latest_data.get('ATR', 0),
                                'result': 'BLOCKED_BY_GEMINI',
                                'profit_loss': 0.0,
                                'expiry_time': duration,
                                'notes': notes_json
                            }
                            trade_logger.log_trade(trade_data)

                            # --- GUARDAR TAMBIÉN EN BASE DE DATOS SQL (SQLite local) ---
                            timeframe_str = f"{duration // 60}min" if duration >= 60 else f"{duration}seg"
                            db_trade_blocked = {
                                'trade_id': trade_id,
                                'pair': pair,
                                'action': action,
                                'strategy': strat_name,
                                'timeframe': timeframe_str,
                                'amount': 0.0,
                                'open_price': close_val,
                                'close_price': close_val,
                                'result': 'blocked',
                                'profit': 0.0,
                                'telegram_message_id': None,
                                'ai_decision': 'BLOCKED',
                                'ai_confidence': ai_confidence,
                                'ai_reason': ai_reason,
                                'ai_snapshot': json.dumps(ai_snapshot)
                            }
                            self.db.save_trade(db_trade_blocked)
                            print(f"  [DB] Bloqueo de IA guardado en feedback.db")
                        except Exception as e:
                            print(f"  [ERROR] No se pudo guardar log de operacion bloqueada: {e}")
                            
                        continue

                    print(f"EJECUTANDO ORDEN: {action} en {pair} por {duration}s. Estrategia: {strat_name}")
                    
                    try:
                        amount = await self.calculate_trade_amount(pair)
                        
                        # --- COLOCAR ORDEN (Alpaca se coloca primero para obtener el ID real de la orden) ---
                        placed_id = None
                        if self.broker == 'alpaca':
                            duration_alpaca = self.config.get('holding_period_seconds', 14400)
                            buy_kwargs = {
                                "asset": pair, 
                                "amount": amount, 
                                "time": duration_alpaca, 
                                "check_win": False,
                                "latest_candle": latest_data
                            }
                            try:
                                if action == 'BUY':
                                    placed_id, _ = await asyncio.wait_for(
                                        self.api.buy(**buy_kwargs),
                                        timeout=15.0
                                    )
                                else:
                                    placed_id, _ = await asyncio.wait_for(
                                        self.api.sell(**buy_kwargs),
                                        timeout=15.0
                                    )
                                trade_id = str(placed_id)
                            except Exception as e:
                                print(f"  [ERROR] Excepcion colocando orden en Alpaca: {e}")
                                continue
                        else:
                            trade_id = str(uuid.uuid4())[:8]

                        # --- LOCK / BLOQUEO CONCURRENTE ---
                        if self.broker == 'alpaca':
                            duration_alpaca = self.config.get('holding_period_seconds', 14400)
                            self.active_trade_expiry_dict[pair] = datetime.now(timezone.utc) + timedelta(seconds=duration_alpaca + 60)
                            print(f"  [LOCK] Par {pair} bloqueado por {duration_alpaca}s en Alpaca.")
                        else:
                            self.active_trade_expiry = datetime.now(timezone.utc) + timedelta(seconds=duration + 10)
                            print(f"  [LOCK] Bot bloqueado hasta {self.active_trade_expiry.strftime('%H:%M:%S')} UTC")

                        # --- LOGGING PREVIO CON DETALLES COMPLETOS ---
                        # Calcular score MTF y detalles
                        mtf_score, mtf_details = await self.get_mtf_alignment_score(pair, action)
                        
                        # Distancia a la EMA20
                        close_val = latest_data.get('Close', 0)
                        ema20_val = latest_data.get('EMA_20', 0)
                        distance_ema20 = close_val - ema20_val
                        
                        # Construir el JSON de contexto
                        trade_context = {
                            "indicators": {
                                "price": close_val,
                                "ema20": ema20_val,
                                "ema50": latest_data.get('EMA_50', 0),
                                "sma200": latest_data.get('SMA_200', 0),
                                "distance_ema20": distance_ema20,
                                "rsi": latest_data.get('RSI', 0),
                                "stoch_k": latest_data.get('Stoch_K', 0),
                                "stoch_d": latest_data.get('Stoch_D', 0),
                                "atr": latest_data.get('ATR', 0),
                                "macd": latest_data.get('MACD', 0),
                                "macd_signal": latest_data.get('MACD_Signal', 0)
                            },
                            "market_state": ctx.get("market_state", "UNKNOWN") if isinstance(ctx, dict) else "UNKNOWN",
                            "regime": ctx.get("regime", "NEUTRAL") if isinstance(ctx, dict) else "NEUTRAL",
                            "mtf_alignment": {
                                "score": mtf_score,
                                "details": mtf_details
                            },
                            "gemini_validation": {
                                "approved": ai_ok,
                                "reason": ai_reason
                            }
                        }
                        
                        notes_json = json.dumps(trade_context)

                        trade_data = {
                            'timestamp': datetime.now(timezone(timedelta(hours=-3))),
                            'trade_id': trade_id,
                            'pair': pair,
                            'timeframe': duration,
                            'decision': action,
                            'pattern_detected': strat_name,
                            'price': close_val,
                            'ema': ema20_val, 
                            'rsi': latest_data.get('RSI', 0), 
                            'atr': latest_data.get('ATR', 0),
                            'result': 'PENDING',
                            'expiry_time': duration,
                            'notes': notes_json
                        }
                        trade_logger.log_trade(trade_data)
                        
                        # Notificar Apertura
                        await self.notifier.notify_open(pair, action, strat_name, duration, amount)

                        # --- PROCESO EXCLUSIVO ALPACA (Retorno Inmediato) ---
                        if self.broker == 'alpaca':
                            try:
                                timeframe_str = f"{duration // 60}min" if duration >= 60 else f"{duration}seg"
                                trade_db_data = {
                                    'trade_id': trade_id,
                                    'pair': pair,
                                    'action': action,
                                    'strategy': strat_name,
                                    'timeframe': timeframe_str,
                                    'amount': amount,
                                    'open_price': close_val,
                                    'close_price': close_val,
                                    'result': 'PENDING',
                                    'profit': 0.0,
                                    'telegram_message_id': None,
                                    'ai_decision': 'APPROVED',
                                    'ai_confidence': ai_confidence,
                                    'ai_reason': ai_reason,
                                    'ai_snapshot': json.dumps(ai_snapshot)
                                }
                                self.db.save_trade(trade_db_data)
                                print(f"  [DB] Operación {trade_id} (PENDING) guardada en base de datos.")
                            except Exception as db_e:
                                print(f"  [WARN] Error guardando en DB: {db_e}")
                            
                            await asyncio.sleep(5)
                            break # Salir del loop de pares para este ciclo

                        # --- PROCESO EXCLUSIVO POCKETOPTION (Bloqueante con Espera) ---
                        placed_id = None
                        try:
                            buy_kwargs = {"asset": pair, "amount": amount, "time": duration, "check_win": False}
                            if action == 'BUY':
                                placed_id, _ = await asyncio.wait_for(
                                    self.api.buy(**buy_kwargs),
                                    timeout=15.0
                                )
                            else:
                                placed_id, _ = await asyncio.wait_for(
                                    self.api.sell(**buy_kwargs),
                                    timeout=15.0
                                )
                        except asyncio.TimeoutError:
                            print(f"  [ERROR] Timeout colocando la orden. PocketOption no respondio en 15s.")
                            self.active_trade_expiry = datetime.now(timezone.utc)
                            continue
                        except Exception as e:
                            print(f"  [ERROR] Excepcion colocando orden: {e}")
                            self.active_trade_expiry = datetime.now(timezone.utc)
                            continue

                        print(f"  [OK] Orden colocada. API trade_id: {placed_id or 'desconocido'}")
                        
                        # --- ESPERAR DURACIÓN DEL TRADE ---
                        print(f"  [WAIT] Esperando {duration}s para confirmar resultado...")
                        await asyncio.sleep(duration + 5)  # +5s de margen para que cierre
                        
                        # --- CONSULTAR RESULTADO VÍA closed_deals (sin depender del WebSocket bloqueante) ---
                        is_win = False
                        profit = 0.0
                        result_confirmed = False
                        
                        try:
                            closed = await asyncio.wait_for(self.api.closed_deals(), timeout=10.0)
                            # Buscar el trade por el ID de la API o por el más reciente del par
                            matched = None
                            if placed_id:
                                matched = next((d for d in closed if str(d.get('id', '')) == str(placed_id)), None)
                            if not matched and closed:
                                # Fallback: el trade más reciente del mismo par
                                recent = sorted(
                                    [d for d in closed if d.get('asset', '').replace('-', '_') == pair or d.get('asset') == pair],
                                    key=lambda x: x.get('close_time', 0),
                                    reverse=True
                                )
                                if recent:
                                    matched = recent[0]
                            
                            if matched:
                                profit = float(matched.get('profit', 0.0))
                                is_win = profit > 0
                                result_confirmed = True
                                print(f"  [OK] Resultado confirmado via closed_deals: {'WIN' if is_win else 'LOSS'} | Profit: {profit:.2f}")
                            else:
                                print(f"  [WARN] No se encontro el trade en closed_deals. Marcando resultado como desconocido.")
                        except asyncio.TimeoutError:
                            print(f"  [WARN] Timeout consultando closed_deals. Resultado no confirmado.")
                        except Exception as e:
                            print(f"  [WARN] Error consultando closed_deals: {e}")
                        
                        if not result_confirmed:
                            # Último recurso: intentar check_win con el ID de API
                            if placed_id:
                                try:
                                    details = await asyncio.wait_for(self.api.check_win(placed_id), timeout=10.0)
                                    profit = float(details.get('profit', 0.0))
                                    is_win = profit > 0
                                    result_confirmed = True
                                    print(f"  [OK] Resultado via check_win: {'WIN' if is_win else 'LOSS'}")
                                except Exception:
                                    print(f"  [WARN] check_win tambien fallo. Registrando como pendiente.")
                                    profit = 0.0
                                    is_win = False
                        
                        print(f"  >>> Resultado Operacion: {'GANADA' if is_win else 'PERDIDA'}")
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
                                'telegram_message_id': None, # Se actualizará si hay feedback manual
                                'ai_decision': 'APPROVED',
                                'ai_confidence': ai_confidence,
                                'ai_reason': ai_reason,
                                'ai_snapshot': json.dumps(ai_snapshot)
                            }
                            self.db.save_trade(trade_db_data)
                            print(f"  [DB] Operación {trade_id} guardada en feedback.db")
                        except Exception as db_e:
                            print(f"  [WARN] Error guardando en DB: {db_e}")

                        # --- RE-CALCULAR INTELIGENCIA Y RE-APRENDER EN TIEMPO REAL ---
                        try:
                            print("🧠 [Self-Improvement] Recalculando zonas de rendimiento y umbrales dinámicos...")
                            analyze_logs(config_path=self.config_path)
                            from analyze_best_times import generate_dynamic_threshold_matrix
                            generate_dynamic_threshold_matrix(config_path=self.config_path)
                            self.intelligence = self._load_intelligence()
                            self.thresholds = self._load_thresholds()
                        except Exception as intel_e:
                            print(f"⚠️ Error actualizando inteligencia de trading tras trade: {intel_e}")

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

_LOCK_SOCKET = None

def acquire_port_lock(config_file):
    import socket
    import hashlib
    import os
    
    # Crear un hash único a partir de la ruta absoluta del archivo de configuración
    abs_path = os.path.abspath(config_file)
    h = int(hashlib.md5(abs_path.encode('utf-8')).hexdigest(), 16)
    port = 50000 + (h % 10000) # Rango de puertos seguros 50000 - 59999
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', port))
        s.listen(1)
        return s # Retener socket abierto durante la vida de la app
    except OSError:
        return None

async def main():
    global _LOCK_SOCKET
    import sys
    # Reconfigurar salida standard para evitar errores Unicode en Windows
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    # Determinar ruta del archivo de configuración
    config_file = 'config.json'
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
        
    # Adquirir bloqueo de puerto único para evitar instancias concurrentes de la misma configuración
    _LOCK_SOCKET = acquire_port_lock(config_file)
    if not _LOCK_SOCKET:
        print(f"\n❌ ERROR CRÍTICO: Ya hay una instancia de este bot ejecutándose con la configuración '{config_file}'!")
        print("Para evitar duplicación de operaciones y riesgos de capital, se aborta la ejecución.")
        return
        
    # 1. Intentar cargar configuración desde Variables de Entorno (Modo Nube)
    config = {}
    env_config = os.getenv('BOT_CONFIG')
    
    if env_config:
        try:
            config = json.loads(env_config)
            print("🌐 Configuración cargada desde Variable de Entorno (BOT_CONFIG)")
        except Exception as e:
            print(f"⚠️ Error parseando BOT_CONFIG: {e}")
    
    # 2. Si no hay en env, intentar desde el archivo configurado
    if not config:
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"🏠 Configuración cargada desde {config_file}")
            except Exception as e:
                print(f"⚠️ Error leyendo {config_file}: {e}")

    broker = config.get('broker', 'pocketoption')
    ssid = config.get('ssid')
    tg_token = config.get('telegram_token')
    tg_chat = config.get('telegram_chat_id')
    tg_owner = config.get('telegram_owner_id')
    
    if broker == 'pocketoption' and not ssid:
        print("❌ CRÍTICO: No se encontró SSID en la configuración ni en las variables de entorno.")
        return
    elif broker == 'alpaca':
        # Verificar credenciales de Alpaca
        alpaca_key = config.get('alpaca_key_id')
        alpaca_secret = config.get('alpaca_secret_key')
        if not alpaca_key or not alpaca_secret:
            print("❌ CRÍTICO: No se encontraron las credenciales de Alpaca (alpaca_key_id / alpaca_secret_key) en la configuración.")
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
        
        async def start_server():
            try:
                await site.start()
                print(f"📡 Servidor keep-alive iniciado en puerto {port}")
            except OSError as bind_err:
                print(f"⚠️ Servidor keep-alive no pudo iniciarse en puerto {port} (puerto en uso): {bind_err}")
            except Exception as e:
                print(f"⚠️ Error al iniciar servidor keep-alive: {e}")
                
        asyncio.create_task(start_server())

    # 5. Iniciar el Bot
    bot = TradingBot(ssid, tg_token, tg_chat, tg_owner, config=config.get('trading', config), root_config=config, config_path=config_file)
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")
