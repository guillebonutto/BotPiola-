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

async def fetch_historical_candles(api, pair, interval, total_candles=5000):
    """
    Descarga velas históricas en múltiples chunks retroactivos para lograr un histórico largo.
    """
    print(f"  [API] Descargando {total_candles} velas históricas de {pair}...")
    all_candles = []
    
    try:
        # Primer chunk (más reciente)
        offset = interval * 300
        candles = await asyncio.wait_for(api.get_candles(pair, interval, offset), timeout=15.0)
        
        if not candles:
            print(f"  [WARN] No se recibieron velas iniciales de {pair}")
            return pd.DataFrame()
            
        all_candles.extend(candles)
        
        # Obtener clave de tiempo
        time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
        if not time_key:
            print(f"  [WARN] No se encontró clave de tiempo en los datos de {pair}")
            return pd.DataFrame()
            
        current_end_time = int(candles[0][time_key])
        
        # Descargar chunks adicionales (hacia atrás en el tiempo)
        # Cada get_candles_advanced típicamente descarga unas 200-300 velas
        chunks_needed = max(1, (total_candles - len(all_candles)) // 200)
        for chunk_idx in range(chunks_needed):
            await asyncio.sleep(0.5) # Pausa corta para evitar rate-limiting
            print(f"    - Descargando Chunk {chunk_idx + 2} terminando en {current_end_time}...")
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
    except Exception as e:
        print(f"  [ERR] Error descargando histórico de {pair}: {e}")
        return pd.DataFrame()

def run_backtest_routed(df, strategies, analyzer, pattern_recognizer):
    """
    Simula la ejecución del bot respetando el Router de Régimen de Mercado.
    """
    # 1. Calcular indicadores base
    df = analyzer.compute_indicators(df)
    
    trades = []
    wins = 0
    losses = 0
    
    # Empezamos en 200 para estabilidad de indicadores
    for i in range(200, len(df) - 1):
        sub_df = df.iloc[:i+1].copy()
        
        # 2. Calcular patrones en la ventana deslizante
        sub_df = pattern_recognizer.find_candlestick_patterns(sub_df)
        sub_df = pattern_recognizer.find_chart_patterns(sub_df)
        
        # 3. Determinar estado de mercado
        market_state = analyzer.determine_market_state(sub_df)
        
        # --- Router ---
        allowed_types = []
        if market_state in ['TRENDING_UP', 'TRENDING_DOWN']:
            allowed_types = ['TREND']
        elif market_state == 'NEUTRAL':
            allowed_types = ['REVERSION']
        else: # SIDEWAYS o VOLATILE
            allowed_types = []
            
        if not allowed_types:
            continue
            
        # Buscar señales de estrategias compatibles
        for strategy in strategies:
            strat_type = getattr(strategy, 'type', 'TREND')
            if strat_type not in allowed_types:
                continue
                
            action, reason, duration = strategy.get_signal(sub_df)
            if action in ['BUY', 'SELL']:
                current_candle = df.iloc[i]
                next_candle = df.iloc[i+1]
                
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
                    
                trades.append({
                    'time': current_candle['Timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                    'strategy': strategy.name,
                    'action': action,
                    'result': 'WIN' if is_win else 'LOSS',
                    'reason': reason
                })
                break # Romper loop de estrategias para evitar multiples señales en la misma vela
                
    total = len(trades)
    wr = (wins / total * 100) if total > 0 else 0.0
    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': wr,
        'details': trades
    }

async def main():
    print("====================================================")
    print("SIMULACION DE BACKTEST EN NUEVOS PARES CANDIDATOS (HISTORICO LARGO)")
    print("====================================================")
    
    if not Path('config.json').exists():
        print("[ERR] config.json no encontrado.")
        return
        
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    ssid = config.get('ssid')
    
    api = PocketOptionAsync(ssid)
    await asyncio.sleep(2)
    
    print("Conectando y obteniendo balance...")
    balance = await api.balance()
    if balance == -1.0:
        print("[ERR] SSID invalido.")
        return
    print(f"Conectado. Balance: ${balance:.2f}")
    
    analyzer = MarketAnalyzer()
    pattern_recognizer = PatternRecognizer()
    
    strategies = [
        StrategyStochastic(),
        StrategyFibonacci(),
        StrategyStructure(),
        StrategyExpertVision()
    ]
    
    candidate_pairs = [
        "EURUSD_otc",
        "GBPUSD_otc",
        "AUDUSD_otc",
        "USDCAD_otc",
        "AUDCAD_otc",
        "GBPJPY_otc",
        "USDCHF_otc",
        "NZDUSD_otc",
        "AUDJPY_otc"
    ]
    
    results_summary = []
    
    for pair in candidate_pairs:
        print(f"\nProcesando par: {pair}...")
        # Descargamos 5000 velas (aprox 17 dias de M5)
        df = await fetch_historical_candles(api, pair, 300, 5000)
        
        if df.empty or len(df) < 300:
            print(f"  [WARN] No se pudo obtener suficiente data para {pair}")
            continue
            
        print(f"  [OK] Cargadas {len(df)} velas. Ejecutando backtest con Router...")
        res = run_backtest_routed(df, strategies, analyzer, pattern_recognizer)
        
        results_summary.append({
            'pair': pair,
            'total_trades': res['total_trades'],
            'win_rate': res['win_rate'],
            'wins': res['wins'],
            'losses': res['losses']
        })
        
        print(f"  [RESULT] {pair}: {res['total_trades']} trades | WR: {res['win_rate']:.2f}% (Wins: {res['wins']} | Losses: {res['losses']})")
        if res['details']:
            print("    Muestra de operativas:")
            for t in res['details'][-3:]:
                print(f"      - [{t['time']}] {t['strategy']} -> {t['action']} | {t['result']} ({t['reason']})")
        
    print("\n====================================================")
    print("RESUMEN DE RESULTADOS EN NUEVOS PARES (HISTORICO LARGO):")
    print("====================================================")
    for r in results_summary:
        print(f"- {r['pair']}: {r['total_trades']} trades | WR: {r['win_rate']:.2f}% (W/L: {r['wins']}/{r['losses']})")
    print("====================================================")
    
    valid_results = [r for r in results_summary if r['total_trades'] >= 3]
    if valid_results:
        best = max(valid_results, key=lambda x: x['win_rate'])
        print(f"\nEl mejor par candidato es {best['pair']} con un Win Rate de {best['win_rate']:.2f}% en {best['total_trades']} trades simulados.")
        if best['win_rate'] >= 55.0:
            print(f"Se sugiere considerar añadir {best['pair']} a config.json en reemplazo de los pares con bajo rendimiento.")
        else:
            print("Aunque es el mejor, el win rate historico simulado en este periodo de prueba esta por debajo del 55%. Operar con precaucion.")
    else:
        print("\nNo hubo suficientes operaciones para dar una recomendacion concluyente.")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
