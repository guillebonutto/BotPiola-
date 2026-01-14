from flask import Flask, render_template, jsonify
import sqlite3
import pandas as pd
from datetime import datetime

app = Flask(__name__)
DB_PATH = 'feedback.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    
    # 1. Win Rate General
    trades = pd.read_sql_query("SELECT * FROM trades", conn)
    if trades.empty:
        return jsonify({'win_rate': 0, 'total_profit': 0, 'total_trades': 0})
        
    total_trades = len(trades)
    wins = len(trades[trades['result'] == 'win'])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    total_profit = trades['profit'].sum()
    
    # 2. Win Rate por Estrategia
    strategy_stats = trades.groupby('strategy')['result'].apply(lambda x: (x == 'win').mean() * 100).to_dict()
    
    # 3. Equity Curve (Profit Acumulado)
    trades['timestamp'] = pd.to_datetime(trades['timestamp'])
    trades = trades.sort_values('timestamp')
    trades['cumulative_profit'] = trades['profit'].cumsum()
    
    equity_curve = {
        'labels': trades['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist(),
        'data': trades['cumulative_profit'].tolist()
    }
    
    conn.close()
    
    return jsonify({
        'win_rate': round(win_rate, 2),
        'total_profit': round(total_profit, 2),
        'total_trades': total_trades,
        'strategy_stats': strategy_stats,
        'equity_curve': equity_curve
    })

if __name__ == '__main__':
    print("🚀 Dashboard running on http://localhost:5000")
    app.run(debug=True, port=5000)
