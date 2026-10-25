import os
import glob
from pathlib import Path
import pandas as pd
import numpy as np
import ta

def test_optimized_portfolio():
    historical_dir = Path("historical_data")
    
    # Target pairs and timeframes
    portfolio = {
        "NZDUSD_otc_900s.csv": 900,
        "GBPJPY_otc_900s.csv": 900,
        "AUDCAD_otc_900s.csv": 900,
        "USDCAD_otc_900s.csv": 900,
        "AUDJPY_otc_900s.csv": 900,
        "EURUSD_otc_900s.csv": 900,
        "#INTC_otc_900s.csv": 900,
        "#INTC_otc_300s.csv": 300,
        "#AAPL_otc_900s.csv": 900,
        "AUDUSD_otc_900s.csv": 900,
        "USDCHF_otc_900s.csv": 900
    }
    
    payout = 0.85
    total_trades = 0
    total_wins = 0
    total_losses = 0
    net_pnl = 0.0
    
    results = []
    
    for filename, tf in portfolio.items():
        fpath = historical_dir / filename
        if not fpath.exists():
            continue
            
        df = pd.read_csv(fpath)
        cols = {c: c.capitalize() for c in df.columns}
        df.rename(columns=cols, inplace=True)
        for c in ['Open', 'High', 'Low', 'Close']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
        
        # Calculate Indicators
        close = df['Close']
        high = df['High']
        low = df['Low']
        open_p = df['Open']
        
        df['EMA_20'] = ta.trend.ema_indicator(close, window=20)
        df['EMA_50'] = ta.trend.ema_indicator(close, window=50)
        df['SMA_200'] = ta.trend.sma_indicator(close, window=200)
        df['ATR'] = ta.volatility.average_true_range(high, low, close, window=14)
        
        # Keltner
        kc_ema = ta.trend.ema_indicator(close, window=20)
        kc_atr = ta.volatility.average_true_range(high, low, close, window=10)
        df['KC_Upper'] = kc_ema + (1.8 * kc_atr)
        df['KC_Lower'] = kc_ema - (1.8 * kc_atr)
        
        # WaveTrend
        ap = (high + low + close) / 3.0
        esa = ta.trend.ema_indicator(ap, window=10)
        d = ta.trend.ema_indicator(abs(ap - esa), window=10)
        ci = (ap - esa) / (0.015 * d.replace(0, 0.00001))
        df['WT1'] = ta.trend.ema_indicator(ci, window=21)
        df['WT2'] = df['WT1'].rolling(window=4).mean()
        
        # MACD
        macd = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
        df['MACD_Diff'] = macd.macd_diff()
        
        df = df.dropna().reset_index(drop=True)
        
        p_wins = 0
        p_losses = 0
        p_pnl = 0.0
        
        for i in range(50, len(df) - 1):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            exit_bar = df.iloc[i+1]
            
            c_close = curr['Close']
            c_open = curr['Open']
            c_high = curr['High']
            c_low = curr['Low']
            p_low = prev['Low']
            p_high = prev['High']
            
            c_ema20 = curr['EMA_20']
            c_ema50 = curr['EMA_50']
            
            c_wt1 = curr['WT1']
            c_wt2 = curr['WT2']
            p_wt1 = prev['WT1']
            p_wt2 = prev['WT2']
            
            c_kcu = curr['KC_Upper']
            c_kcl = curr['KC_Lower']
            p_kcl = prev['KC_Lower']
            p_kcu = prev['KC_Upper']
            
            c_atr = curr['ATR']
            spread_penalty = c_atr * 0.03 # Real slippage model
            
            # Trend Shield Filters
            pass_buy_trend = not (c_close < c_ema20 < c_ema50) and (curr['MACD_Diff'] > prev['MACD_Diff'])
            pass_sell_trend = not (c_close > c_ema20 > c_ema50) and (curr['MACD_Diff'] < prev['MACD_Diff'])
            
            # WT Reversion Buy
            sig_buy = ((c_low <= c_kcl) or (p_low <= p_kcl)) and (c_wt1 < -45) and (p_wt1 < p_wt2 and c_wt1 > c_wt2) and (c_close > c_open) and pass_buy_trend
            # WT Reversion Sell
            sig_sell = ((c_high >= c_kcu) or (p_high >= p_kcu)) and (c_wt1 > 45) and (p_wt1 > p_wt2 and c_wt1 < c_wt2) and (c_close < c_open) and pass_sell_trend
            
            if sig_buy:
                is_win = exit_bar['Close'] > (c_close + spread_penalty)
                if is_win:
                    p_wins += 1
                    p_pnl += payout
                else:
                    p_losses += 1
                    p_pnl -= 1.0
            elif sig_sell:
                is_win = exit_bar['Close'] < (c_close - spread_penalty)
                if is_win:
                    p_wins += 1
                    p_pnl += payout
                else:
                    p_losses += 1
                    p_pnl -= 1.0
                    
        p_tot = p_wins + p_losses
        if p_tot > 0:
            p_wr = (p_wins / p_tot) * 100
            pf = (p_wins * payout) / p_losses if p_losses > 0 else 99.0
            results.append({
                'asset': filename.replace('.csv', ''),
                'tf': f"{tf}s ({tf//60}m)",
                'trades': p_tot,
                'wins': p_wins,
                'losses': p_losses,
                'winrate': p_wr,
                'pnl': p_pnl,
                'profit_factor': pf
            })
            total_trades += p_tot
            total_wins += p_wins
            total_losses += p_losses
            net_pnl += p_pnl

    print("="*85)
    print("FINAL OPTIMIZED PORTFOLIO BACKTEST (WITH TREND SHIELD & EXACT DURATION)")
    print("="*85)
    print(f"{'Asset / Pair':<24} | {'Timeframe':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Net P&L ($)':<12} | {'Profit Factor':<14}")
    print("-" * 88)
    for r in results:
        print(f"{r['asset']:<24} | {r['tf']:<10} | {r['trades']:<8} | {r['winrate']:<9.2f}% | ${r['pnl']:<11.2f} | {r['profit_factor']:<13.2f}")
    
    total_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    overall_pf = (total_wins * payout) / total_losses if total_losses > 0 else 0.0
    print("="*85)
    print(f"PORTFOLIO TOTALS: {total_trades} Trades | {total_wins} Wins / {total_losses} Losses | Win Rate: {total_wr:.2f}% | Net P&L: ${net_pnl:+.2f} USD | Profit Factor: {overall_pf:.2f}")
    print("="*85)

if __name__ == '__main__':
    test_optimized_portfolio()
