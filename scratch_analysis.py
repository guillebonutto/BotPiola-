import pandas as pd
import glob
from pathlib import Path
from datetime import datetime

def run_analysis():
    logs_dir = Path("c:/Users/Guille/Desktop/NuevoBot/logs/trades")
    files = glob.glob(str(logs_dir / "trades_*.csv"))
    
    if not files:
        print("No log files found.")
        return
        
    dfs = []
    for f in files:
        try:
            temp_df = pd.read_csv(f)
            if not temp_df.empty:
                dfs.append(temp_df)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    if not dfs:
        print("No data could be loaded.")
        return
        
    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'result'])
    df = df[df['result'].isin(['WIN', 'LOSS'])]
    
    print("====================================================")
    print(f"HISTORIAL TOTAL ANALIZADO: {len(df)} TRADES")
    print("====================================================")
    
    # 1. Win Rate global
    wins = len(df[df['result'] == 'WIN'])
    losses = len(df[df['result'] == 'LOSS'])
    wr = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
    print(f"Win Rate Global: {wr:.2f}% (Wins: {wins} | Losses: {losses})")
    print()
    
    # 2. Frecuencia de operaciones
    dfs_sorted = []
    for f in files:
        try:
            tdf = pd.read_csv(f)
            if len(tdf) > 1:
                tdf['timestamp'] = pd.to_datetime(tdf['timestamp'], errors='coerce')
                tdf = tdf.dropna(subset=['timestamp'])
                tdf = tdf.sort_values('timestamp')
                tdf['time_diff'] = tdf['timestamp'].diff().dt.total_seconds() / 60.0
                dfs_sorted.append(tdf)
        except:
            pass
    if dfs_sorted:
        all_sorted = pd.concat(dfs_sorted, ignore_index=True)
        avg_diff = all_sorted['time_diff'].mean()
        median_diff = all_sorted['time_diff'].median()
        print(f"Frecuencia de Operaciones:")
        print(f"  - Tiempo promedio entre trades: {avg_diff:.2f} minutos")
        print(f"  - Tiempo mediano entre trades: {median_diff:.2f} minutos")
    else:
        print("No se pudo calcular la frecuencia de tiempo.")
    print()
    
    # 3. Horarios más activos y su Win Rate
    df['hour'] = df['timestamp'].dt.hour
    hour_stats = df.groupby('hour').agg(
        total_trades=('trade_id', 'count'),
        win_rate=('result', lambda x: (x == 'WIN').sum() / len(x) * 100)
    ).reset_index()
    
    print("Distribucion de Horarios (Ordenados por volumen de trades):")
    for _, row in hour_stats.sort_values('total_trades', ascending=False).iterrows():
        print(f"  - Hora {int(row['hour']):02d}:00: {int(row['total_trades'])} trades | WR: {row['win_rate']:.2f}%")
    print()
    
    # 4. Rendimiento por Par (Activos)
    pair_stats = df.groupby('pair').agg(
        total_trades=('trade_id', 'count'),
        win_rate=('result', lambda x: (x == 'WIN').sum() / len(x) * 100)
    ).reset_index()
    
    print("Rendimiento por Par de Divisas (Actualmente en Logs):")
    for _, row in pair_stats.sort_values('total_trades', ascending=False).iterrows():
        print(f"  - {row['pair']}: {int(row['total_trades'])} trades | WR: {row['win_rate']:.2f}%")
    print()
    
    # 5. Analizar otros pares sugeridos (por ejemplo, buscar cuáles tienen mejor WR con muestra > 10 trades)
    print("Analisis de Calidad y Sugerencias de Optimizacion:")
    # Pares buenos (WR > 55% y muestra >= 15 trades)
    good_pairs = pair_stats[(pair_stats['win_rate'] >= 55.0) & (pair_stats['total_trades'] >= 15)]
    # Pares malos (WR < 50% y muestra >= 15 trades)
    bad_pairs = pair_stats[(pair_stats['win_rate'] < 50.0) & (pair_stats['total_trades'] >= 15)]
    
    print("  Pares recomendados para continuar/potenciar (WR >= 55% y muestras >= 15):")
    if not good_pairs.empty:
        for _, row in good_pairs.iterrows():
            print(f"    * {row['pair']} (WR: {row['win_rate']:.2f}% | {int(row['total_trades'])} trades)")
    else:
        print("    * Ninguno con muestra suficiente")
        
    print("  Pares sugeridos para suspender/revisar (WR < 50% y muestras >= 15):")
    if not bad_pairs.empty:
        for _, row in bad_pairs.iterrows():
            print(f"    * {row['pair']} (WR: {row['win_rate']:.2f}% | {int(row['total_trades'])} trades)")
    else:
        print("    * Ninguno con muestra suficiente")

if __name__ == "__main__":
    run_analysis()
