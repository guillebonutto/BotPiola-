import pandas as pd
from pathlib import Path

csv_path = Path('paper_backtest.csv')
if not csv_path.exists():
    print("⚠️ No se encontró el archivo paper_backtest.csv en este directorio.")
    exit(0)

df = pd.read_csv(csv_path)
df_usdars = df[df['pair'] == 'USDARS_otc'].copy()

df_usdars['is_win'] = df_usdars['result'].apply(lambda x: 1 if str(x).upper() == 'WIN' else 0)
df_usdars['is_loss'] = df_usdars['result'].apply(lambda x: 1 if str(x).upper() == 'LOSS' else 0)

grouped = df_usdars.groupby(['timeframe', 'pattern_detected']).agg(
    trades=('result', 'count'),
    wins=('is_win', 'sum'),
    losses=('is_loss', 'sum'),
    pnl=('profit_loss', 'sum')
).reset_index()

grouped['win_rate'] = (grouped['wins'] / grouped['trades']) * 100

best = grouped.sort_values(by=['pnl', 'win_rate'], ascending=[False, False])
print("=== TOP ESTRATEGIAS PARA USDARS_otc EN PAPER (Ordenado por PNL) ===")
print(best.to_string(index=False))
