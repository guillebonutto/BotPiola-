import asyncio
import pandas as pd
import json
import sys
from pathlib import Path
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from patterns import PatternRecognizer
from strategy_stochastic import StrategyStochastic
from strategy_continuation import StrategyContinuation
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure

async def fetch_historical_candles(api, pair, interval, count):
    """Obtiene velas históricas usando el mismo mecanismo con timeout del bot."""
    offset = interval * count
    try:
        print(f"  [API] Descargando {count} velas de {pair} (offset={offset}s)...")
        # Timeout de 15 segundos para evitar bloqueos
        candles = await asyncio.wait_for(api.get_candles(pair, interval, offset), timeout=15.0)
        
        # Fallback si retorna una lista vacía con el offset grande
        if not candles and count > 300:
            print(f"  [WARN] Offset de {count} muy grande. Intentando fallback con 300 velas...")
            offset = interval * 300
            candles = await asyncio.wait_for(api.get_candles(pair, interval, offset), timeout=15.0)
            
        if not candles:
            print("  [ERROR] No se recibieron velas del API.")
            return pd.DataFrame()
            
        # Replicar el Chunk 2 si es necesario para tener más datos (como hace el bot)
        time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
        if time_key and len(candles) < 200:
            try:
                oldest_time = int(candles[0][time_key])
                print(f"  [API] Descargando Chunk 2 ending at {oldest_time}...")
                chunk2 = await asyncio.wait_for(
                    api.get_candles_advanced(pair, interval, offset, oldest_time), 
                    timeout=15.0
                )
                candles = chunk2 + candles
            except Exception as chunk_e:
                print(f"  [WARN] Error descargando chunk 2: {chunk_e}")

        df = pd.DataFrame(candles)
        df.columns = [c.lower() for c in df.columns]
        rename_map = {'time': 'Timestamp', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low'}
        df.rename(columns=rename_map, inplace=True)
        
        required = ['Open', 'High', 'Low', 'Close']
        for col in required:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
        
        # Eliminar duplicados y ordenar por tiempo
        if 'timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        elif 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', utc=True)
            
        df = df.drop_duplicates(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)
        return df
    except asyncio.TimeoutError:
        print("  [TIMEOUT] PocketOption no respondió a tiempo.")
        return pd.DataFrame()
    except Exception as e:
        print(f"  [ERROR] Excepción descargando datos: {e}")
        return pd.DataFrame()

def run_backtest(df, strategy, analyzer, pattern_recognizer):
    """Simula operaciones en el histórico de velas."""
    df = analyzer.compute_indicators(df)
    
    trades = []
    wins = 0
    losses = 0
    
    # Empezamos desde la vela 200 para que SMA_200 y otros indicadores estén estables
    for i in range(200, len(df) - 1):
        # Tomar la porción del dataframe hasta el índice i (inclusive)
        sub_df = df.iloc[:i+1].copy()
        
        # Reconocer patrones en la ventana temporal actual (como hace el bot real)
        sub_df = pattern_recognizer.find_candlestick_patterns(sub_df)
        sub_df = pattern_recognizer.find_chart_patterns(sub_df)
        
        # Consultar la estrategia
        action, reason, duration = strategy.get_signal(sub_df)
        
        if action in ['BUY', 'SELL']:
            current_candle = df.iloc[i]
            next_candle = df.iloc[i+1] # La vela de resultado (M5)
            
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
                'time': current_candle['Timestamp'].strftime("%H:%M:%S"),
                'action': action,
                'entry': entry_price,
                'exit': exit_price,
                'result': 'WIN' if is_win else 'LOSS',
                'reason': reason
            })
            
            # Imprimir velas circundantes para analizar la acción del precio
            print(f"\n--- DETALLE DE OPERACIÓN SIMULADA [{action}] a las {current_candle['Timestamp'].strftime('%H:%M:%S')} ({'WIN' if is_win else 'LOSS'}) ---")
            print(f"Razón: {reason}")
            start_print = max(0, i - 3)
            end_print = min(len(df) - 1, i + 3)
            print(f"{'Hora':<10} | {'Open':<8} | {'High':<8} | {'Low':<8} | {'Close':<8} | {'Stoch_K':<8} | {'RSI':<8}")
            print("-" * 70)
            for idx in range(start_print, end_print + 1):
                c = df.iloc[idx]
                prefix = "=> " if idx == i else "   "
                print(f"{prefix}{c['Timestamp'].strftime('%H:%M:%S'):<7} | {c['Open']:<8.5f} | {c['High']:<8.5f} | {c['Low']:<8.5f} | {c['Close']:<8.5f} | {c.get('Stoch_K', 0.0):<8.2f} | {c.get('RSI', 0.0):<8.2f}")
            print("-" * 70)
            
    total_trades = len(trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    
    return {
        'strategy': strategy.name,
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'trades': trades
    }

async def main():
    print("=== INICIANDO SIMULADOR DE BACKTESTING ===")
    
    # Cargar configuración
    if not Path('config.json').exists():
        print("❌ Archivo config.json no encontrado.")
        return
        
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    ssid = config.get('ssid')
    trading_config = config.get('trading', {})
    pairs = trading_config.get('pairs', ['EURUSD_otc'])
    interval = trading_config.get('interval', 300)
    
    api = PocketOptionAsync(ssid)
    
    # Esperar a que la conexión WebSocket se establezca
    await asyncio.sleep(3)
    
    # Verificar conexión primero obteniendo balance
    print("🔑 Verificando SSID y obteniendo balance...")
    try:
        balance = await asyncio.wait_for(api.balance(), timeout=10.0)
        if balance == -1.0:
            print("❌ SSID Expirado o Inválido. Por favor actualiza config.json.")
            return
        print(f"✅ Conexión Exitosa. Balance de cuenta: ${balance:.2f}")
    except Exception as conn_e:
        print(f"❌ Error conectando a PocketOption: {conn_e}")
        return

    analyzer = MarketAnalyzer()
    pattern_recognizer = PatternRecognizer()
    
    strategies = [
        StrategyStochastic(),
        StrategyContinuation(),
        StrategyFibonacci(),
        StrategyStructure()
    ]
    
    # Usar el primer par disponible
    target_pair = pairs[0]
    
    # Descargar 400 velas (adecuado para backtest estable y rápido)
    df = await fetch_historical_candles(api, target_pair, interval, 400)
    if df.empty or len(df) < 210:
        print(f"❌ No se pudieron obtener suficientes datos para {target_pair} (mínimo 210 velas).")
        return
        
    print(f"✅ Velas cargadas para backtest: {len(df)}")
    
    for strategy in strategies:
        print(f"\nSimulando estrategia: {strategy.name}...")
        results = run_backtest(df, strategy, analyzer, pattern_recognizer)
        print(f"📊 RESULTADO:")
        print(f"   - Operaciones Totales: {results['total_trades']}")
        print(f"   - Ganadas (Wins): {results['wins']}")
        print(f"   - Perdidas (Losses): {results['losses']}")
        print(f"   - Win Rate: {results['win_rate']:.2f}%")
        
        if results['trades']:
            print("   - Últimas operaciones simuladas:")
            for t in results['trades'][-5:]:
                print(f"     [{t['time']}] {t['action']} @ {t['entry']:.5f} -> {t['exit']:.5f} | {t['result']} ({t['reason']})")
        else:
            print("   - Sin operaciones detectadas.")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
