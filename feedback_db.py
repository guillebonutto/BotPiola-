import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import os

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

        # Verificar y agregar columnas adicionales si no existen (migración dinámica)
        try:
            cursor.execute("PRAGMA table_info(trades)")
            columns = [info[1] for info in cursor.fetchall()]
            
            additional_columns = {
                'ai_decision': 'TEXT',
                'ai_confidence': 'INTEGER',
                'ai_reason': 'TEXT',
                'ai_snapshot': 'TEXT',
                'close_timestamp': 'TEXT',
                'rsi': 'REAL',
                'stoch_k': 'REAL',
                'macd_hist': 'REAL',
                'ema_distance': 'REAL',
                'atr': 'REAL'
            }
            
            for col_name, col_type in additional_columns.items():
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
                    print(f"[DB Migration] Columna '{col_name}' añadida con éxito a la tabla 'trades'.")
            conn.commit()
        except Exception as e:
            print(f"[DB Migration] Error durante la migración dinámica de columnas de IA: {e}")
        
        conn.close()
    
    def save_trade(self, trade_data):
        """
        Guarda una operación en la base de datos.
        
        Args:
            trade_data: dict con keys: trade_id, pair, action, strategy, timeframe, 
                       amount, result, profit, telegram_message_id,
                       ai_decision, ai_confidence, ai_reason, ai_snapshot,
                       close_timestamp, rsi, stoch_k, macd_hist, ema_distance, atr
        
        Returns:
            trade_id de la operación guardada
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                trade_id, timestamp, pair, action, strategy, timeframe,
                amount, open_price, close_price, result, profit, telegram_message_id,
                ai_decision, ai_confidence, ai_reason, ai_snapshot,
                close_timestamp, rsi, stoch_k, macd_hist, ema_distance, atr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data['trade_id'],
            trade_data.get('timestamp') or datetime.now().isoformat(),
            trade_data['pair'],
            trade_data['action'],
            trade_data['strategy'],
            trade_data['timeframe'],
            trade_data['amount'],
            trade_data.get('open_price'),
            trade_data.get('close_price'),
            trade_data['result'],
            trade_data['profit'],
            trade_data.get('telegram_message_id'),
            trade_data.get('ai_decision'),
            trade_data.get('ai_confidence'),
            trade_data.get('ai_reason'),
            trade_data.get('ai_snapshot'),
            trade_data.get('close_timestamp'),
            trade_data.get('rsi'),
            trade_data.get('stoch_k'),
            trade_data.get('macd_hist'),
            trade_data.get('ema_distance'),
            trade_data.get('atr')
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

    def maintain(self, days_to_keep=None):
        """Ejecuta tareas de mantenimiento: backup y optimización."""
        print("--- Iniciando mantenimiento de base de datos ---")
        self.backup()
        # self.prune_old_data(days_to_keep) # Desactivado por pedido del usuario
        self.optimize()
        print("--- Mantenimiento completado ---")

    def backup(self):
        """Crea una copia de seguridad de la base de datos."""
        try:
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"feedback_backup_{timestamp}.db"
            
            shutil.copy2(self.db_path, backup_path)
            print(f"[OK] Backup creado: {backup_path.name}")
            
            # Limpiar backups viejos (mantener solo los últimos 5)
            backups = sorted(list(backup_dir.glob("feedback_backup_*.db")), key=os.path.getmtime)
            if len(backups) > 5:
                for old_backup in backups[:-5]:
                    old_backup.unlink()
                    print(f"[INFO] Backup antiguo eliminado: {old_backup.name}")
                    
        except Exception as e:
            print(f"[WARN] Error creando backup: {e}")

    def prune_old_data(self, days):
        """Elimina registros más antiguos que N días."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            cursor.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff_date,))
            rows_deleted = cursor.rowcount
            
            conn.commit()
            conn.close()
            print(f"[OK] Limpieza: {rows_deleted} registros eliminados (anteriores a {days} días)")
        except Exception as e:
            print(f"[WARN] Error en limpieza de datos: {e}")

    def optimize(self):
        """Optimiza el archivo de base de datos."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            conn.close()
            print("[OK] Base de datos optimizada (VACUUM/ANALYZE)")
        except Exception as e:
            print(f"[WARN] Error optimizando base de datos: {e}")
