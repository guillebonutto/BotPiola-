import sqlite3
import pandas as pd

conn = sqlite3.connect('feedback.db')
query = """
    SELECT timestamp, pair, timeframe, action, result, profit, feedback_text 
    FROM trades 
    WHERE strategy LIKE '%Estoc%'
    ORDER BY timestamp DESC
"""
df = pd.read_sql_query(query, conn)
conn.close()

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 100)
pd.set_option('display.width', 1000)

print("Recent Stochastic + SMA200 Trades:")
print(df.head(40))

print("\nPerformance by Pair:")
print(df.groupby('pair').agg(
    total_trades=('result', 'count'),
    wins=('result', lambda x: (x == 'win').sum()),
    losses=('result', lambda x: (x == 'loss').sum()),
    win_rate=('result', lambda x: (x == 'win').mean() * 100)
))

print("\nPerformance by Timeframe:")
print(df.groupby('timeframe').agg(
    total_trades=('result', 'count'),
    wins=('result', lambda x: (x == 'win').sum()),
    losses=('result', lambda x: (x == 'loss').sum()),
    win_rate=('result', lambda x: (x == 'win').mean() * 100)
))
