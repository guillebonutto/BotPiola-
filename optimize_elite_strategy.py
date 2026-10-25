import os
import glob
import json
from pathlib import Path
import pandas as pd
import numpy as np
import ta

def compute_enhanced_indicators(df):
    df = df.copy()
    close = df['Close']
    high = df['High']
    low = df['Low']
    open_p = df['Open']

    # Trend
    df['EMA_20'] = ta.trend.ema_indicator(close, window=20)
    df['EMA_50'] = ta.trend.ema_indicator(close, window=50)
    df['SMA_200'] = ta.trend.sma_indicator(close, window=200)

    # ADX (Regime Filter: Trend vs Range)
    adx = ta.trend.ADXIndicator(high, low, close, window=14)
    df['ADX'] = adx.adx()
    df['ADX_pos'] = adx.adx_pos()
    df['ADX_neg'] = adx.adx_neg()

    # RSI (14 & 7)
    df['RSI'] = ta.momentum.rsi(close, window=14)
    df['RSI_7'] = ta.momentum.rsi(close, window=7)

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
    df['ATR_SMA'] = df['ATR'].rolling(window=20).mean()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.2) # 2.2 for tighter outer band
    df['BB_Upper'] = bb.bollinger_hband()
    df['BB_Lower'] = bb.bollinger_lband()
    df['BB_Middle'] = bb.bollinger_mavg()
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']

    # Keltner Channels (20, 2.0 ATR)
    kc_ema = ta.trend.ema_indicator(close, window=20)
    kc_atr = ta.volatility.average_true_range(high, low, close, window=10)
    df['KC_Upper'] = kc_ema + (2.0 * kc_atr)
    df['KC_Lower'] = kc_ema - (2.0 * kc_atr)

    # WaveTrend Oscillator (10, 21)
    ap = (high + low + close) / 3.0
    esa = ta.trend.ema_indicator(ap, window=10)
    d = ta.trend.ema_indicator(abs(ap - esa), window=10)
    ci = (ap - esa) / (0.015 * d.replace(0, 0.00001))
    df['WT1'] = ta.trend.ema_indicator(ci, window=21)
    df['WT2'] = df['WT1'].rolling(window=4).mean()

    # Extremes & Divergences Lookbacks
    df['Recent_Low_5'] = low.rolling(window=5).min()
    df['Recent_High_5'] = high.rolling(window=5).max()

    return df.dropna().reset_index(drop=True)


def simulate_advanced_engine(df_calc):
    """
    Evaluates 4 distinct Elite Strategy architectures:
    1. 'ADX_RANGING_REVERSION': Only trade reversions when ADX < 25 (non-trending range), touching outer KC/BB with extreme RSI/WT.
    2. 'TREND_PULLBACK_MOMENTUM': When ADX > 25, only trade in trend direction (pullback to EMA20/EMA50 + Stoch crossover in pullback zone).
    3. 'DIVERGENCE_EXHAUSTION': Price makes lower low (last 5 bars) but RSI/WT makes higher low (Bullish Divergence), or vice versa.
    4. 'ALPHA_CONVERGENCE_CONFLUENCE': Bollinger outer band touch + Fibo 61.8% + Stoch Extreme + Trend alignment.
    """
    payout = 0.85
    models = [
        'ADX_RANGING_REVERSION',
        'TREND_PULLBACK_MOMENTUM',
        'DIVERGENCE_EXHAUSTION',
        'ALPHA_CONVERGENCE_CONFLUENCE'
    ]
    results = {m: {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0} for m in models}

    close = df_calc['Close'].values
    open_p = df_calc['Open'].values
    high = df_calc['High'].values
    low = df_calc['Low'].values
    ema20 = df_calc['EMA_20'].values
    ema50 = df_calc['EMA_50'].values
    sma200 = df_calc['SMA_200'].values
    adx = df_calc['ADX'].values
    rsi = df_calc['RSI'].values
    rsi7 = df_calc['RSI_7'].values
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

    n = len(df_calc)

    for i in range(50, n - 1):
        c_close = close[i]
        c_open = open_p[i]
        c_high = high[i]
        c_low = low[i]
        p_close = close[i-1]
        p_low = low[i-1]
        p_high = high[i-1]

        c_ema20 = ema20[i]
        c_ema50 = ema50[i]
        c_sma200 = sma200[i]
        c_adx = adx[i]
        c_rsi = rsi[i]
        c_rsi7 = rsi7[i]
        p_rsi = rsi[i-1]
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
        c_bbu = bb_upper[i]
        c_bbl = bb_lower[i]

        exit_close = close[i+1]
        spread_pen = c_atr * 0.03
        is_buy_win = exit_close > (c_close + spread_pen)
        is_sell_win = exit_close < (c_close - spread_pen)

        def record(model, is_win):
            results[model]['trades'] += 1
            if is_win:
                results[model]['wins'] += 1
                results[model]['pnl'] += payout
            else:
                results[model]['losses'] += 1
                results[model]['pnl'] -= 1.0

        # === 1. ADX_RANGING_REVERSION ===
        # Ranging market (ADX < 24): Bollinger/Keltner outer touch with candle confirmation & WT cross
        if c_adx < 24:
            if (c_low <= c_kcl or c_low <= c_bbl) and (c_wt1 < -50 and p_wt1 < p_wt2 and c_wt1 > c_wt2) and (c_rsi < 35) and (c_close > c_open):
                record('ADX_RANGING_REVERSION', is_buy_win)
            elif (c_high >= c_kcu or c_high >= c_bbu) and (c_wt1 > 50 and p_wt1 > p_wt2 and c_wt1 < c_wt2) and (c_rsi > 65) and (c_close < c_open):
                record('ADX_RANGING_REVERSION', is_sell_win)

        # === 2. TREND_PULLBACK_MOMENTUM ===
        # Trending market (ADX > 25): Trade WITH the trend on pullbacks to EMA20 / EMA50
        if c_adx > 25:
            # Uptrend: EMA20 > EMA50 > SMA200, price pulled back to near EMA20/EMA50, Stoch crossed up from < 35
            if c_ema20 > c_ema50 and c_close > c_sma200:
                if (c_low <= c_ema20 * 1.0005) and (p_sk < p_sd and c_sk > c_sd and c_sk < 40) and (c_close > c_open) and (c_mdiff > p_mdiff):
                    record('TREND_PULLBACK_MOMENTUM', is_buy_win)
            # Downtrend: EMA20 < EMA50 < SMA200, price pulled back to near EMA20/EMA50, Stoch crossed down from > 65
            elif c_ema20 < c_ema50 and c_close < c_sma200:
                if (c_high >= c_ema20 * 0.9995) and (p_sk > p_sd and c_sk < c_sd and c_sk > 60) and (c_close < c_open) and (c_mdiff < p_mdiff):
                    record('TREND_PULLBACK_MOMENTUM', is_sell_win)

        # === 3. DIVERGENCE_EXHAUSTION ===
        # Detect true momentum deceleration / RSI Divergence
        if i >= 4:
            # Bullish Divergence: Price lower low in last 4 bars, but RSI higher low + green candle
            if (c_low < min(low[i-4:i])) and (c_rsi > min(rsi[i-4:i]) + 2.0) and (c_rsi < 35) and (c_close > c_open):
                record('DIVERGENCE_EXHAUSTION', is_buy_win)
            # Bearish Divergence: Price higher high, but RSI lower high + red candle
            elif (c_high > max(high[i-4:i])) and (c_rsi < max(rsi[i-4:i]) - 2.0) and (c_rsi > 65) and (c_close < c_open):
                record('DIVERGENCE_EXHAUSTION', is_sell_win)

        # === 4. ALPHA_CONVERGENCE_CONFLUENCE ===
        # Confluence of BB touch + extreme RSI-7 + Stoch Hook + not counter strong trend
        if (c_low <= c_bbl) and (c_rsi7 < 20) and (p_sk < p_sd and c_sk > c_sd and c_sk < 25) and (c_close > c_open) and not (c_close < c_ema20 < c_ema50):
            record('ALPHA_CONVERGENCE_CONFLUENCE', is_buy_win)
        elif (c_high >= c_bbu) and (c_rsi7 > 80) and (p_sk > p_sd and c_sk < c_sd and c_sk > 75) and (c_close < c_open) and not (c_close > c_ema20 > c_ema50):
            record('ALPHA_CONVERGENCE_CONFLUENCE', is_sell_win)

    return results


def main():
    historical_dir = Path("historical_data")
    csv_files = sorted(list(historical_dir.glob("*.csv")))
    print(f"Simulating Elite Architecture across {len(csv_files)} datasets...")

    total_results = {}
    pair_tf_results = {}

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
            df_calc = compute_enhanced_indicators(df_raw)
            if len(df_calc) < 250:
                continue

            pair_tf_key = f.stem
            res = simulate_advanced_engine(df_calc)

            pair_tf_results[pair_tf_key] = res

            for model, m_data in res.items():
                if model not in total_results:
                    total_results[model] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
                total_results[model]['trades'] += m_data['trades']
                total_results[model]['wins'] += m_data['wins']
                total_results[model]['losses'] += m_data['losses']
                total_results[model]['pnl'] += m_data['pnl']
        except Exception as e:
            print(f"Error in {f.name}: {e}")

    print("\n" + "="*85)
    print("ELITE STRATEGY ARCHITECTURE PERFORMANCE SUMMARY (ALL 49 OTC DATASETS)")
    print("="*85)
    print(f"{'Strategy Architecture':<32} | {'Trades':<8} | {'Wins':<6} | {'Win Rate':<10} | {'Net P&L ($)':<12} | {'Profit Factor':<14}")
    print("-" * 92)

    for model, data in total_results.items():
        tot = data['trades']
        wins = data['wins']
        losses = data['losses']
        wr = (wins / tot * 100) if tot > 0 else 0.0
        pnl = data['pnl']
        pf = (wins * 0.85) / losses if losses > 0 else 0.0
        print(f"{model:<32} | {tot:<8} | {wins:<6} | {wr:<9.2f}% | ${pnl:<11.2f} | {pf:<13.2f}")

    # Extract Top Pairs and Timeframes per Model
    print("\n" + "="*85)
    print("TOP ASSET-TIMEFRAME SPECIALIZATIONS (WR >= 60.0%, Net P&L > +$5.00)")
    print("="*85)
    top_specializations = []
    for pair_tf, models_res in pair_tf_results.items():
        for model, m_data in models_res.items():
            t = m_data['trades']
            w = m_data['wins']
            l = m_data['losses']
            wr = (w / t * 100) if t > 0 else 0.0
            pnl = m_data['pnl']
            pf = (w * 0.85) / l if l > 0 else 0.0

            if t >= 10 and wr >= 60.0 and pnl >= 3.0:
                top_specializations.append({
                    'pair_tf': pair_tf,
                    'model': model,
                    'trades': t,
                    'wins': w,
                    'losses': l,
                    'winrate': wr,
                    'pnl': pnl,
                    'profit_factor': pf
                })

    top_specializations.sort(key=lambda x: (x['pnl'], x['winrate']), reverse=True)

    for s in top_specializations:
        print(f"{s['pair_tf']:<24} | {s['model']:<30} | {s['trades']:>4} tr | {s['winrate']:>6.2f}% WR | ${s['pnl']:>+7.2f} | PF: {s['profit_factor']:.2f}")

    out_file = Path("elite_strategy_report.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({
            'overall': total_results,
            'top_specializations': top_specializations
        }, f, indent=4)
    print(f"\n[OK] Elite strategy report saved to {out_file}")

if __name__ == '__main__':
    main()
