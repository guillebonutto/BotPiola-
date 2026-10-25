import glob
from pathlib import Path
import pandas as pd
import numpy as np
import ta

def run_fast_portfolio():
    files = sorted(list(Path('historical_data').glob('*900s.csv')) + list(Path('historical_data').glob('*300s.csv')))
    payout = 0.85
    results = []

    for fpath in files:
        df = pd.read_csv(fpath)
        cols = {c: c.capitalize() for c in df.columns}
        df.rename(columns=cols, inplace=True)
        for c in ['Open', 'High', 'Low', 'Close']:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
        if len(df) < 250: continue

        close = df['Close'].values
        open_p = df['Open'].values
        high = df['High'].values
        low = df['Low'].values

        ema20 = ta.trend.ema_indicator(df['Close'], window=20).values
        ema50 = ta.trend.ema_indicator(df['Close'], window=50).values
        sma200 = ta.trend.sma_indicator(df['Close'], window=200).values
        atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14).values

        kc_ema = ema20
        kc_atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=10).values
        kc_upper = kc_ema + (1.8 * kc_atr)
        kc_lower = kc_ema - (1.8 * kc_atr)

        ap = (high + low + close) / 3.0
        esa = ta.trend.ema_indicator(pd.Series(ap), window=10).values
        d = ta.trend.ema_indicator(pd.Series(abs(ap - esa)), window=10).values
        d[d == 0] = 0.00001
        ci = (ap - esa) / (0.015 * d)
        wt1 = ta.trend.ema_indicator(pd.Series(ci), window=21).values
        wt2 = pd.Series(wt1).rolling(window=4).mean().values

        n = len(df)
        wins = 0
        losses = 0

        for i in range(200, n - 1):
            if np.isnan(wt2[i]) or np.isnan(sma200[i]): continue
            c_close = close[i]
            c_open = open_p[i]
            c_high = high[i]
            c_low = low[i]
            p_low = low[i-1]
            p_high = high[i-1]

            c_wt1 = wt1[i]
            c_wt2 = wt2[i]
            p_wt1 = wt1[i-1]
            p_wt2 = wt2[i-1]

            c_kcu = kc_upper[i]
            c_kcl = kc_lower[i]
            p_kcl = kc_lower[i-1]
            p_kcu = kc_upper[i-1]

            c_ema20 = ema20[i]
            c_ema50 = ema50[i]

            # Signal
            sig_buy = ((c_low <= c_kcl) or (p_low <= p_kcl)) and (c_wt1 < -45) and (p_wt1 < p_wt2 and c_wt1 > c_wt2) and (c_close > c_open)
            sig_sell = ((c_high >= c_kcu) or (p_high >= p_kcu)) and (c_wt1 > 45) and (p_wt1 > p_wt2 and c_wt1 < c_wt2) and (c_close < c_open)

            # Trend Confluence Shield (Don't trade against strong bear/bull momentum)
            pass_buy = not (c_close < c_ema20 < c_ema50)
            pass_sell = not (c_close > c_ema20 > c_ema50)

            exit_close = close[i+1]
            spread_pen = atr[i] * 0.03

            if sig_buy and pass_buy:
                if exit_close > (c_close + spread_pen): wins += 1
                else: losses += 1
            elif sig_sell and pass_sell:
                if exit_close < (c_close - spread_pen): wins += 1
                else: losses += 1

        tot = wins + losses
        if tot >= 10:
            wr = wins / tot * 100
            pnl = (wins * payout) - (losses * 1.0)
            pf = (wins * payout) / losses if losses > 0 else 99.0
            results.append({
                'pair_tf': fpath.stem,
                'trades': tot,
                'wins': wins,
                'losses': losses,
                'winrate': wr,
                'pnl': pnl,
                'pf': pf
            })

    results.sort(key=lambda x: (x['pnl'], x['winrate']), reverse=True)

    print("\n" + "="*85)
    print("ALL 10,000 CANDLE HISTORICAL DATASETS - COMPLETE BENCHMARK")
    print("="*85)
    print(f"{'Asset / Timeframe':<24} | {'Trades':<8} | {'Win Rate':<10} | {'Net P&L ($)':<12} | {'Profit Factor':<14}")
    print("-" * 88)
    
    tot_w = sum(r['wins'] for r in results)
    tot_l = sum(r['losses'] for r in results)
    tot_pnl = sum(r['pnl'] for r in results)

    for r in results:
        print(f"{r['pair_tf']:<24} | {r['trades']:<8} | {r['winrate']:<9.2f}% | ${r['pnl']:<11.2f} | {r['pf']:<13.2f}")

    print("="*85)
    print(f"BENCHMARK TOTAL: {tot_w+tot_l} Trades | {tot_w}W / {tot_l}L | WR: {(tot_w/(tot_w+tot_l)*100):.2f}% | Net P&L: ${tot_pnl:+.2f} USD")

    # Filter for Whitelist
    whitelist = [r for r in results if r['winrate'] >= 54.5 and r['pnl'] > 0]
    print("\n" + "="*85)
    print(f"WINNING WHITELIST (WR >= 54.5%, Positive Net P&L): {len(whitelist)} Pairs")
    print("="*85)
    w_trades = sum(r['trades'] for r in whitelist)
    w_wins = sum(r['wins'] for r in whitelist)
    w_losses = sum(r['losses'] for r in whitelist)
    w_pnl = sum(r['pnl'] for r in whitelist)
    w_pf = (w_wins * payout) / w_losses if w_losses > 0 else 0

    for r in whitelist:
        print(f"⭐ {r['pair_tf']:<22} | {r['trades']:>4} tr | {r['winrate']:>6.2f}% WR | ${r['pnl']:>+7.2f} | PF: {r['pf']:.2f}")

    print("-" * 88)
    print(f"WHITELIST TOTAL: {w_trades} Trades | {w_wins}W / {w_losses}L | WR: {(w_wins/w_trades*100):.2f}% | Net P&L: ${w_pnl:+.2f} USD | PF: {w_pf:.2f}")
    print("="*85)

if __name__ == '__main__':
    run_fast_portfolio()
