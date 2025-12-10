"""
Script para agregar trades manualmente a la base de datos.
Útil para recuperar operaciones históricas de las que solo tenés mensajes de Telegram.
"""
import sqlite3
from datetime import datetime

def add_manual_trade():
    """Agrega un trade manualmente a la base de datos."""
    
    print("\n=== AGREGAR TRADE MANUAL ===\n")
    
    # Recopilar datos
    print("Ingresá los datos del trade (dejá en blanco si no lo tenés):\n")
    
    pair = input("Par (ej: EURUSD_otc): ").strip()
    action = input("Acción (BUY/SELL): ").strip().upper()
    strategy = input("Estrategia: ").strip()
    timeframe = input("Timeframe (ej: 5min): ").strip()
    
    amount_str = input("Monto apostado (default: 1.0): ").strip()
    amount = float(amount_str) if amount_str else 1.0
    
    open_price_str = input("Precio de entrada (open_price): ").strip()
    open_price = float(open_price_str) if open_price_str else None
    
    close_price_str = input("Precio de cierre (close_price): ").strip()
    close_price = float(close_price_str) if close_price_str else None
    
    result = input("Resultado (win/loss): ").strip().lower()
    
    profit_str = input("Profit (ej: 0.92 o -1.0): ").strip()
    profit = float(profit_str) if profit_str else 0.0
    
    feedback_text = input("Feedback (opcional): ").strip()
    feedback_image = input("Ruta de imagen (opcional): ").strip()
    
    # Generar trade_id único
    trade_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    timestamp = datetime.now().isoformat()
    
    # Mostrar resumen
    print("\n📋 RESUMEN DEL TRADE:")
    print(f"  Trade ID: {trade_id}")
    print(f"  Par: {pair}")
    print(f"  Acción: {action}")
    print(f"  Estrategia: {strategy}")
    print(f"  Timeframe: {timeframe}")
    print(f"  Monto: ${amount}")
    print(f"  Precio entrada: {open_price if open_price else 'N/A'}")
    print(f"  Precio cierre: {close_price if close_price else 'N/A'}")
    print(f"  Resultado: {result}")
    print(f"  Profit: ${profit}")
    if feedback_text:
        print(f"  Feedback: {feedback_text[:50]}...")
    if feedback_image:
        print(f"  Imagen: {feedback_image}")
    
    confirm = input("\n¿Guardar este trade? (s/n): ").strip().lower()
    
    if confirm != 's':
        print("❌ Trade cancelado")
        return False
    
    # Guardar en base de datos
    try:
        conn = sqlite3.connect('feedback.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                trade_id, timestamp, pair, action, strategy, timeframe,
                amount, open_price, close_price, result, profit, telegram_message_id,
                feedback_text, feedback_image, feedback_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_id,
            timestamp,
            pair,
            action,
            strategy,
            timeframe,
            amount,
            open_price,
            close_price,
            result,
            profit,
            None,  # telegram_message_id (no disponible para trades manuales)
            feedback_text if feedback_text else None,
            feedback_image if feedback_image else None,
            timestamp if feedback_text else None
        ))
        
        conn.commit()
        conn.close()
        
        print("✅ Trade guardado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error guardando trade: {e}")
        return False

def main():
    print("🤖 HERRAMIENTA DE INGRESO MANUAL DE TRADES")
    print("=" * 50)
    
    while True:
        success = add_manual_trade()
        
        another = input("\n¿Agregar otro trade? (s/n): ").strip().lower()
        if another != 's':
            break
    
    # Mostrar resumen final
    conn = sqlite3.connect('feedback.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]
    conn.close()
    
    print(f"\n✨ Total de trades en la base de datos: {total}")
    print("Podés ver todos con: python -c \"from feedback_db import FeedbackDB; db = FeedbackDB(); print(db.get_all_trades())\"")

if __name__ == '__main__':
    main()
