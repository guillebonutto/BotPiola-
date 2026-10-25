"""
=============================================================================
    GRADUATED STRATEGY LOADER — INYECTOR DE ESTRATEGIAS GRADUADAS
=============================================================================
Carga dinámicamente las estrategias promovidas por el optimizador genético
(auto_optimizer_daemon.py) desde 'strategies_ready_for_live.json' y las
instancia con sus hiperparámetros óptimos, pares de alta efectividad y
filtros de horarios de oro / horas tóxicas para su ejecución en vivo.
=============================================================================
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from strategy_rapid_scalper import (
    FastEMAPullbackScalper,
    StochasticBollingerBurst,
    RSIVelocityMomentum,
    MicroRangeBreakout
)
from strategy_liquidity_fvg import StrategyLiquidityFVG
from strategy_micro_breakout_7v import StrategyMicroBreakout7v

# Estrategias Clásicas Institucionales (que pueden graduar con clusters especializados de pares/horas)
from strategy_stochastic import StrategyStochastic
from strategy_price_action_engulfing import StrategyPriceActionEngulfing
from strategy_divergence_pivot import StrategyDivergencePivot
from strategy_smart_money_smc import StrategySmartMoneySMC
from strategy_ttm_squeeze import StrategyTTMSqueeze
from strategy_wavetrend_keltner import StrategyWaveTrendKeltner
from strategy_fibonacci_master import StrategyFibonacciMasterSniper
from strategy_chartist_patterns import StrategyChartistPatterns
from strategy_alpha_convergence import StrategyAlphaConvergence


def parse_and_instantiate_strategy(name: str, meta: Optional[dict] = None):
    """
    Analiza el nombre y metadatos de una estrategia graduada y retorna una
    instancia lista para operar en vivo con target_pairs, toxic_hours y bypass_filter.
    """
    meta = meta or {}
    strat = None

    # --- FAMILIAS DE ESTRATEGIAS DINÁMICAS / RAPID / SMC ---

    # 1. Élite Micro Breakout (Gen35 u otra variante de 7 velas con confirmación de cuerpo)
    if "Micro Breakout 7v" in name or "StrategyMicroBreakout7v" in name or "[ÉLITE]" in name:
        m = re.search(r"(\d+)\s*v", name)
        window = int(m.group(1)) if m else 7
        strat = StrategyMicroBreakout7v(range_window=window, expansion_factor=1.15, bypass_filter=True)
        strat.name = name

    # 2. Micro Breakout / Micro Range Breakout (Gen44, Gen45, etc.)
    elif "Micro Breakout" in name or "Micro Range Breakout" in name or ("Breakout" in name and "RAPID" in name):
        m = re.search(r"(\d+)\s*v", name)
        window = int(m.group(1)) if m else 5
        strat = MicroRangeBreakout(range_window=window, name=name)

    # 3. RSI Velocity Momentum (Gen34, etc.)
    elif "RSI Velocity" in name or ("RSI" in name and "Velocity" in name):
        m = re.search(r"(\d+)\s*p", name)
        period = int(m.group(1)) if m else 7
        strat = RSIVelocityMomentum(rsi_period=period, name=name)

    # 4. Fast EMA Pullback Scalper (9/21, 7/16, etc.)
    elif "EMA Pullback" in name or "Fast EMA Scalp" in name or ("EMA" in name and "Pullback" in name):
        m = re.search(r"(\d+)[^\d]+(\d+)", name)
        if m:
            fast, slow = int(m.group(1)), int(m.group(2))
        else:
            fast, slow = 9, 21
        strat = FastEMAPullbackScalper(fast_period=fast, slow_period=slow, name=name)

    # 5. Stochastic Bollinger Burst (BB Dev, 5/3+BB14, etc.)
    elif "Stoch" in name and ("BB" in name or "Burst" in name or "Scalp" in name):
        dev = 1.8
        bb_w = 14
        k = 5
        d = 3

        m_dev = re.search(r"Dev([\d\.]+)", name)
        if m_dev:
            try:
                dev = float(m_dev.group(1))
            except ValueError:
                pass

        m_w = re.search(r"W(\d+)|BB(\d+)", name)
        if m_w:
            bb_w = int(m_w.group(1) or m_w.group(2))

        m_kd = re.search(r"(\d+)/(\d+)", name)
        if m_kd:
            k = int(m_kd.group(1))
            d = int(m_kd.group(2))

        strat = StochasticBollingerBurst(stoch_k=k, stoch_d=d, bb_window=bb_w, bb_dev=dev, name=name)

    # 6. SMC Liquidity & FVG
    elif "Liquidity" in name or "FVG" in name:
        w = 15
        wick = 0.32
        fvg = 5
        m_w = re.search(r"W(\d+)", name)
        if m_w:
            w = int(m_w.group(1))
        m_wick = re.search(r"M(\d+)", name)
        if m_wick:
            wick = int(m_wick.group(1)) / 100.0
        strat = StrategyLiquidityFVG(swing_window=w, min_wick_ratio=wick, fvg_lookback=fvg, rsi_filter_enabled=True, name=name)

    # --- ESTRATEGIAS CLÁSICAS GRADUADAS POR ESPECIALIZACIÓN (CLUSTER) ---
    elif "Estocástico" in name or "Stochastic" in name:
        strat = StrategyStochastic(bypass_filter=True)
        strat.name = name
    elif "Envolvente" in name or "Engulfing" in name or "Price Action" in name:
        strat = StrategyPriceActionEngulfing(bypass_filter=True)
        strat.name = name
    elif "Divergence" in name or "Divergencia" in name:
        strat = StrategyDivergencePivot(bypass_filter=True)
        strat.name = name
    elif "SMC" in name or "Smart Money" in name:
        strat = StrategySmartMoneySMC(bypass_filter=True)
        strat.name = name
    elif "Squeeze" in name or "TTM" in name:
        strat = StrategyTTMSqueeze(bypass_filter=True)
        strat.name = name
    elif "WaveTrend" in name:
        strat = StrategyWaveTrendKeltner(bypass_filter=True)
        strat.name = name
    elif "Fibonacci" in name:
        strat = StrategyFibonacciMasterSniper(bypass_filter=True)
        strat.name = name
    elif "Chartist" in name:
        strat = StrategyChartistPatterns(bypass_filter=True)
        strat.name = name
    elif "Alpha Convergence" in name:
        strat = StrategyAlphaConvergence(bypass_filter=True)
        strat.name = name

    # Configurar banderas institucionales y metadatos multidimensionales
    if strat is not None:
        strat.bypass_filter = True
        strat.is_dynamic = True
        strat.is_graduated = True
        strat.bypass_regime = True # Ha demostrado efectividad empírica en Paper

        if meta:
            if "pairs" in meta:
                strat.target_pairs = meta["pairs"]
            if "toxic_pairs" in meta:
                strat.toxic_pairs = meta["toxic_pairs"]
            if "allowed_hours_utc" in meta:
                strat.allowed_hours = meta["allowed_hours_utc"]
            if "toxic_hours_utc" in meta:
                strat.toxic_hours = meta["toxic_hours_utc"]
            if "win_rate" in meta:
                strat.paper_win_rate = meta["win_rate"]
            if "trades" in meta:
                strat.paper_trades = meta["trades"]
            if "graduation_type" in meta:
                strat.graduation_type = meta["graduation_type"]

    return strat


def load_graduated_strategies(file_path: str = "strategies_ready_for_live.json") -> List:
    """
    Lee 'strategies_ready_for_live.json' y devuelve una lista de instancias
    de estrategias listas para operar en cuenta real con sus filtros multidimensionales.
    """
    path = Path(file_path)
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[GraduatedLoader] Error leyendo {file_path}: {e}")
        return []

    strategies = []
    for strat_name, meta in data.items():
        # Validar si tiene estado apto para operar
        status = meta.get("status", "")
        if status and status != "READY_FOR_LIVE_ACCOUNT":
            continue

        strat_obj = parse_and_instantiate_strategy(strat_name, meta)
        if strat_obj is not None:
            strategies.append(strat_obj)
        else:
            print(f"[GraduatedLoader] [WARN] No se pudo mapear estrategia graduada: '{strat_name}'")

    return strategies
