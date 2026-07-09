import os
import json
import sys
import pandas as pd
import numpy as np
import ta
from pathlib import Path

# Agregar el directorio actual al path
sys.path.insert(0, os.path.abspath("."))
from analysis import MarketAnalyzer

def compute_base_indicators(df):
    """Calcula los indicadores base necesarios en pandas."""
    analyzer = MarketAnalyzer()
    df = analyzer.compute_indicators(df)
    
    # Calcular ADX para el estado de mercado
    adx_series = ta.trend.ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
    df['ADX'] = adx_series
    return df

def simulate_wavetrend_keltner(df, wt_limit=53, kc_multiplier=1.8, wt_cross_lookback=2):
    """
    Simulación optimizada y vectorizada de la estrategia WaveTrend + Keltner.
    """
    wins = 0
    losses = 0
    trades = []
    
    # Extraer arrays numpy para velocidad máxima
    high = df['High'].values
    low = df['Low'].values
    close = df['Close'].values
    open_p = df['Open'].values
    
    # Keltner base
    kc_middle = df['KC_Middle'].values
    # El ATR de 10 períodos usado en Keltner se puede despejar del KC_Upper y KC_Middle precalculados
    # KC_Upper = KC_Middle + 2 * ATR_10 => ATR_10 = (KC_Upper - KC_Middle) / 2
    kc_upper_base = df['KC_Upper'].values
    atr_10 = (kc_upper_base - kc_middle) / 2.0
    
    # WaveTrend
    wt1 = df['WT1'].values
    wt2 = df['WT2'].values
    
    # Estado de mercado precalculado
    ema20 = df['EMA_20'].values
    ema50 = df['EMA_50'].values
    adx = df['ADX'].values
    atr = df['ATR'].values if 'ATR' in df.columns else np.zeros(len(df))
    
    # Calcular media móvil rodante de ATR
    atr_series = pd.Series(atr)
    atr_avg = atr_series.rolling(20).mean().values
    
    # Precalcular estados de mercado
    market_states = []
    for idx in range(len(df)):
        if idx < 50 or pd.isna(ema20[idx]) or pd.isna(ema50[idx]) or pd.isna(adx[idx]):
            market_states.append('UNKNOWN')
            continue
            
        adx_val = adx[idx]
        ema20_val = ema20[idx]
        ema50_val = ema50[idx]
        close_val = close[idx]
        
        state = 'NEUTRAL'
        if adx_val > 25:
            if ema20_val > ema50_val and close_val > ema50_val:
                state = 'TRENDING_UP'
            elif ema20_val < ema50_val and close_val < ema50_val:
                state = 'TRENDING_DOWN'
                
        if state == 'NEUTRAL' and adx_val < 18:
            state = 'SIDEWAYS'
            
        if state == 'NEUTRAL' and 'ATR' in df.columns:
            atr_val = atr[idx]
            atr_avg_val = atr_avg[idx]
            if atr_val > atr_avg_val * 1.8:
                state = 'VOLATILE'
                
        market_states.append(state)
        
    # Bucle de simulación
    for i in range(50, len(df) - 1):
        market_state = market_states[i]
        
        # Filtro de régimen: Solo reversión (Neutral y Sideways)
        if market_state not in ['NEUTRAL', 'SIDEWAYS']:
            continue
            
        # --- COMPRAS (BUY) ---
        # Canal Keltner dinámico basado en el multiplicador de la simulación
        kc_lower_custom = kc_middle[i] - (kc_multiplier * atr_10[i])
        
        # El precio toca/rompe canal de Keltner inferior en la vela actual o en la anterior
        kc_lower_prev = kc_middle[i-1] - (kc_multiplier * atr_10[i-1])
        kc_buy = (low[i] <= kc_lower_custom) or (low[i-1] <= kc_lower_prev)
        
        # WaveTrend en sobreventa
        wt_oversold = wt1[i] < -wt_limit
        
        # Cruce alcista de WaveTrend en el lookback de velas especificado
        wt_cross_buy = False
        for l in range(wt_cross_lookback):
            idx = i - l
            if idx > 0 and wt1[idx-1] < wt2[idx-1] and wt1[idx] > wt2[idx]:
                wt_cross_buy = True
                break
                
        # Confirmación de vela alcista
        confirm_buy = close[i] > open_p[i]
        
        if kc_buy and wt_oversold and wt_cross_buy and confirm_buy:
            next_close = close[i+1]
            is_win = next_close > close[i]
            if is_win:
                wins += 1
            else:
                losses += 1
            trades.append(1)
            continue
            
        # --- VENTAS (SELL) ---
        kc_upper_custom = kc_middle[i] + (kc_multiplier * atr_10[i])
        kc_upper_prev = kc_middle[i-1] + (kc_multiplier * atr_10[i-1])
        kc_sell = (high[i] >= kc_upper_custom) or (high[i-1] >= kc_upper_prev)
        
        # WaveTrend en sobrecompra
        wt_overbought = wt1[i] > wt_limit
        
        # Cruce bajista de WaveTrend
        wt_cross_sell = False
        for l in range(wt_cross_lookback):
            idx = i - l
            if idx > 0 and wt1[idx-1] > wt2[idx-1] and wt1[idx] < wt2[idx]:
                wt_cross_sell = True
                break
                
        # Confirmación de vela bajista
        confirm_sell = close[i] < open_p[i]
        
        if kc_sell and wt_overbought and wt_cross_sell and confirm_sell:
            next_close = close[i+1]
            is_win = next_close < close[i]
            if is_win:
                wins += 1
            else:
                losses += 1
            trades.append(1)
            
    total = len(trades)
    wr = (wins / total * 100) if total > 0 else 0.0
    return wins, losses, wr, total

def main():
    historical_dir = Path("historical_data")
    if not historical_dir.exists():
        print("[ERR] Carpeta historical_data no encontrada.")
        return
        
    csv_files = list(historical_dir.glob("*.csv"))
    print(f"Cargando y procesando {len(csv_files)} archivos históricos en memoria...")
    
    datasets = {}
    for f in csv_files:
        df = pd.read_csv(f)
        if len(df) > 500:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
            # Precalcular indicadores base de análisis para ahorrar tiempo en el bucle
            df = compute_base_indicators(df)
            datasets[f.name] = df
            print(f"  -> {f.name} cargado ({len(df)} velas).")
            
    print("\nIniciando GRID SEARCH de Optimización...")
    
    # Rango de parámetros a evaluar
    grid = []
    for wt_limit in [50, 53, 55, 60]:
        for kc_multiplier in [1.5, 1.6, 1.7, 1.8, 1.9, 2.0]:
            for wt_cross_lookback in [1, 2]:
                grid.append({
                    "wt_limit": wt_limit,
                    "kc_multiplier": kc_multiplier,
                    "wt_cross_lookback": wt_cross_lookback
                })
                
    print(f"Total combinaciones a evaluar en el Grid: {len(grid)}")
    
    best_overall_wr = 0.0
    best_config = None
    best_total_trades = 0
    best_results_by_file = {}
    
    for idx, params in enumerate(grid, 1):
        total_wins = 0
        total_losses = 0
        total_trades = 0
        file_stats = {}
        
        for filename, df in datasets.items():
            w, l, wr, cnt = simulate_wavetrend_keltner(
                df, 
                wt_limit=params["wt_limit"], 
                kc_multiplier=params["kc_multiplier"], 
                wt_cross_lookback=params["wt_cross_lookback"]
            )
            total_wins += w
            total_losses += l
            total_trades += cnt
            file_stats[filename] = {"trades": cnt, "win_rate": wr}
            
        overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
        
        # Filtros mínimos para considerar una configuración ganadora:
        # 1. Al menos 150 operaciones en total sumando todos los datasets (para validez estadística)
        # 2. Mayor Win Rate promedio
        if total_trades >= 150 and overall_wr > best_overall_wr:
            best_overall_wr = overall_wr
            best_config = params
            best_total_trades = total_trades
            best_results_by_file = file_stats
            print(f"[MEJORADA] Config {idx}/{len(grid)}: Limit={params['wt_limit']}, Mult={params['kc_multiplier']}, Lookback={params['wt_cross_lookback']} | Total Trades: {total_trades} | Win Rate: {overall_wr:.2f}%")
            
    print("\n==========================================")
    print("CONFIGURACIÓN ÓPTIMA ENCONTRADA:")
    print("==========================================")
    print(f"Límite WaveTrend: {best_config['wt_limit']}")
    print(f"Multiplicador Keltner: {best_config['kc_multiplier']}")
    print(f"Lookback Cruce WT: {best_config['wt_cross_lookback']} velas")
    print(f"Total Trades evaluados: {best_total_trades}")
    print(f"Win Rate Promedio Global: {best_overall_wr:.2f}%")
    print("==========================================")
    print("\nResultados detallados por archivo con la mejor configuración:")
    
    allowed_combinations_json = []
    
    for filename, stats in best_results_by_file.items():
        # Desglosar nombre de archivo en par e intervalo
        parts = filename.replace(".csv", "").split("_")
        # Ejemplo: EURUSD_otc_900s -> par: EURUSD_otc, intervalo: 900
        pair = f"{parts[0]}_{parts[1]}"
        interval = int(parts[2].replace("s", ""))
        
        print(f"  - {filename}: {stats['trades']} trades | WR: {stats['win_rate']:.2f}%")
        
        # Si la combinación tiene al menos 5 trades e histórico de Win Rate > 55%
        if stats['trades'] >= 5 and stats['win_rate'] >= 55.0:
            allowed_combinations_json.append({
                "pair": pair,
                "interval": interval,
                "win_rate": stats['win_rate'],
                "trades": stats['trades']
            })
            
    print("\nCombinaciones recomendadas para producción (>55% WR, >=5 trades):")
    for rec in allowed_combinations_json:
        print(f"  - (\"{rec['pair']}\", {rec['interval']}) -> WR: {rec['win_rate']:.2f}% en {rec['trades']} trades")
        
    # Guardar en un json para lectura fácil
    out_path = Path("wavetrend_keltner_opt.json")
    with open(out_path, "w") as f:
        json.dump({
            "best_config": best_config,
            "overall_win_rate": best_overall_wr,
            "total_trades": best_total_trades,
            "recommendations": allowed_combinations_json
        }, f, indent=4)
    print(f"\nResultados guardados en {out_path}")

if __name__ == "__main__":
    main()
