import asyncio
import pandas as pd
import numpy as np
import json
import sys
import os
import ta
from pathlib import Path
from datetime import datetime, timezone
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from analysis import MarketAnalyzer
from strategy_stochastic import StrategyStochastic
from strategy_fibonacci import StrategyFibonacci
from strategy_structure import StrategyStructure
from strategy_expert_vision import StrategyExpertVision
from strategy_alpha_convergence import StrategyAlphaConvergence
from strategy_wavetrend_keltner import StrategyWaveTrendKeltner


# Redefinir detector rápido de patrones sin lookahead bias
def precompute_candlestick_patterns(df):
    df = df.copy()
    df['Body'] = abs(df['Close'] - df['Open'])
    df['UpperShadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['LowerShadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['TotalRange'] = df['High'] - df['Low']
    df['TotalRange'] = df['TotalRange'].replace(0, 0.00001)
    
    df['CDL_DOJI'] = np.where(df['Body'] <= df['TotalRange'] * 0.1, 100, 0)
    
    is_hammer = (df['Body'] <= df['TotalRange'] * 0.3) & (df['LowerShadow'] >= df['Body'] * 2) & (df['UpperShadow'] <= df['Body'] * 0.5)
    df['CDL_HAMMER'] = np.where(is_hammer, 100, 0)
    
    is_shooting_star = (df['Body'] <= df['TotalRange'] * 0.3) & (df['UpperShadow'] >= df['Body'] * 2) & (df['LowerShadow'] <= df['Body'] * 0.5)
    df['CDL_SHOOTINGSTAR'] = np.where(is_shooting_star, -100, 0)
    
    prev_open = df['Open'].shift(1)
    prev_close = df['Close'].shift(1)
    prev_body = abs(prev_close - prev_open)
    
    is_bull_engul = (prev_close < prev_open) & (df['Close'] > df['Open']) & (df['Close'] > prev_open) & (df['Open'] < prev_close)
    is_bear_engul = (prev_close > prev_open) & (df['Close'] < df['Open']) & (df['Close'] < prev_open) & (df['Open'] > prev_close)
    
    df['CDL_ENGULFING'] = 0
    df.loc[is_bull_engul, 'CDL_ENGULFING'] = 100
    df.loc[is_bear_engul, 'CDL_ENGULFING'] = -100
    
    p2_open = df['Open'].shift(2)
    p2_close = df['Close'].shift(2)
    p2_body = abs(p2_close - p2_open)
    
    c1_long_red = (p2_close < p2_open) & (p2_body > df['TotalRange'].shift(2) * 0.5)
    c2_small = (prev_body < p2_body * 0.5)
    c3_long_green = (df['Close'] > df['Open']) & (df['Close'] > (p2_open + p2_close)/2)
    df['CDL_MORNINGSTAR'] = np.where(c1_long_red & c2_small & c3_long_green, 100, 0)
    
    c1_long_green = (p2_close > p2_open) & (p2_body > df['TotalRange'].shift(2) * 0.5)
    c3_long_red = (df['Close'] < df['Open']) & (df['Close'] < (p2_open + p2_close)/2)
    df['CDL_EVENINGSTAR'] = np.where(c1_long_green & c2_small & c3_long_red, -100, 0)
    
    df.drop(columns=['Body', 'UpperShadow', 'LowerShadow', 'TotalRange'], inplace=True)
    return df

def precompute_chart_patterns(df, lookback=60):
    df = df.copy()
    df['Pattern_DoubleTop'] = 0
    df['Pattern_DoubleTop_Neck'] = np.nan
    df['Pattern_DoubleBottom'] = 0
    df['Pattern_DoubleBottom_Neck'] = np.nan
    df['Pattern_Triangle'] = 0
    
    window = 11
    half_window = 5
    max_in_window = df['High'].rolling(window).max()
    min_in_window = df['Low'].rolling(window).min()
    
    df['max_local'] = (df['High'].shift(half_window) == max_in_window)
    df['min_local'] = (df['Low'].shift(half_window) == min_in_window)
    
    # Ejecutamos la búsqueda de forma secuencial ultra-rápida usando los booleanos precalculados
    max_local_arr = df['max_local'].values
    min_local_arr = df['min_local'].values
    high_arr = df['High'].values
    low_arr = df['Low'].values
    atr_arr = df['ATR'].values if 'ATR' in df.columns else np.zeros(len(df))
    
    dt_col = np.zeros(len(df), dtype=int)
    dt_neck_col = np.full(len(df), np.nan)
    db_col = np.zeros(len(df), dtype=int)
    db_neck_col = np.full(len(df), np.nan)
    tri_col = np.zeros(len(df), dtype=int)
    
    for t in range(lookback, len(df)):
        # Buscar picos locales en la ventana [t-lookback+1, t]
        max_indices = []
        min_indices = []
        for idx in range(t - lookback + 1, t + 1):
            if max_local_arr[idx]:
                max_indices.append(idx)
            if min_local_arr[idx]:
                min_indices.append(idx)
                
        # Doble Techo
        if len(max_indices) >= 2:
            p1_confirm = max_indices[-2]
            p2_confirm = max_indices[-1]
            p1_idx = p1_confirm - 5
            p2_idx = p2_confirm - 5
            if p1_idx >= 0 and p2_idx >= 0:
                p1_price = high_arr[p1_idx]
                p2_price = high_arr[p2_idx]
                atr_current = atr_arr[p2_confirm] if atr_arr[p2_confirm] > 0 else 0.0002
                
                price_match = abs(p1_price - p2_price) < (atr_current * 0.25)
                separation = p2_idx - p1_idx
                time_check = separation > 5
                
                if time_check:
                    valley_min = np.min(low_arr[p1_idx:p2_idx+1])
                    valley_depth = p1_price - valley_min
                    valley_check = valley_depth > (atr_current * 0.25)
                    if price_match and valley_check:
                        dt_col[p2_confirm] = 1
                        dt_neck_col[p2_confirm] = valley_min
                        
        # Doble Suelo
        if len(min_indices) >= 2:
            p1_confirm = min_indices[-2]
            p2_confirm = min_indices[-1]
            p1_idx = p1_confirm - 5
            p2_idx = p2_confirm - 5
            if p1_idx >= 0 and p2_idx >= 0:
                p1_price = low_arr[p1_idx]
                p2_price = low_arr[p2_idx]
                atr_current = atr_arr[p2_confirm] if atr_arr[p2_confirm] > 0 else 0.0002
                
                price_match = abs(p1_price - p2_price) < (atr_current * 0.25)
                separation = p2_idx - p1_idx
                time_check = separation > 5
                
                if time_check:
                    peak_max = np.max(high_arr[p1_idx:p2_idx+1])
                    peak_height = peak_max - p1_price
                    peak_check = peak_height > (atr_current * 0.25)
                    if price_match and peak_check:
                        db_col[p2_confirm] = 1
                        db_neck_col[p2_confirm] = peak_max
                        
        # Triángulo
        if len(max_indices) >= 3 and len(min_indices) >= 3:
            p1_idx = max_indices[-3] - 5
            p2_idx = max_indices[-2] - 5
            p3_idx = max_indices[-1] - 5
            v1_idx = min_indices[-3] - 5
            v2_idx = min_indices[-2] - 5
            v3_idx = min_indices[-1] - 5
            
            if p1_idx >= 0 and v1_idx >= 0:
                peaks_decreasing = high_arr[p1_idx] > high_arr[p2_idx] > high_arr[p3_idx]
                troughs_increasing = low_arr[v1_idx] < low_arr[v2_idx] < low_arr[v3_idx]
                
                range1 = high_arr[p1_idx] - low_arr[v1_idx]
                range2 = high_arr[p2_idx] - low_arr[v2_idx]
                range3 = high_arr[p3_idx] - low_arr[v3_idx]
                range_decreasing = range1 > range2 > range3
                
                if 'ATR' in df.columns:
                    atr_current = atr_arr[t]
                    # Tomar la media de atr_arr de las últimas 20 velas
                    atr_avg_20 = np.mean(atr_arr[max(0, t-19):t+1])
                    atr_compress = atr_current < atr_avg_20
                else:
                    atr_compress = True
                    
                if peaks_decreasing and troughs_increasing and range_decreasing and atr_compress:
                    tri_col[t] = 1
                    
    df['Pattern_DoubleTop'] = dt_col
    df['Pattern_DoubleTop_Neck'] = dt_neck_col
    df['Pattern_DoubleBottom'] = db_col
    df['Pattern_DoubleBottom_Neck'] = db_neck_col
    df['Pattern_Triangle'] = tri_col
    return df

async def fetch_historical_candles_large(api, pair, interval, total_candles=50000):
    """
    Descarga hasta total_candles (máximo que permita la API) o carga desde cache local en CSV.
    Si la cache tiene pocas velas en comparación a lo solicitado, se fuerza una redescarga profunda.
    Si el broker falla, usa la cache disponible sin importar la cantidad.
    """
    cache_dir = Path("historical_data")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{pair}_{interval}s.csv"
    
    cached_df = None
    if cache_file.exists():
        try:
            df = pd.read_csv(cache_file)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
            cached_df = df
            # Si el archivo en cache contiene al menos el 80% de lo solicitado, lo usamos directamente
            if len(df) >= total_candles * 0.8:
                print(f"  [CACHE] Cargando {len(df)} velas desde cache local: {cache_file.name}")
                return df
            else:
                print(f"  [CACHE] Cache local tiene pocas velas ({len(df)} vs {total_candles} deseadas). Intentando descarga profunda desde el Broker...")
        except Exception as e:
            print(f"  [CACHE] Error leyendo cache {cache_file.name}: {e}.")

    print(f"  [API] Descargando de forma profunda hasta {total_candles} velas para {pair} (TF: {interval}s)...")
    all_candles = []
    
    try:
        if api is None:
            raise ConnectionError("Broker API no conectada. Modo offline.")
            
        offset = interval * 300
        candles = await asyncio.wait_for(api.get_candles(pair, interval, offset), timeout=15.0)
        if not candles:
            raise ValueError("No candles returned")
            
        all_candles.extend(candles)
        time_key = next((k for k in candles[0].keys() if k.lower() in ['time', 'timestamp', 'date']), None)
        if not time_key:
            raise ValueError("Time key not found")
            
        current_end_time = int(candles[0][time_key])
        
        # Descargar chunks hasta alcanzar el límite del broker o el total solicitado
        chunk_idx = 1
        consecutive_empty = 0
        while len(all_candles) < total_candles:
            await asyncio.sleep(0.3)
            try:
                chunk = await asyncio.wait_for(
                    api.get_candles_advanced(pair, interval, offset, current_end_time),
                    timeout=12.0
                )
                if not chunk:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    continue
                consecutive_empty = 0
                all_candles = chunk + all_candles
                current_end_time = int(chunk[0][time_key])
                chunk_idx += 1
                if len(chunk) < 5: # Si el broker devuelve casi nada, alcanzamos su límite histórico
                    break
            except Exception as e:
                print(f"    [WARN] Error descargando chunk {chunk_idx}: {e}. Terminando descarga aquí.")
                break
                
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
        
        # Guardar en cache local en CSV
        try:
            df.to_csv(cache_file, index=False)
            print(f"  [CACHE] Guardadas {len(df)} velas de {pair} en {cache_file.name}")
        except Exception as save_err:
            print(f"  [WARN] Fallo al guardar cache CSV: {save_err}")
            
        return df
    except Exception as e:
        if cached_df is not None:
            print(f"  [OFFLINE FALLBACK] Fallo descarga ({e}). Utilizando cache local existente con {len(cached_df)} velas.")
            return cached_df
        print(f"  [ERR] Error descargando {pair} y no hay cache local: {e}")
        return pd.DataFrame()


def run_backtest_fast_routed(df, strategies, analyzer):
    """
    Simulación optimizada ultra-rápida (en milisegundos).
    """
    # 1. Calcular indicadores
    df = analyzer.compute_indicators(df)
    # 2. Precalcular patrones
    df = precompute_candlestick_patterns(df)
    df = precompute_chart_patterns(df)
    
    # --- PRECALCULAR EL ESTADO DE MERCADO VECTORIZADO ---
    adx_series = ta.trend.ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx().values
    atr_avg_series = df['ATR'].rolling(20).mean().values if 'ATR' in df.columns else np.zeros(len(df))
    
    high_vals = df['High'].values
    low_vals = df['Low'].values
    close_vals = df['Close'].values
    ema20_vals = df['EMA_20'].values
    ema50_vals = df['EMA_50'].values
    atr_vals = df['ATR'].values if 'ATR' in df.columns else np.zeros(len(df))
    
    market_states = []
    for idx in range(len(df)):
        if idx < 50 or pd.isna(ema20_vals[idx]) or pd.isna(ema50_vals[idx]) or pd.isna(adx_series[idx]):
            market_states.append('UNKNOWN')
            continue
            
        adx = adx_series[idx]
        ema20 = ema20_vals[idx]
        ema50 = ema50_vals[idx]
        close = close_vals[idx]
        
        state = 'NEUTRAL'
        if adx > 25:
            if ema20 > ema50 and close > ema50:
                state = 'TRENDING_UP'
            elif ema20 < ema50 and close < ema50:
                state = 'TRENDING_DOWN'
                
        if state == 'NEUTRAL' and adx < 18:
            state = 'SIDEWAYS'
            
        if state == 'NEUTRAL' and 'ATR' in df.columns:
            atr = atr_vals[idx]
            atr_avg = atr_avg_series[idx]
            if atr > atr_avg * 1.8:
                state = 'VOLATILE'
                
        market_states.append(state)
        
    trades = []
    wins = 0
    losses = 0
    
    # Creamos mapeo rápido de estrategias por tipo
    strat_by_type = {}
    for s in strategies:
        stype = getattr(s, 'type', 'TREND')
        if stype not in strat_by_type:
            strat_by_type[stype] = []
        strat_by_type[stype].append(s)
        
    for i in range(200, len(df) - 1):
        market_state = market_states[i]
        
        # Router
        allowed_types = []
        if market_state in ['TRENDING_UP', 'TRENDING_DOWN']:
            allowed_types = ['TREND']
        elif market_state == 'NEUTRAL':
            allowed_types = ['REVERSION']
            
        if not allowed_types:
            continue
            
        sub_df = df.iloc[max(0, i-250):i+1]
        
        for stype in allowed_types:
            if stype not in strat_by_type:
                continue
            triggered = False
            for strategy in strat_by_type[stype]:
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
                    triggered = True
                    break # Detener para esta vela
            if triggered:
                break
                
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
    print("BACKTESTING DE ALTA PRECISIÓN MULTI-TEMPORALIDAD (10,000 VELAS)")
    print("====================================================")
    
    config_path = Path("config.json")
    if not config_path.exists():
        print("[ERR] config.json no encontrado.")
        return
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    ssid = config.get('ssid')
    
    api = None
    try:
        print("[INFO] Intentando conectar con el broker para descarga (Timeout 5s)...")
        # Envolviendo la creación en un thread y timeout por si se cuelga en el constructor
        api = await asyncio.wait_for(asyncio.to_thread(PocketOptionAsync, ssid), timeout=5.0)
        await asyncio.sleep(0.5)
        balance = await asyncio.wait_for(api.balance(), timeout=5.0)
        if balance == -1.0:
            print("[WARN] Conexión rechazada por el broker. Usando cache local...")
            api = None
        else:
            print(f"[OK] Conectado. Balance: ${balance:.2f}")
    except Exception as e:
        print(f"[WARN] No se pudo conectar al broker: {e}. Continuando en MODO OFFLINE con cache local...")
        api = None
    
    analyzer = MarketAnalyzer()
    strategies = [
        StrategyStochastic(),
        StrategyFibonacci(),
        StrategyStructure(),
        StrategyExpertVision(),
        StrategyAlphaConvergence(),
        StrategyWaveTrendKeltner(bypass_filter=True)
    ]

    # Cargar pares dinámicamente de config.json, o usar fallback si no existen
    pairs = config.get("trading", {}).get("pairs", [])
    if not pairs:
        pairs = [
            "EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", 
            "USDCAD_otc", "AUDCAD_otc", "GBPJPY_otc", 
            "USDCHF_otc", "NZDUSD_otc", "AUDJPY_otc"
        ]
    
    # Evaluar M1 (1m), M5 (5m), M15 (15m), M30 (30m) y H1 (1h)
    timeframes = [
        {"name": "H1 (1 Hora)", "interval": 3600, "candles": 10000},
        {"name": "M30 (30 Minutos)", "interval": 1800, "candles": 20000},
        {"name": "M15 (15 Minutos)", "interval": 900, "candles": 35000},
        {"name": "M5 (5 Minutos)", "interval": 300, "candles": 50000},
        {"name": "M1 (1 Minuto)", "interval": 60, "candles": 50000}
    ]
    
    results = {}
    
    for tf in timeframes:
        tf_name = tf["name"]
        interval = tf["interval"]
        candles_to_fetch = tf["candles"]
        
        print(f"\n>>> INICIANDO BACKTEST PARA TEMPORALIDAD: {tf_name} <<<")
        results[tf_name] = {}
        
        for pair in pairs:
            # Descargar histórico
            df = await fetch_historical_candles_large(api, pair, interval, candles_to_fetch)
            if df.empty or len(df) < 250:
                print(f"  [WARN] {pair} no tiene suficiente historial para {tf_name}.")
                continue
                
            print(f"  [OK] Descargadas {len(df)} velas de {pair}. Simulando...")
            
            # Ejecutar simulación ultra rápida
            res = run_backtest_fast_routed(df, strategies, analyzer)
            
            results[tf_name][pair] = {
                'total_trades': res['total_trades'],
                'win_rate': res['win_rate'],
                'wins': res['wins'],
                'losses': res['losses']
            }
            print(f"  [RESULT] {pair}: {res['total_trades']} trades | WR: {res['win_rate']:.2f}% (Wins: {res['wins']} | Losses: {res['losses']})")
            
            # Imprimir rendimiento detallado por estrategia
            strat_stats = {}
            for t_info in res['details']:
                s_name = t_info['strategy']
                if s_name not in strat_stats:
                    strat_stats[s_name] = {'wins': 0, 'losses': 0}
                if t_info['result'] == 'WIN':
                    strat_stats[s_name]['wins'] += 1
                else:
                    strat_stats[s_name]['losses'] += 1
            for s_name, stats in strat_stats.items():
                s_total = stats['wins'] + stats['losses']
                s_wr = (stats['wins'] / s_total * 100) if s_total > 0 else 0.0
                print(f"    -> {s_name}: {s_total} trades | WR: {s_wr:.2f}% (Wins: {stats['wins']} | Losses: {stats['losses']})")
            
    # --- PROCESAR RESULTADOS ---
    print("\n\n====================================================")
    print("REPORTE MAESTRO DE RENDIMIENTO MULTI-TEMPORALIDAD")
    print("====================================================")
    
    pair_recommendations = {}
    
    for pair in pairs:
        print(f"\nAnalizando mejor configuración para {pair}:")
        best_tf = None
        best_wr = 0.0
        best_trades = 0
        
        for tf_name in results.keys():
            if pair in results[tf_name]:
                stats = results[tf_name][pair]
                print(f"  - {tf_name}: {stats['total_trades']} trades | WR: {stats['win_rate']:.2f}%")
                if stats['total_trades'] >= 3 and stats['win_rate'] > best_wr:
                    best_wr = stats['win_rate']
                    best_tf = tf_name
                    best_trades = stats['total_trades']
                    
        if best_tf:
            pair_recommendations[pair] = {
                "timeframe": best_tf,
                "win_rate": best_wr,
                "trades": best_trades
            }
            print(f"  [RECOMMENDED] Operar {pair} en {best_tf} (WR: {best_wr:.2f}% en {best_trades} trades)")
        else:
            print("  [SKIP] Sin datos suficientes para dar recomendacion confiable.")
            
    print("\n====================================================")
    print("RESUMEN DE RECOMENDACIONES POR PAR:")
    print("====================================================")
    for pair, rec in pair_recommendations.items():
        print(f"- {pair} -> Temporalidad: {rec['timeframe']} | Win Rate: {rec['win_rate']:.2f}% ({rec['trades']} trades)")
    print("====================================================")
    
    # Guardar en archivo para que el bot lo conozca si es necesario
    out_path = Path("multi_tf_recommendations.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pair_recommendations, f, indent=4)
    print(f"\n[OK] Recomendaciones maestras guardadas en {out_path}")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
