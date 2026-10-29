import asyncio
import pandas as pd
import numpy as np
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
from strategy_ttm_squeeze import StrategyTTMSqueeze
from strategy_hybrid_sniper import StrategyHybridSniper
from strategy_bollinger_rsi import StrategyBollingerRSI
from strategy_price_action_engulfing import StrategyPriceActionEngulfing
from strategy_trend_pullback import StrategyTrendPullback
from strategy_divergence_pivot import StrategyDivergencePivot
from strategy_smart_money_smc import StrategySmartMoneySMC
from strategy_fibonacci_master import StrategyFibonacciMasterSniper
from strategy_smc_elite import StrategySMCElite
from strategy_chartist_patterns import StrategyChartistPatterns
from strategy_micro_breakout_7v import StrategyMicroBreakout7v
from strategy_bb_burst_pro import StrategyBBBurstPro
from strategy_ttm_squeeze_pro import StrategyTTMSqueezePro
from strategy_vsa_climax import StrategyVSAClimax
from strategy_orderblock_mtf import StrategyOrderBlockMTF
from strategy_vwap_reversion import StrategyVWAPReversion
from strategy_momentum_conf import StrategyMomentumConfluence
from graduated_strategy_loader import load_graduated_strategies

from trade_logger import TradeLogger, trade_logger
from feedback_db import FeedbackDB
from money_management import MoneyManagement
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
    "verbose_telegram": False,
    "amount": 1.0,
    "daily_stop_loss": -15.0,
    "daily_take_profit": 10.0
}

class TradingBot:
    def __init__(self, ssid, telegram_token=None, telegram_chat_id=None, telegram_owner_id=None, config=None, root_config=None, config_path='config.json'):
        self.config_path = config_path
        self.root_config = root_config or {}
        self.broker = self.root_config.get('broker', 'pocketoption')
        
        # Configurar logger independiente por instancia según configuración
        logger_suffix = Path(self.config_path).stem
        if logger_suffix == "config":
            tbl_cfg = self.root_config.get('supabase_table', '')
            logger_suffix = "pocketoption_real" if "real" in tbl_cfg else "pocketoption"
        self.trade_logger = TradeLogger(
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
        
        gemini_key = self.root_config.get('gemini_api_key') or (config or {}).get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
        security_pin = str(self.root_config.get('security_pin') or (config or {}).get('security_pin', '2026'))
        self.notifier = TelegramNotifier(
            telegram_token, 
            telegram_chat_id, 
            telegram_owner_id,
            get_balance_callback=self.get_balance,
            gemini_api_key=gemini_key,
            bot_ref=self,
            security_pin=security_pin
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
        # ESTRATEGIAS BLINDADAS: Solo estrategias con ventaja estadística en tendencia y estructura
        # WaveTrendKeltner y reversiones descontroladas desactivadas por alto índice de fallas (WR < 20% en OTC).
        all_strategies = [
            StrategySMCElite(bypass_filter=False),
            StrategyTrendPullback(bypass_filter=False),
            StrategyStochastic(bypass_filter=False),
            StrategySmartMoneySMC(bypass_filter=False),
            StrategyMomentumConfluence(bypass_filter=False),
            StrategyContinuation()
        ]
        
        enabled_list = self.config.get('enabled_strategies')
        if enabled_list is not None:
            self.strategies = [s for s in all_strategies if s.name in enabled_list]
            print(f"[Bot] Estrategias activas filtradas: {[s.name for s in self.strategies]}")
        else:
            self.strategies = all_strategies

        # Cargar e inyectar automáticamente estrategias graduadas (WR >= 60% en Paper)
        self.graduated_strategies = {}
        self._load_and_inject_graduated_strategies(verbose=True)

        
        # Base de datos de feedback y mantenimiento
        db_stem = Path(self.config_path).stem
        db_name = f"feedback_{db_stem}.db" if db_stem != "config" else "feedback.db"
        self.db = FeedbackDB(db_name)
        self.db.maintain()
        
        # Inteligencia Artificial (Filtros Históricos)
        self.intelligence = self._load_intelligence()
        self.thresholds = self._load_thresholds()
        self.whitelist = self._load_whitelist()

        # --- GESTIÓN DE RIESGO Y CAPITAL ---
        if self.broker != 'alpaca':
            # PocketOption: Gestión estricta Miriam Molina (Proyecto Nuevo)
            mm_cfg = self.config.get('money_management') or self.root_config.get('money_management') or {}
            self.mm = MoneyManagement(
                base_amount=mm_cfg.get('base_amount', self.config.get('amount', 1.0)),
                max_compound_levels=mm_cfg.get('max_compound_levels', 2),
                max_session_trades=mm_cfg.get('max_session_trades', 5),
                max_wins=mm_cfg.get('max_wins_take_profit', 3),
                max_losses=mm_cfg.get('max_losses_stop_loss', 3),
                auto_reset_on_target=mm_cfg.get('auto_reset_on_target', False),
                state_file="session_state.json",
                db_file=db_name
            )
            self.session_profit = self.mm.session_pnl
        else:
            # Alpaca: Gestión para acciones/ETFs según config_alpaca.json
            self.mm = None
            self.session_profit = 0.0
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                import sqlite3
                conn = sqlite3.connect(db_name)
                cur = conn.cursor()
                rows = cur.execute("SELECT profit FROM trades WHERE timestamp LIKE ? AND result IN ('win', 'loss')", (f"{today}%",)).fetchall()
                conn.close()
                self.session_profit = sum(float(r[0]) for r in rows)
            except Exception:
                pass

        self.daily_stop_loss = self.config.get('daily_stop_loss', DEFAULT_CONFIG['daily_stop_loss'])
        self.daily_take_profit = self.config.get('daily_take_profit', DEFAULT_CONFIG['daily_take_profit'])
        self.strategy_fails = {}      # Seguimiento de rachas negativas por sesión
        self.consecutive_losses = {}  # Seguimiento por par
        
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
                    model_name='gemini-1.5-flash',
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
                            
                            real_close = float(matched.get('close_price') or matched.get('close') or 0.0)
                            close_ts = datetime.now().isoformat()
                            # Actualizar el registro con precio real y timestamp de salida
                            cursor.execute("""
                                UPDATE trades 
                                SET result = ?, profit = ?, close_price = ?, close_timestamp = ?
                                WHERE trade_id = ?
                            """, ('win' if is_win else 'loss', profit, real_close if real_close > 0 else (open_price + (profit / amount if amount > 0 else 0)), close_ts, db_trade_id))
                            conn.commit()
                            
                            # Actualizar CSV
                            self.trade_logger.update_trade_result(
                                trade_id=db_trade_id,
                                result='WIN' if is_win else 'LOSS',
                                profit_loss=profit
                            )
                            
                            # Actualizar métricas de sesión y Money Management
                            outcome = 'WIN' if is_win else ('DRAW' if profit == 0 else 'LOSS')
                            if hasattr(self, 'mm') and self.mm is not None:
                                self.mm.register_result(outcome, profit)
                                self.session_profit = self.mm.session_pnl
                            else:
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
                            print(f"[Alpaca Monitor] Trade sincronizado {placed_id} finalizado. Profit: ${profit:.2f}. Notificando en Telegram...")
                            outcome = 'WIN' if is_win else ('DRAW' if profit == 0 else 'LOSS')
                            if hasattr(self, 'mm') and self.mm is not None:
                                self.mm.register_result(outcome, profit)
                                self.session_profit = self.mm.session_pnl
                            else:
                                self.session_profit += profit
                            if pair in self.active_trade_expiry_dict:
                                self.active_trade_expiry_dict[pair] = datetime.min.replace(tzinfo=timezone.utc)
                            await self.notifier.notify_close(pair, profit, is_win, trade_id=str(placed_id))
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
                    self.use_gemini_live = trading_config.get('use_gemini_live', new_config.get('use_gemini_live', False))
                    
                    self.config = trading_config
                    
                    enabled_list = trading_config.get('enabled_strategies')
                    if enabled_list is not None:
                        is_alpaca = self.broker == 'alpaca'
                        all_strats = [
                            StrategyHybridSniper(bypass_filter=True),
                            StrategyBollingerRSI(bypass_filter=True),
                            StrategyPriceActionEngulfing(bypass_filter=True),
                            StrategyTrendPullback(bypass_filter=True),
                            StrategyWaveTrendKeltner(bypass_filter=True),
                            StrategyTTMSqueeze(bypass_filter=True),
                            StrategyStochastic(bypass_filter=False),
                            StrategyAlphaConvergence(bypass_filter=True),
                            StrategyFibonacci(bypass_filter=True),
                            StrategyStructure(),
                            StrategyExpertVision(bypass_filter=True),
                            StrategyContinuation(),
                            StrategyDivergencePivot(bypass_filter=True),
                            StrategySmartMoneySMC(bypass_filter=True),
                            StrategyFibonacciMasterSniper(bypass_filter=True),
                            StrategyChartistPatterns(bypass_filter=True),
                            StrategyMicroBreakout7v(bypass_filter=True),
                            StrategyBBBurstPro(bypass_filter=True),
                            StrategyTTMSqueezePro(bypass_filter=True),
                            StrategyVSAClimax(bypass_filter=True),
                            StrategyOrderBlockMTF(bypass_filter=True),
                            StrategyVWAPReversion(bypass_filter=True),
                            StrategyMomentumConfluence(bypass_filter=True)
                        ]
                        self.strategies = [s for s in all_strats if s.name in enabled_list]
                        self._load_and_inject_graduated_strategies(verbose=True)
                        print(f"[Bot] Estrategias activas recargadas: {[s.name for s in self.strategies]}")
                    
                # Recargar parámetros de MoneyManagement
                mm_cfg = trading_config.get('money_management') or new_config.get('money_management')
                if mm_cfg and getattr(self, 'mm', None) is not None:
                    self.mm.base_amount = float(mm_cfg.get('base_amount', getattr(self.mm, 'base_amount', 1.0)))
                    self.mm.max_compound_levels = int(mm_cfg.get('max_compound_levels', getattr(self.mm, 'max_compound_levels', 2)))
                    self.mm.max_session_trades = int(mm_cfg.get('max_session_trades', getattr(self.mm, 'max_session_trades', 5)))
                    self.mm.max_wins = int(mm_cfg.get('max_wins_take_profit', getattr(self.mm, 'max_wins', 3)))
                    self.mm.max_losses = int(mm_cfg.get('max_losses_stop_loss', getattr(self.mm, 'max_losses', 2)))
                    
                # Recargar inteligencia estática en memoria
                self.intelligence = self._load_intelligence()
                self.thresholds = self._load_thresholds()
                
                # Recargar dinámicamente estrategias graduadas en cada ciclo
                self._load_and_inject_graduated_strategies(verbose=False)
                
        except Exception as e:
            print(f"[WARN] [Config] Error al recargar configuracion dinamica: {e}")

    def _load_and_inject_graduated_strategies(self, verbose=True):
        """
        Inyecta dinámicamente las estrategias promovidas por el optimizador genético
        desde 'strategies_ready_for_live.json' (WR >= 60.0% en Paper Trading).
        """
        try:
            graduated_list = load_graduated_strategies()
            if not graduated_list:
                return

            if not hasattr(self, 'graduated_strategies'):
                self.graduated_strategies = {}

            existing_names = {s.name: s for s in self.strategies}
            newly_injected = []

            for strat in graduated_list:
                self.graduated_strategies[strat.name] = strat
                if strat.name not in existing_names:
                    self.strategies.append(strat)
                    existing_names[strat.name] = strat
                    newly_injected.append(strat.name)
                else:
                    existing = existing_names[strat.name]
                    if hasattr(strat, 'target_pairs') and strat.target_pairs:
                        existing.target_pairs = strat.target_pairs
                    if hasattr(strat, 'toxic_pairs') and strat.toxic_pairs:
                        existing.toxic_pairs = strat.toxic_pairs
                    if hasattr(strat, 'allowed_hours') and strat.allowed_hours:
                        existing.allowed_hours = strat.allowed_hours
                    if hasattr(strat, 'toxic_hours') and strat.toxic_hours:
                        existing.toxic_hours = strat.toxic_hours
                    if hasattr(strat, 'paper_win_rate'):
                        existing.paper_win_rate = strat.paper_win_rate
                    existing.is_graduated = True

            if newly_injected and verbose:
                msg = f"🎓 [GRADUATED] Inyectadas {len(newly_injected)} variantes graduadas para operar en real: {newly_injected}"
                print(f"[Bot] {msg}")
                try:
                    from gui_bridge import gui_bridge
                    gui_bridge.log(msg, "WIN")
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Error inyectando estrategias graduadas: {e}")

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
        # Reactivado para bloquear zonas horarias perdedoras y estrategias sin edge estadístico.
            
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

    def check_chop_entropy(self, df):
        """
        INNOVACIÓN 3: Detector dinámico de pares tóxicos y ruido (Anti-Chop).
        Analiza las últimas 12 velas. Si hay demasiados Dojis o cuerpos ínfimos, el par se bloquea.
        """
        if df is None or len(df) < 12:
            return True, "Datos insuficientes para filtro de ruido"
        
        recent = df.iloc[-12:].copy()
        highs = recent['High'].values
        lows = recent['Low'].values
        opens = recent['Open'].values
        closes = recent['Close'].values

        ranges = np.maximum(highs - lows, 0.00001)
        bodies = np.abs(closes - opens)
        
        # Un Doji en OTC tiene cuerpo menor al 12% del rango total de la vela
        dojis = (bodies / ranges) <= 0.12
        doji_count = int(np.sum(dojis))

        # Si 3 o más velas de las últimas 12 son Dojis, el mercado está en indecisión errática
        if doji_count >= 3:
            return False, f"Mercado Tóxico en Vivo: {doji_count}/12 velas Doji detectadas (Chop market)"

        # Ratio promedio de cuerpo vs mecha
        mean_body_ratio = float(np.mean(bodies / ranges))
        if mean_body_ratio < 0.25:
            return False, f"Mercado sin Volumen: Cuerpos de vela anémicos ({mean_body_ratio*100:.1f}% del rango)"

        return True, "Volumen y estructura de velas saludable"

    def check_wick_absorption(self, latest_candle, action):
        """
        INNOVACIÓN 1: Detector de Absorción de Mechas OTC (Liquidity Vacuum).
        Bloquea señales si la vela gatillo sufrió un rechazo violento contrario a la dirección deseada.
        """
        high = latest_candle.get('High', 0)
        low = latest_candle.get('Low', 0)
        open_p = latest_candle.get('Open', 0)
        close_p = latest_candle.get('Close', 0)

        total_range = max(high - low, 0.00001)
        upper_shadow = high - max(open_p, close_p)
        lower_shadow = min(open_p, close_p) - low

        upper_wick_ratio = upper_shadow / total_range
        lower_wick_ratio = lower_shadow / total_range

        # En compras (BUY): Si dejó más de 38% de mecha superior, hubo absorción institucional bajista
        if action == "BUY":
            if upper_wick_ratio >= 0.38:
                return False, f"Absorción Bajista OTC: Mecha superior excesiva ({upper_wick_ratio*100:.1f}% de rechazo)"

        # En ventas (SELL): Si dejó más de 38% de mecha inferior, hubo absorción institucional alcista
        elif action == "SELL":
            if lower_wick_ratio >= 0.38:
                return False, f"Absorción Alcista OTC: Mecha inferior excesiva ({lower_wick_ratio*100:.1f}% de rechazo)"

        return True, "Sin absorción contraria peligrosa"

    def evaluate_candle_footprint(self, latest_candle, action, market_state, df=None):
        """
        INNOVACIÓN 4: Huella de Vela Cuantitativa (Candle Footprint Score de 0 a 10).
        Solo autoriza la orden si el score de calidad de la vela gatillo es >= 7.5 / 10.
        """
        score = 0.0
        details = []

        close_p = latest_candle.get('Close', 0)
        open_p = latest_candle.get('Open', 0)
        high = latest_candle.get('High', 0)
        low = latest_candle.get('Low', 0)
        ema_20 = latest_candle.get('EMA_20', 0)
        total_range = max(high - low, 0.00001)
        body = abs(close_p - open_p)

        # 1. Dirección del cuerpo de la vela (+3.0 pts)
        if action == "BUY" and close_p > open_p:
            score += 3.0
            details.append("Cuerpo alcista (+3)")
        elif action == "SELL" and close_p < open_p:
            score += 3.0
            details.append("Cuerpo bajista (+3)")

        # 2. Dominancia del cuerpo vs mechas (+2.5 pts)
        body_ratio = body / total_range
        if body_ratio >= 0.50:
            score += 2.5
            details.append(f"Cuerpo sólido {body_ratio*100:.0f}% (+2.5)")
        elif body_ratio >= 0.35:
            score += 1.5
            details.append(f"Cuerpo moderado {body_ratio*100:.0f}% (+1.5)")

        # 3. Alineación con EMA20 (+2.5 pts)
        if action == "BUY" and ema_20 > 0 and close_p > ema_20:
            score += 2.5
            details.append("Sobre EMA20 (+2.5)")
        elif action == "SELL" and ema_20 > 0 and close_p < ema_20:
            score += 2.5
            details.append("Bajo EMA20 (+2.5)")

        # 4. Régimen de mercado favorable (+2.0 pts)
        if action == "BUY" and market_state in ["TRENDING_UP", "NEUTRAL"]:
            score += 2.0
            details.append("Régimen afín (+2)")
        elif action == "SELL" and market_state in ["TRENDING_DOWN", "NEUTRAL"]:
            score += 2.0
            details.append("Régimen afín (+2)")

        passed_fp = score >= 7.5
        reason_fp = f"Footprint Score: {score:.1f}/10 ({', '.join(details)})"
        return passed_fp, reason_fp, score

    def local_risk_fallback(self, snapshot):
        """
        Filtro técnico local directo de protección de capital (Candado anti-cuchillo cayendo y anti-OTC rally).
        Bloquea compras cuando el precio se desploma y ventas cuando el precio sube verticalmente.
        """
        action = snapshot.get("action")
        close = snapshot.get("close", 0)
        ema_20 = snapshot.get("ema_20", 0)
        ema_50 = snapshot.get("ema_50", 0)
        rsi = snapshot.get("rsi", 50)
        stoch_k = snapshot.get("stoch_k", 50)
        market_state = snapshot.get("market_state", "")

        # 1. Candado Anti-Cuchillo Cayendo en BUY
        if action == "BUY":
            # Si el mercado está en tendencia bajista fuerte o el precio está muy por debajo de ambas EMAs con RSI aplastado
            if market_state == "TRENDING_DOWN" and ema_20 > 0 and close < ema_20 and rsi < 35:
                return False, f"Bloqueado por Candado Técnico: Compra en caída libre sin soporte (RSI={rsi:.1f}, Close < EMA20)"
            if stoch_k > 85:
                return False, f"Bloqueado por Agotamiento: Compra en sobrecompra extrema (Stoch_K={stoch_k:.1f})"

        # 2. Candado Anti-Rally Vertical en SELL
        elif action == "SELL":
            # Si el mercado está en tendencia alcista fuerte o el precio está disparado por encima de ambas EMAs con RSI sobreextendido
            if market_state == "TRENDING_UP" and ema_20 > 0 and close > ema_20 and rsi > 65:
                return False, f"Bloqueado por Candado Técnico: Venta contra tendencia alcista vertical (RSI={rsi:.1f}, Close > EMA20)"
            if stoch_k < 15:
                return False, f"Bloqueado por Agotamiento: Venta en sobreventa extrema (Stoch_K={stoch_k:.1f})"

        return True, "Aprobado (Validación técnica local superada)"


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

        prompt = f"""Eres un filtro inteligente de riesgo para un bot de trading algorítmico (PocketOption). Analiza esta señal técnica y responde SOLO con un objeto JSON.

SEÑAL PROPUESTA Y CONTEXTO COMPLETO:
{json.dumps(snapshot, indent=2)}

INSTRUCCIONES DE EVALUACIÓN SEGÚN TIPO DE ESTRATEGIA:
1. Si la estrategia es de REVERSIÓN / SOBRECOMPRA-SOBREVENTA ('REVERSION' como WaveTrend, Alpha Convergence, Estocástico, Fibonacci, Expert Vision):
   - Es NORMAL y ESPERADO que para una VENTA (SELL) el precio esté alto (RSI > 55, Stoch > 75) y para una COMPRA (BUY) el precio esté bajo (RSI < 45, Stoch < 25). NO bloquees por estas condiciones normales de giro.
   - SOLO BLOQUEA si el mercado está en una tendencia macro H1 imparable y violenta en contra (ej: VENDER en una tendencia alcista agresiva 'TRENDING_UP' con velas gigantes sin mechas de rechazo), o en consolidación sin volatilidad (ATR plano).

2. Si la estrategia es de TENDENCIA / CONTINUACIÓN ('TREND' como Patrones de Continuación):
   - BLOQUEA si intenta COMPRAR en el pico máximo de sobrecompra extrema (RSI > 75, Stoch > 95) o VENDER en el piso de sobreventa extrema (RSI < 25, Stoch < 5).
   - BLOQUEA si va en contra de la dirección del régimen macro.

3. REGLA GENERAL:
   - Si la señal es coherente técnicamente con el propósito de su estrategia, tu veredicto DEBE SER "APPROVED".
   - Reserva "BLOCKED" únicamente para trampas de mercado evidentes o riesgos extremos.

Devuelve SOLO este JSON:
{{"decision": "APPROVED" o "BLOCKED", "confidence": 1-100, "reason": "Una frase concisa en español explicando por qué se aprueba o el riesgo exacto por el que se bloquea"}}"""

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

    async def trigger_killapp(self, stop_reason):
        """Ejecuta Killapp: Notifica por Telegram y cierra todos los procesos del bot para blindar la cuenta."""
        st = self.mm.get_status() if hasattr(self, 'mm') and self.mm is not None else {
            'session_trades': 0, 'session_wins': 0, 'session_losses': 0, 'session_pnl': self.session_profit
        }
        max_trades = getattr(self.mm, 'max_session_trades', 5) if hasattr(self, 'mm') and self.mm is not None else 5
        
        msg = (
            f"🛑 <b>[PocketOption] KILLAPP EJECUTADO - RETIRO DEL MERCADO</b>\n\n"
            f"📌 <b>Motivo:</b> {stop_reason}\n"
            f"📊 <b>Operaciones hoy:</b> {st['session_trades']}/{max_trades}\n"
            f"🏆 <b>Score final:</b> {st['session_wins']}W - {st['session_losses']}L\n"
            f"💰 <b>PnL Sesión:</b> ${st['session_pnl']:+.2f} USD\n\n"
            f"🔒 <b>Seguridad:</b> <i>Killapp ha cerrado por completo el bot y sus procesos. Tu capital queda 100% resguardado hasta el próximo encendido de tu PC o mañana.</i>"
        )
        print(f"\n" + "="*65)
        print(f"🛑 [KILLAPP] {stop_reason}")
        print(f"   Score: {st['session_wins']}W - {st['session_losses']}L | PnL: ${st['session_pnl']:+.2f} USD")
        print(f"   Apagando el bot por killapp...")
        print("="*65 + "\n")
        
        try:
            if self.notifier and self.notifier.token:
                await self.notifier.send_message(msg)
                await asyncio.sleep(2) # Esperar a que Telegram complete el envío
        except Exception as e:
            print(f"⚠️ Error enviando notificación de Killapp: {e}")

        # Marcar archivo de bandera killapp para avisar al supervisor run_bot.py
        try:
            with open("killapp.flag", "w", encoding="utf-8") as kf:
                kf.write(f"{datetime.now().isoformat()} - {stop_reason}")
        except Exception:
            pass

        # Salir con código 0: esto le indica al supervisor run_bot.py que se apague de inmediato
        import os
        os._exit(0)

    async def get_balance(self):
        """Obtiene el balance actual de la cuenta con reintentos para permitir el handshake del WebSocket."""
        for attempt in range(4):
            try:
                balance = await self.api.balance()
                if balance > -1.0:
                    return balance
                # Si devuelve -1.0 en el primer segundo, dar tiempo al handshake del WebSocket
                await asyncio.sleep(1.5)
            except Exception as e:
                if self.verbose:
                    print(f"[Bot] Intento {attempt+1} obteniendo balance: {e}")
                await asyncio.sleep(1.5)
                
        print("[Bot] [ERR] ERROR: SSID Invalido o Expirado tras 4 intentos (Balance: -1.0)")
        return "SSID Expirado"

    async def calculate_trade_amount(self, pair):
        """Calcula el monto de la operación según el broker y la gestión de capital."""
        balance = await self.get_balance()
        bal_float = balance if isinstance(balance, (int, float)) and balance > 0 else None
        
        # PocketOption usa MoneyManagement (Miriam Molina / Proyecto Nuevo - Soros 2 niveles)
        if self.broker != 'alpaca' and hasattr(self, 'mm') and self.mm is not None:
            amount = self.mm.get_trade_amount(bal_float)
            bal_str = f"${balance:.2f}" if bal_float else str(balance)
            print(f"  [PocketOption - Soros Nivel {self.mm.compound_level + 1}] {pair}: Inversión ${amount:.2f} USD (Saldo: {bal_str})")
            return max(1.0, float(amount))
            
        # Alpaca usa gestión para acciones según config_alpaca.json
        if self.broker == 'alpaca':
            import math
            mm_config = self.config.get('money_management', {})
            mode = mm_config.get('mode', 'compound')
            fixed_amt = float(mm_config.get('fixed_amount', self.amount))
            if mode == 'compound' and bal_float:
                pct = min(float(mm_config.get('compound_percentage', 0.05)), 0.05)
                amt = max(fixed_amt, math.floor(bal_float * pct))
                return float(amt)
            return float(fixed_amt)

        return max(1.0, float(self.amount))

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
                    err_str = str(e)
                    if "Invalid asset" in err_str:
                        if self.verbose:
                            print(f"⚠️ Activo no disponible en PocketOption ({pair}): omitiendo.")
                        return pd.DataFrame()
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
                allowed_types = ['TREND', 'REVERSION', 'REVERSAL', 'BREAKOUT', 'MOMENTUM', 'TREND_PULLBACK', 'TREND_FOLLOWING']
            else:
                allowed_types = []
        else:
            if market_state in ['TRENDING_UP', 'TRENDING_DOWN']:
                allowed_types = ['TREND', 'BREAKOUT', 'MOMENTUM', 'TREND_PULLBACK', 'TREND_FOLLOWING']
            elif market_state == 'SIDEWAYS':
                # Evitamos operar por completo en consolidaciones de bajo rango (chop market)
                allowed_types = []
            elif market_state == 'VOLATILE':
                # Protegemos el capital evitando operaciones durante volatilidad descontrolada
                allowed_types = []
            elif market_state == 'NEUTRAL':
                # En transiciones o mercados sin tendencia, permitimos reversión y rupturas de compresión
                allowed_types = ['REVERSION', 'REVERSAL', 'TREND', 'BREAKOUT', 'MOMENTUM', 'TREND_PULLBACK']
            else:
                allowed_types = []

        curr_hour_utc = datetime.now(timezone.utc).hour
        for strategy in self.strategies:
            # 1. Filtro de par restringido (target_pairs y toxic_pairs de la optimización)
            clean_pair = pair.replace('#', '').replace('_otc', '').upper()
            target_pairs = getattr(strategy, 'target_pairs', None)
            if target_pairs:
                allowed_pairs = [p.replace('#', '').replace('_otc', '').upper() for p in target_pairs]
                if clean_pair not in allowed_pairs:
                    continue

            toxic_pairs = getattr(strategy, 'toxic_pairs', None)
            if toxic_pairs:
                blocked_pairs = [p.replace('#', '').replace('_otc', '').upper() for p in toxic_pairs]
                if clean_pair in blocked_pairs:
                    if self.verbose:
                        print(f"  [PAIR SHIELD] Saltando {strategy.name}: Par {pair} identificado como tóxico (<45% WR)")
                    continue

            # 2. Filtro Horario Dinámico por Estrategia (Horas de Oro y Horas Tóxicas)
            allowed_hours = getattr(strategy, 'allowed_hours', None)
            if allowed_hours and curr_hour_utc not in allowed_hours:
                continue

            toxic_hours = getattr(strategy, 'toxic_hours', None)
            if toxic_hours and curr_hour_utc in toxic_hours:
                if self.verbose:
                    print(f"  [HOURLY SHIELD] Saltando {strategy.name}: Hora {curr_hour_utc:02d}:00 UTC es tóxica para esta estrategia")
                strategy_logs.append(f"   🛡️ <b>{strategy.name}</b>: Hora tóxica ({curr_hour_utc:02d}:00 UTC)")
                continue

            # 3. Filtro de régimen de mercado
            strat_type = getattr(strategy, 'type', 'TREND')
            is_graduated = getattr(strategy, 'is_graduated', False) or getattr(strategy, 'bypass_regime', False)
            if not is_graduated and strat_type not in allowed_types:
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
            await self.notifier.send_message("🤖 <b>Bot Started</b>\nReady to trade.")
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
                    active_trades_data = {}
                    if hasattr(self.api, 'active_trades'):
                        active_trades_data = {k: v for k, v in self.api.active_trades.items()}
                    inv_cap = 0.0
                    if hasattr(self.api, 'get_invested_capital'):
                        inv_cap = await self.api.get_invested_capital()
                    open_cnt = len([t for t in active_trades_data.values() if t.get('status', 'active') == 'active'])
                    with open('alpaca_status.json', 'w', encoding='utf-8') as sf:
                        json.dump({
                            'balance': balance,
                            'invested_capital': inv_cap,
                            'max_invested_capital': float(self.config.get('max_invested_capital_usd', 40000.0)),
                            'open_trades_count': open_cnt,
                            'active_trades': active_trades_data,
                            'last_updated': datetime.now(timezone.utc).isoformat()
                        }, sf)
                except Exception as sf_err:
                    print(f"[Alpaca Status] Error escribiendo status compartido: {sf_err}")

            if balance == "Network Error":
                print("[WARN] Error temporal de red al consultar balance. Reintentando en el próximo ciclo...")
                await asyncio.sleep(10)
                continue
            elif balance == "SSID Expirado" or (self.broker == 'alpaca' and balance == -1.0):
                if self.broker != 'alpaca':
                    creds = self.root_config.get('credentials') or self.config.get('credentials')
                    if creds and creds.get('email') and creds.get('password'):
                        print("\n[PocketOption] 🔄 SSID expirado detectado. Intentando auto-renovación de sesión vía Playwright...")
                        if self.notifier and self.notifier.token:
                            try:
                                await self.notifier.send_message("🔄 <b>PocketOption:</b> SSID expirado. Iniciando auto-login para renovar sesión...")
                            except Exception:
                                pass
                        try:
                            from auto_session_refresher import refresh_pocketoption_session
                            refreshed = await refresh_pocketoption_session(creds['email'], creds['password'], headless=True)
                            if refreshed:
                                print("✅ [PocketOption] ¡Sesión renovada con éxito! Reconectando WebSocket...")
                                self.reload_config()
                                new_ssid = self.root_config.get('ssid') or self.config.get('ssid')
                                if new_ssid:
                                    self.api = PocketOptionAsync(new_ssid)
                                    if self.notifier and self.notifier.token:
                                        try:
                                            await self.notifier.send_message("✅ <b>PocketOption:</b> Nueva sesión generada y conectada con éxito. Continuando operativa normal.")
                                        except Exception:
                                            pass
                                    await asyncio.sleep(3)
                                    continue
                        except Exception as ref_err:
                            print(f"[PocketOption] ⚠️ Error en auto-renovación de sesión: {ref_err}")

                msg = "[ERR] The bot cannot continue without valid Alpaca credentials." if self.broker == 'alpaca' else "[ERR] The bot cannot continue without a valid SSID. Please update config.json."
                print(msg)
                if self.notifier.token:
                    await self.notifier.send_message(f"🛑 <b>CRITICAL ERROR:</b> {msg}")
                break # Detener el bot

            # Guardar balance de PocketOption en archivo de status
            if self.broker == 'pocketoption' and isinstance(balance, (int, float)):
                try:
                    with open('pocketoption_status.json', 'w', encoding='utf-8') as sf:
                        json.dump({
                            'balance': balance,
                            'last_updated': datetime.now(timezone.utc).isoformat()
                        }, sf)
                except Exception as sf_err:
                    print(f"[PocketOption Status] Error escribiendo status compartido: {sf_err}")

            # 1. Chequeo de Concurrencia y Riesgo
            now_utc = datetime.now(timezone.utc)
            
            # --- VERIFICACIÓN DE PAUSA ---
            if getattr(self, 'is_paused', False) or (self.notifier and getattr(self.notifier, 'is_paused', False)):
                print(f"[{now_utc.strftime('%H:%M:%S')}] ⏸️ Bot en pausa. Esperando comando /reanudar desde Telegram...")
                await asyncio.sleep(10)
                continue

            # --- VERIFICACIÓN DE GESTIÓN DE CAPITAL (Miriam Molina - PocketOption) ---
            if self.broker != 'alpaca' and hasattr(self, 'mm') and self.mm is not None:
                can_trade, stop_reason = self.mm.can_trade()
                if not can_trade:
                    if not getattr(self, 'is_retired', False):
                        self.is_retired = True
                        self.retirement_reason = stop_reason
                        st = self.mm.get_status()
                        msg = (
                            f"🛡️ <b>[PocketOption] OBJETIVO DE SESIÓN CUMPLIDO - EN REPOSO</b>\n\n"
                            f"📌 <b>Motivo:</b> {stop_reason}\n"
                            f"📊 <b>Operaciones hoy:</b> {st['session_trades']}/{self.mm.max_session_trades}\n"
                            f"🏆 <b>Score final:</b> {st['session_wins']}W - {st['session_losses']}L\n"
                            f"💰 <b>PnL Sesión:</b> ${st['session_pnl']:+.2f} USD\n\n"
                            f"🔒 <i>PocketOption en reposo para proteger capital. Las otras instancias (Alpaca / Paper) continúan activas.</i>"
                        )
                        print(f"\n[{now_utc.strftime('%H:%M:%S')}] [PocketOption MM] {stop_reason}")
                        print(f"   Score: {st['session_wins']}W - {st['session_losses']}L | PnL: ${st['session_pnl']:+.2f} USD")
                        print(f"   PocketOption en reposo. Alpaca y Paper continúan operando...\n")
                        try:
                            await self.notifier.send_message(msg)
                        except Exception:
                            pass
                    await asyncio.sleep(60)
                    continue
                else:
                    self.is_retired = False

            # --- CONTROL DE RIESGO Y EXPOSICION DE CAPITAL PARA ALPACA ---
            if self.broker == 'alpaca':
                max_invested_cap = float(self.config.get('max_invested_capital_usd', 40000.0))
                max_concurrent = int(self.config.get('max_concurrent_trades', 3))
                
                # Obtener capital invertido y operaciones abiertas en tiempo real
                try:
                    invested_capital = await self.api.get_invested_capital()
                    open_trades_count = await self.api.get_open_positions_count()
                except Exception:
                    invested_capital = sum(
                        abs(float(t.get('qty', 0.0)) * float(t.get('entry_price', 0.0)))
                        for t in getattr(self.api, 'active_trades', {}).values()
                        if t.get('status', 'active') == 'active'
                    )
                    open_trades_count = len([
                        t for t in getattr(self.api, 'active_trades', {}).values()
                        if t.get('status', 'active') == 'active'
                    ])

                # 1. CONTROL DE EXPOSICION: Si supera el monto invertido o limite de operaciones abiertas, detener nuevas compras
                if invested_capital >= max_invested_cap or open_trades_count >= max_concurrent:
                    if not getattr(self, '_alpaca_exposure_notified', False):
                        reason = (
                            f"Capital invertido: ${invested_capital:,.2f} / Limite: ${max_invested_cap:,.2f}"
                            if invested_capital >= max_invested_cap
                            else f"Operaciones activas: {open_trades_count} / Maximo: {max_concurrent}"
                        )
                        msg = f"⚠️ <b>[Alpaca] LIMITE DE EXPOSICION ALCANZADO:</b> {reason}. Pausando nuevas aperturas para proteger la cuenta mientras se gestionan las posiciones abiertas."
                        print(f"[{now_utc.strftime('%H:%M:%S')}] {msg}")
                        try:
                            await self.notifier.send_message(msg)
                        except Exception:
                            pass
                        self._alpaca_exposure_notified = True
                    # Breve pausa para dar tiempo al monitor de posiciones y reintentar
                    await asyncio.sleep(20)
                    continue
                else:
                    self._alpaca_exposure_notified = False

                # 2. CONTROL DE STOP LOSS / TAKE PROFIT DIARIO:
                # REGLA: Si hay operaciones abiertas, NO pausar por limite diario para no congelar la gestion ni el monitoreo.
                if open_trades_count == 0:
                    if self.session_profit <= self.daily_stop_loss:
                        if not getattr(self, '_alpaca_stop_notified', False):
                            msg = f"🛑 <b>[Alpaca] STOP LOSS DIARIO ALCANZADO:</b> ${self.session_profit:.2f} (Limite: ${self.daily_stop_loss:.2f}). Sin posiciones abiertas. Pausando nuevas aperturas por hoy."
                            print(f"[{now_utc.strftime('%H:%M:%S')}] {msg}")
                            try:
                                await self.notifier.send_message(msg)
                            except Exception:
                                pass
                            self._alpaca_stop_notified = True
                        await asyncio.sleep(60)
                        continue
                    elif self.session_profit >= self.daily_take_profit:
                        if not getattr(self, '_alpaca_tp_notified', False):
                            msg = f"🎯 <b>[Alpaca] TAKE PROFIT DIARIO ALCANZADO:</b> ${self.session_profit:.2f} (Meta: ${self.daily_take_profit:.2f}). Sin posiciones abiertas. Pausando nuevas aperturas por hoy."
                            print(f"[{now_utc.strftime('%H:%M:%S')}] {msg}")
                            try:
                                await self.notifier.send_message(msg)
                            except Exception:
                                pass
                            self._alpaca_tp_notified = True
                        await asyncio.sleep(60)
                        continue
                    else:
                        self._alpaca_stop_notified = False
                        self._alpaca_tp_notified = False

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
                    
                    # --- FILTRO DE WHITELIST DE BACKTESTING (>= 70% Win Rate para PocketOption) ---
                    if self.whitelist is not None and self.broker != 'alpaca':
                        is_graduated = (
                            getattr(self, 'graduated_strategies', {}) and strat_name in self.graduated_strategies
                        )
                        if is_graduated:
                            grad_strat = self.graduated_strategies[strat_name]
                            target_pairs = getattr(grad_strat, 'target_pairs', None)
                            toxic_pairs = getattr(grad_strat, 'toxic_pairs', [])
                            allowed_hours = getattr(grad_strat, 'allowed_hours', None)
                            toxic_hours = getattr(grad_strat, 'toxic_hours', [])

                            # 1. Si tiene toxic_pairs y el par actual es tóxico, BLOQUEAR
                            if toxic_pairs and pair in toxic_pairs:
                                print(f"  [GRADUATED BLOCK] {strat_name} bloqueada: par {pair} clasificado como tóxico.")
                                cycle_report[-1] += f"\n   🚫 <b>GRADUATED BLOCK:</b> {strat_name} en par tóxico {pair}"
                                continue

                            # 2. Si tiene allowed_hours y la hora actual no está, BLOQUEAR
                            now_h = datetime.now(timezone.utc).hour
                            if allowed_hours and now_h not in allowed_hours:
                                print(f"  [GRADUATED BLOCK] {strat_name} bloqueada en hora UTC {now_h} (fuera de allowed_hours).")
                                cycle_report[-1] += f"\n   ⏱️ <b>GRADUATED BLOCK:</b> {strat_name} fuera de horario óptimo ({now_h}:00 UTC)"
                                continue

                            # 3. Si tiene toxic_hours y la hora actual es tóxica, BLOQUEAR
                            if toxic_hours and now_h in toxic_hours:
                                print(f"  [GRADUATED BLOCK] {strat_name} bloqueada en hora tóxica UTC {now_h}.")
                                cycle_report[-1] += f"\n   ⏱️ <b>GRADUATED BLOCK:</b> {strat_name} en hora tóxica ({now_h}:00 UTC)"
                                continue

                            # 4. Si NO tiene target_pairs explícitos, NO puede bypassear la whitelist general
                            if not target_pairs:
                                pair_mapped = pair if pair.endswith('_otc') else (f"{pair}_otc" if len(pair) == 6 and not pair.startswith('#') else f"#{pair}_otc")
                                sig_key = (pair_mapped, strat_name, int(interval))
                                if sig_key not in self.whitelist:
                                    print(f"  [GRADUATED BLOCK] {strat_name} sin target_pairs no cumple whitelist estricta en {pair} ({interval}s).")
                                    cycle_report[-1] += f"\n   🚫 <b>GRADUATED BLOCK:</b> {strat_name} sin target_pairs no cumple whitelist en {pair}"
                                    continue
                            elif pair not in target_pairs:
                                print(f"  [GRADUATED BLOCK] {strat_name} bloqueada: {pair} no está en su lista de target_pairs {target_pairs}.")
                                cycle_report[-1] += f"\n   🚫 <b>GRADUATED BLOCK:</b> {strat_name} no autorizada en {pair} (solo {target_pairs})"
                                continue

                            print(f"  [GRADUATED EXECUTION] Estrategia graduada '{strat_name}' autorizada en par especializado ({pair}).")

                        else:
                            pair_mapped = pair
                            if not pair.endswith('_otc'):
                                if len(pair) == 6 and not pair.startswith('#'):
                                    pair_mapped = f"{pair}_otc"
                                else:
                                    pair_mapped = f"#{pair}_otc"
                            
                            sig_key = (pair_mapped, strat_name, int(interval))
                            if sig_key not in self.whitelist:
                                print(f"  [WHITELIST FILTER] Señal bloqueada: {pair} (mapeado a {pair_mapped}) | {strat_name} | {interval}s no cumple el umbral estricto de Win Rate (>=70%).")
                                cycle_report[-1] += f"\n   🚫 <b>WHITELIST BLOCK:</b> {strat_name} no permitida en {pair} ({interval}s) por WR &lt; 70%"
                                continue

                    # --- FILTRO HORARIO DINÁMICO (HOURLY SHIELD - Matriz de Backtesting Ciclo 2 & 5) ---
                    if self.broker != 'alpaca':
                        now_utc_hour = datetime.now(timezone.utc).hour
                        h_arg = (now_utc_hour - 3) % 24
                        
                        is_toxic = False
                        toxic_reason = ""
                        
                        # 1. Rollover y ensanchamiento de spreads (00:00 UTC / 21:00 Arg)
                        if now_utc_hour == 0 and "Bollinger" in strat_name:
                            is_toxic = True
                            toxic_reason = "Cambio de día del broker / ensanchamiento de spreads (WR 20%)"
                        elif now_utc_hour in [3, 18, 23] and "WaveTrend" in strat_name:
                            is_toxic = True
                            toxic_reason = f"Hora tóxica para WaveTrend {now_utc_hour:02d}:00 UTC (WR histórico 16.7% - 30%)"
                        elif now_utc_hour in [0, 1, 6] and "TTM" in strat_name:
                            is_toxic = True
                            toxic_reason = f"Consolidación errática pre-Londres para TTM {now_utc_hour:02d}:00 UTC (WR histórico 28%)"
                        elif now_utc_hour in [11, 13] and "HYBRID" in strat_name:
                            is_toxic = True
                            toxic_reason = f"Turbulencia macro pre-NY para HYBRID {now_utc_hour:02d}:00 UTC (WR histórico 28.6%)"
                        
                        if is_toxic:
                            msg_toxic = f"[HOURLY SHIELD] Señal bloqueada: {pair} | {strat_name} a las {now_utc_hour:02d}:00 UTC (Arg {h_arg:02d}:00). Razón: {toxic_reason}"
                            print(f"  {msg_toxic}")
                            cycle_report[-1] += f"\n   ⏱️ <b>HOURLY SHIELD BLOCK:</b> {strat_name} bloqueada a las {h_arg:02d}:00 Arg ({toxic_reason})"
                            continue

                    # --- ESCUDO DE MACRO TENDENCIA (TREND SHIELD - Ciclo 3 & 4) ---
                    if self.broker != 'alpaca':
                        close_p = latest_data.get('Close', 0)
                        ema20_p = latest_data.get('EMA_20', 0)
                        ema50_p = latest_data.get('EMA_50', 0)
                        sma200_p = latest_data.get('SMA_200', 0)
                        
                        # Bloquear compras si el precio está en cascada bajista severa
                        if action == 'BUY' and ema20_p > 0 and ema50_p > 0:
                            if close_p < ema20_p < ema50_p:
                                print(f"  [TREND SHIELD] BUY bloqueado en {pair}: Cascada bajista activa (Close < EMA20 < EMA50).")
                                cycle_report[-1] += f"\n   🛡️ <b>TREND SHIELD:</b> BUY bloqueado por cascada bajista"
                                continue
                                
                        # Bloquear ventas si el precio está en rally alcista vertical
                        if action == 'SELL' and ema20_p > 0 and ema50_p > 0:
                            if close_p > ema20_p > ema50_p:
                                print(f"  [TREND SHIELD] SELL bloqueado en {pair}: Rally alcista vertical activo (Close > EMA20 > EMA50).")
                                cycle_report[-1] += f"\n   🛡️ <b>TREND SHIELD:</b> SELL bloqueado por rally alcista"
                                continue
                                
                        # Macro filtro SMA200 para evitar operar reversiones contra dislocaciones extremas (>1.5%)
                        if sma200_p > 0:
                            if action == 'BUY' and close_p < sma200_p * 0.985:
                                print(f"  [TREND SHIELD] BUY bloqueado en {pair}: Desviación extrema bajista bajo SMA200 (>1.5%).")
                                cycle_report[-1] += f"\n   🛡️ <b>TREND SHIELD:</b> BUY bloqueado por colapso bajo SMA200"
                                continue
                            if action == 'SELL' and close_p > sma200_p * 1.015:
                                print(f"  [TREND SHIELD] SELL bloqueado en {pair}: Dislocación extrema alcista sobre SMA200 (>1.5%).")
                                cycle_report[-1] += f"\n   🛡️ <b>TREND SHIELD:</b> SELL bloqueado por sobre-extensión sobre SMA200"
                                continue

                    # --- INNOVACIÓN 3: DETECTOR DINÁMICO DE PARES TÓXICOS / CHOP MARKET ---
                    chop_ok, chop_reason = self.check_chop_entropy(df)
                    if not chop_ok:
                        print(f"  [ANTI-CHOP] Par {pair} bloqueado: {chop_reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>ANTI-CHOP:</b> {chop_reason}"
                        continue

                    # --- INNOVACIÓN 1: ABSORCIÓN DE MECHAS OTC (LIQUIDITY VACUUM) ---
                    wick_ok, wick_reason = self.check_wick_absorption(latest_data, action)
                    if not wick_ok:
                        print(f"  [WICK REJECTION] Entrada bloqueada en {pair}: {wick_reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>WICK SHIELD:</b> {wick_reason}"
                        continue

                    # --- INNOVACIÓN 4: HUELLA DE VELA CUANTITATIVA (FOOTPRINT SCORE) ---
                    m_state = ctx.get("market_state", "UNKNOWN") if isinstance(ctx, dict) else "UNKNOWN"
                    fp_ok, fp_reason, fp_score = self.evaluate_candle_footprint(latest_data, action, m_state, df)
                    if not fp_ok:
                        print(f"  [FOOTPRINT] Entrada descartada por baja calidad: {fp_reason}")
                        cycle_report[-1] += f"\n   🛡️ <b>FOOTPRINT:</b> Calidad insuficiente ({fp_score:.1f}/10)"
                        continue

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
                            self.trade_logger.log_trade(trade_data)

                            # --- GUARDAR TAMBIÉN EN BASE DE DATOS SQL (SQLite local) ---
                            macd_v = latest_data.get('MACD', 0)
                            macd_s = latest_data.get('MACD_Signal', 0)
                            macd_h = latest_data.get('MACD_Hist')
                            if macd_h is None:
                                macd_h = macd_v - macd_s

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
                                'ai_snapshot': json.dumps(ai_snapshot),
                                'close_timestamp': datetime.now().isoformat(),
                                'rsi': latest_data.get('RSI', 0),
                                'stoch_k': latest_data.get('Stoch_K', 0),
                                'macd_hist': macd_h,
                                'ema_distance': distance_ema20,
                                'atr': latest_data.get('ATR', 0)
                            }
                            self.db.save_trade(db_trade_blocked)
                            print(f"  [DB] Bloqueo de IA guardado en feedback.db")
                        except Exception as e:
                            print(f"  [ERROR] No se pudo guardar log de operacion bloqueada: {e}")
                            
                        continue

                    print(f"EJECUTANDO ORDEN: {action} en {pair} por {duration}s. Estrategia: {strat_name}")
                    
                    try:
                        if hasattr(self, 'mm') and self.mm is not None:
                            can_op, stop_reason = self.mm.can_trade()
                            if not can_op:
                                print(f"  [BLOQUEO MM] Operación cancelada por reglas de sesión: {stop_reason}")
                                continue

                        amount = await self.calculate_trade_amount(pair)
                        
                        # --- COLOCAR ORDEN (Alpaca se coloca primero para obtener el ID real de la orden) ---
                        placed_id = None
                        if self.broker == 'alpaca':
                            # Pre-check de capital y operaciones concurrentes antes de mandar la orden
                            inv_cap = await self.api.get_invested_capital() if hasattr(self.api, 'get_invested_capital') else 0.0
                            max_inv = float(self.config.get('max_invested_capital_usd', 40000.0))
                            max_ops = int(self.config.get('max_concurrent_trades', 3))
                            open_ops = await self.api.get_open_positions_count() if hasattr(self.api, 'get_open_positions_count') else len(self.api.active_trades)
                            
                            if open_ops >= max_ops:
                                print(f"  [Alpaca Pre-Check] Limite de operaciones simultaneas alcanzado ({open_ops}/{max_ops}). Omitiendo orden en {pair}.")
                                continue
                            if inv_cap >= max_inv:
                                print(f"  [Alpaca Pre-Check] Limite de capital invertido alcanzado (${inv_cap:,.2f} >= ${max_inv:,.2f}). Omitiendo orden en {pair}.")
                                continue

                            duration_alpaca = self.config.get('holding_period_seconds', 14400)
                            buy_kwargs = {
                                "asset": pair, 
                                "amount": amount, 
                                "time": duration_alpaca, 
                                "check_win": False
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
                                if not placed_id:
                                    print(f"  [Alpaca] Orden omitida o no colocada para {pair}.")
                                    continue
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
                            cooldown_post = int(self.config.get('cooldown_between_trades_seconds', 180))
                            self.active_trade_expiry = datetime.now(timezone.utc) + timedelta(seconds=duration + 10 + cooldown_post)
                            print(f"  [LOCK] Bot bloqueado hasta {self.active_trade_expiry.strftime('%H:%M:%S')} UTC (incluye {cooldown_post}s cooldown anti-sobreoperación)")

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
                        self.trade_logger.log_trade(trade_data)
                        
                        # Notificar Apertura
                        await self.notifier.notify_open(pair, action, strat_name, duration, amount)

                        # --- PROCESO EXCLUSIVO ALPACA (Retorno Inmediato) ---
                        if self.broker == 'alpaca':
                            try:
                                timeframe_str = f"{duration // 60}min" if duration >= 60 else f"{duration}seg"
                                macd_v = latest_data.get('MACD', 0)
                                macd_s = latest_data.get('MACD_Signal', 0)
                                macd_h = latest_data.get('MACD_Hist')
                                if macd_h is None:
                                    macd_h = macd_v - macd_s
                                dist_ema20 = close_val - ema20_val

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
                                    'ai_decision': 'APPROVED',
                                    'ai_confidence': ai_confidence,
                                    'ai_reason': ai_reason,
                                    'ai_snapshot': json.dumps(ai_snapshot),
                                    'rsi': latest_data.get('RSI', 0),
                                    'stoch_k': latest_data.get('Stoch_K', 0),
                                    'macd_hist': macd_h,
                                    'ema_distance': dist_ema20,
                                    'atr': latest_data.get('ATR', 0)
                                }
                                self.db.save_trade(trade_db_data)
                                print(f"  [DB] Operación {trade_id} (PENDING) guardada en base de datos.")
                            except Exception as db_e:
                                print(f"  [WARN] Error guardando en DB: {db_e}")
                            
                            await asyncio.sleep(5)
                            break # Salir del loop de pares para este ciclo

                        # --- PROCESO EXCLUSIVO POCKETOPTION (Bloqueante con Espera) ---
                        # INNOVACIÓN 2: MICRO-TIMING PULLBACK TRIGGER (Entrada con descuento)
                        # Espera una micro-fluctuación de 2 a 4 segundos para evitar comprar en el pico o vender en el fondo absoluto.
                        await asyncio.sleep(2.5)

                        placed_id = None
                        balance_before = await self.get_balance()
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

                        print(f"  [OK] Orden colocada. API trade_id: {placed_id or 'desconocido'} (Balance inicial: ${balance_before if isinstance(balance_before, (int, float)) else 'N/A'})")
                        
                        # --- ESPERAR DURACIÓN DEL TRADE ---
                        print(f"  [WAIT] Esperando {duration}s para confirmar resultado...")
                        await asyncio.sleep(duration + 4)  # Margen para que expire la opción
                        
                        # --- SISTEMA MULTI-CAPA DE CONFIRMACIÓN DE RESULTADOS ---
                        is_win = False
                        profit = 0.0
                        result_confirmed = False
                        real_close_price = None
                        
                        # CAPA 1: Consultar closed_deals()
                        for attempt in range(3):
                            try:
                                closed = await asyncio.wait_for(self.api.closed_deals(), timeout=8.0)
                                if isinstance(closed, dict):
                                    closed_list = list(closed.values())
                                elif isinstance(closed, list):
                                    closed_list = closed
                                else:
                                    closed_list = []

                                matched = None
                                if placed_id:
                                    placed_str = str(placed_id).lower()
                                    matched = next(
                                        (
                                            d for d in closed_list 
                                            if isinstance(d, dict) and (
                                                str(d.get('id', '')).lower() == placed_str or 
                                                str(d.get('request_id', '')).lower() == placed_str or 
                                                str(d.get('copy_ticket', '')).lower() == placed_str
                                            )
                                        ),
                                        None
                                    )
                                if not matched and closed_list:
                                    clean_pair = pair.replace('-', '_').upper()
                                    recent = [
                                        d for d in closed_list 
                                        if isinstance(d, dict) and str(d.get('asset', '')).replace('-', '_').upper() == clean_pair
                                    ]
                                    if recent:
                                        matched = recent[-1]
                                
                                if matched:
                                    try:
                                        real_close_price = float(matched.get('close_price') or matched.get('closeQuote') or matched.get('close') or 0.0)
                                    except Exception:
                                        real_close_price = None
                                    deal_amount = float(matched.get('amount', amount))
                                    raw_profit = float(matched.get('profit', 0.0))
                                    
                                    if raw_profit > deal_amount:
                                        is_win = True
                                        profit = round(raw_profit - deal_amount, 2)
                                    elif raw_profit > 0 and raw_profit < deal_amount:
                                        is_win = True
                                        profit = round(raw_profit, 2)
                                    elif raw_profit == deal_amount:
                                        is_win = True
                                        profit = 0.0
                                    elif raw_profit > 0:
                                        is_win = True
                                        profit = round(raw_profit, 2)
                                    else:
                                        is_win = False
                                        profit = -round(deal_amount, 2)
                                        
                                    result_confirmed = True
                                    print(f"  [OK] Resultado confirmado via closed_deals: {'WIN' if is_win else 'LOSS'} | Net Profit: ${profit:+.2f}")
                                    break
                            except Exception as e:
                                if self.verbose:
                                    print(f"  [DEBUG] Intento {attempt+1}/3 closed_deals: {e}")
                            await asyncio.sleep(1.5)

                        # CAPA 2: Intentar check_win con ID si Capa 1 no confirmó
                        if not result_confirmed and placed_id:
                            try:
                                details = await asyncio.wait_for(self.api.check_win(placed_id), timeout=6.0)
                                if not real_close_price:
                                    try:
                                        real_close_price = float(details.get('close_price') or details.get('closeQuote') or details.get('close') or 0.0)
                                    except Exception:
                                        pass
                                deal_amount = float(details.get('amount', amount))
                                raw_profit = float(details.get('profit', 0.0))
                                
                                if raw_profit > deal_amount:
                                    is_win = True
                                    profit = round(raw_profit - deal_amount, 2)
                                    result_confirmed = True
                                elif raw_profit > 0:
                                    is_win = True
                                    profit = round(raw_profit, 2)
                                    result_confirmed = True
                                elif str(details.get('result', '')).lower() == 'win':
                                    is_win = True
                                    profit = round(deal_amount * 0.85, 2)
                                    result_confirmed = True
                            except Exception:
                                pass

                        # CAPA 3 (VERDAD DEFINITIVA): Comparación de Delta de Balance Real
                        balance_after = await self.get_balance()
                        if isinstance(balance_before, (int, float)) and isinstance(balance_after, (int, float)):
                            balance_delta = round(balance_after - balance_before, 2)
                            if balance_delta > 0.05:
                                is_win = True
                                profit = balance_delta
                                result_confirmed = True
                                print(f"  [OK] Resultado verificado por Balance Delta: GANADA (+${profit:.2f}) [${balance_before:.2f} -> ${balance_after:.2f}]")
                            elif balance_delta < -0.05:
                                is_win = False
                                profit = balance_delta
                                result_confirmed = True
                                print(f"  [OK] Resultado verificado por Balance Delta: PERDIDA (${profit:.2f}) [${balance_before:.2f} -> ${balance_after:.2f}]")
                            elif abs(balance_delta) <= 0.05 and not result_confirmed:
                                is_win = True
                                profit = 0.0
                                result_confirmed = True
                                print(f"  [OK] Resultado verificado por Balance Delta: EMPATE / REFUND ($0.00)")

                        if not result_confirmed:
                            # Fallback por acción del precio si la red falló
                            profit = -amount
                            is_win = False
                            print(f"  [WARN] No se pudo verificar resultado con broker. Asignando pérdida estimada (-${amount:.2f}).")
                        
                        print(f"  >>> Resultado Operacion: {'GANADA' if is_win else 'PERDIDA'} (${profit:+.2f})")
                        await self.notifier.notify_close(pair, profit, is_win, trade_id=trade_id)

                        # --- ACTUALIZAR MÉTRICAS DE SESIÓN Y MONEY MANAGEMENT ---
                        outcome = 'WIN' if is_win else ('DRAW' if profit == 0 else 'LOSS')
                        if hasattr(self, 'mm') and self.mm is not None:
                            self.mm.register_result(outcome, profit)
                            self.session_profit = self.mm.session_pnl
                            mm_st = self.mm.get_status()
                            print(f"  [PocketOption MM] Ops: {mm_st['session_trades']}/{self.mm.max_session_trades} | Score: {mm_st['session_wins']}W - {mm_st['session_losses']}L | PnL: ${mm_st['session_pnl']:+.2f} USD")
                            if not mm_st['session_active']:
                                print(f"  [PocketOption MM RETIRO] {mm_st['stop_reason']}")
                                self.is_retired = True
                                self.retirement_reason = mm_st['stop_reason']
                        else:
                            self.session_profit += profit

                        if is_win:
                            self.strategy_fails[strat_name] = 0 # Reset racha
                            self.consecutive_losses[pair] = 0   # Reset Martingala
                        else:
                            self.strategy_fails[strat_name] = self.strategy_fails.get(strat_name, 0) + 1
                            self.consecutive_losses[pair] = self.consecutive_losses.get(pair, 0) + 1

                        # --- ACTUALIZAR LOG CSV ---
                        self.trade_logger.update_trade_result(
                            trade_id=trade_id,
                            result='WIN' if is_win else 'LOSS',
                            profit_loss=profit
                        )

                        # --- GUARDAR EN BASE DE DATOS SQL (Restaurado) ---
                        try:
                            timeframe_str = f"{duration // 60}min" if duration >= 60 else f"{duration}seg"
                            macd_v = latest_data.get('MACD', 0)
                            macd_s = latest_data.get('MACD_Signal', 0)
                            macd_h = latest_data.get('MACD_Hist')
                            if macd_h is None:
                                macd_h = macd_v - macd_s
                            dist_ema20 = close_val - ema20_val
                            c_price = real_close_price if (real_close_price and real_close_price > 0) else close_val

                            trade_db_data = {
                                'trade_id': trade_id,
                                'pair': pair,
                                'action': action,
                                'strategy': strat_name,
                                'timeframe': timeframe_str,
                                'amount': amount,
                                'open_price': close_val,
                                'close_price': c_price,
                                'result': 'win' if is_win else 'loss',
                                'profit': profit,
                                'telegram_message_id': None, # Se actualizará si hay feedback manual
                                'ai_decision': 'APPROVED',
                                'ai_confidence': ai_confidence,
                                'ai_reason': ai_reason,
                                'ai_snapshot': json.dumps(ai_snapshot),
                                'close_timestamp': datetime.now().isoformat(),
                                'rsi': latest_data.get('RSI', 0),
                                'stoch_k': latest_data.get('Stoch_K', 0),
                                'macd_hist': macd_h,
                                'ema_distance': dist_ema20,
                                'atr': latest_data.get('ATR', 0)
                            }
                            self.db.save_trade(trade_db_data)
                            print(f"  [DB] Operación {trade_id} guardada en feedback.db (RSI: {latest_data.get('RSI', 0):.1f}, Close: {c_price})")
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
                        await self.notifier.send_message(f"⚠️ Error executing order on {pair}: {e}")
                        
                else:
                    # print(f"Sin señal clara en {pair}")
                    pass
                
                await asyncio.sleep(2) # Pausa entre pares para no saturar
            
            # --- Mantenimiento Periódico y Reporte de Fin de Día ---
            now_dt = datetime.now()
            today_date = now_dt.date()
            
            if now_dt.hour == 0 and now_dt.minute < 5:
                self.db.maintain()
            
            if getattr(self, '_last_daily_report_date', None) != today_date:
                if now_dt.hour == 0 and now_dt.minute <= 15:
                    yesterday = today_date - timedelta(days=1)
                    if getattr(self, '_last_daily_report_sent_for', None) != yesterday:
                        print(f"[{now_dt.strftime('%H:%M:%S')}] 📢 Generando y enviando reporte de cierre diario para {yesterday}...")
                        try:
                            await self.notifier.send_daily_report(target_date=yesterday)
                            self._last_daily_report_sent_for = yesterday
                        except Exception as dre:
                            print(f"[Daily Report Error] {dre}")
                    self._last_daily_report_date = today_date
            
            # --- Reporte Telegram (Al final del ciclo) ---
            if self.verbose_telegram and cycle_report and self.notifier.token:
                header = "📊 <b>Cycle Report</b>\n\n"
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

    # 4. Servidor Web y Mini App Biométrica para Telegram
    if web:
        async def handle(request):
            return web.Response(text="Bot is running in Dual Mode!")

        async def handle_biometric(request):
            bio_path = Path("web_app/biometric.html")
            if bio_path.exists():
                return web.Response(text=bio_path.read_text(encoding="utf-8"), content_type="text/html")
            return web.Response(text="<h1>Biometric Auth page not found</h1>", content_type="text/html", status=404)

        async def handle_face_status(request):
            try:
                from face_verifier import face_verifier
                return web.json_response({"enrolled": face_verifier.is_enrolled()})
            except Exception as e:
                return web.json_response({"enrolled": False, "error": str(e)})

        async def handle_enroll_face(request):
            try:
                data = await request.json()
                img_data = data.get("image")
                if not img_data:
                    return web.json_response({"success": False, "error": "Falta la imagen."}, status=400)
                from face_verifier import face_verifier
                res = face_verifier.enroll_face(img_data)
                return web.json_response(res)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)}, status=500)

        async def handle_verify_face(request):
            try:
                data = await request.json()
                img_data = data.get("image")
                if not img_data:
                    return web.json_response({"verified": False, "error": "Falta la imagen."}, status=400)
                from face_verifier import face_verifier
                res = face_verifier.verify_face(img_data)
                return web.json_response(res)
            except Exception as e:
                return web.json_response({"verified": False, "error": str(e)}, status=500)

        app = web.Application()
        app.router.add_get('/', handle)
        app.router.add_get('/biometric', handle_biometric)
        app.router.add_get('/api/face_status', handle_face_status)
        app.router.add_post('/api/enroll_face', handle_enroll_face)
        app.router.add_post('/api/verify_face', handle_verify_face)
        port = int(os.getenv("PORT", 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        is_cloud = bool(os.getenv("KOYEB_APP_NAME") or os.getenv("RENDER") or os.getenv("DYNO") or os.getenv("RAILWAY_ENVIRONMENT"))
        bind_host = '0.0.0.0' if is_cloud else '127.0.0.1'
        site = web.TCPSite(runner, bind_host, port)
        
        async def start_server():
            try:
                await site.start()
                print(f"📡 Servidor local iniciado en puerto {port}")
                # Iniciar túnel Cloudflare seguro para la Mini App de Telegram
                try:
                    from tunnel_manager import tunnel_manager
                    bio_url = await asyncio.to_thread(tunnel_manager.get_biometric_url)
                    if bio_url:
                        print(f"[OK] Mini App Biometrica lista: {bio_url}")
                except Exception as te:
                    print(f"⚠️ Error iniciando túnel biométrico: {te}")
            except OSError as bind_err:
                print(f"⚠️ Servidor web no pudo iniciarse en puerto {port} (puerto en uso): {bind_err}")
            except Exception as e:
                print(f"⚠️ Error al iniciar servidor web: {e}")
                
        asyncio.create_task(start_server())

    # 5. Cargar e iniciar bots (Modo Dual: PocketOption + Alpaca en paralelo)
    tasks = []
    
    # 5a. Instancia PocketOption
    po_ssid = config.get('ssid')
    if po_ssid and po_ssid != "PONER_SSID_AQUI":
        bot_po = TradingBot(po_ssid, tg_token, tg_chat, tg_owner, config=config.get('trading', config), root_config=config, config_path='config.json')
        tasks.append(asyncio.create_task(bot_po.run()))
        print("🟢 Instancia PocketOption preparada.")
        
        # 🧪 PAPER TRIAL (backtesting en vivo sin filtros — sin dinero real)
        try:
            from paper_bot import PaperTrialBot
            paper = PaperTrialBot(bot_po)
            tasks.append(asyncio.create_task(paper.run()))
            print("🧪 Instancia Paper Trial preparada (explorador en paralelo).")
        except Exception as pe:
            print(f"⚠️ Paper Trial no pudo iniciarse: {pe}")
    else:
        print("⚠️ Instancia PocketOption omitida (sin SSID válido).")
        
    # 5b. Instancia Alpaca
    alpaca_config_path = Path('config_alpaca.json')
    if alpaca_config_path.exists():
        try:
            with open(alpaca_config_path, 'r', encoding='utf-8') as af:
                cfg_alpaca = json.load(af)
                alpaca_key = cfg_alpaca.get('alpaca_key_id') or cfg_alpaca.get('trading', {}).get('alpaca_key_id')
                alpaca_secret = cfg_alpaca.get('alpaca_secret_key') or cfg_alpaca.get('trading', {}).get('alpaca_secret_key')
                if alpaca_key and alpaca_secret:
                    bot_alpaca = TradingBot(
                        ssid=None,
                        telegram_token=cfg_alpaca.get('telegram_token', tg_token),
                        telegram_chat_id=cfg_alpaca.get('telegram_chat_id', tg_chat),
                        telegram_owner_id=cfg_alpaca.get('telegram_owner_id', tg_owner),
                        config=cfg_alpaca.get('trading', cfg_alpaca),
                        root_config=cfg_alpaca,
                        config_path='config_alpaca.json'
                    )
                    tasks.append(asyncio.create_task(bot_alpaca.run()))
                    print("🔸 Instancia Alpaca preparada.")
        except Exception as e:
            print(f"⚠️ Error cargando config_alpaca.json: {e}")

    if not tasks:
        print("❌ CRÍTICO: No hay ninguna instancia de bot configurada para ejecutar.")
        return

    print(f"🚀 Iniciando {len(tasks)} instancias de trading en paralelo...")
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")
