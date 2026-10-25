import asyncio
import pandas as pd
from datetime import datetime
from broker_alpaca import download_yahoo_candles
from analysis import MarketAnalyzer
from strategy_stochastic import StrategyStochastic
from strategy_fibonacci import StrategyFibonacci
from strategy_wavetrend_keltner import StrategyWaveTrendKeltner

async def run_crypto_backtest():
    print("=== INICIANDO BACKTEST TRADICIONAL CRYPTO ALPACA ===")
    
    pairs = ["BTCUSD", "ETHUSD", "SOLUSD"]
    intervals = [900, 3600, 14400] # 15m, 1h, 4h
    
    strategies = [
        StrategyStochastic(bypass_filter=True),
        StrategyWaveTrendKeltner(bypass_filter=True)
    ]
    
    analyzer = MarketAnalyzer()
    
    results = []

    for pair in pairs:
        for interval in intervals:
            print(f"\nDescargando datos para {pair} en {interval}s...")
            raw_candles = await download_yahoo_candles(pair, interval, lookback=2000)
            if not raw_candles:
                print(f"  [ERROR] Datos insuficientes para {pair} ({interval}s).")
                continue
                
            df = pd.DataFrame(raw_candles)
            if df.empty or len(df) < 300:
                print(f"  [ERROR] Datos insuficientes para {pair} ({interval}s). Velas: {len(df)}")
                continue
            
            df.columns = [c.lower() for c in df.columns]
            rename_map = {'time': 'Timestamp', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low'}
            df.rename(columns=rename_map, inplace=True)
            if 'timestamp' in df.columns:
                df['Timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            elif 'Timestamp' in df.columns:
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', utc=True)
                
            print(f"  ✅ Velas obtenidas: {len(df)}")
            df = analyzer.compute_indicators(df)
            
            # Simple MTF bias mock for testing speed
            if 'bias_1d' not in df.columns:
                df['bias_1d'] = 1
                df['bias_4h'] = 1
                
            for strategy in strategies:
                wins = 0
                losses = 0
                
                # Run through candles
                for i in range(300, len(df) - 1):
                    sub_df = df.iloc[:i+1].copy()
                    
                    action, reason, duration = strategy.get_signal(sub_df)
                    
                    if action in ['BUY', 'SELL']:
                        entry_price = df.iloc[i]['Close']
                        exit_price = df.iloc[i+1]['Close']
                        
                        is_win = False
                        if action == 'BUY' and exit_price > entry_price:
                            is_win = True
                        elif action == 'SELL' and exit_price < entry_price:
                            is_win = True
                            
                        if is_win:
                            wins += 1
                        else:
                            losses += 1
                            
                total_trades = wins + losses
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                
                print(f"  -> {strategy.name}: {total_trades} trades | WR: {win_rate:.1f}%")
                
                results.append({
                    'pair': pair,
                    'interval': interval,
                    'strategy': strategy.name,
                    'trades': total_trades,
                    'win_rate': win_rate
                })

    print("\n\n=== RESUMEN DE MEJORES CONFIGURACIONES ===")
    results.sort(key=lambda x: x['win_rate'], reverse=True)
    
    import json
    with open('crypto_backtest_results.json', 'w') as f:
        json.dump(results, f, indent=4)
        
    for r in results[:10]:
        if r['trades'] >= 3:
            print(f"{r['pair']} | {r['interval']}s | {r['strategy']} -> WR: {r['win_rate']:.1f}% ({r['trades']} trades)")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_crypto_backtest())
