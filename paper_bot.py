"""
=============================================================================
     PAPER TRIAL BOT — BACKTESTING EN VIVO SIN FILTROS (v3 EVOLUTIVO)
=============================================================================
Corre en PARALELO al bot real, compartiendo SOLO la lectura de velas.
Nunca coloca órdenes, nunca toca dinero real.

  • AUTOCONFIGURACIÓN: analiza tus trades REALES de los últimos N días,
    selecciona las estrategias ganadoras y las explora en un universo
    ampliado de pares.
  • CIRCUIT BREAKER & CUARENTENA: Pausa automáticamente cualquier estrategia
    que sufra rachas perdedoras o Win Rate inferior al umbral matemático (52.5%).
  • MOTOR DE EVOLUCIÓN DINÁMICA: Genera, prueba y muta estrategias rápidas
    de alta frecuencia (Fast EMA Pullbacks, Stoch Bollinger Bursts, etc.).
  • Un único CSV acumulativo: paper_backtest.csv
=============================================================================
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import asyncio
import csv
import glob
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

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
from strategy_chartist_patterns import StrategyChartistPatterns
from strategy_smc_elite import StrategySMCElite
from strategy_squeeze_volume import StrategySqueezeVolume
from strategy_rapid_scalper import (
    FastEMAPullbackScalper,
    StochasticBollingerBurst,
    RSIVelocityMomentum,
    MicroRangeBreakout
)
from strategy_evolution import StrategyEvolutionEngine
from strategy_liquidity_fvg import StrategyLiquidityFVG
from strategy_bb_burst_pro import StrategyBBBurstPro
from strategy_ttm_squeeze_pro import StrategyTTMSqueezePro
from strategy_micro_breakout_7v import StrategyMicroBreakout7v
from strategy_vsa_climax import StrategyVSAClimax
from strategy_orderblock_mtf import StrategyOrderBlockMTF
from strategy_vwap_reversion import StrategyVWAPReversion
from strategy_momentum_conf import StrategyMomentumConfluence
from ai_filter import AIFilter

TZ_ARG = timezone(timedelta(hours=-3))

CSV_FILE = Path("paper_backtest.csv")
PENDING_FILE = Path("paper_pending.json")
CONFIG_FILE = Path("config_paper.json")

CSV_COLUMNS = ["timestamp", "trade_id", "pair", "timeframe", "decision",
               "pattern_detected", "price", "exit_price", "result",
               "payout", "stake", "profit_loss", "balance", "notes"]

DEFAULT_CONFIG = {
    "enabled": True,

    # --- SELECCIÓN DESDE HISTORIAL REAL ---
    "history_days": 14,            # ventana mínima de análisis
    "min_trades": 3,               # muestra mínima por estrategia para calificar
    "min_win_rate": 0.50,          # WR mínimo (draws excluidos del cálculo)
    "top_strategies": 8,           # cuántas ganadoras explorar
    "include_all_strategies": False,  # True = modo descubrimiento total (las 17)

    # --- UNIVERSO DE PARES (exploración) ---
    "explore_pairs": [
        # Majors
        "EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "NZDUSD_otc",
        "USDCAD_otc", "USDCHF_otc", "USDJPY_otc",
        # Cruces
        "EURGBP_otc", "EURJPY_otc", "EURCHF_otc", "EURAUD_otc", "EURCAD_otc",
        "GBPJPY_otc", "GBPCHF_otc", "GBPAUD_otc", "GBPCAD_otc",
        "AUDJPY_otc", "AUDCAD_otc", "AUDCHF_otc", "AUDNZD_otc",
        "NZDJPY_otc", "CADJPY_otc", "CADCHF_otc", "CHFJPY_otc",
        # Exóticos LATAM / emergentes
        "USDMXN_otc", "USDCOP_otc", "USDBRL_otc", "USDARS_otc",
        "USDCLP_otc", "USDTRY_otc", "USDZAR_otc",
        # Metales
        "XAUUSD_otc", "XAGUSD_otc",
    ],
    "max_pairs": 40,               # límite de seguridad (semillas primero)

    # --- CAPITAL / GESTIÓN ---
    "payout": 0.92,
    "stake_percent": 0.01,         # stake = 1% del balance (mín $1)
    "stake_fixed": None,
    "max_exposure_pct": 0.20,      # 🛡️ nunca más del 20% del balance en simultáneo

    # --- OPERATIVA ---
    "intervals": [300],
    "max_open_per_pair": 1,        # 🛡️ Máximo 1 sola operación abierta por par a la vez
    "cycle_delay": 30,

    # --- CIRCUIT BREAKER & CUARENTENA DINÁMICA ---
    "circuit_breaker": {
        "enabled": True,
        "max_consecutive_losses": 3,
        "min_win_rate": 0.525,     # Mínimo 52.5% para cubrir el payout
        "min_trades_to_eval": 10,
        "quarantine_minutes": 60,
    },

    # --- MOTOR DE EVOLUCIÓN DINÁMICA DE ESTRATEGIAS ---
    "evolution_engine": {
        "enabled": True,
        "max_active_dynamic_strategies": 6,
        "eval_interval_seconds": 1800,  # cada 30 min evalúa y muta
        "min_validation_trades": 10,
        "target_win_rate": 0.56,
        "min_win_rate": 0.525,
    }
}


class PaperTrialBot:
    def __init__(self, real_bot):
        self.bot = real_bot          # analyzer / patterns / semáforo / balance
        self.api = real_bot.api      # SOLO lectura de velas

        cfg = {}
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[PAPER] ⚠️ config_paper.json inválido ({e}). Usando defaults.")
        self.config = {**DEFAULT_CONFIG, **(cfg if isinstance(cfg, dict) else {})}

        self.demo_api = None
        demo_ssid = self.config.get("demo_ssid")
        if self.config.get("demo_execution", False) and demo_ssid:
            try:
                self.demo_api = PocketOptionAsync(demo_ssid)
                print("[PAPER] 🔌 Cliente PocketOption DEMO configurado para ejecución directa.")
            except Exception as e:
                print(f"[PAPER] ⚠️ Error inicializando cliente Demo: {e}")

        self.all_strategies = [
            StrategyHybridSniper(bypass_filter=True),
            StrategyBollingerRSI(bypass_filter=True),
            StrategyPriceActionEngulfing(bypass_filter=True),
            StrategyTrendPullback(bypass_filter=True),
            StrategyWaveTrendKeltner(bypass_filter=True),
            StrategyTTMSqueeze(bypass_filter=True),
            StrategyStochastic(bypass_filter=True),
            StrategyAlphaConvergence(bypass_filter=True),
            StrategyFibonacci(bypass_filter=True),
            StrategyStructure(),
            StrategyExpertVision(bypass_filter=True),
            StrategyContinuation(),
            StrategyDivergencePivot(bypass_filter=True),
            StrategySmartMoneySMC(bypass_filter=True),
            StrategyFibonacciMasterSniper(bypass_filter=True),
            StrategyChartistPatterns(bypass_filter=True),
            StrategySMCElite(bypass_filter=True),
            StrategySqueezeVolume(bypass_filter=True),
            StrategyLiquidityFVG(swing_window=15, min_wick_ratio=0.32, fvg_lookback=5, rsi_filter_enabled=True),
            StrategyBBBurstPro(),
            StrategyTTMSqueezePro(),
            StrategyMicroBreakout7v(),
            StrategyVSAClimax(),
            StrategyOrderBlockMTF(),
            StrategyVWAPReversion(),
            StrategyMomentumConfluence(),
        ]

        self.balance = None
        self.pending = []
        self._seen_signals = set()
        self._seen_pair_candles = set()
        self._pair_fail_count = {}   # poda de pares no disponibles en tu cuenta
        
        self.ai = AIFilter()         # Instancia del Filtro Predictivo de Machine Learning

        # ⛔ CIRCUIT BREAKER & CUARENTENA
        self.quarantine = {}         # { strategy_name: datetime_expiration_utc }
        self.strat_stats = {}        # { strategy_name: {"consecutive_losses": 0, "recent": []} }

        # 🧬 MOTOR DE EVOLUCIÓN DINÁMICA DE ESTRATEGIAS RÁPIDAS
        evo_cfg = self.config.get("evolution_engine", {})
        max_dyn = int(evo_cfg.get("max_active_dynamic_strategies", 6))
        self.evolution = StrategyEvolutionEngine(max_dynamic_strategies=max_dyn)
        self.last_evolution_ts = datetime.now(timezone.utc)

        # Cargar historial previo de paper para activar Circuit Breaker desde el inicio
        self._bootstrap_circuit_breaker()

    # ============================================================= CIRCUIT BREAKER
    def _bootstrap_circuit_breaker(self):
        """Lee el historial existente de paper para pausar de inmediato las estrategias en racha perdedora."""
        if not CSV_FILE.exists():
            return
        try:
            df = pd.read_csv(CSV_FILE)
            if df.empty or "pattern_detected" not in df.columns or "result" not in df.columns:
                return

            cb_cfg = self.config.get("circuit_breaker", {})
            if not cb_cfg.get("enabled", True):
                return

            max_losses = int(cb_cfg.get("max_consecutive_losses", 3))
            min_wr = float(cb_cfg.get("min_win_rate", 0.525))
            mins = int(cb_cfg.get("quarantine_minutes", 60))
            now_utc = datetime.now(timezone.utc)

            for strat, grp in df.groupby("pattern_detected"):
                recent = grp.tail(15)
                wins = int((recent["result"].str.upper() == "WIN").sum())
                total = int((recent["result"].str.upper().isin(["WIN", "LOSS"])).sum())
                wr = (wins / total) if total > 0 else 0.0

                # Calcular racha de derrotas consecutivas
                streak = 0
                for r in reversed(grp["result"].tolist()):
                    if str(r).upper() == "LOSS":
                        streak += 1
                    elif str(r).upper() == "WIN":
                        break

                recent_bits = [1 if str(r).upper() == "WIN" else 0 for r in recent["result"].tolist() if str(r).upper() in ["WIN", "LOSS"]]
                self.strat_stats[strat] = {"consecutive_losses": streak, "recent": recent_bits}

                # Disparo de cuarentena preventiva si arranca perdiendo feo
                if streak >= max_losses:
                    self.quarantine[strat] = now_utc + timedelta(minutes=mins)
                    print(f"[PAPER] ⛔ CIRCUIT BREAKER PREVENTIVO: '{strat}' entra en CUARENTENA por {mins}m (Racha: {streak}L consecutivas)")
                elif total >= int(cb_cfg.get("min_trades_to_eval", 10)) and wr < min_wr:
                    self.quarantine[strat] = now_utc + timedelta(minutes=mins)
                    print(f"[PAPER] ⛔ CIRCUIT BREAKER PREVENTIVO: '{strat}' entra en CUARENTENA por {mins}m (WR reciente: {wr*100:.1f}%)")

        except Exception as e:
            print(f"[PAPER] Error inicializando Circuit Breaker: {e}")

    def _is_strat_in_quarantine(self, strat_name):
        """Verifica si una estrategia está en cuarentena activa."""
        cb_cfg = self.config.get("circuit_breaker", {})
        if not cb_cfg.get("enabled", True):
            return False

        if strat_name in self.quarantine:
            expiry = self.quarantine[strat_name]
            now = datetime.now(timezone.utc)
            if now < expiry:
                return True
            else:
                del self.quarantine[strat_name]
                st = self.strat_stats.setdefault(strat_name, {"consecutive_losses": 0, "recent": []})
                st["consecutive_losses"] = 0
                st["recent"] = []
                print(f"[PAPER] 🟢 CUARENTENA FINALIZADA: '{strat_name}' rehabilitada a modo prueba.")
                return False
        return False

    def _update_circuit_breaker(self, strat_name, result):
        """Actualiza el rendimiento y aplica cuarentena tras un trade terminado."""
        cb_cfg = self.config.get("circuit_breaker", {})
        if not cb_cfg.get("enabled", True):
            return

        st = self.strat_stats.setdefault(strat_name, {"consecutive_losses": 0, "recent": []})
        if result == "WIN":
            st["consecutive_losses"] = 0
            st["recent"].append(1)
        elif result == "LOSS":
            st["consecutive_losses"] += 1
            st["recent"].append(0)

        window_size = int(cb_cfg.get("min_trades_to_eval", 10))
        if len(st["recent"]) > window_size:
            st["recent"].pop(0)

        max_losses = int(cb_cfg.get("max_consecutive_losses", 3))
        mins = int(cb_cfg.get("quarantine_minutes", 60))

        # Regla 1: Racha de pérdidas consecutivas
        if st["consecutive_losses"] >= max_losses:
            self.quarantine[strat_name] = datetime.now(timezone.utc) + timedelta(minutes=mins)
            print(f"[PAPER] ⛔ CIRCUIT BREAKER: '{strat_name}' entra en CUARENTENA por {mins}m tras {st['consecutive_losses']} derrotas seguidas.")

        # Regla 2: Win Rate por debajo del umbral mínimo
        elif len(st["recent"]) >= window_size:
            recent_wr = sum(st["recent"]) / len(st["recent"])
            min_wr = float(cb_cfg.get("min_win_rate", 0.525))
            if recent_wr < min_wr:
                self.quarantine[strat_name] = datetime.now(timezone.utc) + timedelta(minutes=mins)
                print(f"[PAPER] ⛔ CIRCUIT BREAKER: '{strat_name}' entra en CUARENTENA por {mins}m (WR reciente {recent_wr*100:.1f}% < {min_wr*100:.1f}% en {len(st['recent'])}t).")

    # ============================================================= EVOLUCIÓN
    def _run_evolution_step(self):
        """Evalúa las estrategias rápidas dinámicas, descarta las malas y genera nuevas mutaciones."""
        try:
            paper_stats = {}
            if CSV_FILE.exists():
                with open(CSV_FILE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        s_name = row.get("pattern_detected")
                        res = row.get("result", "").upper()
                        if s_name and res in ["WIN", "LOSS"]:
                            st = paper_stats.setdefault(s_name, {"trades": 0, "wins": 0, "losses": 0})
                            st["trades"] += 1
                            if res == "WIN":
                                st["wins"] += 1
                            else:
                                st["losses"] += 1

            evo_cfg = self.config.get("evolution_engine", {})
            min_trades = int(evo_cfg.get("min_validation_trades", 10))
            min_wr = float(evo_cfg.get("min_win_rate", 0.525))
            target_wr = float(evo_cfg.get("target_win_rate", 0.56))

            logs = self.evolution.evaluate_and_evolve(paper_stats, min_trades=min_trades, min_wr=min_wr, target_wr=target_wr)
            curr_names = {s.name for s in self.evolution.dynamic_strategies}

            # Mantener estrategias estáticas y sincronizar las dinámicas activas
            self.strategies = [s for s in self.strategies if getattr(s, "is_dynamic", False) is False or s.name in curr_names]
            for ds in self.evolution.dynamic_strategies:
                if ds not in self.strategies:
                    self.strategies.append(ds)

            if logs:
                for l in logs:
                    print(f"[PAPER] {l}")
        except Exception as e:
            print(f"[PAPER] ⚠️ Error en ciclo de evolución: {e}")

    # ============================================================= FETCH
    async def _fetch(self, pair, interval):
        try:
            df = await self.bot.fetch_data(pair, interval)
            if df is None or df.empty:
                return pd.DataFrame()
            return df
        except Exception as e:
            print(f"[PAPER] Error fetching {pair}: {e}")
            return pd.DataFrame()

    # ============================================================= HISTORIAL REAL
    def _load_real_history(self):
        """Lee TODOS los trades reales dentro de la ventana y devuelve el DataFrame."""
        cutoff = datetime.now() - timedelta(days=int(self.config.get("history_days", 14)))
        frames = []
        for f in glob.glob(str(Path("logs/trades") / "trades_*.csv")):
            try:
                d = pd.read_csv(f)
                if not d.empty and {"timestamp", "result"}.issubset(d.columns):
                    frames.append(d[["timestamp", "pair", "pattern_detected", "result", "profit_loss"]])
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df[df["timestamp"] >= cutoff]
        df = df[df["result"].astype(str).str.upper().isin(["WIN", "LOSS", "DRAW"])]
        return df

    def _select_winning_strategies(self, hist):
        """Rankea estrategias por WR/PnL con tu data real. Devuelve (nombres, seed_pairs)."""
        if hist.empty:
            print("[PAPER] ⚠️ Sin historial real utilizable. Modo descubrimiento TOTAL (las 17 estrategias).")
            return None, []

        span_days = (hist["timestamp"].max() - hist["timestamp"].min()).days
        if span_days < self.config.get("history_days", 14):
            print(f"[PAPER] ⚠️ Historial cubre solo {span_days} días (<{self.config['history_days']}): "
                  f"selección preliminar, se afianzará con más data.")

        g = hist.groupby("pattern_detected").agg(
            trades=("result", "count"),
            pnl=("profit_loss", "sum"),
        )
        wins = hist[hist["result"].str.upper() == "WIN"].groupby("pattern_detected").size()
        losses = hist[hist["result"].str.upper() == "LOSS"].groupby("pattern_detected").size()
        g["wins"] = wins.reindex(g.index).fillna(0).astype(int)
        g["losses"] = losses.reindex(g.index).fillna(0).astype(int)
        decided = g["wins"] + g["losses"]
        g["wr"] = (g["wins"] / decided.replace(0, pd.NA)).fillna(0.0)

        min_t, min_wr = int(self.config.get("min_trades", 3)), float(self.config.get("min_win_rate", 0.50))
        top_n = int(self.config.get("top_strategies", 8))

        qualified = g[(g["trades"] >= min_t) & (g["wr"] >= min_wr) & (g["pnl"] > 0)]
        relaxed = False
        if qualified.empty:
            relaxed = True
            qualified = g[g["trades"] >= 1].sort_values(["wr", "pnl"], ascending=False).head(top_n)
        else:
            qualified = qualified.sort_values(["wr", "pnl"], ascending=False).head(top_n)

        print(f"[PAPER] 📊 Historial real: {len(hist)} trades en {span_days} días")
        print(f"[PAPER] 🏆 Estrategias seleccionadas{' (criterio relajado: poca data)' if relaxed else ''}:")
        for name, r in qualified.iterrows():
            print(f"   • {name[:52]:<52} {int(r['trades']):>3}t | WR {r['wr']*100:5.1f}% | PnL {r['pnl']:+.2f}")

        seed_pairs = sorted(hist[hist["pattern_detected"].isin(qualified.index)]["pair"].dropna().unique())
        return list(qualified.index), seed_pairs

    async def _init_balance(self):
        if self.demo_api:
            for _ in range(5):
                try:
                    d_bal = await asyncio.wait_for(self.demo_api.balance(), timeout=5.0)
                    if isinstance(d_bal, (int, float)) and d_bal > 0:
                        print(f"[PAPER] 💰 Balance DEMO oficial PocketOption: ${d_bal:.2f} USD")
                        return float(d_bal)
                except Exception as de:
                    await asyncio.sleep(1)
            print(f"[PAPER] ⚠️ No se pudo leer balance de Demo API tras 5 intentos.")

        if CSV_FILE.exists():
            try:
                with open(CSV_FILE, "r", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                if rows:
                    bal = float(rows[-1].get("balance", 0) or 0)
                    if bal > 0:
                        print(f"[PAPER] 📂 Continuando curva: ${bal:.2f} ({len(rows)} trades simulados)")
                        return bal
            except Exception:
                pass
        bal = await self.bot.get_balance()
        if isinstance(bal, (int, float)) and bal > 0:
            real_pnl = getattr(self.bot, 'session_profit', 0.0)
            start_bal = bal - real_pnl
            print(f"[PAPER] 🎬 Capital inicial = saldo real (${bal:.2f}) - PnL de hoy (${real_pnl:+.2f}) = ${start_bal:.2f} USD")
            return float(start_bal)
        print("[PAPER] ⚠️ Sin acceso al balance real. Arrancando con capital inicial ficticio de $100.00 USD")
        return 100.0

    def _stake(self):
        if self.config.get("demo_execution", False) and self.config.get("demo_stake"):
            return round(float(self.config["demo_stake"]), 2)
        if self.config.get("stake_fixed"):
            return round(float(self.config["stake_fixed"]), 2)
        return max(1.0, round(self.balance * float(self.config.get("stake_percent", 0.01)), 2))

    # ============================================================= CSV
    def _append_csv(self, row):
        exists = CSV_FILE.exists()
        try:
            with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                if not exists:
                    w.writeheader()
                w.writerow(row)
        except Exception as e:
            print(f"[PAPER] ⚠️ Error escribiendo CSV: {e}")

    # ============================================================= PERSISTENCIA DE PENDIENTES
    def _load_pending_trades(self):
        if not PENDING_FILE.exists():
            return []
        try:
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            trades = []
            for t in data:
                if isinstance(t.get("exit_ts"), str):
                    t["exit_ts"] = datetime.fromisoformat(t["exit_ts"])
                if isinstance(t.get("resolvable_at"), str):
                    t["resolvable_at"] = datetime.fromisoformat(t["resolvable_at"])
                trades.append(t)
            if trades:
                print(f"[PAPER] 🔄 Recuperadas {len(trades)} operaciones pendientes desde {PENDING_FILE.name}")
            return trades
        except Exception as e:
            print(f"[PAPER] ⚠️ Error leyendo {PENDING_FILE.name}: {e}")
            return []

    def _save_pending_trades(self):
        try:
            serializable = []
            for t in self.pending:
                item = dict(t)
                if isinstance(item.get("exit_ts"), datetime):
                    item["exit_ts"] = item["exit_ts"].isoformat()
                if isinstance(item.get("resolvable_at"), datetime):
                    item["resolvable_at"] = item["resolvable_at"].isoformat()
                serializable.append(item)
            with open(PENDING_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            print(f"[PAPER] ⚠️ Error guardando {PENDING_FILE.name}: {e}")

    # ============================================================= TELEGRAM
    async def _notify_open(self, t):
        if not self.config.get("notify_telegram", True):
            return
        try:
            arrow = "🟢 COMPRA" if t["action"] == "BUY" else "🔴 VENTA"
            tf_str = f"{t['interval']//60}m" if t['interval'] >= 60 else f"{t['interval']}s"
            payout_pct = int(t['payout'] * 100)
            
            msg = (
                f"🧪 <b>[PAPER] NUEVA OPERACIÓN ABIERTA</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💱 <b>{t['pair']}</b> ({tf_str})\n"
                f"🎯 Estrategia: {t['strategy']}\n"
                f"📈 Dirección: {arrow}\n"
                f"💵 Monto simulado: ${t['stake']:.2f}\n"
                f"📊 Payout actual: {payout_pct}%\n"
                f"ℹ️ <i>Dinero ficticio — no afecta cuenta real</i>"
            )
            await self.bot.notifier.send_message(msg)
        except Exception as e:
            print(f"[PAPER] ⚠️ Error notificando apertura: {e}")

    async def _notify_result(self, t, pair, result, profit, exit_p=None):
        if not self.config.get("notify_telegram", True):
            return
        try:
            if result == "WIN":
                icon, res_es = "✅", "GANADA"
            elif result == "LOSS":
                icon, res_es = "❌", "PERDIDA"
            else:
                icon, res_es = "🤝", "EMPATE"
                
            arrow = "🟢 COMPRA" if t["action"] == "BUY" else "🔴 VENTA"
            tf_str = f"{t['interval']//60}m" if t['interval'] >= 60 else f"{t['interval']}s"
            
            price_detail = ""
            if exit_p is not None and t.get("entry_price") is not None:
                price_detail = f"📍 Entrada: <b>{t['entry_price']}</b> ➔ Salida: <b>{exit_p}</b>\n"
            
            msg = (
                f"🧪 <b>[PAPER] Operación Simulada</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💱 <b>{pair}</b> ({tf_str}) | {arrow}\n"
                f"🎯 {t['strategy']}\n"
                f"💵 Apuesta: ${t['stake']:.2f} (ficticia)\n"
                f"{price_detail}"
                f"{icon} <b>RESULTADO: {res_es}</b> ({profit:+.2f} USD sim.)\n"
                f"📊 Balance simulado: <b>${self.balance:.2f}</b>\n"
                f"ℹ️ <i>Dinero de prueba — no afecta tu cuenta real</i>"
            )
            await self.bot.notifier.send_message(msg)
            await asyncio.sleep(0.4)
        except Exception as e:
            print(f"[PAPER] ⚠️ No se pudo notificar por Telegram: {e}")

    # ============================================================= LOOP
    async def run(self):
        if not self.config.get("enabled", True):
            print("[PAPER] Desactivado en config_paper.json.")
            return

        if self.demo_api:
            try:
                print("[PAPER] 🔌 Conectando sesión PocketOption DEMO...")
                await self.demo_api.connect()
                await asyncio.sleep(2)
                d_bal = await self.demo_api.balance()
                print(f"[PAPER] ✅ Conectado a PocketOption DEMO. Saldo Demo: ${d_bal} USD")
            except Exception as e:
                print(f"[PAPER] ⚠️ Error conectando a PocketOption DEMO: {e}")

        await asyncio.sleep(3)
        self.pending = self._load_pending_trades()
        self.balance = await self._init_balance()

        hist = self._load_real_history()
        
        # Entrenar la IA EXCLUSIVAMENTE con el historial simulado (paper)
        try:
            if CSV_FILE.exists():
                paper_hist = pd.read_csv(CSV_FILE)
                if not paper_hist.empty:
                    paper_hist["timestamp"] = pd.to_datetime(paper_hist["timestamp"], errors="coerce")
                    self.ai.train(paper_hist)
                else:
                    print("[PAPER] ⚠️ paper_backtest.csv está vacío. IA inactiva.")
            else:
                print("[PAPER] ⚠️ No existe paper_backtest.csv. IA inactiva.")
        except Exception as e:
            print(f"[PAPER] ❌ Error entrenando IA con datos de paper: {e}")
        
        if self.config.get("include_all_strategies", False):
            self.strategies = list(self.all_strategies)
            seed_pairs = sorted(hist["pair"].dropna().unique()) if not hist.empty else []
            print("[PAPER] 🧪 include_all_strategies=True → explorando con las 17 estrategias base.")
        else:
            names, seed_pairs = self._select_winning_strategies(hist)
            if names is None:
                self.strategies = list(self.all_strategies)
            else:
                self.strategies = [s for s in self.all_strategies if s.name in names]
                
        # Agregar manualmente estrategias extras
        extra = self.config.get("extra_strategies", [])
        if extra:
            for s in self.all_strategies:
                if s.name in extra and s not in self.strategies:
                    self.strategies.append(s)
            print(f"[PAPER] ➕ Estrategias extras forzadas: {extra}")

        # 🧬 Integrar estrategias dinámicas rápidas del motor de evolución
        evo_cfg = self.config.get("evolution_engine", {})
        if evo_cfg.get("enabled", True):
            for ds in self.evolution.dynamic_strategies:
                if ds not in self.strategies:
                    self.strategies.append(ds)
            print(f"[PAPER] 🧬 Integradas {len(self.evolution.dynamic_strategies)} estrategias rápidas dinámicas.")

        universe = list(dict.fromkeys(seed_pairs + list(self.config.get("explore_pairs", []))))
        self.active_pairs = universe[: int(self.config.get("max_pairs", 40))]
        self.seed_pairs = set(seed_pairs)

        cap_pct = float(self.config.get("max_exposure_pct", 0.50))
        print(f"[PAPER] 🌍 Universo: {len(seed_pairs)} pares semilla + "
              f"{len(self.active_pairs) - len(seed_pairs)} de exploración = {len(self.active_pairs)} pares")
        print(f"[PAPER] 🛡️ Gestión: stake 1% (mín $1) | exposición máx {cap_pct*100:.0f}% "
              f"(≈${self.balance * cap_pct:.2f} → ~{int(self.balance * cap_pct)} ops simultáneas)")

        was_paused = False
        while True:
            try:
                if CONFIG_FILE.exists():
                    try:
                        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                        if isinstance(cfg, dict):
                            self.config.update(cfg)
                    except Exception:
                        pass

                if not self.config.get("enabled", True):
                    if not was_paused:
                        print("[PAPER] ⏸️ Paper Trading pausado desde config_paper.json (escaneo detenido).")
                        was_paused = True
                    if self.pending:
                        await self._resolve_pending()
                    await asyncio.sleep(10)
                    continue

                if was_paused:
                    print("[PAPER] ▶️ Paper Trading reanudado desde config_paper.json.")
                    was_paused = False

                # 🧬 Chequeo periódico de evolución de estrategias rápidas
                now_utc = datetime.now(timezone.utc)
                evo_cfg = self.config.get("evolution_engine", {})
                evo_interval = int(evo_cfg.get("eval_interval_seconds", 1800))
                if evo_cfg.get("enabled", True) and (now_utc - self.last_evolution_ts).total_seconds() >= evo_interval:
                    self.last_evolution_ts = now_utc
                    self._run_evolution_step()

                await self._resolve_pending()
                await self._scan()
            except Exception as e:
                print(f"[PAPER] ⚠️ Error en ciclo: {e}")
            await asyncio.sleep(int(self.config.get("cycle_delay", 30)))

    def _run_evolution_step(self):
        """
        Ejecuta un ciclo del motor de evolución dinámica sobre las estrategias probadas en Paper Trading.
        Evalúa el desempeño acumulado, auto-ajusta parámetros de variantes con bajo rendimiento
        y promueve las estrategias con WR >= 60.0% a '⭐ VALIDADA EN PAPER'.
        """
        try:
            if not CSV_FILE.exists():
                return

            df = pd.read_csv(CSV_FILE)
            if df.empty or "pattern_detected" not in df.columns:
                return

            paper_stats = {}
            for strat_name, grp in df.groupby("pattern_detected"):
                wins = int((grp["result"].str.upper() == "WIN").sum())
                losses = int((grp["result"].str.upper() == "LOSS").sum())
                paper_stats[strat_name] = {
                    "wins": wins,
                    "losses": losses,
                    "trades": wins + losses
                }

            evo_cfg = self.config.get("evolution_engine", {})
            min_trades = int(evo_cfg.get("min_validation_trades", 10))
            min_wr = float(evo_cfg.get("min_win_rate", 0.525))
            target_wr = float(evo_cfg.get("target_win_rate", 0.60))

            logs = self.evolution.evaluate_and_evolve(
                paper_stats,
                min_trades=min_trades,
                min_wr=min_wr,
                target_wr=target_wr
            )

            # Actualizar la lista de estrategias activas en paper_bot
            self.strategies = [s for s in self.strategies if not getattr(s, 'is_dynamic', False)]
            for ds in self.evolution.dynamic_strategies:
                if ds not in self.strategies:
                    self.strategies.append(ds)

            if logs:
                print(f"[PAPER-EVO] 🧬 Ciclo completado. {len(logs)} eventos procesados. Estrategias activas en Paper: {len(self.strategies)}")
        except Exception as e:
            print(f"[PAPER-EVO] ⚠️ Error en _run_evolution_step: {e}")

    def _get_dynamic_interval(self, pair, base_interval):
        if not hasattr(self, '_interval_stats'):
            self._interval_stats = {}
            if CSV_FILE.exists():
                try:
                    with open(CSV_FILE, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            p = row.get('pair')
                            try:
                                i = int(row.get('timeframe', 0))
                            except:
                                continue
                            r = row.get('result')
                            if not p or not i or r not in ['WIN', 'LOSS']: continue
                            key = (p, i)
                            stats = self._interval_stats.setdefault(key, {'w':0, 'l':0})
                            if r == 'WIN': stats['w'] += 1
                            else: stats['l'] += 1
                except Exception:
                    pass

        stats = self._interval_stats.get((pair, base_interval), {'w':0, 'l':0})
        total = stats['w'] + stats['l']
        
        if total >= 3 and (stats['w'] / total) < 0.45:
            import random
            pool = [60, 120, 300, 900]
            if base_interval in pool:
                pool.remove(base_interval)
            return random.choice(pool)
            
        return base_interval

    # ============================================================= ESCANEO
    async def _scan(self):
        for pair in list(self.active_pairs):
            base_intervals = self.config.get("intervals", [300])
            intervals_to_test = []
            for inv in base_intervals:
                dyn_inv = self._get_dynamic_interval(pair, inv)
                if dyn_inv not in intervals_to_test:
                    intervals_to_test.append(dyn_inv)

            for interval in intervals_to_test:
                try:
                    # 🛡️ ANTI-SOBREOPERACIÓN: Solo 1 operación abierta por par a la vez
                    if any(t["pair"] == pair for t in self.pending):
                        continue

                    df = await self._fetch(pair, interval)
                    if df.empty or len(df) < 210:
                        if pair not in self.seed_pairs:
                            fails = self._pair_fail_count.get(pair, 0) + 1
                            self._pair_fail_count[pair] = fails
                            if fails >= 5:
                                self.active_pairs.remove(pair)
                                print(f"[PAPER] 🧹 Par {pair} sin datos 5 veces → fuera del universo.")
                        continue

                    df = self.bot.analyzer.compute_indicators(df)
                    df = self.bot.pattern_recognizer.find_candlestick_patterns(df)
                    df = self.bot.pattern_recognizer.find_chart_patterns(df)

                    last = df.iloc[-1]
                    sig_ts = last.get("Timestamp")
                    if sig_ts is None:
                        continue

                    # 🛡️ ANTI-SOBREOPERACIÓN: No permitir más de 1 estrategia en la misma vela del par
                    pair_candle_key = (pair, str(sig_ts))
                    if pair_candle_key in self._seen_pair_candles:
                        continue

                    for strat in self.strategies:
                        # ⛔ 1. CIRCUIT BREAKER CHECK (Si está en cuarentena, no pierde dinero simulado)
                        if self._is_strat_in_quarantine(strat.name):
                            continue

                        # Filtro estricto para RSI Divergence
                        if "RSI Divergence" in strat.name and pair not in ["EURJPY_otc", "USDARS_otc", "XAUUSD_otc", "#AAPL_otc"]:
                            continue
                            
                        key = (pair, interval, strat.name, str(sig_ts))
                        if key in self._seen_signals:
                            continue
                        try:
                            action, reason, _ = strat.get_signal(df)
                        except Exception:
                            continue
                        if action not in ("BUY", "SELL"):
                            continue

                        # 🧠 FILTRO DE INTELIGENCIA ARTIFICIAL (Machine Learning)
                        sig_dt = pd.to_datetime(sig_ts) if not isinstance(sig_ts, datetime) else sig_ts
                        ai_prob = self.ai.predict_probability(sig_dt, pair, strat.name)
                        
                        if ai_prob is not None:
                            if ai_prob < 0.50:
                                print(f"[PAPER] 🧠 IA RECHAZA {action} de {strat.name} en {pair} (Probabilidad éxito: {ai_prob*100:.1f}%)")
                                self._seen_signals.add(key)
                                continue
                            else:
                                print(f"[PAPER] 🧠 IA APRUEBA {action} de {strat.name} en {pair} (Probabilidad éxito: {ai_prob*100:.1f}%)")

                        # 🛡️ CAP DE EXPOSICIÓN (simula cuenta chica gestionada)
                        stake = self._stake()
                        exposure = sum(t["stake"] for t in self.pending)
                        cap_usd = self.balance * float(self.config.get("max_exposure_pct", 0.20))
                        if self.pending and (exposure + stake) > cap_usd:
                            break

                        self._seen_signals.add(key)
                        self._seen_pair_candles.add(pair_candle_key)
                        
                        payout_pct = float(self.config.get("payout", 0.92)) * 100
                        try:
                            po_val = await asyncio.wait_for(self.bot.api.payout(pair), timeout=2.0)
                            if po_val and isinstance(po_val, (int, float)) and po_val > 0:
                                payout_pct = float(po_val)
                        except Exception:
                            pass
                        payout_multi = round(payout_pct / 100.0, 2)
                        
                        now_utc = datetime.now(timezone.utc)
                        trade_id = f"demo_{uuid.uuid4().hex[:8]}"
                        demo_deal_id = None
                        balance_before_trade = None
                        
                        # Si demo_api está conectado, colocar la orden real en saldo Demo
                        if self.demo_api:
                            try:
                                try:
                                    balance_before_trade = await asyncio.wait_for(self.demo_api.balance(), timeout=2.5)
                                except Exception:
                                    balance_before_trade = self.balance

                                demo_stake = float(self.config.get("demo_stake", stake))
                                buy_kwargs = {"asset": pair, "amount": demo_stake, "time": interval, "check_win": False}
                                if action == "BUY":
                                    placed_id, deal_dict = await asyncio.wait_for(self.demo_api.buy(**buy_kwargs), timeout=10.0)
                                else:
                                    placed_id, deal_dict = await asyncio.wait_for(self.demo_api.sell(**buy_kwargs), timeout=10.0)
                                if placed_id:
                                    demo_deal_id = str(placed_id)
                                    trade_id = f"po_demo_{demo_deal_id}"
                            except Exception as po_err:
                                print(f"[PAPER-DEMO] ⚠️ Error enviando orden a PocketOption DEMO: {po_err}")

                            # 🛑 Si la orden falló en Demo, NO registrarla en Paper
                            if not demo_deal_id:
                                print(f"[PAPER-DEMO] ⛔ Trade omitido en Paper porque no se pudo ejecutar en el broker Demo ({pair}).")
                                continue

                        t_obj = {
                            "trade_id": trade_id,
                            "demo_deal_id": demo_deal_id,
                            "pair": pair,
                            "interval": interval,
                            "strategy": strat.name,
                            "action": action,
                            "entry_price": round(float(last["Close"]), 5),
                            "sig_ts": str(sig_ts),
                            "exit_ts": now_utc + timedelta(seconds=interval),
                            "resolvable_at": now_utc + timedelta(seconds=interval + 3),
                            "opened_local": datetime.now(TZ_ARG).strftime("%Y-%m-%d %H:%M:%S"),
                            "stake": stake,
                            "payout": payout_multi,
                            "balance_before": balance_before_trade,
                            "misses": 0,
                        }
                        self.pending.append(t_obj)
                        self._save_pending_trades()
                        
                        demo_tag = "[DEMO REAL]" if demo_deal_id else "[PAPER SIM]"
                        print(f"[PAPER] 🚀 {demo_tag} OPERACIÓN: {pair} ({interval}s) | {strat.name[:35]} | {action} | In: {t_obj['entry_price']} | Stake: ${stake:.2f}")
                        asyncio.create_task(self._notify_open(t_obj))

                        # 🎯 Si es demo_deal_id, levantar watcher inmediato en vivo idéntico a live
                        if demo_deal_id and self.demo_api:
                            asyncio.create_task(self._watch_demo_trade(t_obj))

                        # 🛡️ Break inmediato: solo 1 operación por vela/par para evitar sobreoperación simultánea
                        break
                except Exception as e:
                    print(f"[PAPER] ⚠️ {pair}@{interval}: {e}")
                await asyncio.sleep(0.2)

        if len(self._seen_signals) > 20000:
            self._seen_signals.clear()
        if len(self._seen_pair_candles) > 10000:
            self._seen_pair_candles.clear()

    # ============================================================= WATCHER DEALS DEMO (PARIDAD EN VIVO)
    async def _watch_demo_trade(self, t_obj):
        """
        Monitorea la operación demo en tiempo real con resolución instantánea al vencimiento exacto,
        utilizando las mismas 3 capas de verificación que el bot en Vivo:
        Capa 1: check_win(demo_id) inmediato al expirar.
        Capa 2: closed_deals() del broker.
        Capa 3: Balance Delta en tiempo real (Verdad definitiva).
        """
        demo_id = t_obj.get("demo_deal_id")
        pair = t_obj.get("pair")
        interval = t_obj.get("interval")
        stake = float(t_obj.get("stake", 1.0))
        balance_before = t_obj.get("balance_before")
        if not demo_id or not self.demo_api:
            return

        # Esperar la duración exacta del trade + 3 segundos de margen broker
        wait_seconds = max(1.0, float(interval + 3))
        await asyncio.sleep(wait_seconds)

        is_resolved = False
        res = "LOSS"
        calc_profit = -round(stake, 2)
        close_p = t_obj.get("entry_price")
        matched_info = None

        # --- CAPA 1: check_win activo inmediato ---
        for attempt in range(2):
            try:
                deal_info = await asyncio.wait_for(self.demo_api.check_win(demo_id), timeout=4.0)
                if isinstance(deal_info, dict) and "openPrice" in deal_info and "closePrice" in deal_info:
                    matched_info = deal_info
                    d_open = float(deal_info.get("openPrice", t_obj["entry_price"]))
                    d_close = float(deal_info.get("closePrice", t_obj["entry_price"]))
                    close_p = d_close
                    t_obj["entry_price"] = d_open
                    raw_profit = deal_info.get("profit")

                    if abs(d_open - d_close) < 1e-6 or (raw_profit is not None and float(raw_profit) == 0):
                        res = "DRAW"
                        calc_profit = 0.0
                    elif raw_profit is not None and float(raw_profit) > 0:
                        res = "WIN"
                        payout_rate = float(deal_info.get("percentProfit", 92)) / 100.0
                        calc_profit = round(stake * payout_rate, 2)
                    elif raw_profit is not None and float(raw_profit) < 0:
                        res = "LOSS"
                        calc_profit = -round(stake, 2)
                    elif d_open == d_close:
                        res = "DRAW"
                        calc_profit = 0.0
                    else:
                        res = "LOSS"
                        calc_profit = -round(stake, 2)

                    is_resolved = True
                    break
            except Exception:
                await asyncio.sleep(1.0)

        # --- CAPA 2: closed_deals() si Capa 1 no confirmó ---
        if not is_resolved:
            try:
                closed = await asyncio.wait_for(self.demo_api.closed_deals(), timeout=4.0)
                if closed:
                    deal_list = list(closed.values()) if isinstance(closed, dict) else closed
                    for d in deal_list:
                        if isinstance(d, dict) and (str(d.get("id")) == str(demo_id) or str(d.get("deal_id")) == str(demo_id)):
                            matched_info = d
                            d_open = float(d.get("openPrice", t_obj["entry_price"]))
                            d_close = float(d.get("closePrice", t_obj["entry_price"]))
                            close_p = d_close
                            t_obj["entry_price"] = d_open
                            raw_profit = d.get("profit")

                            if abs(d_open - d_close) < 1e-6 or (raw_profit is not None and float(raw_profit) == 0):
                                res = "DRAW"
                                calc_profit = 0.0
                            elif raw_profit is not None and float(raw_profit) > 0:
                                res = "WIN"
                                payout_rate = float(d.get("percentProfit", 92)) / 100.0
                                calc_profit = round(stake * payout_rate, 2)
                            else:
                                res = "LOSS"
                                calc_profit = -round(stake, 2)
                            is_resolved = True
                            break
            except Exception:
                pass

        # --- CAPA 3: Comparación de Balance Delta Real (Verdad Definitiva como en Live) ---
        try:
            live_bal = await asyncio.wait_for(self.demo_api.balance(), timeout=3.5)
            if isinstance(live_bal, (int, float)) and live_bal > 0:
                self.balance = round(float(live_bal), 2)
                if isinstance(balance_before, (int, float)):
                    b_delta = round(live_bal - balance_before, 2)
                    if not is_resolved:
                        if b_delta > 0.05:
                            res = "WIN"
                            calc_profit = b_delta
                            is_resolved = True
                        elif b_delta < -0.05:
                            res = "LOSS"
                            calc_profit = b_delta
                            is_resolved = True
                        elif abs(b_delta) <= 0.05:
                            res = "DRAW"
                            calc_profit = 0.0
                            is_resolved = True
        except Exception:
            pass

        # Si ninguna capa de broker respondió (desconexión o error), fallback por velas
        if not is_resolved:
            try:
                df = await self._fetch(pair, interval)
                if not df.empty:
                    close_p = round(float(df.iloc[-1]["Close"]), 5)
                    entry_p = t_obj["entry_price"]
                    if abs(close_p - entry_p) < 1e-6:
                        res = "DRAW"
                        calc_profit = 0.0
                    elif (t_obj["action"] == "BUY" and close_p > entry_p) or (t_obj["action"] == "SELL" and close_p < entry_p):
                        res = "WIN"
                        calc_profit = round(stake * float(t_obj.get("payout", 0.92)), 2)
                    else:
                        res = "LOSS"
                        calc_profit = -round(stake, 2)
            except Exception:
                pass

        await self._finish_trade(
            t_obj, pair, interval, close_p,
            note="pocketoption_demo_official",
            official_result=res,
            official_profit=calc_profit
        )

    # ============================================================= RESOLUCIÓN
    async def _resolve_pending(self):
        now = datetime.now(timezone.utc)
        due = [t for t in self.pending if now >= t["resolvable_at"]]
        if not due:
            return

        groups = {}
        for t in due:
            groups.setdefault((t["pair"], t["interval"]), []).append(t)

        for (pair, interval), trades in groups.items():
            df = await self._fetch(pair, interval)
            if df.empty:
                for t in trades:
                    t["misses"] = t.get("misses", 0) + 1
                    if t["misses"] >= 15:
                        print(f"[PAPER] ⚠️ Fallback sin datos para {pair} ({t['strategy']}) tras {t['misses']} intentos. Resolviendo DRAW de seguridad.")
                        await self._finish_trade(t, pair, interval, t["entry_price"], note="nodata_draw_fallback")
                self._save_pending_trades()
                continue

            for t in list(trades):
                # 1. Si la orden fue colocada en PocketOption DEMO, consultar resultado oficial directamente al broker
                demo_id = t.get("demo_deal_id")
                matched_deal = None
                if demo_id and self.demo_api:
                    try:
                        deal_info = await asyncio.wait_for(self.demo_api.check_win(demo_id), timeout=6.0)
                        if isinstance(deal_info, dict) and "openPrice" in deal_info and "closePrice" in deal_info:
                            matched_deal = deal_info
                    except Exception:
                        pass
                    if not matched_deal:
                        try:
                            deals = await asyncio.wait_for(self.demo_api.closed_deals(), timeout=3.0)
                            if deals:
                                deal_list = list(deals.values()) if isinstance(deals, dict) else deals
                                for d in deal_list:
                                    if isinstance(d, dict) and (str(d.get("id")) == str(demo_id) or str(d.get("deal_id")) == str(demo_id)):
                                        matched_deal = d
                                        break
                        except Exception:
                            pass

                if matched_deal:
                    d_open = float(matched_deal.get("openPrice", t["entry_price"]))
                    d_close = float(matched_deal.get("closePrice", t["entry_price"]))
                    raw_profit = matched_deal.get("profit")
                    # En PocketOption, si es DRAW devuelve 0 o el monto exacto reembolsado
                    # Si d_open == d_close, o profit == 0, o closePrice == openPrice -> DRAW
                    if abs(d_open - d_close) < 1e-6:
                        res = "DRAW"
                        calc_profit = 0.0
                    elif raw_profit is not None and float(raw_profit) > 0:
                        res = "WIN"
                        payout_rate = float(matched_deal.get("percentProfit", 92)) / 100.0
                        calc_profit = round(t["stake"] * payout_rate, 2)
                    elif raw_profit is not None and float(raw_profit) < 0:
                        res = "LOSS"
                        calc_profit = -round(t["stake"], 2)
                    elif d_open == d_close:
                        res = "DRAW"
                        calc_profit = 0.0
                    else:
                        res = "LOSS"
                        calc_profit = -round(t["stake"], 2)

                    t["entry_price"] = d_open
                    await self._finish_trade(t, pair, interval, d_close, note="pocketoption_demo_official", official_result=res, official_profit=calc_profit)
                    continue

                # 2. Si es orden de Demo y el broker ya no tiene el deal en memoria inmediata
                if demo_id:
                    # Si aún no venció con holgura, esperar 1 intento
                    t["misses"] = t.get("misses", 0) + 1
                    if t["misses"] < 2 and now < (t["resolvable_at"] + timedelta(seconds=10)):
                        continue
                    # Si el broker ya lo purgó, resolver inmediatamente por velas para registrar sin demoras
                    print(f"[PAPER] ⚡ Deal demo {demo_id} resuelto por cotización de mercado ({pair}).")

                # 3. Fallback de resolución estándar por velas (SOLO para órdenes simuladas sin broker)
                try:
                    mask = df["Timestamp"] >= t["exit_ts"]
                    if mask.any():
                        exit_p = round(float(df.loc[mask].iloc[0]["Open"]), 5)
                    else:
                        exit_p = round(float(df.iloc[-1]["Close"]), 5)
                except Exception as e:
                    print(f"[PAPER] ⚠️ Error extrayendo precio para {pair} ({t['strategy']}): {e}")
                    t["misses"] = t.get("misses", 0) + 1
                    if t["misses"] >= 15:
                        await self._finish_trade(t, pair, interval, t["entry_price"], note="error_draw_fallback")
                    continue

                await self._finish_trade(t, pair, interval, exit_p, note="paper_trial")

    async def _finish_trade(self, t, pair, interval, exit_p, note="paper_trial", official_result=None, official_profit=None):
        entry = t["entry_price"]
        payout = float(t.get("payout", self.config.get("payout", 0.92)))
        if official_result is not None:
            result = official_result
            profit = round(float(official_profit), 2)
        else:
            if exit_p == entry:
                result = "DRAW"
            elif (t["action"] == "BUY" and exit_p > entry) or (t["action"] == "SELL" and exit_p < entry):
                result = "WIN"
            else:
                result = "LOSS"
            profit = round(t["stake"] * payout, 2) if result == "WIN" else (-round(t["stake"], 2) if result == "LOSS" else 0.0)

        # ⛔ Actualizar Circuit Breaker
        self._update_circuit_breaker(t["strategy"], result)

        # Actualizar stats dinámicos en tiempo real para la rotación de pares
        if hasattr(self, '_interval_stats') and result in ['WIN', 'LOSS']:
            st = self._interval_stats.setdefault((pair, interval), {'w':0, 'l':0})
            if result == 'WIN':
                st['w'] += 1
            else:
                st['l'] += 1

        self.balance = round(self.balance + profit, 2)
        if self.demo_api:
            try:
                live_bal = await asyncio.wait_for(self.demo_api.balance(), timeout=3.0)
                if isinstance(live_bal, (int, float)) and live_bal > 0:
                    self.balance = round(float(live_bal), 2)
            except Exception:
                pass

        self._append_csv({
            "timestamp": t["opened_local"],
            "trade_id": t["trade_id"],
            "pair": pair,
            "timeframe": interval,
            "decision": t["action"],
            "pattern_detected": t["strategy"],
            "price": entry,
            "exit_price": exit_p,
            "result": result,
            "payout": payout,
            "stake": t["stake"],
            "profit_loss": profit,
            "balance": self.balance,
            "notes": note,
        })

        if t in self.pending:
            self.pending.remove(t)
        self._save_pending_trades()

        asyncio.create_task(self._notify_result(t, pair, result, profit, exit_p))

        icon = "✅" if result == "WIN" else ("❌" if result == "LOSS" else "🤝")
        print(f"[PAPER] {icon} {pair} | {t['strategy'][:38]} | {t['action']} | "
              f"{result} {profit:+.2f} (In: {entry} -> Out: {exit_p}) | Bal: ${self.balance:.2f} | abiertos: {len(self.pending)}")
