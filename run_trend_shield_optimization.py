import os
import glob
import json
from pathlib import Path
import pandas as pd
import numpy as np
import ta

def compute_all_indicators(df):
    df = df.copy()
    close = df['Close']
    high = df['High']
    low = df['Low']
    open_p = df['Open']

    # EMAs & SMAs
    df['EMA_20'] = ta.trend.ema_indicator(close, window=20)
    df['EMA_50'] = ta.trend.ema_indicator(close, window=50)
    df['SMA_200'] = ta.trend.sma_indicator(close, window=200)

    # RSI
    df['RSI'] = ta.momentum.rsi(close, window=14)

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    df['Stoch_K'] = stoch.stoch()
    df['Stoch_D'] = stoch.stoch_signal()

    # MACD
    macd = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Diff'] = macd.macd_diff()

    # ATR
    df['ATR'] = ta.volatility.average_true_range(high, low, close, window=14)

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df['BB_Upper'] = bb.bollinger_hband()
    df['BB_Lower'] = bb.bollinger_lband()
    df['BB_Middle'] = bb.bollinger_mavg()

    # Keltner Channels
    kc_ema = ta.trend.ema_indicator(close, window=20)
    kc_atr = ta.volatility.average_true_range(high, low, close, window=10)
    df['KC_Upper'] = kc_ema + (1.8 * kc_atr)
    df['KC_Lower'] = kc_ema - (1.8 * kc_atr)
    df['KC_Middle'] = kc_ema

    # WaveTrend Oscillator (10, 21)
    ap = (high + low + close) / 3.0
    esa = ta.trend.ema_indicator(ap, window=10)
    d = ta.trend.ema_indicator(abs(ap - esa), window=10)
    ci = (ap - esa) / (0.015 * d.replace(0, 0.00001))
    df['WT1'] = ta.trend.ema_indicator(ci, window=21)
    df['WT2'] = df['WT1'].rolling(window=4).mean()

    # Donchian Channels (20)
    df['Donchian_High'] = high.rolling(window=20).max()
    df['Donchian_Low'] = low.rolling(window=20).min()

    # Local Highs/Lows for Fibonacci
    df['Recent_High_30'] = high.rolling(window=30).max()
    df['Recent_Low_30'] = low.rolling(window=30).min()

    return df.dropna().reset_index(drop=True)


def evaluate_strategies_at_bar(df, i, trend_filter_mode='NONE'):
    """
    Evaluates trading signals at index i with specified Trend Shield mode:
    - 'NONE': Raw strategy trigger
    - 'EMA_CONFLUENCE': BUY requires (Close >= EMA50 or EMA20 > EMA50); SELL requires (Close <= EMA50 or EMA20 < EMA50)
    - 'SMA200_CONFLUENCE': BUY requires (Close > SMA200 or RSI < 25); SELL requires (Close < SMA200 or RSI > 75)
    - 'MACD_MOMENTUM_EXHAUSTION': BUY requires MACD_Diff > MACD_Diff[prev]; SELL requires MACD_Diff < MACD_Diff[prev]
    - 'FULL_SHIELD': EMA_CONFLUENCE + MACD_MOMENTUM_EXHAUSTION
    """
    curr = df.iloc[i]
    prev = df.iloc[i-1]

    signals = []

    close = curr['Close']
    open_p = curr['Open']
    high = curr['High']
    low = curr['Low']

    ema20 = curr['EMA_20']
    ema50 = curr['EMA_50']
    sma200 = curr['SMA_200']

    # Trend Shield Checks
    pass_trend_buy = True
    pass_trend_sell = True

    if trend_filter_mode == 'EMA_CONFLUENCE':
        # Don't buy in active strong bear trend
        pass_trend_buy = not (close < ema20 < ema50)
        # Don't sell in active strong bull rally
        pass_trend_sell = not (close > ema20 > ema50)

    elif trend_filter_mode == 'SMA200_CONFLUENCE':
        pass_trend_buy = (close > sma200) or (curr['RSI'] < 25)
        pass_trend_sell = (close < sma200) or (curr['RSI'] > 75)

    elif trend_filter_mode == 'MACD_MOMENTUM_EXHAUSTION':
        pass_trend_buy = curr['MACD_Diff'] > prev['MACD_Diff']
        pass_trend_sell = curr['MACD_Diff'] < prev['MACD_Diff']

    elif trend_filter_mode == 'FULL_SHIELD':
        pass_trend_buy = (not (close < ema20 < ema50)) and (curr['MACD_Diff'] > prev['MACD_Diff'])
        pass_trend_sell = (not (close > ema20 > ema50)) and (curr['MACD_Diff'] < prev['MACD_Diff'])

    # --- 1. WaveTrend + Keltner Channel Reversion ---
    wt1 = curr['WT1']
    wt2 = curr['WT2']
    prev_wt1 = prev['WT1']
    prev_wt2 = prev['WT2']
    kc_upper = curr['KC_Upper']
    kc_lower = curr['KC_Lower']

    kc_buy = (low <= kc_lower) or (prev['Low'] <= prev['KC_Lower'])
    wt_buy = (wt1 < -45) and (prev_wt1 < prev_wt2 and wt1 > wt2) and (close > open_p)
    if kc_buy and wt_buy and pass_trend_buy:
        signals.append(('WaveTrend + Keltner Channel Reversion', 'BUY'))

    kc_sell = (high >= kc_upper) or (prev['High'] >= prev['KC_Upper'])
    wt_sell = (wt1 > 45) and (prev_wt1 > prev_wt2 and wt1 < wt2) and (close < open_p)
    if kc_sell and wt_sell and pass_trend_sell:
        signals.append(('WaveTrend + Keltner Channel Reversion', 'SELL'))

    # --- 2. Alpha Convergence (Bollinger + Fibo + Stoch) ---
    bb_lower = curr['BB_Lower']
    bb_upper = curr['BB_Upper']
    stoch_k = curr['Stoch_K']
    stoch_d = curr['Stoch_D']
    prev_stoch_k = prev['Stoch_K']
    prev_stoch_d = prev['Stoch_D']

    recent_h = curr['Recent_High_30']
    recent_l = curr['Recent_Low_30']
    diff_hl = recent_h - recent_l
    if diff_hl > 0:
        fibo_618_buy = recent_h - (diff_hl * 0.618)
        fibo_618_sell = recent_l + (diff_hl * 0.618)

        # Alpha Buy
        alpha_buy = (low <= bb_lower or abs(low - fibo_618_buy) / close < 0.0015) and (stoch_k < 25 and prev_stoch_k < prev_stoch_d and stoch_k > stoch_d) and (close > open_p)
        if alpha_buy and pass_trend_buy:
            signals.append(('Alpha Convergence (Bollinger + Fibo + Stoch)', 'BUY'))

        # Alpha Sell
        alpha_sell = (high >= bb_upper or abs(high - fibo_618_sell) / close < 0.0015) and (stoch_k > 75 and prev_stoch_k > prev_stoch_d and stoch_k < stoch_d) and (close < open_p)
        if alpha_sell and pass_trend_sell:
            signals.append(('Alpha Convergence (Bollinger + Fibo + Stoch)', 'SELL'))

    # --- 3. Stochastic + SMA200 (Trend Following Pullbacks) ---
    if close > sma200 and stoch_k < 25 and (prev_stoch_k < prev_stoch_d and stoch_k > stoch_d) and (close > open_p):
        signals.append(('Estocástico + SMA200', 'BUY'))
    elif close < sma200 and stoch_k > 75 and (prev_stoch_k > prev_stoch_d and stoch_k < stoch_d) and (close < open_p):
        signals.append(('Estocástico + SMA200', 'SELL'))

    # --- 4. Fibonacci Retracement 61.8% ---
    if diff_hl > 0:
        if abs(low - fibo_618_buy) / close < 0.0010 and (stoch_k < 30) and (close > open_p) and pass_trend_buy:
            signals.append(('Fibonacci Retracement 61.8%', 'BUY'))
        elif abs(high - fibo_618_sell) / close < 0.0010 and (stoch_k > 70) and (close < open_p) and pass_trend_sell:
            signals.append(('Fibonacci Retracement 61.8%', 'SELL'))

    # --- 5. Expert Vision Donchian Reversion ---
    dh = curr['Donchian_High']
    dl = curr['Donchian_Low']
    if low <= dl and (curr['RSI'] < 30) and (close > open_p) and pass_trend_buy:
        signals.append(('Expert Vision Donchian Reversion', 'BUY'))
    elif high >= dh and (curr['RSI'] > 70) and (close < open_p) and pass_trend_sell:
        signals.append(('Expert Vision Donchian Reversion', 'SELL'))

    return signals


def run_full_backtest(csv_path, trend_filter_mode='NONE'):
    try:
        df_raw = pd.read_csv(csv_path)
        if df_raw.empty or len(df_raw) < 250:
            return None

        # Standardize columns
        cols = {c: c.capitalize() for c in df_raw.columns}
        df_raw.rename(columns=cols, inplace=True)
        if 'Time' in df_raw.columns:
            df_raw.rename(columns={'Time': 'Timestamp'}, inplace=True)

        for col in ['Open', 'High', 'Low', 'Close']:
            if col in df_raw.columns:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')

        df_raw = df_raw.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
        df_calc = compute_all_indicators(df_raw)

        if len(df_calc) < 250:
            return None

        payout = 0.85 # Standard PocketOption 85% payout
        results = {}

        for i in range(50, len(df_calc) - 1):
            signals = evaluate_strategies_at_bar(df_calc, i, trend_filter_mode=trend_filter_mode)
            if not signals:
                continue

            entry_bar = df_calc.iloc[i]
            exit_bar = df_calc.iloc[i+1] # 1 candle full duration
            
            # Incorporate slippage penalty
            spread_penalty = entry_bar['ATR'] * 0.03

            for strat_name, action in signals:
                if strat_name not in results:
                    results[strat_name] = {'wins': 0, 'losses': 0, 'pnl': 0.0, 'trades': 0}

                is_win = False
                if action == 'BUY':
                    if exit_bar['Close'] > (entry_bar['Close'] + spread_penalty):
                        is_win = True
                elif action == 'SELL':
                    if exit_bar['Close'] < (entry_bar['Close'] - spread_penalty):
                        is_win = True

                results[strat_name]['trades'] += 1
                if is_win:
                    results[strat_name]['wins'] += 1
                    results[strat_name]['pnl'] += payout
                else:
                    results[strat_name]['losses'] += 1
                    results[strat_name]['pnl'] -= 1.0

        return results
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
        return None


def main():
    historical_dir = Path("historical_data")
    csv_files = sorted(list(historical_dir.glob("*.csv")))
    print(f"Found {len(csv_files)} historical datasets.")

    modes = ['NONE', 'EMA_CONFLUENCE', 'SMA200_CONFLUENCE', 'MACD_MOMENTUM_EXHAUSTION', 'FULL_SHIELD']
    mode_summaries = {}

    for mode in modes:
        mode_summaries[mode] = {
            'total_trades': 0,
            'total_wins': 0,
            'total_losses': 0,
            'net_pnl': 0.0,
            'by_strategy': {},
            'by_pair_tf': {}
        }

        for f in csv_files:
            # Extract pair and timeframe from filename e.g. "EURUSD_otc_300s.csv"
            name_parts = f.stem.split('_')
            pair_tf_key = f.stem
            
            res = run_full_backtest(f, trend_filter_mode=mode)
            if not res:
                continue

            for strat, s_data in res.items():
                if s_data['trades'] == 0:
                    continue

                # Strategy aggregation
                if strat not in mode_summaries[mode]['by_strategy']:
                    mode_summaries[mode]['by_strategy'][strat] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
                mode_summaries[mode]['by_strategy'][strat]['trades'] += s_data['trades']
                mode_summaries[mode]['by_strategy'][strat]['wins'] += s_data['wins']
                mode_summaries[mode]['by_strategy'][strat]['losses'] += s_data['losses']
                mode_summaries[mode]['by_strategy'][strat]['pnl'] += s_data['pnl']

                # Pair & TF aggregation
                if pair_tf_key not in mode_summaries[mode]['by_pair_tf']:
                    mode_summaries[mode]['by_pair_tf'][pair_tf_key] = {}
                mode_summaries[mode]['by_pair_tf'][pair_tf_key][strat] = s_data

                mode_summaries[mode]['total_trades'] += s_data['trades']
                mode_summaries[mode]['total_wins'] += s_data['wins']
                mode_summaries[mode]['total_losses'] += s_data['losses']
                mode_summaries[mode]['net_pnl'] += s_data['pnl']

    # --- PRINT COMPARATIVE MATRIX ---
    print("\n" + "="*80)
    print("COMPARATIVE TREND SHIELD MODES MATRIX (49 DATASETS - ALL ASSETS)")
    print("="*80)
    print(f"{'Filter Mode':<28} | {'Trades':<8} | {'Wins':<6} | {'Win Rate':<10} | {'Net P&L ($)':<12} | {'Profit Factor':<14}")
    print("-" * 88)

    best_mode = None
    best_mode_pnl = -999999

    for mode in modes:
        tot = mode_summaries[mode]['total_trades']
        wins = mode_summaries[mode]['total_wins']
        losses = mode_summaries[mode]['total_losses']
        pnl = mode_summaries[mode]['net_pnl']
        wr = (wins / tot * 100) if tot > 0 else 0.0
        gross_profit = wins * 0.85
        gross_loss = losses * 1.0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        if pnl > best_mode_pnl:
            best_mode_pnl = pnl
            best_mode = mode

        print(f"{mode:<28} | {tot:<8} | {wins:<6} | {wr:<9.2f}% | ${pnl:<11.2f} | {pf:<13.2f}")

    print("\n" + "="*80)
    print(f"BREAKDOWN BY STRATEGY IN BEST MODE: {best_mode}")
    print("="*80)
    for strat, data in mode_summaries[best_mode]['by_strategy'].items():
        t = data['trades']
        w = data['wins']
        l = data['losses']
        wr = (w / t * 100) if t > 0 else 0.0
        pnl = data['pnl']
        pf = (w * 0.85) / l if l > 0 else 0.0
        print(f"• {strat:<45} | {t:>5} tr | {wr:>6.2f}% WR | ${pnl:>+8.2f} | PF: {pf:.2f}")

    # Extract Top High-Winrate Combinations (Pair + TF + Strategy)
    top_combos = []
    for pair_tf, strats in mode_summaries[best_mode]['by_pair_tf'].items():
        for strat, data in strats.items():
            t = data['trades']
            w = data['wins']
            l = data['losses']
            wr = (w / t * 100) if t > 0 else 0.0
            pnl = data['pnl']
            pf = (w * 0.85) / l if l > 0 else 0.0

            if t >= 10 and wr >= 58.0 and pnl > 0:
                top_combos.append({
                    'pair_tf': pair_tf,
                    'strategy': strat,
                    'trades': t,
                    'wins': w,
                    'losses': l,
                    'winrate': wr,
                    'pnl': pnl,
                    'profit_factor': pf
                })

    top_combos.sort(key=lambda x: (x['pnl'], x['winrate']), reverse=True)

    print("\n" + "="*80)
    print(f"TOP WINNING COMBINATIONS (WR >= 58%, Net Profit > 0, Min 10 Trades)")
    print("="*80)
    for c in top_combos:
        print(f"{c['pair_tf']:<22} | {c['strategy']:<42} | {c['trades']:>4} tr | {c['winrate']:>6.2f}% WR | ${c['pnl']:>+7.2f} | PF: {c['profit_factor']:.2f}")

    # Save to JSON
    out_file = Path("trend_shield_optimization_report.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({
            'best_mode': best_mode,
            'summary': mode_summaries,
            'top_combinations': top_combos
        }, f, indent=4)

    print(f"\n[OK] Complete report saved to {out_file}")

if __name__ == '__main__':
    main()
