import pandas as pd
import glob
import json
import os
from datetime import datetime
from pathlib import Path

def analyze_logs(logs_dir="logs/trades"):
    logs_path = Path(logs_dir)
    all_files = glob.glob(str(logs_path / "trades_*.csv"))
    
    if not all_files:
        print("❌ No se encontraron archivos de log para analizar.")
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
        print("❌ No se pudo leer ningún dato de los archivos de log.")
        return None
        
    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'result'])
    df = df[df['result'].isin(['WIN', 'LOSS'])]
    
    if df.empty:
        print("❌ No hay suficientes trades cerrados (WIN/LOSS) para analizar.")
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

    # 3. Identificar Zonas de Riesgo (Win Rate < 45% y al menos 3 trades)
    risk_zones = hour_pair_stats[(hour_pair_stats['win_rate'] < 0.45) & (hour_pair_stats['count'] >= 3)]
    
    # 4. Identificar Zonas de Alta Confianza (Win Rate > 70% y al menos 2 trades)
    confidence_zones = hour_pair_stats[(hour_pair_stats['win_rate'] > 0.70) & (hour_pair_stats['count'] >= 2)]

    report = {
        'last_update': datetime.now().isoformat(),
        'total_trades_analyzed': len(df),
        'risk_zones': risk_zones.to_dict(orient='records'),
        'confidence_zones': confidence_zones.to_dict(orient='records'),
        'strategy_performance': strat_stats.to_dict(orient='records')
    }
    
    with open('trading_intelligence.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
        
    print(f"✅ Inteligencia generada: trading_intelligence.json")
    print(f"   - Trades analizados: {len(df)}")
    print(f"   - Zonas de riesgo detectadas: {len(risk_zones)}")
    print(f"   - Zonas de confianza detectadas: {len(confidence_zones)}")
    
    return report

if __name__ == "__main__":
    analyze_logs()
