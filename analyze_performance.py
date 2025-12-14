import sqlite3
import datetime
from pathlib import Path
import json

DB_PATH = 'feedback.db'
REPORT_FILE = 'PERFORMANCE_REPORT.md'

def get_connection():
    return sqlite3.connect(DB_PATH)

def analyze_trades(days=7):
    """Analiza los trades de los últimos 'days' días."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    
    # Obtener trades recientes
    cursor.execute('''
        SELECT * FROM trades 
        WHERE timestamp >= ? 
        ORDER BY timestamp DESC
    ''', (cutoff_date,))
    
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return trades

def generate_stats(trades):
    if not trades:
        return None
        
    total_ops = len(trades)
    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    
    win_rate = (len(wins) / total_ops * 100) if total_ops > 0 else 0
    total_profit = sum(t['profit'] for t in trades)
    
    # Análisis por estrategia
    strategies = {}
    for t in trades:
        strat = t['strategy']
        if strat not in strategies:
            strategies[strat] = {'count': 0, 'wins': 0, 'losses': 0, 'profit': 0.0}
        
        strategies[strat]['count'] += 1
        strategies[strat]['profit'] += t['profit']
        if t['result'] == 'win':
            strategies[strat]['wins'] += 1
        else:
            strategies[strat]['losses'] += 1
            
    # Calcular win rate por estrategia
    for strat in strategies:
        s = strategies[strat]
        s['win_rate'] = (s['wins'] / s['count'] * 100) if s['count'] > 0 else 0

    return {
        'total_ops': total_ops,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'total_profit': total_profit,
        'strategies': strategies,
        'raw_trades': trades
    }

def create_report_for_ai(stats):
    """Genera un reporte en Markdown optimizado para que la IA (Gemini) lo lea."""
    if not stats:
        print("⚠️ No hay datos suficientes para generar reporte.")
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = f"""# 🤖 Reporte de Rendimiento del Bot
**Fecha:** {timestamp}

## 📊 Resumen General
- **Total Operaciones:** {stats['total_ops']}
- **Win Rate Global:** {stats['win_rate']:.2f}%
- **Profit Total:** ${stats['total_profit']:.2f}
- **Wins:** {stats['wins']} | **Losses:** {stats['losses']}

## 📈 Rendimiento por Estrategia
"""

    for name, data in stats['strategies'].items():
        icon = "✅" if data['profit'] > 0 else "❌"
        report += f"""
### {icon} {name}
- **Operaciones:** {data['count']}
- **Win Rate:** {data['win_rate']:.2f}%
- **Profit:** ${data['profit']:.2f}
- **Wins/Losses:** {data['wins']}/{data['losses']}
"""
    
    report += "\n## 📝 Feedback de Usuarios (Últimos 10)\n"
    
    trades_with_feedback = [t for t in stats['raw_trades'] if t.get('feedback_text')]
    if trades_with_feedback:
        for t in trades_with_feedback[:10]:
            report += f"- **{t['strategy']}** ({t['result']}): \"{t['feedback_text']}\"\n"
    else:
        report += "No hay feedback registrado recientemente.\n"
        
    report += """
---
## 🧠 Instrucciones para la IA
Por favor, analiza estos datos y propón mejoras concretas en el código:
1. Identifica qué estrategia está fallando más.
2. Basado en el feedback (si hay), ¿cuál es la causa raíz logica? (falsos positivos, tendencia, etc).
3. Escribe el bloque de código corregido para `strategy_*.py` o `main.py` para solucionar el problema.
"""

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(f"\n✅ Reporte generado exitosamente: {REPORT_FILE}")
    print("👉 Abre este archivo, COPIA su contenido y PÉGALO en el chat con tu Asistente de IA.")

if __name__ == "__main__":
    print("🔍 Analizando base de datos...")
    data = analyze_trades(days=7)
    stats = generate_stats(data)
    create_report_for_ai(stats)
