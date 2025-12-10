import sqlite3
import json
from datetime import datetime
from pathlib import Path

class FeedbackDB:
    def __init__(self, db_path='feedback.db'):
        self.db_path = db_path
        self.create_tables()
    
    def create_tables(self):
        """Crea la tabla de trades si no existe."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
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
        
        conn.commit()
        conn.close()
    
    def save_trade(self, trade_data):
        """
        Guarda una operación en la base de datos.
        
        Args:
            trade_data: dict con keys: trade_id, pair, action, strategy, timeframe, 
                       amount, result, profit, telegram_message_id
        
        Returns:
            trade_id de la operación guardada
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                trade_id, timestamp, pair, action, strategy, timeframe,
                amount, open_price, close_price, result, profit, telegram_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data['trade_id'],
            datetime.now().isoformat(),
            trade_data['pair'],
            trade_data['action'],
            trade_data['strategy'],
            trade_data['timeframe'],
            trade_data['amount'],
            trade_data.get('open_price'),
            trade_data.get('close_price'),
            trade_data['result'],
            trade_data['profit'],
            trade_data.get('telegram_message_id')
        ))
        
        conn.commit()
        conn.close()
        
        return trade_data['trade_id']
    
    def add_feedback(self, telegram_message_id, feedback_text, image_path=None):
        """
        Agrega feedback a una operación usando el message_id de Telegram.
        
        Args:
            telegram_message_id: ID del mensaje de Telegram al que se respondió
            feedback_text: Texto del feedback del usuario
            image_path: Ruta de la imagen guardada (opcional)
        
        Returns:
            True si se actualizó correctamente
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE trades 
            SET feedback_text = ?, 
                feedback_image = ?,
                feedback_timestamp = ?
            WHERE telegram_message_id = ?
        ''', (feedback_text, image_path, datetime.now().isoformat(), telegram_message_id))
        
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return rows_affected > 0
    
    def get_all_trades(self, limit=100):
        """Obtiene todas las operaciones con su feedback."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_trades_with_feedback(self):
        """Obtiene solo las operaciones que tienen feedback."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE feedback_text IS NOT NULL
            ORDER BY timestamp DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def export_to_json(self, output_file='feedback_export.json'):
        """Exporta todos los datos a JSON para análisis."""
        trades = self.get_all_trades(limit=10000)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
        
        return output_file
