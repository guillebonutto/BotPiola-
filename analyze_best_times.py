import pandas as pd
import glob
import json
import os
from datetime import datetime
from pathlib import Path

def analyze_logs(logs_dir="logs/trades", config_path="config.json"):
    logs_path = Path(logs_dir)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            broker = cfg.get('broker', 'pocketoption')
    except Exception:
        broker = 'pocketoption'
        
    stem = Path(config_path).stem
    if stem == "config":
        csv_suffix = "pocketoption"
        out_suffix = ""
    else:
        csv_suffix = stem
        out_suffix = f"_{stem}"
        
    all_files = glob.glob(str(logs_path / f"trades_{csv_suffix}_*.csv"))
    
    if not all_files:
        print(f"[ERR] No se encontraron archivos de log (trades_{csv_suffix}_*.csv) para analizar.")
        return None

    dfs = []
    for f in all_files:
        try:
            df_temp = pd.read_csv(f)
            if not df_temp.empty:
                dfs.append(df_temp)
        except Exception:
            continue
    
    if not dfs:
        print("[ERR] No se pudo leer ningún dato de los archivos de log.")
        return None
        
    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'result'])
    df = df[df['result'].isin(['WIN', 'LOSS'])]
    
    if df.empty:
        print("[ERR] No hay suficientes trades cerrados (WIN/LOSS) para analizar.")
        return None

    # Extraer hora del día
    df['hour'] = df['timestamp'].dt.hour
    
    # 1. Análisis por Hora y Par
    hour_pair_stats = df.groupby(['hour', 'pair']).agg({
        'result': lambda x: (x == 'WIN').sum() / len(x),
        'trade_id': 'count'
    }).reset_index()
    hour_pair_stats.columns = ['hour', 'pair', 'win_rate', 'count']
    
    # 2. Análisis por Estrategia
    df['strategy_clean'] = df['pattern_detected'].apply(lambda x: str(x).split(':')[0] if ':' in str(x) else str(x))
    strat_stats = df.groupby('strategy_clean').agg({
        'result': lambda x: (x == 'WIN').sum() / len(x),
        'trade_id': 'count'
    }).reset_index()
    strat_stats.columns = ['strategy', 'win_rate', 'count']
    
    # 2.5 Análisis por Par y Estrategia (Matriz de Rendimiento)
    pair_strat_stats = df.groupby(['pair', 'strategy_clean']).agg({
        'result': lambda x: (x == 'WIN').sum() / len(x),
        'trade_id': 'count'
    }).reset_index()
    pair_strat_stats.columns = ['pair', 'strategy', 'win_rate', 'count']

    # 3. Identificar Zonas de Riesgo (Win Rate < 38% para Alpaca, < 45% para otros; y al menos 15 trades)
    risk_wr = 0.38 if broker == 'alpaca' else 0.45
    risk_zones = hour_pair_stats[(hour_pair_stats['win_rate'] < risk_wr) & (hour_pair_stats['count'] >= 15)]
    
    # 4. Identificar Zonas de Alta Confianza (Win Rate > 55% para Alpaca, > 70% para otros; y al menos 15 trades)
    conf_wr = 0.55 if broker == 'alpaca' else 0.70
    confidence_zones = hour_pair_stats[(hour_pair_stats['win_rate'] > conf_wr) & (hour_pair_stats['count'] >= 15)]

    report = {
        'last_update': datetime.now().isoformat(),
        'total_trades_analyzed': len(df),
        'risk_zones': risk_zones.to_dict(orient='records'),
        'confidence_zones': confidence_zones.to_dict(orient='records'),
        'strategy_performance': strat_stats.to_dict(orient='records'),
        'pair_strategy_performance': pair_strat_stats.to_dict(orient='records')
    }
    
    intel_file = f"trading_intelligence{out_suffix}.json"
    with open(intel_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
        
    print(f"[OK] Inteligencia generada: {intel_file}")
    print(f"   - Trades analizados: {len(df)}")
    print(f"   - Zonas de riesgo detectadas: {len(risk_zones)}")
    print(f"   - Zonas de confianza detectadas: {len(confidence_zones)}")
    
    return report

def generate_dynamic_threshold_matrix(logs_dir="logs/trades", config_path="config.json"):
    logs_path = Path(logs_dir)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            broker = cfg.get('broker', 'pocketoption')
    except Exception:
        broker = 'pocketoption'
        
    stem = Path(config_path).stem
    if stem == "config":
        csv_suffix = "pocketoption"
        out_suffix = ""
    else:
        csv_suffix = stem
        out_suffix = f"_{stem}"
        
    all_files = glob.glob(str(logs_path / f"trades_{csv_suffix}_*.csv"))
    thresholds_file = f"strategy_thresholds{out_suffix}.json"
    
    matrix = {}
    known_strategies = [
        "Estocástico + SMA200",
        "WaveTrend + Keltner Channel Reversion",
        "Alpha Convergence (Bollinger + Fibo + Stoch)",
        "Cambio de Estructura (MSS)",
        "Expert Vision Donchian Reversion",
        "Fibonacci Retracement 61.8%",
        "Patrones de Continuación (Chartismo)"
    ]
    
    default_pairs = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "SPY", "AAPL"] if broker == 'alpaca' else ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "USDCAD_otc", "AUDCAD_otc", "USDMXN_otc", "USDCOP_otc", "GBPJPY_otc", "AUDJPY_otc", "NZDUSD_otc", "USDCHF_otc"]
    default_thresh = 0.45 if broker == 'alpaca' else 0.55
    for strat in known_strategies:
        matrix[strat] = {}
        for pair in default_pairs:
            matrix[strat][pair] = default_thresh
            
    if not all_files:
        try:
            with open(thresholds_file, 'w', encoding='utf-8') as f:
                json.dump(matrix, f, indent=4)
        except Exception:
            pass
        return matrix

    dfs = []
    for f in all_files:
        try:
            df_temp = pd.read_csv(f)
            if not df_temp.empty:
                dfs.append(df_temp)
        except Exception:
            continue
            
    if not dfs:
        try:
            with open(thresholds_file, 'w', encoding='utf-8') as f:
                json.dump(matrix, f, indent=4)
        except Exception:
            pass
        return matrix
        
    df = pd.concat(dfs, ignore_index=True)
    df = df.dropna(subset=['result'])
    df = df[df['result'].isin(['WIN', 'LOSS'])]
    
    if df.empty:
        try:
            with open(thresholds_file, 'w', encoding='utf-8') as f:
                json.dump(matrix, f, indent=4)
        except Exception:
            pass
        return matrix

    df['strategy_clean'] = df['pattern_detected'].apply(lambda x: str(x).split(':')[0] if ':' in str(x) else str(x))
    
    strat_overall = df.groupby('strategy_clean').agg({
        'result': lambda x: (x == 'WIN').sum() / len(x),
        'trade_id': 'count'
    }).rename(columns={'result': 'win_rate', 'trade_id': 'count'}).to_dict(orient='index')
    
    strat_pair = df.groupby(['strategy_clean', 'pair']).agg({
        'result': lambda x: (x == 'WIN').sum() / len(x),
        'trade_id': 'count'
    }).rename(columns={'result': 'win_rate', 'trade_id': 'count'}).reset_index()
    
    for _, row in strat_pair.iterrows():
        strat = row['strategy_clean']
        pair = row['pair']
        count = row['count']
        win_rate = row['win_rate']
        
        if strat not in matrix:
            matrix[strat] = {}
            
        if count >= 15:
            threshold = max(0.45 if broker == 'alpaca' else 0.55, win_rate + 0.02)
        else:
            overall_stats = strat_overall.get(strat, {})
            overall_count = overall_stats.get('count', 0)
            overall_win_rate = overall_stats.get('win_rate', 0.53 if broker == 'pocketoption' else 0.46)
            
            if overall_count >= 15:
                threshold = max(0.45 if broker == 'alpaca' else 0.55, overall_win_rate + 0.02)
            else:
                threshold = 0.45 if broker == 'alpaca' else 0.55
                
        matrix[strat][pair] = round(threshold, 4)
        
    for strat in known_strategies:
        if strat not in matrix:
            matrix[strat] = {}
        for pair in default_pairs:
            if pair not in matrix[strat]:
                matrix[strat][pair] = default_thresh
                
    try:
        with open(thresholds_file, 'w', encoding='utf-8') as f:
            json.dump(matrix, f, indent=4)
        print(f"[OK] Dynamic threshold matrix generated: {thresholds_file}")
    except Exception as e:
        print(f"[ERR] Error saving {thresholds_file}: {e}")
        
    return matrix

if __name__ == "__main__":
    import sys
    cfg_file = "config.json"
    if len(sys.argv) > 1:
        cfg_file = sys.argv[1]
    analyze_logs(config_path=cfg_file)
    generate_dynamic_threshold_matrix(config_path=cfg_file)
