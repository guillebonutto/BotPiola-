"""
Script de migración de base de datos de feedback.
Exporta datos actuales, crea nueva estructura con precios, y migra datos existentes.
"""
import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path

def migrate_database():
    db_path = 'feedback.db'
    backup_path = f'feedback_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    export_path = f'feedback_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    print("=== MIGRACIÓN DE BASE DE DATOS ===\n")
    
    # 1. Verificar si existe la base de datos
    if not Path(db_path).exists():
        print(f"⚠️  No se encontró {db_path}. No hay nada que migrar.")
        return
    
    # 2. Hacer backup
    print(f"📦 Creando backup: {backup_path}")
    shutil.copy(db_path, backup_path)
    
    # 3. Exportar datos actuales
    print(f"📤 Exportando datos a: {export_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM trades")
        rows = cursor.fetchall()
        trades = [dict(row) for row in rows]
        
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Exportados {len(trades)} registros")
        
        # Mostrar resumen
        if trades:
            print("\n📊 Resumen de datos exportados:")
            for trade in trades:
                print(f"  - Trade ID: {trade.get('trade_id', 'N/A')}")
                print(f"    Par: {trade.get('pair', 'N/A')}")
                print(f"    Resultado: {trade.get('result', 'N/A')}")
                print(f"    Profit: ${trade.get('profit', 0):.2f}")
                if trade.get('feedback_text'):
                    print(f"    Feedback: {trade['feedback_text'][:50]}...")
                print()
    
    except sqlite3.OperationalError as e:
        print(f"⚠️  Error leyendo datos: {e}")
        trades = []
    
    conn.close()
    
    # 4. Eliminar base de datos antigua
    print(f"🗑️  Eliminando base de datos antigua...")
    Path(db_path).unlink()
    
    # 5. Crear nueva estructura
    print(f"🔨 Creando nueva estructura con campos de precio...")
    new_conn = sqlite3.connect(db_path)
    new_cursor = new_conn.cursor()
    
    new_cursor.execute('''
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            timestamp TEXT,
            pair TEXT,
            action TEXT,
            strategy TEXT,
            timeframe TEXT,
            amount REAL,
            open_price REAL,
            close_price REAL,
            result TEXT,
            profit REAL,
            telegram_message_id INTEGER,
            feedback_text TEXT,
            feedback_image TEXT,
            feedback_timestamp TEXT
        )
    ''')
    
    # 6. Migrar datos existentes
    if trades:
        print(f"📥 Migrando {len(trades)} registros a nueva estructura...")
        
        for trade in trades:
            new_cursor.execute('''
                INSERT INTO trades (
                    trade_id, timestamp, pair, action, strategy, timeframe,
                    amount, open_price, close_price, result, profit, telegram_message_id,
                    feedback_text, feedback_image, feedback_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade.get('trade_id'),
                trade.get('timestamp'),
                trade.get('pair'),
                trade.get('action'),
                trade.get('strategy'),
                trade.get('timeframe'),
                trade.get('amount'),
                None,  # open_price (no disponible en datos antiguos)
                None,  # close_price (no disponible en datos antiguos)
                trade.get('result'),
                trade.get('profit'),
                trade.get('telegram_message_id'),
                trade.get('feedback_text'),
                trade.get('feedback_image'),
                trade.get('feedback_timestamp')
            ))
        
        new_conn.commit()
        print(f"✅ Migración completada")
    
    new_conn.close()
    
    print(f"\n✨ MIGRACIÓN EXITOSA")
    print(f"📁 Backup guardado en: {backup_path}")
    print(f"📁 Export JSON guardado en: {export_path}")
    print(f"📁 Nueva base de datos: {db_path}")
    print(f"\n⚠️  NOTA: Los trades antiguos no tienen open_price/close_price (quedan en NULL)")
    print(f"   Los nuevos trades sí tendrán estos datos.")

if __name__ == '__main__':
    migrate_database()
