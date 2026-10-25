import pytest
from graduated_strategy_loader import parse_and_instantiate_strategy, load_graduated_strategies
from strategy_rapid_scalper import MicroRangeBreakout, RSIVelocityMomentum, FastEMAPullbackScalper, StochasticBollingerBurst
from strategy_liquidity_fvg import StrategyLiquidityFVG
from strategy_micro_breakout_7v import StrategyMicroBreakout7v
from strategy_stochastic import StrategyStochastic


def test_parse_elite_micro_breakout():
    name = "[ÉLITE] Micro Breakout 7v (Gen35)"
    strat = parse_and_instantiate_strategy(name, {"pairs": ["AUDUSD_otc"], "win_rate": 92.3})
    assert strat is not None
    assert isinstance(strat, StrategyMicroBreakout7v)
    assert strat.bypass_filter is True
    assert strat.is_graduated is True
    assert strat.target_pairs == ["AUDUSD_otc"]
    assert strat.paper_win_rate == 92.3


def test_parse_rapid_micro_breakout():
    name = "[RAPID] Micro Breakout 4v (Gen44)"
    strat = parse_and_instantiate_strategy(name, {"win_rate": 65.3})
    assert strat is not None
    assert isinstance(strat, MicroRangeBreakout)
    assert strat.range_window == 4
    assert strat.is_graduated is True


def test_parse_rsi_velocity():
    name = "[RAPID] RSI Velocity 6p (Gen34)"
    strat = parse_and_instantiate_strategy(name)
    assert strat is not None
    assert isinstance(strat, RSIVelocityMomentum)
    assert strat.rsi_period == 6
    assert strat.is_graduated is True


def test_parse_ema_pullback():
    name = "[RAPID] EMA Pullback 9/21"
    strat = parse_and_instantiate_strategy(name)
    assert strat is not None
    assert isinstance(strat, FastEMAPullbackScalper)
    assert strat.fast_period == 9
    assert strat.slow_period == 21


def test_parse_stoch_burst():
    name = "[RAPID] Stoch Burst 5/3 + BB14"
    strat = parse_and_instantiate_strategy(name)
    assert strat is not None
    assert isinstance(strat, StochasticBollingerBurst)
    assert strat.stoch_k_period == 5
    assert strat.stoch_d_period == 3
    assert strat.bb_window == 14


def test_parse_liquidity_fvg():
    name = "[SMC] Liquidity & FVG W18/M40 (Gen12)"
    strat = parse_and_instantiate_strategy(name)
    assert strat is not None
    assert isinstance(strat, StrategyLiquidityFVG)
    assert strat.swing_window == 18
    assert strat.min_wick_ratio == 0.40


def test_parse_multidimensional_cluster():
    name = "Estocástico + SMA200"
    meta = {
        "win_rate": 74.4,
        "trades": 117,
        "pairs": ["AUDUSD_otc", "USDCAD_otc"],
        "toxic_pairs": ["EURUSD_otc"],
        "allowed_hours_utc": [7, 8, 10, 12, 14],
        "toxic_hours_utc": [0, 1, 2, 3, 11, 16, 22],
        "graduation_type": "CLUSTER_SPECIALIZED"
    }
    strat = parse_and_instantiate_strategy(name, meta)
    assert strat is not None
    assert isinstance(strat, StrategyStochastic)
    assert strat.is_graduated is True
    assert strat.target_pairs == ["AUDUSD_otc", "USDCAD_otc"]
    assert strat.toxic_pairs == ["EURUSD_otc"]
    assert strat.allowed_hours == [7, 8, 10, 12, 14]
    assert strat.toxic_hours == [0, 1, 2, 3, 11, 16, 22]
    assert strat.paper_win_rate == 74.4


def test_load_graduated_strategies():
    strats = load_graduated_strategies()
    assert len(strats) >= 5
    names = [s.name for s in strats]
    assert "[RAPID] Micro Breakout 4v (Gen44)" in names
    assert "Estocástico + SMA200" in names
