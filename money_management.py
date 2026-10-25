import os
import json
import sqlite3
from datetime import datetime

STATE_FILE = "session_state.json"
DB_FILE = "feedback.db"

class MoneyManagement:
    """
    Gestión de Capital estricta basada en el Plan de Trading de Miriam Molina con
    PERSISTENCIA DE SESIÓN ANTI-SOBREOPERACIÓN (Protección ante apagones, reinicios o caídas).
    
    Reglas:
    - Capital base: $1.00 USD.
    - Interés compuesto a 2 niveles (Soros):
        * Nivel 1: Inversión base ($1.00).
        * Nivel 2: Inversión base + ganancia previa (ej: $1.00 + $0.92 = $1.92).
        * Si gana Nivel 2: Consolida ganancias y resetea a Nivel 1 ($1.00).
        * Si pierde en cualquier nivel: Reseteo inmediato a Nivel 1 ($1.00).
    - Reglas de Sesión Operativa (3W / 3L / 5 trades):
        * Máximo 5 operaciones por sesión ("5 X SESION").
        * Take Profit: 3 operaciones ganadas ("3 me retiro").
        * Stop Loss: 3 operaciones perdidas ("3 me retiro").
        * Persistencia atómica en disco para no reiniciar contadores si el bot se reinicia en el mismo día.
    """

    def __init__(self, base_amount=1.0, max_compound_levels=2, max_session_trades=5, max_wins=3, max_losses=3, 
                 state_file=STATE_FILE, db_file=DB_FILE, auto_reset_on_target=False, *args, **kwargs):
        self.base_amount = float(base_amount)
        self.current_amount = float(base_amount)
        self.max_compound_levels = int(max_compound_levels)
        self.max_session_trades = int(max_session_trades)
        self.max_wins = int(max_wins)
        self.max_losses = int(max_losses)
        self.state_file = state_file
        self.db_file = db_file
        self.auto_reset_on_target = bool(auto_reset_on_target)

        # Estado dinámico por defecto
        self.session_date = datetime.now().strftime('%Y-%m-%d')
        self.compound_level = 0 # 0 = nivel base ($1), 1 = nivel 2 ($1 + profit)
        self.session_trades = 0
        self.session_wins = 0
        self.session_losses = 0
        self.session_draws = 0
        self.session_pnl = 0.0
        self.is_session_active = True
        self.session_stop_reason = None
        self.session_reset_time = None

        # Cargar estado guardado de disco si existe (Anti-apagón / Anti-reinicio)
        self.load_persisted_state()

    def load_persisted_state(self):
        """Carga el estado de sesión del día para evitar sobreoperar si el bot se reinició o hubo apagón."""
        today = datetime.now().strftime('%Y-%m-%d')
        loaded = False

        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if data.get("session_date") == today:
                    self.session_date = today
                    self.session_trades = int(data.get("session_trades", 0))
                    self.session_wins = int(data.get("session_wins", 0))
                    self.session_losses = int(data.get("session_losses", 0))
                    self.session_draws = int(data.get("session_draws", 0))
                    self.session_pnl = float(data.get("session_pnl", 0.0))
                    self.compound_level = int(data.get("compound_level", 0))
                    self.current_amount = float(data.get("current_amount", self.base_amount))
                    self.is_session_active = bool(data.get("is_session_active", True))
                    self.session_stop_reason = data.get("session_stop_reason")
                    self.session_reset_time = data.get("session_reset_time")
                    loaded = True
            except Exception as e:
                print(f"[WARN] [Money Management] Error leyendo {self.state_file}: {e}")

        # Doble verificación contra bases de datos SQLite locales (feedback.db o bitacora_trading.db)
        candidates_db = [self.db_file, "feedback.db", "bitacora_trading.db"]
        for db_path in candidates_db:
            if db_path and os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    rows = []
                    # Intentar formato feedback.db (timestamp ISO y resultado minúscula/mayúscula)
                    try:
                        if getattr(self, 'session_reset_time', None):
                            rows = cur.execute(
                                "SELECT result, profit FROM trades WHERE timestamp >= ? AND result IN ('win', 'loss', 'draw', 'WIN', 'LOSS', 'DRAW') AND trade_id NOT LIKE 'paper_%'",
                                (self.session_reset_time,)
                            ).fetchall()
                        else:
                            rows = cur.execute(
                                "SELECT result, profit FROM trades WHERE timestamp LIKE ? AND result IN ('win', 'loss', 'draw', 'WIN', 'LOSS', 'DRAW') AND trade_id NOT LIKE 'paper_%'",
                                (f"{today}%",)
                            ).fetchall()
                    except Exception:
                        pass

                    # Si no devolvió nada, intentar formato bitacora_trading.db
                    if not rows:
                        try:
                            rows = cur.execute(
                                "SELECT resultado, beneficio FROM trades WHERE fecha = ? AND trade_id NOT LIKE 'paper_%'", 
                                (today,)
                            ).fetchall()
                        except Exception:
                            pass

                    conn.close()

                    if rows:
                        self.session_trades = len(rows)
                        self.session_wins = sum(1 for r in rows if str(r[0]).upper() == 'WIN')
                        self.session_losses = sum(1 for r in rows if str(r[0]).upper() == 'LOSS')
                        self.session_draws = sum(1 for r in rows if str(r[0]).upper() == 'DRAW')
                        self.session_pnl = round(sum(float(r[1]) for r in rows), 2)
                        if self.session_wins % 2 == 1:
                            self.compound_level = 1
                            self.current_amount = round(self.base_amount + (float(rows[-1][1]) if rows[-1][1] > 0 else 0.92), 2)
                        else:
                            self.compound_level = 0
                            self.current_amount = self.base_amount
                        loaded = True
                        break
                except Exception:
                    pass

        # Evaluar si ya se había alcanzado el retiro antes del reinicio
        if self.session_wins >= self.max_wins:
            self.is_session_active = False
            self.session_stop_reason = f"Take Profit ya alcanzado previamente ({self.session_wins}/{self.max_wins} ganadas). Retirado del mercado."
        elif self.session_losses >= self.max_losses:
            self.is_session_active = False
            self.session_stop_reason = f"Stop Loss ya alcanzado previamente ({self.session_losses}/{self.max_losses} perdidas). Retirado del mercado."
        elif self.session_trades >= self.max_session_trades:
            self.is_session_active = False
            self.session_stop_reason = f"Límite de {self.max_session_trades} operaciones ya alcanzado hoy."

        # Guardar estado sincronizado
        self.save_persisted_state()

        if loaded and self.session_trades > 0:
            print(f"[MONEY MANAGEMENT] Estado de hoy ({today}) recuperado con éxito:")
            print(f"   Ops: {self.session_trades}/{self.max_session_trades} | Score: {self.session_wins}W - {self.session_losses}L | PnL: ${self.session_pnl:+.2f} USD")
            if not self.is_session_active:
                print(f"   [AVISO] {self.session_stop_reason}")

    def save_persisted_state(self):
        """Guarda el estado de sesión en disco de forma atómica tras cada operación."""
        state = {
            "session_date": self.session_date,
            "session_trades": self.session_trades,
            "session_wins": self.session_wins,
            "session_losses": self.session_losses,
            "session_draws": self.session_draws,
            "session_pnl": round(self.session_pnl, 2),
            "compound_level": self.compound_level,
            "current_amount": round(self.current_amount, 2),
            "is_session_active": self.is_session_active,
            "session_stop_reason": self.session_stop_reason,
            "session_reset_time": getattr(self, 'session_reset_time', None)
        }
        try:
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(temp_file, self.state_file)
        except Exception as e:
            print(f"[WARN] [Money Management] No se pudo persistir el estado de sesión: {e}")

    def can_trade(self):
        """Comprueba si las reglas de la sesión permiten abrir una nueva operación."""
        today = datetime.now().strftime('%Y-%m-%d')
        # Cambio automático de fecha a medianoche (nuevo día operativo en limpio)
        if today != self.session_date:
            print(f"[MONEY MANAGEMENT] Cambio de día detectado ({self.session_date} -> {today}). Reiniciando sesión diaria.")
            self.session_date = today
            self.reset_session()
            return True, "Permitido operar (Nuevo día)"

        if not self.is_session_active:
            return False, f"Retirado del mercado. Razón: {self.session_stop_reason}"

        if self.session_wins >= self.max_wins:
            self.is_session_active = False
            self.session_stop_reason = f"Take Profit alcanzado ({self.session_wins}/{self.max_wins} ganadas). Retiro del mercado cumplido."
            self.save_persisted_state()
            return False, self.session_stop_reason

        if self.session_losses >= self.max_losses:
            self.is_session_active = False
            self.session_stop_reason = f"Stop Loss alcanzado ({self.session_losses}/{self.max_losses} perdidas). Retiro de protección cumplido."
            self.save_persisted_state()
            return False, self.session_stop_reason

        if self.session_trades >= self.max_session_trades:
            self.is_session_active = False
            self.session_stop_reason = f"Límite de operaciones por sesión alcanzado ({self.session_trades}/{self.max_session_trades})."
            self.save_persisted_state()
            return False, self.session_stop_reason

        return True, "Permitido operar"

    def get_trade_amount(self, current_balance=None, timeframe_interval=300, pair=None):
        """Retorna el importe exacto a invertir según el nivel de interés compuesto."""
        can_op, _ = self.can_trade()
        if not can_op:
            return 0.0

        if current_balance is not None and current_balance > 0:
            risk_pct = 0.01
            
            # Logic 2: Dynamic Money Management based on Pair Preferences
            if pair:
                try:
                    if os.path.exists('pair_preferences.json'):
                        with open('pair_preferences.json', 'r') as f:
                            prefs = json.load(f)
                        if pair in prefs:
                            pref = prefs[pair]
                            best_mode = pref.get('best_mode', '')
                            best_wr = pref.get('best_win_rate', 0)
                            
                            # Validar si el timeframe actual es el óptimo
                            is_optimal = False
                            if timeframe_interval == 300 and best_mode in ['M5', 'MTF']: is_optimal = True
                            if timeframe_interval == 900 and best_mode == 'M15': is_optimal = True
                            
                            if is_optimal and best_wr > 75:
                                risk_pct = 0.03 # 3% for optimal high-winrate timeframes
                            elif is_optimal and best_wr > 68:
                                risk_pct = 0.02
                except Exception:
                    pass
                    
            dynamic_base = max(self.base_amount, round(current_balance * risk_pct, 2))
        else:
            dynamic_base = self.base_amount

        if self.compound_level == 0:
            self.current_amount = dynamic_base
        return round(self.current_amount, 2)

    def register_result(self, outcome, profit, payout_pct=0.84):
        """
        Registra el resultado de la operación ('WIN', 'LOSS', 'DRAW') y actualiza:
        - Interés compuesto (Soros 2 niveles)
        - Contadores de sesión
        - Persistencia inmediata en disco
        """
        self.session_trades += 1
        self.session_pnl += profit

        if outcome == 'WIN':
            self.session_wins += 1
            if self.compound_level < (self.max_compound_levels - 1):
                # Nivel 2 de interés compuesto: base + beneficio ganado
                self.compound_level += 1
                self.current_amount = round(self.current_amount + profit, 2)
            else:
                # Se completó el ciclo de 2 niveles -> consolidar ganancias y volver a base
                self.compound_level = 0
                self.current_amount = self.base_amount

        elif outcome == 'LOSS':
            self.session_losses += 1
            # Pérdida -> reseteo inmediato a capital base
            self.compound_level = 0
            self.current_amount = self.base_amount

        else: # DRAW
            self.session_draws += 1

        # Comprobar límites de retiro
        self.can_trade()

        # Guardar en disco inmediatamente
        self.save_persisted_state()

    def reset_session(self):
        """Inicia una nueva sesión operativa en blanco y limpia el estado guardado."""
        self.compound_level = 0
        self.current_amount = self.base_amount
        self.session_trades = 0
        self.session_wins = 0
        self.session_losses = 0
        self.session_draws = 0
        self.session_pnl = 0.0
        self.is_session_active = True
        self.session_stop_reason = None
        self.session_reset_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_persisted_state()

    def get_status(self):
        """Retorna resumen legible del estado actual de la gestión."""
        return {
            "session_date": self.session_date,
            "session_active": self.is_session_active,
            "session_trades": self.session_trades,
            "session_wins": self.session_wins,
            "session_losses": self.session_losses,
            "session_draws": self.session_draws,
            "session_pnl": round(self.session_pnl, 2),
            "compound_level": self.compound_level + 1,
            "next_amount": self.current_amount,
            "stop_reason": self.session_stop_reason
        }
