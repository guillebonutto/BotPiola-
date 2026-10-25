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

    df['EMA_20'] = ta.trend.ema_indicator(close, window=20)
    df['EMA_50'] = ta.trend.ema_indicator(close, window=50)
    df['SMA_200'] = ta.trend.sma_indicator(close, window=200)

    df['RSI'] = ta.momentum.rsi(close, window=14)

    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    df['Stoch_K'] = stoch.stoch()
    df['Stoch_D'] = stoch.stoch_signal()

    macd = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Diff'] = macd.macd_diff()

    df['ATR'] = ta.volatility.average_true_range(high, low, close, window=14)

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df['BB_Upper'] = bb.bollinger_hband()
    df['BB_Lower'] = bb.bollinger_lband()
    df['BB_Middle'] = bb.bollinger_mavg()

    kc_ema = ta.trend.ema_indicator(close, window=20)
    kc_atr = ta.volatility.average_true_range(high, low, close, window=10)
    df['KC_Upper'] = kc_ema + (1.8 * kc_atr)
    df['KC_Lower'] = kc_ema - (1.8 * kc_atr)

    ap = (high + low + close) / 3.0
    esa = ta.trend.ema_indicator(ap, window=10)
    d = ta.trend.ema_indicator(abs(ap - esa), window=10)
    ci = (ap - esa) / (0.015 * d.replace(0, 0.00001))
    df['WT1'] = ta.trend.ema_indicator(ci, window=21)
    df['WT2'] = df['WT1'].rolling(window=4).mean()

    df['Donchian_High'] = high.rolling(window=20).max()
    df['Donchian_Low'] = low.rolling(window=20).min()

    df['Recent_High_30'] = high.rolling(window=30).max()
    df['Recent_Low_30'] = low.rolling(window=30).min()

    return df.dropna().reset_index(drop=True)


def simulate_dataset(df_calc):
    modes = ['NONE', 'EMA_CONFLUENCE', 'SMA200_CONFLUENCE', 'MACD_MOMENTUM_EXHAUSTION', 'FULL_SHIELD']
    res_modes = {m: {} for m in modes}
    payout = 0.85

    close = df_calc['Close'].values
    open_p = df_calc['Open'].values
    high = df_calc['High'].values
    low = df_calc['Low'].values
    ema20 = df_calc['EMA_20'].values
    ema50 = df_calc['EMA_50'].values
    sma200 = df_calc['SMA_200'].values
    rsi = df_calc['RSI'].values
    stoch_k = df_calc['Stoch_K'].values
    stoch_d = df_calc['Stoch_D'].values
    macd_diff = df_calc['MACD_Diff'].values
    atr = df_calc['ATR'].values
    bb_upper = df_calc['BB_Upper'].values
    bb_lower = df_calc['BB_Lower'].values
    kc_upper = df_calc['KC_Upper'].values
    kc_lower = df_calc['KC_Lower'].values
    wt1 = df_calc['WT1'].values
    wt2 = df_calc['WT2'].values
    recent_h = df_calc['Recent_High_30'].values
    recent_l = df_calc['Recent_Low_30'].values

    n = len(df_calc)

    for i in range(50, n - 1):
        c_close = close[i]
        c_open = open_p[i]
        c_high = high[i]
        c_low = low[i]
        p_low = low[i-1]
        p_high = high[i-1]

        c_ema20 = ema20[i]
        c_ema50 = ema50[i]
        c_sma200 = sma200[i]
        c_rsi = rsi[i]
        c_sk = stoch_k[i]
        c_sd = stoch_d[i]
        p_sk = stoch_k[i-1]
        p_sd = stoch_d[i-1]
        c_mdiff = macd_diff[i]
        p_mdiff = macd_diff[i-1]
        c_atr = atr[i]

        c_wt1 = wt1[i]
        c_wt2 = wt2[i]
        p_wt1 = wt1[i-1]
        p_wt2 = wt2[i-1]

        c_kcu = kc_upper[i]
        c_kcl = kc_lower[i]
        p_kcl = kc_lower[i-1]
        p_kcu = kc_upper[i-1]

        c_bbu = bb_upper[i]
        c_bbl = bb_lower[i]

        diff_hl = recent_h[i] - recent_l[i]
        fibo_buy = recent_h[i] - (diff_hl * 0.618) if diff_hl > 0 else 0
        fibo_sell = recent_l[i] + (diff_hl * 0.618) if diff_hl > 0 else 0

        # Outcome check
        exit_close = close[i+1]
        spread_pen = c_atr * 0.03
        is_buy_win = exit_close > (c_close + spread_pen)
        is_sell_win = exit_close < (c_close - spread_pen)

        # Base Signals
        sig_wt_buy = ((c_low <= c_kcl) or (p_low <= p_kcl)) and (c_wt1 < -45) and (p_wt1 < p_wt2 and c_wt1 > c_wt2) and (c_close > c_open)
        sig_wt_sell = ((c_high >= c_kcu) or (p_high >= p_kcu)) and (c_wt1 > 45) and (p_wt1 > p_wt2 and c_wt1 < c_wt2) and (c_close < c_open)

        sig_alpha_buy = ((c_low <= c_bbl) or (diff_hl > 0 and abs(c_low - fibo_buy)/c_close < 0.0015)) and (c_sk < 25 and p_sk < p_sd and c_sk > c_sd) and (c_close > c_open)
        sig_alpha_sell = ((c_high >= c_bbu) or (diff_hl > 0 and abs(c_high - fibo_sell)/c_close < 0.0015)) and (c_sk > 75 and p_sk > p_sd and c_sk < c_sd) and (c_close < c_open)

        sig_stoch_buy = (c_close > c_sma200) and (c_sk < 25 and p_sk < p_sd and c_sk > c_sd) and (c_close > c_open)
        sig_stoch_sell = (c_close < c_sma200) and (c_sk > 75 and p_sk > p_sd and c_sk < c_sd) and (c_close < c_open)

        sig_fibo_buy = (diff_hl > 0) and (abs(c_low - fibo_buy)/c_close < 0.0010) and (c_sk < 30) and (c_close > c_open)
        sig_fibo_sell = (diff_hl > 0) and (abs(c_high - fibo_sell)/c_close < 0.0010) and (c_sk > 70) and (c_close < c_open)

        for m in modes:
            pass_b = True
            pass_s = True
            if m == 'EMA_CONFLUENCE':
                pass_b = not (c_close < c_ema20 < c_ema50)
                pass_s = not (c_close > c_ema20 > c_ema50)
            elif m == 'SMA200_CONFLUENCE':
                pass_b = (c_close > c_sma200) or (c_rsi < 25)
                pass_s = (c_close < c_sma200) or (c_rsi > 75)
            elif m == 'MACD_MOMENTUM_EXHAUSTION':
                pass_b = c_mdiff > p_mdiff
                pass_s = c_mdiff < p_mdiff
            elif m == 'FULL_SHIELD':
                pass_b = (not (c_close < c_ema20 < c_ema50)) and (c_mdiff > p_mdiff)
                pass_s = (not (c_close > c_ema20 > c_ema50)) and (c_mdiff < p_mdiff)

            def record(strat, action, win):
                if strat not in res_modes[m]:
                    res_modes[m][strat] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
                res_modes[m][strat]['trades'] += 1
                if win:
                    res_modes[m][strat]['wins'] += 1
                    res_modes[m][strat]['pnl'] += payout
                else:
                    res_modes[m][strat]['losses'] += 1
                    res_modes[m][strat]['pnl'] -= 1.0

            if sig_wt_buy and pass_b: record('WaveTrend + Keltner Channel Reversion', 'BUY', is_buy_win)
            if sig_wt_sell and pass_s: record('WaveTrend + Keltner Channel Reversion', 'SELL', is_sell_win)

            if sig_alpha_buy and pass_b: record('Alpha Convergence (Bollinger + Fibo + Stoch)', 'BUY', is_buy_win)
            if sig_alpha_sell and pass_s: record('Alpha Convergence (Bollinger + Fibo + Stoch)', 'SELL', is_sell_win)

            if sig_stoch_buy: record('Estocástico + SMA200', 'BUY', is_buy_win)
            if sig_stoch_sell: record('Estocástico + SMA200', 'SELL', is_sell_win)

            if sig_fibo_buy and pass_b: record('Fibonacci Retracement 61.8%', 'BUY', is_buy_win)
            if sig_fibo_sell and pass_s: record('Fibonacci Retracement 61.8%', 'SELL', is_sell_win)

    return res_modes


def main():
    historical_dir = Path("historical_data")
    csv_files = sorted(list(historical_dir.glob("*.csv")))
    print(f"Executing fast matrix simulation across {len(csv_files)} datasets...")

    modes = ['NONE', 'EMA_CONFLUENCE', 'SMA200_CONFLUENCE', 'MACD_MOMENTUM_EXHAUSTION', 'FULL_SHIELD']
    mode_summaries = {m: {'total_trades': 0, 'total_wins': 0, 'total_losses': 0, 'net_pnl': 0.0, 'by_strategy': {}, 'by_pair_tf': {}} for m in modes}

    for f in csv_files:
        try:
            df_raw = pd.read_csv(f)
            if df_raw.empty or len(df_raw) < 250:
                continue
            cols = {c: c.capitalize() for c in df_raw.columns}
            df_raw.rename(columns=cols, inplace=True)
            if 'Time' in df_raw.columns: df_raw.rename(columns={'Time': 'Timestamp'}, inplace=True)
            for col in ['Open', 'High', 'Low', 'Close']:
                if col in df_raw.columns: df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')
            df_raw = df_raw.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
            df_calc = compute_all_indicators(df_raw)
            if len(df_calc) < 250:
                continue

            pair_tf_key = f.stem
            res_modes = simulate_dataset(df_calc)

            for m in modes:
                for strat, s_data in res_modes[m].items():
                    if s_data['trades'] == 0: continue
                    if strat not in mode_summaries[m]['by_strategy']:
                        mode_summaries[m]['by_strategy'][strat] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
                    mode_summaries[m]['by_strategy'][strat]['trades'] += s_data['trades']
                    mode_summaries[m]['by_strategy'][strat]['wins'] += s_data['wins']
                    mode_summaries[m]['by_strategy'][strat]['losses'] += s_data['losses']
                    mode_summaries[m]['by_strategy'][strat]['pnl'] += s_data['pnl']

                    if pair_tf_key not in mode_summaries[m]['by_pair_tf']:
                        mode_summaries[m]['by_pair_tf'][pair_tf_key] = {}
                    mode_summaries[m]['by_pair_tf'][pair_tf_key][strat] = s_data

                    mode_summaries[m]['total_trades'] += s_data['trades']
                    mode_summaries[m]['total_wins'] += s_data['wins']
                    mode_summaries[m]['total_losses'] += s_data['losses']
                    mode_summaries[m]['net_pnl'] += s_data['pnl']
        except Exception as e:
            print(f"Error in {f.name}: {e}")

    # --- PRINT COMPARISON ---
    print("\n" + "="*85)
    print("COMPARATIVE TREND SHIELD MODES MATRIX (49 HISTORICAL DATASETS)")
    print("="*85)
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

    print("\n" + "="*85)
    print(f"STRATEGY BREAKDOWN IN BEST MODE ({best_mode})")
    print("="*85)
    for strat, data in mode_summaries[best_mode]['by_strategy'].items():
        t = data['trades']
        w = data['wins']
        l = data['losses']
        wr = (w / t * 100) if t > 0 else 0.0
        pnl = data['pnl']
        pf = (w * 0.85) / l if l > 0 else 0.0
        print(f"• {strat:<45} | {t:>5} tr | {wr:>6.2f}% WR | ${pnl:>+8.2f} | PF: {pf:.2f}")

    top_combos = []
    for pair_tf, strats in mode_summaries[best_mode]['by_pair_tf'].items():
        for strat, data in strats.items():
            t = data['trades']
            w = data['wins']
            l = data['losses']
            wr = (w / t * 100) if t > 0 else 0.0
            pnl = data['pnl']
            pf = (w * 0.85) / l if l > 0 else 0.0

            if t >= 10 and wr >= 57.0 and pnl > 0:
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

    print("\n" + "="*85)
    print(f"TOP WINNING COMBINATIONS (WR >= 57%, Net Profit > 0, Min 10 Trades)")
    print("="*85)
    for c in top_combos:
        print(f"{c['pair_tf']:<24} | {c['strategy']:<42} | {c['trades']:>4} tr | {c['winrate']:>6.2f}% WR | ${c['pnl']:>+7.2f} | PF: {c['profit_factor']:.2f}")

    out_file = Path("fast_trend_shield_report.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({
            'best_mode': best_mode,
            'summary': mode_summaries,
            'top_combinations': top_combos
        }, f, indent=4)

    print(f"\n[OK] Results saved to {out_file}")

if __name__ == '__main__':
    main()
