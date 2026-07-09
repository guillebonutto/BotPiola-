import asyncio
import pandas as pd
import json
import sys
from pathlib import Path
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from patterns import PatternRecognizer
from strategy_stochastic import StrategyStochastic
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure
from strategy_expert_vision import StrategyExpertVision

async def fetch_historical_candles(api, pair, interval, total_candles=800):
    all_candles = []
    try:
        offset = interval * 300
        candles = await asyncio.wait_for(api.get_candles(pair, interval, offset), timeout=15.0)
        if not candles:
            return pd.DataFrame()
        all_candles.extend(candles)
        
        time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
        if not time_key:
            return pd.DataFrame()
            
        current_end_time = int(candles[0][time_key])
        chunks_needed = max(1, (total_candles - len(all_candles)) // 200)
        for chunk_idx in range(chunks_needed):
            await asyncio.sleep(0.3)
            chunk = await asyncio.wait_for(
                api.get_candles_advanced(pair, interval, offset, current_end_time),
                timeout=15.0
            )
            if not chunk:
                break
            all_candles = chunk + all_candles
            current_end_time = int(chunk[0][time_key])
            
        df = pd.DataFrame(all_candles)
        df.columns = [c.lower() for c in df.columns]
        rename_map = {'time': 'Timestamp', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low'}
        df.rename(columns=rename_map, inplace=True)
        
        for col in ['Open', 'High', 'Low', 'Close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
                
        if 'timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        elif 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', utc=True)
            
        df = df.drop_duplicates(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()

def run_strategy_backtest(df, strategy, analyzer, pattern_recognizer):
    df_calc = df.copy()
    df_calc = analyzer.compute_indicators(df_calc)
    
    trades = []
    wins = 0
    losses = 0
    
    for i in range(200, len(df_calc) - 1):
        sub_df = df_calc.iloc[:i+1].copy()
        sub_df = pattern_recognizer.find_candlestick_patterns(sub_df)
        sub_df = pattern_recognizer.find_chart_patterns(sub_df)
        
        action, reason, duration = strategy.get_signal(sub_df)
        if action in ['BUY', 'SELL']:
            current_candle = df_calc.iloc[i]
            next_candle = df_calc.iloc[i+1]
            entry_price = current_candle['Close']
            exit_price = next_candle['Close']
            
            is_win = False
            if action == 'BUY' and exit_price > entry_price:
                is_win = True
            elif action == 'SELL' and exit_price < entry_price:
                is_win = True
                
            if is_win:
                wins += 1
            else:
                losses += 1
            trades.append(is_win)
            
    total = len(trades)
    wr = (wins / total * 100) if total > 0 else 0.0
    return total, wins, losses, wr

async def main():
    print("====================================================")
    print("MATRIX BACKTEST: EVALUACION PAR-ESTRATEGIA")
    print("====================================================")
    
    if not Path('config.json').exists():
        print("[ERR] config.json no encontrado.")
        return
        
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    ssid = config.get('ssid')
    pairs = config.get('trading', {}).get('pairs', [])
    
    if not pairs:
        print("[ERR] No hay pares configurados en config.json.")
        return
        
    api = PocketOptionAsync(ssid)
    await asyncio.sleep(2)
    
    print("Conectando y obteniendo balance...")
    balance = await api.balance()
    if balance == -1.0:
        print("[ERR] SSID invalido.")
        return
    print(f"Conectado. Balance: ${balance:.2f}\n")
    
    analyzer = MarketAnalyzer()
    pattern_recognizer = PatternRecognizer()
    
    strategies = [
        StrategyStochastic(),
        StrategyFibonacci(),
        StrategyStructure(),
        StrategyExpertVision()
    ]
    
    records = []
    
    for pair in pairs:
        print(f"Descargando datos históricos para {pair}...")
        df = await fetch_historical_candles(api, pair, 300, 800)
        
        if df.empty or len(df) < 220:
            print(f"  [WARN] No se pudo obtener datos para {pair}")
            continue
            
        print(f"  [OK] Velas cargadas: {len(df)}. Simulando estrategias...")
        
        for strategy in strategies:
            total, wins, losses, wr = run_strategy_backtest(df, strategy, analyzer, pattern_recognizer)
            records.append({
                'pair': pair,
                'strategy': strategy.name.split(' (')[0],
                'trades': total,
                'wins': wins,
                'losses': losses,
                'win_rate': wr
            })
            print(f"    * {strategy.name.split(' (')[0]}: {total} trades | WR: {wr:.2f}%")
        print()
        
    # Mostrar matriz comparativa en formato tabla ASCII
    print("=========================================================================")
    print(f"{'PAR':<15} | {'ESTRATEGIA':<25} | {'TRADES':<6} | {'W/L':<8} | {'WIN RATE':<10}")
    print("=========================================================================")
    for r in sorted(records, key=lambda x: x['win_rate'], reverse=True):
        wl_str = f"{r['wins']}/{r['losses']}"
        wr_str = f"{r['win_rate']:.2f}%"
        print(f"{r['pair']:<15} | {r['strategy']:<25} | {r['trades']:<6} | {wl_str:<8} | {wr_str:<10}")
    print("=========================================================================")
    
    print("\nRecomendacion Matricial:")
    print("  1. Mejores Combinaciones (WR >= 55% y al menos 2 trades):")
    good_combos = [r for r in records if r['win_rate'] >= 55.0 and r['trades'] >= 2]
    if good_combos:
        for c in sorted(good_combos, key=lambda x: x['win_rate'], reverse=True):
            print(f"     * {c['pair']} + {c['strategy']} (WR: {c['win_rate']:.2f}% en {c['trades']} trades)")
    else:
        print("     * Ninguna combinacion supero el 55% WR con volumen suficiente en este periodo.")
        
    print("  2. Peores Combinaciones (WR < 50% y al menos 2 trades) -> Sugeridas para filtrar:")
    bad_combos = [r for r in records if r['win_rate'] < 50.0 and r['trades'] >= 2]
    if bad_combos:
        for c in sorted(bad_combos, key=lambda x: x['win_rate']):
            print(f"     * {c['pair']} + {c['strategy']} (WR: {c['win_rate']:.2f}% en {c['trades']} trades)")
    else:
        print("     * Ninguna combinacion por debajo de 50% con volumen suficiente.")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
