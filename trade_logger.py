"""
trade_logger.py
===============
Sistema de logging de trades con estructura detallada.
Guarda cada operación en CSV con indicadores técnicos.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import json
from supabase import create_client, Client


class TradeLogger:
    """Logger para guardar trades en CSV con estructura detallada."""
    
    def __init__(self, logs_dir="logs/trades", filename_pattern="trades_{date}.csv"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.filename_pattern = filename_pattern
        self.current_file = None
        self.headers = None
        self._ensure_file()
        self._init_supabase()
    
    def _init_supabase(self):
        """Inicializar cliente de Supabase."""
        try:
            config_path = Path('config.json')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                url = config.get("supabase_url")
                key = config.get("supabase_key")
                
                if url and key:
                    self.supabase: Client = create_client(url, key)
                    print("✅ Supabase conectado en TradeLogger")
                else:
                    self.supabase = None
            else:
                self.supabase = None
        except Exception as e:
            print(f"⚠️ Error inicializando Supabase en TradeLogger: {e}")
            self.supabase = None
    
    def _get_filename(self):
        """Obtener nombre del archivo basado en la fecha."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.logs_dir / self.filename_pattern.format(date=date_str)
    
    def _ensure_file(self):
        """Crear archivo si no existe o si tiene headers incorrectos."""
        filename = self._get_filename()
        
        # Cambiar de archivo si pasamos a nuevo día
        if self.current_file != filename:
            self.current_file = filename
            self.headers = self._get_headers()
            
            # Si el archivo existe, verificar headers
            if filename.exists():
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        existing_headers = next(reader, [])
                        
                    # Si los headers no coinciden (ej. por corrupción de test), renombrar
                    if len(existing_headers) < len(self.headers):
                        print(f"⚠️ Headers de log incorrectos en {filename.name}. Renombrando...")
                        backup_name = filename.with_suffix(f".corrupted_{int(datetime.now().timestamp())}.csv")
                        filename.rename(backup_name)
                except Exception as e:
                    print(f"⚠️ Error verificando headers: {e}")

            # Si es archivo nuevo (o renombrado), crear con headers
            if not filename.exists():
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=self.headers)
                    writer.writeheader()
    
    def _get_headers(self):
        """Definir estructura de headers."""
        return [
            # Identificación
            'timestamp',
            'trade_id',
            'pair',
            'timeframe',
            
            # Decisión
            'decision',
            'signal_score',
            'pattern_detected',
            
            # Indicadores técnicos
            'price',
            'ema',
            'rsi',
            'ema_conf',
            'tf_signal',
            'atr',
            'triangle_active',
            'reversal_candle',
            
            # Niveles
            'near_support',
            'near_resistance',
            'support_level',
            'resistance_level',
            
            # Higher Timeframe
            'htf_signal',
            
            # Resultado
            'result',
            'profit_loss',
            'expiry_time',
            
            # Meta
            'notes'
        ]
    
    def log_trade(self, trade_data):
        """
        Registrar un trade en el CSV.
        
        Args:
            trade_data (dict): Diccionario con datos del trade
                - timestamp: datetime del trade
                - trade_id: ID de la operación
                - pair: Par (EURUSD_otc, etc)
                - timeframe: TF (M5, M15, etc)
                - decision: BUY o SELL
                - signal_score: Score numérico
                - pattern_detected: Nombre del patrón o indicadores
                - price: Precio actual
                - ema: Valor de EMA
                - rsi: Valor RSI
                - ema_conf: -1, 0, 1
                - tf_signal: -1, 0, 1
                - atr: Average True Range
                - triangle_active: 0 o 1
                - reversal_candle: 0 o 1
                - near_support: True/False
                - near_resistance: True/False
                - support_level: Precio
                - resistance_level: Precio
                - htf_signal: -1, 0, 1
                - result: 'WIN', 'LOSS', o 'PENDING'
                - profit_loss: Cantidad
                - expiry_time: segundos
                - notes: Campo libre
        """
        self._ensure_file()
        
        # Normalizar datos
        row = {}
        for header in self.headers:
            row[header] = trade_data.get(header, '')
        
        # Convertir timestamp si es datetime
        if isinstance(row['timestamp'], datetime):
            row['timestamp'] = row['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(row['timestamp'], 'strftime'):
            row['timestamp'] = row['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        
        # Escribir fila
        try:
            with open(self.current_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writerow(row)
            return True
        except Exception as e:
            print(f"❌ Error escribiendo trade log: {e}")
            return False
        finally:
            self._sync_to_supabase(row)

    def _sync_to_supabase(self, row):
        """Sincronizar una fila con Supabase."""
        if not hasattr(self, 'supabase') or not self.supabase:
            return
        
        try:
            # Limpiar datos para Supabase (reemplazar strings vacíos por None)
            clean_row = {k: (v if v != '' else None) for k, v in row.items()}
            self.supabase.table("trades").upsert(clean_row).execute()
        except Exception as e:
            print(f"⚠️ Error sincronizando con Supabase: {e}")
    
    def update_trade_result(self, trade_id, result, profit_loss=None, notes=None):
        """
        Actualizar resultado de un trade existente.
        
        Args:
            trade_id: ID del trade a actualizar
            result: 'WIN' o 'LOSS'
            profit_loss: Monto ganado/perdido
            notes: Notas adicionales
        """
        self._ensure_file()
        
        try:
            # Leer el archivo
            df = pd.read_csv(self.current_file)
            
            # Buscar y actualizar
            mask = df['trade_id'] == str(trade_id)
            if mask.any():
                df.loc[mask, 'result'] = result
                if profit_loss is not None:
                    df.loc[mask, 'profit_loss'] = profit_loss
                if notes is not None:
                    df.loc[mask, 'notes'] = notes
                
                # Guardar
                df.to_csv(self.current_file, index=False, encoding='utf-8')
                
                # Sincronizar actualización con Supabase
                if hasattr(self, 'supabase') and self.supabase:
                    try:
                        update_data = {'result': result}
                        if profit_loss is not None:
                            update_data['profit_loss'] = profit_loss
                        if notes is not None:
                            update_data['notes'] = notes
                        
                        self.supabase.table("trades").update(update_data).eq("trade_id", str(trade_id)).execute()
                    except Exception as e:
                        print(f"⚠️ Error actualizando Supabase: {e}")
                
                return True
        except Exception as e:
            print(f"❌ Error actualizando trade result: {e}")
        
        return False
    
    def get_todays_trades(self):
        """Obtener trades de hoy."""
        self._ensure_file()
        
        try:
            df = pd.read_csv(self.current_file)
            return df
        except Exception as e:
            print(f"❌ Error leyendo trades: {e}")
            return pd.DataFrame()
    
    def get_stats(self):
        """Calcular estadísticas básicas del día."""
        df = self.get_todays_trades()
        
        if df.empty:
            return {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'pending': 0,
                'winrate': 0,
                'total_profit': 0
            }
        
        stats = {
            'total': len(df),
            'wins': len(df[df['result'] == 'WIN']),
            'losses': len(df[df['result'] == 'LOSS']),
            'pending': len(df[df['result'] == 'PENDING']),
            'total_profit': df['profit_loss'].sum() if 'profit_loss' in df.columns else 0
        }
        
        if stats['wins'] + stats['losses'] > 0:
            stats['winrate'] = stats['wins'] / (stats['wins'] + stats['losses']) * 100
        else:
            stats['winrate'] = 0
        
        return stats

    def cleanup_old_logs(self, days=30):
        """Elimina archivos de log más antiguos que N días."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            for log_file in self.logs_dir.glob("trades_*.csv"):
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff:
                    log_file.unlink()
                    print(f"🗑️ Log antiguo eliminado: {log_file.name}")
        except Exception as e:
            print(f"⚠️ Error limpiando logs: {e}")


# Instancia global
trade_logger = TradeLogger()
