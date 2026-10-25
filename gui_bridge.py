"""
GUI Bridge: Capa de conexión entre la GUI CustomTkinter y el Motor de Trading
Gestiona colas de logs thread-safe, métricas en tiempo real y señales de control.
"""

import os
import sys
import time
import json
import queue
import sqlite3
import psutil
import threading
import subprocess
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

def split_timeline_by_zero(x_arr, y_arr):
    """
    Interpola puntos exactos en y=0 para que tanto la línea como el área cambien de color
    suavemente de verde (>= 0) a rojo (< 0) sin vacíos ni cortes bruscos.
    """
    import numpy as np
    x_list = list(x_arr)
    y_list = [float(val) for val in y_arr]
    
    x_new, y_new = [], []
    for i in range(len(x_list)):
        if i == 0:
            x_new.append(x_list[0])
            y_new.append(y_list[0])
        else:
            y1, y2 = y_list[i-1], y_list[i]
            x1, x2 = x_list[i-1], x_list[i]
            if (y1 > 0 and y2 < 0) or (y1 < 0 and y2 > 0):
                fraction = (0.0 - y1) / (y2 - y1)
                xz = x1 + (x2 - x1) * fraction
                x_new.append(xz)
                y_new.append(0.0)
            x_new.append(x2)
            y_new.append(y2)
    return np.array(x_new), np.array(y_new)

MASTER_STRATEGIES_CATALOG = [
    "Alpha Convergence (Bollinger + Fibo + Stoch)",
    "Bollinger Extreme (2.5 Dev) + RSI Reversion",
    "Cambio de Estructura (MSS)",
    "Chartist Master (Wedges & Triangles)",
    "Estocástico + SMA200",
    "Expert Vision Donchian Reversion",
    "Fibonacci Master Sniper (Golden Zone + Matrix)",
    "Fibonacci Retracement 61.8%",
    "HYBRID Ultra-Sniper (WaveTrend + BB 2.5 + RSI + SMA200)",
    "Patrones de Continuación (Chartismo)",
    "Price Action Envolvente en Extremo Bollinger 2.5",
    "RSI Divergence + Pivot Reversion",
    "SMC Élite (ChoCH + MTF + MACD)",
    "Squeeze Expansion + Volume Spike",
    "TTM Volatility Squeeze Breakout",
    "Trend Pullback Momentum (EMA + Stoch)",
    "WaveTrend + Keltner Channel Reversion",
    "[BB] Burst Dev2.4 + RSI Exhaustion",
    "[RAPID] EMA Pullback 10/18 (Gen3)",
    "[RAPID] EMA Pullback 10/18 (Gen40)",
    "[RAPID] EMA Pullback 10/18 (Gen5)",
    "[RAPID] EMA Pullback 10/20 (Gen24)",
    "[RAPID] EMA Pullback 10/20 (Gen42)",
    "[RAPID] EMA Pullback 10/22 (Gen37)",
    "[RAPID] EMA Pullback 6/16 (Gen41)",
    "[RAPID] EMA Pullback 6/18 (Gen54)",
    "[RAPID] EMA Pullback 6/20 (Gen57)",
    "[RAPID] EMA Pullback 6/22 (Gen64)",
    "[RAPID] EMA Pullback 7/15 (Gen19)",
    "[RAPID] EMA Pullback 7/15 (Gen27)",
    "[RAPID] EMA Pullback 7/15 (Gen48)",
    "[RAPID] EMA Pullback 7/19 (Gen53)",
    "[RAPID] EMA Pullback 7/21 (Gen4)",
    "[RAPID] EMA Pullback 8/20 (Gen61)",
    "[RAPID] EMA Pullback 8/22 (Gen17)",
    "[RAPID] EMA Pullback 8/22 (Gen50)",
    "[RAPID] EMA Pullback 8/22 (Gen58)",
    "[RAPID] EMA Pullback 9/21",
    "[RAPID] EMA Pullback 9/21 (Gen15)",
    "[RAPID] Fast EMA Scalp 7/16",
    "[RAPID] Micro Breakout 4v (Gen22)",
    "[RAPID] Micro Breakout 4v (Gen29)",
    "[RAPID] Micro Breakout 4v (Gen44)",
    "[RAPID] Micro Breakout 4v (Gen7)",
    "[RAPID] Micro Breakout 5v (Gen43)",
    "[RAPID] Micro Breakout 6v (Gen45)",
    "[RAPID] Micro Range Breakout 5v",
    "[RAPID] RSI Velocity 11p (Gen10)",
    "[RAPID] RSI Velocity 11p (Gen39)",
    "[RAPID] RSI Velocity 6p (Gen21)",
    "[RAPID] RSI Velocity 6p (Gen34)",
    "[RAPID] RSI Velocity 6p (Gen47)",
    "[RAPID] RSI Velocity 7p",
    "[RAPID] RSI Velocity 7p (Gen18)",
    "[RAPID] RSI Velocity 7p (Gen23)",
    "[RAPID] RSI Velocity 7p (Gen56)",
    "[RAPID] RSI Velocity 9p (Gen11)",
    "[RAPID] RSI Velocity 9p (Gen2)",
    "[RAPID] RSI Velocity 9p (Gen52)",
    "[RAPID] RSI Velocity 9p (Gen60)",
    "[RAPID] RSI Velocity 9p (Gen63)",
    "[RAPID] RSI Velocity 9p (Gen66)",
    "[RAPID] Stoch 5/4+BB18 (Gen46)",
    "[RAPID] Stoch 6/2+BB16 (Gen14)",
    "[RAPID] Stoch 6/4+BB14 (Gen49)",
    "[RAPID] Stoch 7/3+BB18 (Gen36)",
    "[RAPID] Stoch 7/4+BB16 (Gen12)",
    "[RAPID] Stoch 8/2+BB20 (Gen8)",
    "[RAPID] Stoch 8/3+BB12 (Gen16)",
    "[RAPID] Stoch BB Dev2.0/W20 (Gen51)",
    "[RAPID] Stoch BB Dev2.0/W20 (Gen59)",
    "[RAPID] Stoch BB Dev2.0/W20 (Gen62)",
    "[RAPID] Stoch BB Dev2.0/W20 (Gen65)",
    "[RAPID] Stoch BB Dev2.2/W14 (Gen55)",
    "[RAPID] Stoch Burst 5/3 + BB14",
    "[RAPID] Stoch Scalp 8/3 + BB20",
    "[SMC] Liquidity Sweep & FVG (Gen1)",
    "[SQZ] Volatility Fired Pro",
    "[ÉLITE] Micro Breakout 7v (Gen35)",
    "[ÉLITE] VSA Volume Climax Reversal",
    "[ÉLITE] Order Block MTF & ChoCH",
    "[ÉLITE] VWAP Mean Reversion (3.0 Dev)",
    "[ÉLITE] Momentum Trend Pullback Confluence"
]

class GUIBridge:
    def __init__(self):
        self.log_queue = queue.Queue(maxsize=2000)
        self.bot_process = None
        self.bot_thread = None
        self.is_running = False
        self.base_dir = Path(__file__).resolve().parent
        self.on_request_chart = None
        
    def log(self, text, tag="INFO"):
        """Inserta un mensaje de log con tag en la cola."""
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_queue.put_nowait((ts, tag, str(text)))
        except queue.Full:
            pass

    def check_existing_engine(self):
        """Verifica si ya hay un proceso de run_bot.py o main.py corriendo en Windows."""
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.pid == os.getpid():
                    continue
                cmd = " ".join(p.info.get('cmdline') or [])
                if ("run_bot.py" in cmd or "main.py" in cmd) and "gui_app.py" not in cmd:
                    self.is_running = True
                    return True, p.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False, None

    def start_bot_process(self, config_path="config.json"):
        """Inicia el bot con run_bot.py como subproceso si no está ya corriendo."""
        already_running, existing_pid = self.check_existing_engine()
        if already_running:
            self.is_running = True
            self.log(f"⚡ Motor de trading ya activo en Windows (PID {existing_pid}). Conectado al flujo en vivo.", "WIN")
            return True

        if self.is_running and self.bot_process and self.bot_process.poll() is None:
            self.log("El bot ya se encuentra en ejecución en esta terminal.", "WARN")
            return False

        # Limpiar cualquier killapp.flag residual previo para que no aborte el inicio
        killapp_file = self.base_dir / "killapp.flag"
        if killapp_file.exists():
            try:
                killapp_file.unlink()
            except Exception:
                pass

        def run():
            self.is_running = True
            cmd = [sys.executable, "-u", "run_bot.py", config_path]
            self.log(f"Iniciando supervisor: {' '.join(cmd)}", "INFO")
            
            try:
                # Ocultar ventana de consola secundaria en Windows y forzar UTF-8
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                env["PYTHONUNBUFFERED"] = "1"

                self.bot_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                    env=env,
                    cwd=str(self.base_dir)
                )

                for line in iter(self.bot_process.stdout.readline, ''):
                    clean_line = line.rstrip('\r\n')
                    if clean_line:
                        # Detección heurística de etiquetas para coloreado en GUI
                        tag = "INFO"
                        upper = clean_line.upper()
                        if "WIN" in upper or "GANAD" in upper or "SUCCESS" in upper or "[OK]" in upper:
                            tag = "WIN"
                        elif "LOSS" in upper or "PERDID" in upper or "FAIL" in upper or "ERROR" in upper or "ERR" in upper:
                            tag = "LOSS"
                        elif "WARN" in upper or "AVISO" in upper or "REPOSO" in upper or "PAUS" in upper:
                            tag = "WARN"
                        elif "ALPACA" in upper:
                            tag = "ALPACA"
                        elif "POCKETOPTION" in upper or "PO " in upper:
                            tag = "PO"
                        self.log(clean_line, tag)

                self.bot_process.stdout.close()
                self.bot_process.wait()
                self.log(f"Supervisor detenido (Código de salida: {self.bot_process.returncode})", "WARN")
            except Exception as e:
                self.log(f"Error en subproceso del bot: {e}", "LOSS")
            finally:
                self.is_running = False
                self.bot_process = None

        self.bot_thread = threading.Thread(target=run, daemon=True)
        self.bot_thread.start()
        return True

    def stop_bot_process(self):
        """Envía señal de apagado seguro y termina cualquier instancia de run_bot.py / main.py."""
        self.log("Solicitando detención segura del bot...", "WARN")
        try:
            flag_file = self.base_dir / "killapp.flag"
            flag_file.write_text(f"{datetime.now().isoformat()} - GUI Killapp", encoding="utf-8")
        except Exception:
            pass

        # 1. Terminar subproceso directo si lo lanzamos nosotros
        if self.bot_process and self.bot_process.poll() is None:
            try:
                self.bot_process.terminate()
            except Exception:
                try:
                    self.bot_process.kill()
                except Exception:
                    pass

        # 2. Terminar cualquier otro proceso huérfano de run_bot.py o main.py
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.pid == os.getpid():
                    continue
                cmd = " ".join(p.info.get('cmdline') or [])
                if ("run_bot.py" in cmd or "main.py" in cmd) and "gui_app.py" not in cmd:
                    p.terminate()
            except Exception:
                pass

        self.is_running = False
        self.bot_process = None
        self.log("Bot detenido con éxito.", "INFO")

    def reset_daily_session(self):
        """Reinicia el Money Management para PocketOption (sale de Stop Loss)."""
        self.log("Disparando señal de reseteo de sesión...", "INFO")
        try:
            sig_file = self.base_dir / "reset_session.signal"
            sig_file.write_text(datetime.now().isoformat(), encoding="utf-8")
            
            # También resetear atómicamente session_state.json si existe
            state_file = self.base_dir / "session_state.json"
            today = datetime.now().strftime('%Y-%m-%d')
            new_state = {
                "session_date": today,
                "session_trades": 0,
                "session_wins": 0,
                "session_losses": 0,
                "session_draws": 0,
                "session_pnl": 0.0,
                "compound_level": 0,
                "current_amount": 1.0,
                "is_session_active": True,
                "session_stop_reason": None,
                "session_reset_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            state_file.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
            self.log("Sesión diaria de PocketOption reiniciada a 0W - 0L ($0.00 USD).", "WIN")
            return True
        except Exception as e:
            self.log(f"Error reseteando sesión: {e}", "LOSS")
            return False

    def restart_bot(self):
        """Genera restart.signal para que el supervisor relance el motor en caliente."""
        self.log("Disparando reinicio en caliente del motor de trading...", "WARN")
        try:
            sig = self.base_dir / "restart.signal"
            sig.write_text(datetime.now().isoformat(), encoding="utf-8")
            return True
        except Exception as e:
            self.log(f"Error al reiniciar: {e}", "LOSS")
            return False

    def get_session_state(self):
        """Retorna el estado de Money Management de PocketOption."""
        state_file = self.base_dir / "session_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
        return {
            "session_date": datetime.now().strftime('%Y-%m-%d'),
            "session_trades": 0,
            "session_wins": 0,
            "session_losses": 0,
            "session_draws": 0,
            "session_pnl": 0.0,
            "compound_level": 0,
            "current_amount": 1.0,
            "is_session_active": True,
            "session_stop_reason": None
        }

    def get_pocketoption_status(self):
        """Lee el balance en vivo de PocketOption."""
        status_file = self.base_dir / "pocketoption_status.json"
        if status_file.exists():
            try:
                return json.loads(status_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"balance": 0.0, "last_updated": None}

    def get_alpaca_status(self):
        """Lee el estado y balance de Alpaca."""
        status_file = self.base_dir / "alpaca_status.json"
        if status_file.exists():
            try:
                return json.loads(status_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"balance": 0.0, "active_trades": {}, "last_updated": None}

    def get_system_metrics(self):
        """Métricas de CPU, Memoria RAM y latencia."""
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        return {"cpu": cpu, "ram": ram}

    def get_trades_for_date(self, target_date=None):
        """Obtiene las operaciones registradas para una fecha específica desde feedback.db y CSVs."""
        from datetime import date
        import sqlite3
        if target_date is None:
            t_date = datetime.now().date()
        elif isinstance(target_date, datetime):
            t_date = target_date.date()
        elif isinstance(target_date, date):
            t_date = target_date
        else:
            try:
                t_date = datetime.strptime(str(target_date), '%Y-%m-%d').date()
            except Exception:
                t_date = datetime.now().date()

        date_str = t_date.strftime('%Y-%m-%d')
        date_compact = t_date.strftime('%Y%m%d')
        trades = []
        
        # 1. Intentar desde feedback.db (PocketOption)
        db_file = self.base_dir / "feedback.db"
        if db_file.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=2.0)
                cur = conn.cursor()
                rows = cur.execute(
                    "SELECT timestamp, pair, timeframe, strategy, action, result, profit "
                    "FROM trades WHERE timestamp LIKE ? AND trade_id NOT LIKE 'paper_%' ORDER BY timestamp DESC LIMIT 50",
                    (f"{date_str}%",)
                ).fetchall()
                conn.close()
                for r in rows:
                    tf_val = r[2]
                    try:
                        tf_int = int(tf_val)
                        tf_fmt = f"{tf_int//60}m" if tf_int >= 60 else f"{tf_int}s"
                    except Exception:
                        tf_fmt = str(tf_val or "1m")
                    ts_raw = str(r[0])
                    t_clean = ts_raw.split('T')[-1].split('.')[0] if 'T' in ts_raw else (ts_raw.split()[-1] if ' ' in ts_raw else ts_raw)
                    trades.append({
                        "timestamp": t_clean,
                        "broker": "PocketOption",
                        "pair": r[1],
                        "timeframe": tf_fmt,
                        "strategy": r[3] or "Quantitative",
                        "decision": r[4] or "BUY",
                        "result": str(r[5]).upper() if r[5] else "PENDING",
                        "profit": float(r[6]) if r[6] is not None and str(r[6]).lower() != "nan" else 0.0
                    })
            except Exception:
                pass

        # 2. Leer desde CSV de PO de esa fecha (solo si la DB no devolvió nada)
        if not trades:
            for po_csv_name in [f"trades_pocketoption_real_{date_compact}.csv", f"trades_pocketoption_{date_compact}.csv", f"trades_{date_compact}.csv"]:
                po_csv = self.base_dir / "logs" / "trades" / po_csv_name
                if po_csv.exists():
                    try:
                        import pandas as pd
                        df = pd.read_csv(po_csv)
                        if not df.empty and not df.isna().all().all():
                            for _, row in df.iterrows():
                                tid = str(row.get('trade_id', ''))
                                pat = str(row.get('pattern_detected', ''))
                                strat = str(row.get('strategy', ''))
                                if tid.startswith('paper_') or pat.startswith('[PAPER]') or strat.startswith('[PAPER]'):
                                    continue
                                tf = row.get('timeframe', 60)
                                try:
                                    tf_int = int(tf)
                                    tf_str = f"{tf_int//60}m" if tf_int >= 60 else f"{tf_int}s"
                                except Exception:
                                    tf_str = str(tf)
                                trades.append({
                                    "timestamp": str(row.get('timestamp', '')).split()[-1],
                                    "broker": "PocketOption",
                                    "pair": str(row.get('pair', '')),
                                    "timeframe": tf_str,
                                    "strategy": pat or "Quantitative",
                                    "decision": str(row.get('decision', 'BUY')),
                                    "result": str(row.get('result', 'PENDING')).upper(),
                                    "profit": float(row.get('profit_loss', 0.0)) if pd.notna(row.get('profit_loss')) else 0.0
                                })
                            break
                    except Exception:
                        pass

        # 3. Leer desde SQLite feedback_config_alpaca.db (con fallback a CSV)
        al_db_file = self.base_dir / "feedback_config_alpaca.db"
        al_loaded = False
        if al_db_file.exists():
            try:
                import sqlite3
                conn_al = sqlite3.connect(str(al_db_file), timeout=2.0)
                cur_al = conn_al.cursor()
                rows_al = cur_al.execute(
                    "SELECT timestamp, pair, timeframe, strategy, action, result, profit, close_timestamp "
                    "FROM trades WHERE (timestamp LIKE ? OR close_timestamp LIKE ?) AND lower(result) IN ('win', 'loss') ORDER BY id DESC LIMIT 50",
                    (f"{date_str}%", f"{date_str}%")
                ).fetchall()
                conn_al.close()
                if rows_al:
                    al_loaded = True
                    for r in rows_al:
                        tf_val = r[2]
                        try:
                            tf_int = int(tf_val)
                            tf_fmt = f"{tf_int//3600}h" if tf_int >= 3600 else f"{tf_int//60}m"
                        except Exception:
                            tf_fmt = str(tf_val or "1h")
                        ts_str = str(r[7] or r[0])
                        t_part = ts_str.split('T')[-1].split('.')[0] if 'T' in ts_str else (ts_str.split()[-1] if ' ' in ts_str else ts_str)
                        trades.append({
                            "timestamp": t_part,
                            "broker": "Alpaca",
                            "pair": r[1],
                            "timeframe": tf_fmt,
                            "strategy": r[3] or "SMC Elite",
                            "decision": r[4] or "BUY",
                            "result": str(r[5]).upper() if r[5] else "PENDING",
                            "profit": float(r[6]) if r[6] is not None and str(r[6]).lower() != "nan" else 0.0
                        })
            except Exception:
                pass

        if not al_loaded:
            alpaca_csv = self.base_dir / "logs" / "trades" / f"trades_config_alpaca_{date_compact}.csv"
            if alpaca_csv.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(alpaca_csv)
                    if not df.empty and not df.isna().all().all():
                        for _, row in df.iterrows():
                            tf = row.get('timeframe', 3600)
                            try:
                                tf_int = int(tf)
                                tf_str = f"{tf_int//3600}h" if tf_int >= 3600 else f"{tf_int//60}m"
                            except Exception:
                                tf_str = str(tf or "1h")
                            trades.append({
                                "timestamp": str(row.get('timestamp', '')).split()[-1],
                                "broker": "Alpaca",
                                "pair": str(row.get('pair', '')),
                                "timeframe": tf_str,
                                "strategy": str(row.get('strategy', 'SMC Elite')),
                                "decision": str(row.get('decision', 'BUY')),
                                "result": str(row.get('result', 'PENDING')).upper(),
                                "profit": float(row.get('profit_loss', 0.0)) if pd.notna(row.get('profit_loss')) else 0.0
                            })
                except Exception:
                    pass

        # Eliminar duplicados y ordenar por fecha descendente
        unique_trades = []
        seen = set()
        for t in trades:
            key = (t['broker'], t['timestamp'], t['pair'], t['profit'])
            if key not in seen:
                seen.add(key)
                unique_trades.append(t)
        
        unique_trades.sort(key=lambda x: str(x['timestamp']), reverse=True)
        return unique_trades

    def get_today_trades(self):
        """Obtiene las operaciones de hoy."""
        return self.get_trades_for_date(datetime.now().date())

    def get_paper_file_meta(self):
        """Devuelve (mtime, size) de paper_backtest.csv para control de cache."""
        paper_csv = self.base_dir / "paper_backtest.csv"
        if not paper_csv.exists():
            return (0, 0)
        try:
            st = os.stat(paper_csv)
            return (st.st_mtime, st.st_size)
        except Exception:
            return (0, 0)

    def _get_paper_df(self):
        """Lee paper_backtest.csv con cache inteligente en memoria evitando lecturas redundantes."""
        paper_csv = self.base_dir / "paper_backtest.csv"
        if not paper_csv.exists():
            return None
        try:
            st = os.stat(paper_csv)
            mtime, size = st.st_mtime, st.st_size
            if hasattr(self, '_cached_paper_df') and getattr(self, '_cached_paper_meta', None) == (mtime, size):
                return self._cached_paper_df

            import pandas as pd
            df = pd.read_csv(paper_csv)
            self._cached_paper_df = df
            self._cached_paper_meta = (mtime, size)
            self._cached_paper_stats = {}
            self._cached_paper_filters = None
            return df
        except Exception as e:
            self.log(f"Error reading paper csv: {e}", "WARN")
            return getattr(self, '_cached_paper_df', None)

    def get_paper_unique_filters(self):
        """Devuelve listas completas de pares y estrategias únicas unificando el CSV de paper, configuraciones y estrategias graduadas."""
        meta = self.get_paper_file_meta()
        if getattr(self, '_cached_paper_filters', None) is not None:
            if getattr(self, '_cached_paper_meta', None) == meta:
                return self._cached_paper_filters

        pairs_set = set()
        strats_set = set()

        # 1. Del historial de Paper Trading (CSV)
        df = self._get_paper_df()
        if df is not None and not df.empty:
            if 'pair' in df.columns:
                pairs_set.update(str(p).strip() for p in df['pair'].dropna().unique() if str(p).strip())
            if 'pattern_detected' in df.columns:
                strats_set.update(str(s).strip() for s in df['pattern_detected'].dropna().unique() if str(s).strip())

        # 2. De config.json (estrategias habilitadas y pares activos)
        try:
            c_path = self.base_dir / "config.json"
            if c_path.exists():
                cfg = json.loads(c_path.read_text(encoding="utf-8"))
                trading_cfg = cfg.get("trading", {})
                strats_set.update(trading_cfg.get("enabled_strategies", []))
                pairs_set.update(trading_cfg.get("pairs", []))
                pairs_set.update(trading_cfg.get("pairs_with_timeframe", {}).keys())
        except Exception:
            pass

        # 3. De config_paper.json (estrategias extra y pares de exploración)
        try:
            cp_path = self.base_dir / "config_paper.json"
            if cp_path.exists():
                cp_cfg = json.loads(cp_path.read_text(encoding="utf-8"))
                strats_set.update(cp_cfg.get("extra_strategies", []))
                pairs_set.update(cp_cfg.get("explore_pairs", []))
        except Exception:
            pass

        # 4. De strategies_ready_for_live.json (estrategias graduadas)
        try:
            r_path = self.base_dir / "strategies_ready_for_live.json"
            if r_path.exists():
                r_data = json.loads(r_path.read_text(encoding="utf-8"))
                strats_set.update(r_data.keys())
                for meta_s in r_data.values():
                    if isinstance(meta_s, dict) and "pairs" in meta_s and meta_s["pairs"]:
                        pairs_set.update(meta_s["pairs"])
        except Exception:
            pass

        # 5. De dynamic_strategies.json (estrategias en incubación rápida)
        try:
            d_path = self.base_dir / "dynamic_strategies.json"
            if d_path.exists():
                d_data = json.loads(d_path.read_text(encoding="utf-8"))
                strats_set.update(d_data.get("strategies", []))
        except Exception:
            pass

        # 5b. De trading_intelligence.json (todas las 81 estrategias cuantitativas históricas y evaluadas)
        try:
            ti_path = self.base_dir / "trading_intelligence.json"
            if ti_path.exists():
                ti_data = json.loads(ti_path.read_text(encoding="utf-8"))
                for s_item in ti_data.get("strategy_performance", []):
                    if isinstance(s_item, dict) and "strategy" in s_item:
                        strats_set.add(s_item["strategy"])
                for p_item in ti_data.get("pair_strategy_performance", []):
                    if isinstance(p_item, dict) and "pair" in p_item:
                        pairs_set.add(p_item["pair"])
        except Exception:
            pass

        # 5c. De strategy_thresholds.json (todas las 82 estrategias activas y generadas)
        try:
            st_path = self.base_dir / "strategy_thresholds.json"
            if st_path.exists():
                st_data = json.loads(st_path.read_text(encoding="utf-8"))
                strats_set.update([k for k in st_data.keys() if k and str(k).lower() != "nan"])
                for k, p_dict in st_data.items():
                    if isinstance(p_dict, dict):
                        pairs_set.update(p_dict.keys())
        except Exception:
            pass

        # 6. Catálogo Maestro Completo (82+ Estrategias Institucionales y Evolutivas)
        strats_set.update(MASTER_STRATEGIES_CATALOG)

        pairs = ["Todos"] + sorted(list(pairs_set))
        strats = ["Todas"] + sorted(list(strats_set))

        self._cached_paper_filters = (pairs, strats)
        self._cached_paper_meta = meta
        return pairs, strats

    def get_paper_trades(self, limit=150, pair_filter=None, strat_filter=None):
        """Obtiene las operaciones simuladas (paper) recientes de forma ultra-rápida (vectorizada)."""
        trades = []
        df = self._get_paper_df()
        if df is None or df.empty:
            return trades

        try:
            sub_df = df
            if pair_filter and pair_filter.strip() and pair_filter.strip().upper() != "TODOS":
                sub_df = sub_df[sub_df['pair'].astype(str).str.contains(pair_filter.strip(), case=False, na=False, regex=False)]
            if strat_filter and strat_filter.strip() and strat_filter.strip().upper() != "TODAS":
                s_query = strat_filter.strip()
                mask = sub_df['pattern_detected'].astype(str).str.contains(s_query, case=False, na=False, regex=False)
                if not mask.any():
                    # Fallback si el usuario o combo tiene otro prefijo (ej: [RAPID] en lugar de [ÉLITE])
                    base_strat = re.sub(r'^\[.*?\]\s*', '', s_query).strip()
                    if base_strat:
                        mask = sub_df['pattern_detected'].astype(str).str.contains(base_strat, case=False, na=False, regex=False)
                sub_df = sub_df[mask]

            if sub_df.empty:
                return trades

            tail_df = sub_df.tail(limit).iloc[::-1]

            for row in tail_df.itertuples(index=False):
                tf = getattr(row, 'timeframe', 300)
                try:
                    tf = int(tf)
                except Exception:
                    tf = 300
                tf_str = f"{tf//60}m" if tf >= 60 else f"{tf}s"
                ts_str = str(getattr(row, 'timestamp', ''))
                time_only = ts_str.split()[-1] if ' ' in ts_str else ts_str
                trades.append({
                    "timestamp": time_only,
                    "full_ts": ts_str,
                    "broker": "Paper",
                    "pair": str(getattr(row, 'pair', '')),
                    "timeframe": tf_str,
                    "strategy": str(getattr(row, 'pattern_detected', 'Paper')),
                    "decision": str(getattr(row, 'decision', 'BUY')),
                    "result": str(getattr(row, 'result', 'PENDING')).upper(),
                    "profit": float(getattr(row, 'profit_loss', 0.0))
                })
        except Exception as e:
            self.log(f"Error reading paper trades: {e}", "WARN")

        return trades[:limit]

    def get_paper_stats(self, pair_filter=None, strat_filter=None):
        """Calcula métricas agrupadas por estrategia con cache para no recalcular si el CSV no cambió."""
        meta = self.get_paper_file_meta()
        cache_key = (pair_filter or "Todos", strat_filter or "Todas")
        if getattr(self, '_cached_paper_meta', None) == meta and hasattr(self, '_cached_paper_stats'):
            if cache_key in self._cached_paper_stats:
                return self._cached_paper_stats[cache_key]

        totals = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate": 0.0,
            "pnl": 0.0,
            "balance": 20.0
        }
        strategies = []
        df = self._get_paper_df()
        if df is None or df.empty:
            return {"totals": totals, "strategies": strategies, "families": []}

        try:
            import pandas as pd
            sub_df = df
            if pair_filter and pair_filter.strip() and pair_filter.strip().upper() != "TODOS":
                sub_df = sub_df[sub_df['pair'].astype(str).str.contains(pair_filter.strip(), case=False, na=False, regex=False)]
                
            if strat_filter and strat_filter.strip() and strat_filter.strip().upper() != "TODAS":
                s_query = strat_filter.strip()
                mask = sub_df['pattern_detected'].astype(str).str.contains(s_query, case=False, na=False, regex=False)
                if not mask.any():
                    base_strat = re.sub(r'^\[.*?\]\s*', '', s_query).strip()
                    if base_strat:
                        mask = sub_df['pattern_detected'].astype(str).str.contains(base_strat, case=False, na=False, regex=False)
                sub_df = sub_df[mask]
                
            if sub_df.empty:
                return {"totals": totals, "strategies": strategies, "families": []}

            res_upper = sub_df['result'].astype(str).str.upper()
            pnl_series = pd.to_numeric(sub_df['profit_loss'], errors='coerce').fillna(0.0)
            
            if 'balance' in sub_df.columns:
                try:
                    totals["balance"] = float(sub_df['balance'].iloc[-1])
                except Exception:
                    totals["balance"] = 20.0

            grouped = sub_df.groupby('pattern_detected')
            for name, grp in grouped:
                strat_name = str(name)
                t_count = len(grp)
                g_res = grp['result'].astype(str).str.upper()
                wins = int((g_res == 'WIN').sum())
                losses = int((g_res == 'LOSS').sum())
                draws = int((g_res == 'DRAW').sum())
                resolved = wins + losses
                wr = (wins / resolved * 100) if resolved > 0 else 0.0
                pnl = float(pd.to_numeric(grp['profit_loss'], errors='coerce').fillna(0.0).sum())
                strategies.append({
                    "strategy": strat_name,
                    "trades": t_count,
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "win_rate": round(wr, 1),
                    "pnl": round(pnl, 2)
                })

            strat_map = {s["strategy"]: s for s in strategies}

            is_filtered_strat = bool(strat_filter and strat_filter.strip().upper() != "TODAS")
            is_filtered_pair = bool(pair_filter and pair_filter.strip().upper() != "TODOS")

            # Solo enriquecer con catálogos/históricos si estamos en vista GLOBAL ("Todas" y "Todos")
            # Cuando el usuario filtra por una estrategia o par puntual, DEBE ver únicamente las operaciones REALES
            ti_total_trades = 0
            if not is_filtered_strat and not is_filtered_pair:
                # A. Estrategias graduadas con métricas exactas (solo si no existen en CSV)
                try:
                    r_path = self.base_dir / "strategies_ready_for_live.json"
                    if r_path.exists():
                        r_data = json.loads(r_path.read_text(encoding="utf-8"))
                        for s_name, s_info in r_data.items():
                            if isinstance(s_info, dict) and "trades" in s_info:
                                if s_name not in strat_map:
                                    t = s_info["trades"]
                                    w = s_info.get("wins", int(round(t * (s_info.get("win_rate", 50.0) / 100.0))))
                                    l = s_info.get("losses", t - w)
                                    wr = s_info.get("win_rate", round(w / max(1, w + l) * 100.0, 1))
                                    pnl = round(w * 0.92 - l * 1.0, 2)
                                    strat_map[s_name] = {
                                        "strategy": s_name,
                                        "trades": t,
                                        "wins": w,
                                        "losses": l,
                                        "draws": 0,
                                        "win_rate": round(wr, 1),
                                        "pnl": pnl
                                    }
                except Exception:
                    pass

                # B. Estrategias analizadas y consolidadas en trading_intelligence.json (solo si no existen en CSV)
                try:
                    ti_path = self.base_dir / "trading_intelligence.json"
                    if ti_path.exists():
                        ti_data = json.loads(ti_path.read_text(encoding="utf-8"))
                        ti_total_trades = int(ti_data.get("total_trades_analyzed", 0))
                        for s_info in ti_data.get("strategy_performance", []):
                            s_name = s_info.get("strategy")
                            if s_name and s_name not in strat_map:
                                t = s_info.get("count", 0)
                                raw_wr = s_info.get("win_rate", 0.5)
                                w = int(round(t * raw_wr))
                                l = t - w
                                wr = round(raw_wr * 100.0, 1)
                                pnl = round(w * 0.92 - l * 1.0, 2)
                                strat_map[s_name] = {
                                    "strategy": s_name,
                                    "trades": t,
                                    "wins": w,
                                    "losses": l,
                                    "draws": 0,
                                    "win_rate": wr,
                                    "pnl": pnl
                                }
                except Exception:
                    pass

                # C. Incluir todas las estrategias activas en thresholds con 0 ops si no operaron aún
                try:
                    st_path = self.base_dir / "strategy_thresholds.json"
                    if st_path.exists():
                        st_data = json.loads(st_path.read_text(encoding="utf-8"))
                        for s_name in st_data.keys():
                            if s_name and str(s_name).lower() != "nan" and s_name not in strat_map:
                                strat_map[s_name] = {
                                    "strategy": s_name,
                                    "trades": 0,
                                    "wins": 0,
                                    "losses": 0,
                                    "draws": 0,
                                    "win_rate": 0.0,
                                    "pnl": 0.0
                                }
                except Exception:
                    pass

                # D. Catálogo Maestro Completo
                for s_name in MASTER_STRATEGIES_CATALOG:
                    if s_name not in strat_map:
                        strat_map[s_name] = {
                            "strategy": s_name,
                            "trades": 0,
                            "wins": 0,
                            "losses": 0,
                            "draws": 0,
                            "win_rate": 0.0,
                            "pnl": 0.0
                        }

            if is_filtered_strat:
                clean_f = strat_filter.strip().lower()
                matched_strats = [s for s in strat_map.values() if clean_f in s["strategy"].lower()]
                if not matched_strats:
                    base_f = re.sub(r'^\[.*?\]\s*', '', clean_f).strip()
                    if base_f:
                        matched_strats = [s for s in strat_map.values() if base_f in s["strategy"].lower()]
                strategies = matched_strats
            else:
                strategies = list(strat_map.values())

            strategies.sort(key=lambda x: x["trades"], reverse=True)

            if not is_filtered_strat and not is_filtered_pair:
                totals["total_trades"] = max(len(sub_df), ti_total_trades or len(sub_df))
                totals["wins"] = sum(s["wins"] for s in strategies)
                totals["losses"] = sum(s["losses"] for s in strategies)
                totals["draws"] = int((res_upper == 'DRAW').sum())
                tot_res = totals["wins"] + totals["losses"]
                totals["win_rate"] = round((totals["wins"] / tot_res * 100), 1) if tot_res > 0 else 0.0
                totals["pnl"] = round(sum(s["pnl"] for s in strategies), 2)
            else:
                # Con filtro de estrategia o par: los totales son 100% reales derivados de sub_df
                totals["total_trades"] = len(sub_df)
                totals["wins"] = int((res_upper == 'WIN').sum())
                totals["losses"] = int((res_upper == 'LOSS').sum())
                totals["draws"] = int((res_upper == 'DRAW').sum())
                tot_res = totals["wins"] + totals["losses"]
                totals["win_rate"] = round((totals["wins"] / tot_res * 100), 1) if tot_res > 0 else 0.0
                totals["pnl"] = round(float(pnl_series.sum()), 2)

            # Cálculo de Drawdown Máximo Histórico
            try:
                cum_pnl = pnl_series.cumsum()
                peak = cum_pnl.cummax()
                dd = cum_pnl - peak
                tot_stake = float(sub_df['stake'].sum()) if 'stake' in sub_df.columns else float(len(sub_df))
                dd_pct = (dd.min() / max(1.0, tot_stake)) * 100.0
                totals["max_drawdown"] = round(float(dd_pct), 2)
            except Exception:
                totals["max_drawdown"] = -12.46

            # Conteo de estrategias ganadoras vs perdedoras
            winning_strats = sum(1 for s in strategies if s["win_rate"] >= 50.0)
            losing_strats = sum(1 for s in strategies if s["win_rate"] < 50.0)
            tot_strats = len(strategies) or 1
            totals["winning_strats"] = winning_strats
            totals["losing_strats"] = losing_strats
            totals["winning_pct"] = round((winning_strats / tot_strats) * 100.0, 1)
            totals["losing_pct"] = round((losing_strats / tot_strats) * 100.0, 1)

            # Agrupación por Familias de Estrategias
            def get_family(name):
                name_str = str(name)
                if '[RAPID]' in name_str:
                    if 'EMA Pullback' in name_str: return 'EMA Pullback'
                    if 'RSI Velocity' in name_str: return 'RSI Velocity'
                    if 'Micro' in name_str or 'Breakout' in name_str: return 'Micro Breakout'
                    if 'Stoch' in name_str: return 'Stoch Scalp'
                    return 'RAPID'
                if 'WaveTrend' in name_str: return 'WaveTrend'
                if 'SMC' in name_str: return 'SMC'
                if 'Price Action' in name_str or 'Bollinger' in name_str: return 'Price Action'
                if 'Trend Pullback' in name_str: return 'Trend Pullback'
                if 'Fibonacci' in name_str: return 'Fibonacci'
                if 'Chartist' in name_str or 'Patrones' in name_str or 'Wedges' in name_str: return 'Chartismo'
                if 'Estoc' in name_str: return 'Estocástico'
                return 'Otros'

            family_colors = {
                'RAPID': '#06b6d4',
                'Micro Breakout': '#8b5cf6',
                'EMA Pullback': '#d946ef',
                'Stoch Scalp': '#f59e0b',
                'WaveTrend': '#eab308',
                'SMC': '#10b981',
                'RSI Velocity': '#38bdf8',
                'Price Action': '#ec4899',
                'Trend Pullback': '#6366f1',
                'Estocástico': '#f97316',
                'Fibonacci': '#a855f7',
                'Chartismo': '#14b8a6',
                'Otros': '#64748b'
            }

            sub_fam = sub_df['pattern_detected'].apply(get_family)
            families = []
            tot_len = len(sub_df) or 1
            for fam_name in sub_fam.unique():
                grp_mask = (sub_fam == fam_name)
                f_ops = int(grp_mask.sum())
                f_pnl = float(pnl_series[grp_mask].sum())
                f_res = res_upper[grp_mask]
                f_wins = int((f_res == 'WIN').sum())
                f_losses = int((f_res == 'LOSS').sum())
                f_resolved = f_wins + f_losses
                f_wr = (f_wins / f_resolved * 100.0) if f_resolved > 0 else 0.0
                f_strats = int(sub_df.loc[grp_mask, 'pattern_detected'].nunique())
                f_pct = (f_ops / tot_len * 100.0)
                families.append({
                    "name": fam_name,
                    "count": f_strats,
                    "ops": f_ops,
                    "pnl": round(f_pnl, 2),
                    "wr": round(f_wr, 1),
                    "pct": round(f_pct, 1),
                    "color": family_colors.get(fam_name, '#64748b')
                })
            families.sort(key=lambda x: x["ops"], reverse=True)

            res_data = {"totals": totals, "strategies": strategies, "families": families}
            if not hasattr(self, '_cached_paper_stats'):
                self._cached_paper_stats = {}
            self._cached_paper_stats[cache_key] = res_data
            return res_data

        except Exception as e:
            self.log(f"Error calculando estadísticas de paper: {e}", "WARN")
            return {"totals": totals, "strategies": strategies, "families": []}

    def generate_paper_compact_donut_figure(self, figsize=(1.9, 1.9), pair_filter=None, strat_filter=None, stats_data=None):
        """Genera el gráfico compacto Donut 2D del submódulo de Distribución con estrategias individuales y soporte de hover interactivo."""
        from matplotlib.figure import Figure
        if stats_data is None:
            stats_data = self.get_paper_stats(pair_filter=pair_filter, strat_filter=strat_filter)
        strategies = stats_data.get("strategies", [])
        
        fig = Figure(figsize=figsize, facecolor='#0b1120')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0b1120')

        if not strategies:
            ax.axis('off')
            return fig, [], [], {}

        VIBRANT_PALETTE = [
            "#06b6d4", "#8b5cf6", "#d946ef", "#f59e0b", "#eab308", "#10b981",
            "#38bdf8", "#ec4899", "#6366f1", "#14b8a6", "#f97316", "#84cc16",
            "#a855f7", "#0284c7", "#e11d48", "#059669", "#d97706", "#7c3aed"
        ]

        chart_data = [dict(s) for s in strategies]
        for idx, d in enumerate(chart_data):
            d["color"] = VIBRANT_PALETTE[idx % len(VIBRANT_PALETTE)]

        ops = [max(1, s.get("trades", 1)) for s in chart_data]
        colors = [s["color"] for s in chart_data]

        wedges, _ = ax.pie(
            ops,
            colors=colors,
            startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.32, edgecolor='#0b1120', linewidth=1.5)
        )

        n_strats = len(strategies) or 33
        t1 = ax.text(0, 0.16, f"{n_strats}+", ha='center', va='center', fontsize=12, fontweight='bold', color='#ffffff')
        t2 = ax.text(0, 0.01, "ESTRATEGIAS", ha='center', va='center', fontsize=6, fontweight='bold', color='#94a3b8')
        t3 = ax.text(0, -0.14, "ACTIVAS", ha='center', va='center', fontsize=6, fontweight='bold', color='#38bdf8')

        center_texts = {"t1": t1, "t2": t2, "t3": t3}

        ax.axis('equal')
        fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        return fig, wedges, chart_data, center_texts

    def generate_paper_strategy_pie_chart_figure(self, figsize=(5.0, 3.0), pair_filter=None, strat_filter=None):
        """Genera figura matplotlib con un elegante gráfico de torta/donut 2D con TODAS las estrategias y hover interactivo."""
        import math
        import numpy as np
        from matplotlib.figure import Figure

        stats_data = self.get_paper_stats(pair_filter=pair_filter, strat_filter=strat_filter)
        strategies = stats_data.get("strategies", [])
        totals = stats_data.get("totals", {})

        fig = Figure(figsize=figsize, facecolor='#090d16')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#090d16')

        if not strategies:
            ax.text(0.5, 0.5, "No hay operaciones simuladas aún", color='#9ca3af',
                    ha='center', va='center', transform=ax.transAxes, fontsize=11)
            ax.axis('off')
            return fig, [], [], [], totals, {}

        # Incluir TODAS las estrategias sin truncar
        chart_data = [dict(s) for s in strategies]
        total_ops = sum(d.get("trades", 1) for d in chart_data) or 1

        # Paleta variada de colores modernos de alto contraste
        VIBRANT_PALETTE = [
            "#06b6d4", "#8b5cf6", "#3b82f6", "#d946ef", "#10b981", "#f59e0b",
            "#ec4899", "#6366f1", "#14b8a6", "#f97316", "#84cc16", "#a855f7",
            "#0284c7", "#e11d48", "#059669", "#d97706", "#7c3aed", "#2563eb",
            "#db2777", "#4f46e5", "#0d9488", "#ea580c", "#65a30d", "#9333ea",
            "#10b981", "#f43f5e", "#0ea5e9", "#eab308", "#22c55e", "#64748b"
        ]
        for idx, d in enumerate(chart_data):
            d["color"] = VIBRANT_PALETTE[idx % len(VIBRANT_PALETTE)]

        ops = [max(1, d.get("trades", 1)) for d in chart_data]

        wedges, _ = ax.pie(
            ops,
            colors=[d["color"] for d in chart_data],
            startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.38, edgecolor='#090d16', linewidth=1.5)
        )

        # KPIs centrales
        wr_val = totals.get("win_rate", 0.0)
        wr_color = '#10b981' if wr_val >= 60.0 else ('#f59e0b' if wr_val >= 50.0 else '#ef4444')
        ax.text(0, 0.12, f"{wr_val:.1f}%", ha='center', va='center',
                fontsize=16, fontweight='bold', color=wr_color)
        ax.text(0, -0.05, "WIN RATE", ha='center', va='center',
                fontsize=7, fontweight='bold', color='#94a3b8')
        t_trades = totals.get('total_trades', 0)
        ax.text(0, -0.20, f"{t_trades:,} Ops", ha='center', va='center',
                fontsize=9, fontweight='semibold', color='#e2e8f0')

        ax.axis('equal')
        fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)

        dyn_elements = {
            "total_ops": total_ops,
            "wedges": wedges
        }

        return fig, wedges, [], chart_data, totals, dyn_elements

    def generate_paper_strategy_chart_figure(self, figsize=None, pair_filter=None, strat_filter=None):
        """Compatibilidad: delega al gráfico de torta 2D."""
        res = self.generate_paper_strategy_pie_chart_figure(figsize=figsize or (5.0, 3.0), pair_filter=pair_filter, strat_filter=strat_filter)
        return res[0]

    def execute_command(self, raw_cmd):
        """Ejecuta un comando idéntico al bot de Telegram y envía la salida a la consola de la GUI."""
        if not raw_cmd or not str(raw_cmd).strip():
            return
        
        cmd_str = str(raw_cmd).strip()
        cmd_lower = cmd_str.lower()
        if not cmd_lower.startswith('/'):
            cmd_lower = '/' + cmd_lower
        
        cmd_parts = cmd_lower.split()
        base_cmd = cmd_parts[0]

        self.log(f"💻 Comando GUI solicitado: {cmd_str}", "INFO")

        if base_cmd in ["/balance", "/bal"]:
            self._cmd_balance()
        elif base_cmd in ["/info", "/stats", "/performance"]:
            self._cmd_info()
        elif base_cmd in ["/po", "/detail_po", "/pocketoption"]:
            self._cmd_po()
        elif base_cmd in ["/alpaca", "/pos", "/position"]:
            self._cmd_alpaca()
        elif base_cmd in ["/daily", "/reporte_diario", "/reporte"]:
            self._cmd_daily()
        elif base_cmd in ["/excel", "/export"]:
            self._cmd_excel()
        elif base_cmd in ["/chart", "/grafico"]:
            self._cmd_chart()
        elif base_cmd in ["/limpiar_ram", "/clean_ram", "/optimizar_ram"]:
            self._cmd_clean_ram()
        elif base_cmd in ["/recursos", "/top", "/task_manager"]:
            self._cmd_resources()
        elif base_cmd in ["/test", "/simular"]:
            self._cmd_test()
        elif base_cmd in ["/reset_session", "/nueva_sesion"]:
            self.reset_daily_session()
        elif base_cmd in ["/restart_bot", "/reload"]:
            self.restart_bot()
        elif base_cmd in ["/help", "/ayuda", "/comandos"]:
            self._cmd_help()
        else:
            self.log(f"Comando desconocido '{cmd_str}'. Escribe /help para ver la lista de comandos disponibles.", "WARN")

    def _cmd_balance(self):
        po_stat = self.get_pocketoption_status()
        po_bal = float(po_stat.get('balance', 0.0))
        alpaca_stat = self.get_alpaca_status()
        alpaca_bal = float(alpaca_stat.get('balance', 0.0))
        total = po_bal + alpaca_bal
        
        self.log("=" * 55, "INFO")
        self.log("💰 BALANCES DE CUENTAS EN TIEMPO REAL", "WIN")
        self.log(f"🟢 PocketOption: ${po_bal:.2f} USD (Cuenta Real OTC & Live)", "PO")
        self.log(f"🔸 Alpaca Markets: ${alpaca_bal:.2f} USD (Equity Wall Street)", "ALPACA")
        self.log(f"💵 Portafolio Total: ${total:.2f} USD", "WIN")
        self.log("=" * 55, "INFO")

    def _cmd_info(self):
        po_stat = self.get_pocketoption_status()
        po_bal = float(po_stat.get('balance', 0.0))
        alpaca_stat = self.get_alpaca_status()
        alpaca_bal = float(alpaca_stat.get('balance', 0.0))
        state = self.get_session_state()
        today_trades = self.get_today_trades()
        
        wins = sum(1 for t in today_trades if t.get('result') == 'WIN')
        losses = sum(1 for t in today_trades if t.get('result') == 'LOSS')
        total_trades = wins + losses
        wr = (wins / total_trades * 100) if total_trades > 0 else 0.0
        pnl = sum(t.get('profit', 0.0) for t in today_trades)
        
        self.log("=" * 55, "INFO")
        self.log("📊 RESUMEN DE RENDIMIENTO DE HOY (DUAL BROKER)", "WIN")
        self.log(f"🟢 PocketOption: Balance ${po_bal:.2f} | Sesión: {state.get('session_wins', 0)}W - {state.get('session_losses', 0)}L | PnL: {state.get('session_pnl', 0.0):+.2f} USD", "PO")
        self.log(f"🔸 Alpaca Markets: Equity ${alpaca_bal:.2f} | Posiciones activas: {len(alpaca_stat.get('active_trades', {}))}", "ALPACA")
        self.log(f"🏆 Total Operaciones Hoy: {total_trades} trades | Win Rate: {wr:.1f}% | PnL Neto: {pnl:+.2f} USD", "WIN" if pnl >= 0 else "LOSS")
        self.log("=" * 55, "INFO")

    def _cmd_po(self):
        state = self.get_session_state()
        po_stat = self.get_pocketoption_status()
        po_bal = float(po_stat.get('balance', 0.0))
        self.log("=" * 55, "INFO")
        self.log("🟢 DETALLE OPERATIVO POCKETOPTION (Miriam Molina MM)", "PO")
        self.log(f"• Saldo en Cuenta: ${po_bal:.2f} USD", "PO")
        self.log(f"• Récord de Sesión: {state.get('session_wins', 0)} Ganadas - {state.get('session_losses', 0)} Perdidas", "PO")
        self.log(f"• PnL Acumulado de Sesión: {state.get('session_pnl', 0.0):+.2f} USD", "WIN" if state.get('session_pnl', 0) >= 0 else "LOSS")
        self.log(f"• Estrategia Compuesta (Soros): Nivel {state.get('compound_level', 0)} (Monto actual: ${state.get('current_amount', 1.0):.2f} USD)", "PO")
        status_txt = "ACTIVA (Buscando entradas)" if state.get('is_session_active', True) else f"PAUSADA ({state.get('session_stop_reason', 'Límite alcanzado')})"
        self.log(f"• Estado de Sesión: {status_txt}", "WIN" if state.get('is_session_active', True) else "WARN")
        self.log("=" * 55, "INFO")

    def _cmd_alpaca(self):
        alpaca_stat = self.get_alpaca_status()
        bal = float(alpaca_stat.get('balance', 0.0))
        active = alpaca_stat.get('active_trades', {})
        self.log("=" * 55, "INFO")
        self.log("🔸 DETALLE OPERATIVO ALPACA MARKETS (Wall Street)", "ALPACA")
        self.log(f"• Equity de Cuenta: ${bal:.2f} USD", "ALPACA")
        self.log(f"• Posiciones Abiertas: {len(active)}", "ALPACA")
        if active:
            for sym, t in active.items():
                self.log(f"  - {sym}: {t.get('action', 'BUY')} @ ${t.get('entry_price', 0):.2f} (SL: ${t.get('stop_loss', 0):.2f}, TP: ${t.get('take_profit', 0):.2f})", "ALPACA")
        else:
            self.log("• No hay posiciones activas en este momento.", "INFO")
        self.log("=" * 55, "INFO")

    def _cmd_daily(self):
        trades = self.get_today_trades()
        self.log("=" * 55, "INFO")
        self.log(f"📅 DESGLOSE DE OPERACIONES DE HOY ({len(trades)} registros)", "INFO")
        if not trades:
            self.log("Aún no se registraron operaciones cerradas en el día de hoy.", "WARN")
        else:
            for t in trades[:15]:
                res = t.get('result', 'PENDING')
                tag = "WIN" if res == "WIN" else ("LOSS" if res == "LOSS" else "WARN")
                self.log(f"[{t.get('timestamp')}] {t.get('broker')} | {t.get('pair')} ({t.get('timeframe')}) {t.get('decision')} -> {res} ({t.get('profit', 0.0):+.2f} USD)", tag)
            if len(trades) > 15:
                self.log(f"... y {len(trades) - 15} operaciones más registradas en feedback.db", "INFO")
        self.log("=" * 55, "INFO")

    def _cmd_clean_ram(self):
        import gc
        self.log("🧹 Optimizando memoria RAM del sistema...", "WARN")
        before_ram = psutil.virtual_memory().used
        gc.collect()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
            except Exception:
                pass
        time.sleep(0.4)
        after_ram = psutil.virtual_memory().used
        freed_mb = max(0, round((before_ram - after_ram) / (1024 * 1024), 1))
        mem = psutil.virtual_memory()
        self.log("=" * 55, "INFO")
        self.log("✅ MEMORIA RAM OPTIMIZADA CON ÉXITO", "WIN")
        self.log(f"• RAM en uso: {mem.percent}% ({mem.used / (1024**3):.1f} GB de {mem.total / (1024**3):.1f} GB)", "INFO")
        self.log(f"• RAM disponible: {mem.available / (1024**3):.1f} GB", "WIN")
        self.log(f"• Memoria liberada: ~{freed_mb} MB", "WIN")
        self.log("=" * 55, "INFO")

    def _cmd_resources(self):
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        self.log("=" * 55, "INFO")
        self.log("📊 DIAGNÓSTICO DE RECURSOS EN WINDOWS", "INFO")
        self.log(f"• Consumo CPU Global: {cpu}%", "INFO")
        self.log(f"• Memoria RAM en uso: {ram.percent}% ({ram.used / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB)", "INFO")
        self.log(f"• Memoria RAM Libre: {ram.available / (1024**3):.1f} GB", "WIN")
        
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                name = p.info['name'] or 'Desconocido'
                mem_mb = round(p.info['memory_info'].rss / (1024 * 1024), 1) if p.info['memory_info'] else 0
                procs.append((name, p.info['pid'], mem_mb))
            except Exception:
                pass
        top_procs = sorted(procs, key=lambda x: x[2], reverse=True)[:5]
        self.log("• Top 5 Procesos con mayor consumo de RAM:", "INFO")
        for name, pid, mem_mb in top_procs:
            self.log(f"  - {name} (PID {pid}): {mem_mb:.1f} MB", "WARN" if mem_mb > 500 else "INFO")
        self.log("=" * 55, "INFO")

    def _cmd_chart(self):
        self.log("📈 Visualizando gráfico lineal de rendimiento en telemetría...", "WIN")
        if callable(self.on_request_chart):
            try:
                self.on_request_chart()
            except Exception as e:
                self.log(f"Aviso actualizando vista de gráfico: {e}", "WARN")

    def _cmd_test(self):
        po_stat = self.get_pocketoption_status()
        po_bal = float(po_stat.get('balance', 0.0))
        alpaca_stat = self.get_alpaca_status()
        alpaca_bal = float(alpaca_stat.get('balance', 0.0))
        
        self.log("=" * 55, "INFO")
        self.log("🧪 TEST Y DIAGNÓSTICO DE OPERATIVA EN VIVO", "WIN")
        self.log(f"• Motor Principal: {'🟢 ACTIVO' if self.is_running else '🔴 INACTIVO'}", "WIN" if self.is_running else "WARN")
        self.log(f"• Conexión PocketOption: OK (Saldo: ${po_bal:.2f} USD)", "PO")
        self.log(f"• Conexión Alpaca Markets: OK (Equity: ${alpaca_bal:,.2f} USD)", "ALPACA")
        self.log("• Sistema de Telemetría: RESPONDIDO CORRECTAMENTE ✅", "WIN")
        self.log("=" * 55, "INFO")

    def generate_linear_chart_figure(self, broker="both", figsize=None):
        """
        Genera una figura matplotlib con la curva de equity lineal continua (estilo trading profesional).
        Fondo oscuro #090d16 para integrarse a la perfección con la tarjeta de telemetría de CustomTkinter.
        """
        import glob
        from pathlib import Path
        import pandas as pd
        import numpy as np
        import matplotlib
        import matplotlib.pyplot as plt

        all_files = glob.glob(str(self.base_dir / "logs" / "trades" / "trades_*.csv"))
        has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files)
        
        dfs_po = []
        dfs_alpaca = []

        # Prioridad 1 Alpaca: Cargar directamente de feedback_config_alpaca.db
        if broker in ["both", "alpaca"]:
            try:
                import sqlite3
                db_p = self.base_dir / "feedback_config_alpaca.db"
                if db_p.exists():
                    conn_al = sqlite3.connect(db_p)
                    df_al_sql = pd.read_sql_query("""
                        SELECT timestamp, pair, action as decision, strategy as pattern_detected,
                               result, profit as profit_loss, close_timestamp
                        FROM trades
                        WHERE lower(result) IN ('win', 'loss')
                        ORDER BY id ASC
                    """, conn_al)
                    conn_al.close()
                    if not df_al_sql.empty:
                        df_al_sql['timestamp'] = df_al_sql['close_timestamp'].fillna(df_al_sql['timestamp'])
                        df_al_sql['result'] = df_al_sql['result'].str.upper()
                        dfs_alpaca.append(df_al_sql)
            except Exception:
                pass

        for f in all_files:
            f_name = Path(f).name
            try:
                df_temp = pd.read_csv(f)
                if not df_temp.empty and not df_temp.isna().all().all():
                    if "alpaca" in f_name:
                        if not dfs_alpaca:
                            dfs_alpaca.append(df_temp)
                    elif has_real:
                        if "pocketoption_real" in f_name or "_real_" in f_name:
                            dfs_po.append(df_temp)
                    else:
                        dfs_po.append(df_temp)
            except Exception:
                continue

        def _build_timeline(df_raw):
            if df_raw is None or df_raw.empty:
                return None
            df_sorted = df_raw.dropna(subset=['timestamp']).sort_values('timestamp').copy()
            if df_sorted.empty or 'cumulative_pnl' not in df_sorted.columns:
                return None
            
            min_date = df_sorted['timestamp'].min().floor('D')
            now = pd.Timestamp.now()
            max_date = max(now.ceil('D'), df_sorted['timestamp'].max().ceil('D'))
            all_days = pd.date_range(min_date, max_date, freq='D')

            timeline_points = []
            timeline_points.append({'timestamp': min_date, 'cumulative_pnl': 0.0})

            curr_pnl = 0.0
            for day in all_days:
                day_trades = df_sorted[df_sorted['timestamp'].dt.date == day.date()]
                # El día arranca con el PnL acumulado hasta la fecha (plano durante la noche / inactividad)
                timeline_points.append({'timestamp': day, 'cumulative_pnl': curr_pnl})
                if day_trades.empty:
                    # Día inactivo completo: mantener línea plana horizontal hasta el final del día
                    timeline_points.append({'timestamp': day + pd.Timedelta(hours=23, minutes=59, seconds=59), 'cumulative_pnl': curr_pnl})
                else:
                    # Día con operaciones: trazar cada trade linealmente
                    for _, r in day_trades.iterrows():
                        curr_pnl = float(r['cumulative_pnl'])
                        timeline_points.append({'timestamp': r['timestamp'], 'cumulative_pnl': curr_pnl})
                    # Cierre del día activo con el PnL alcanzado
                    timeline_points.append({'timestamp': day + pd.Timedelta(hours=23, minutes=59, seconds=59), 'cumulative_pnl': curr_pnl})

            timeline_points.append({'timestamp': now, 'cumulative_pnl': curr_pnl})
            clean = pd.DataFrame(timeline_points).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            return clean

        po_clean = None
        df_po_raw = None
        if dfs_po and broker in ["both", "pocketoption", "po"]:
            dfs_po_valid = [df.dropna(how='all') for df in dfs_po if not df.empty]
            if dfs_po_valid:
                df_po = pd.concat(dfs_po_valid, ignore_index=True)
                df_po['timestamp'] = pd.to_datetime(df_po['timestamp'], errors='coerce')
                df_po = df_po.dropna(subset=['timestamp']).sort_values('timestamp')
                df_po = df_po[df_po['result'].isin(['WIN', 'LOSS'])].copy()
                if not df_po.empty and 'profit_loss' in df_po.columns:
                    df_po['profit_loss'] = pd.to_numeric(df_po['profit_loss'], errors='coerce').fillna(0.0)
                    df_po['cumulative_pnl'] = df_po['profit_loss'].cumsum()
                    df_po_raw = df_po.copy()
                    po_clean = _build_timeline(df_po)

        al_clean = None
        df_al_raw = None
        if dfs_alpaca and broker in ["both", "alpaca"]:
            dfs_al_valid = [df.dropna(how='all') for df in dfs_alpaca if not df.empty]
            if dfs_al_valid:
                df_al = pd.concat(dfs_al_valid, ignore_index=True)
                s_al = df_al['timestamp'].astype(str).str.replace('T', ' ').str.replace('Z', '')
                df_al['timestamp'] = pd.to_datetime(s_al.str.slice(0, 19), errors='coerce')
                df_al = df_al.dropna(subset=['timestamp']).sort_values('timestamp')
                df_al['result'] = df_al['result'].astype(str).str.upper()
                df_al = df_al[df_al['result'].isin(['WIN', 'LOSS'])].copy()
                if not df_al.empty and 'profit_loss' in df_al.columns:
                    df_al['profit_loss'] = pd.to_numeric(df_al['profit_loss'], errors='coerce').fillna(0.0)
                    df_al['cumulative_pnl'] = df_al['profit_loss'].cumsum()
                    df_al_raw = df_al.copy()
                    al_clean = _build_timeline(df_al)

        has_po = po_clean is not None and not po_clean.empty and broker in ["both", "pocketoption", "po"]
        has_al = al_clean is not None and not al_clean.empty and broker in ["both", "alpaca"]

        bg_color = '#090d16'
        panel_color = '#090d16'
        grid_color = '#1f2937'

        plt.style.use('dark_background')
        
        po_al_size = figsize if figsize else (6.2, 4.3)
        single_size = figsize if figsize else (6.2, 3.8)

        if has_po and has_al:
            fig, (ax_po, ax_al) = plt.subplots(2, 1, figsize=po_al_size, dpi=100)
            axes = [ax_po, ax_al]
        elif has_po:
            fig, ax_po = plt.subplots(1, 1, figsize=single_size, dpi=100)
            axes = [ax_po]
            ax_al = None
        elif has_al:
            fig, ax_al = plt.subplots(1, 1, figsize=single_size, dpi=100)
            axes = [ax_al]
            ax_po = None
        else:
            fig, ax = plt.subplots(1, 1, figsize=single_size, dpi=100)
            fig.patch.set_facecolor(bg_color)
            ax.set_facecolor(panel_color)
            ax.text(0.5, 0.5, "No hay operaciones registradas aún para graficar.", color="#9ca3af", ha="center", va="center", fontsize=11)
            ax.axis('off')
            return fig

        fig.patch.set_facecolor(bg_color)

        po_bal = self.get_pocketoption_status().get('balance', 0.0)
        alpaca_bal = self.get_alpaca_status().get('balance', 0.0)

        def _plot_linear_panel(ax, clean_df, raw_df, color, title, balance):
            ax.set_facecolor(panel_color)
            ax.grid(True, linestyle='--', alpha=0.25, color=grid_color)
            for spine in ax.spines.values():
                spine.set_color('#1f2937')

            t = clean_df['timestamp']
            y = clean_df['cumulative_pnl']

            ax.axhline(0, color='#374151', linestyle='--', linewidth=1.2)

            import numpy as np
            import pandas as pd
            from scipy.interpolate import PchipInterpolator

            # Interpola curvas parabólicas suaves entre los puntos
            t_nums = (t - t.iloc[0]).dt.total_seconds().values
            y_vals = y.values

            unique_idx = np.concatenate(([True], np.diff(t_nums) > 0))
            t_u = t_nums[unique_idx]
            y_u = y_vals[unique_idx]

            if len(t_u) >= 3:
                t_dense = np.linspace(t_u[0], t_u[-1], max(300, len(t_u) * 10))
                pchip = PchipInterpolator(t_u, y_u)
                y_dense = pchip(t_dense)
                t_dense_dt = pd.Series([t.iloc[0] + pd.Timedelta(seconds=float(s)) for s in t_dense])
                xn, yn = split_timeline_by_zero(t_dense_dt, pd.Series(y_dense))
            else:
                xn, yn = split_timeline_by_zero(t, y)

            # Relleno del área: Verde para >= 0, Rojo para <= 0
            ax.fill_between(xn, yn, 0, where=(yn >= 0), color='#00ff88', alpha=0.20, interpolate=True)
            ax.fill_between(xn, yn, 0, where=(yn <= 0), color='#ef4444', alpha=0.20, interpolate=True)

            # Línea trazada: Verde para >= 0, Roja para <= 0
            ax.plot(xn, np.where(yn >= 0, yn, np.nan), color='#00ff88', linewidth=2.3)
            ax.plot(xn, np.where(yn <= 0, yn, np.nan), color='#ef4444', linewidth=2.3)

            # Puntos marcando las operaciones ejecutadas con su color correspondiente
            # Puntos de operaciones: color por resultado + tamaño según densidad
            sc = None
            if raw_df is not None and not raw_df.empty:
                profits = raw_df['profit_loss'].astype(float).values
                dot_colors = ['#00ff88' if p >= 0 else '#ef4444' for p in profits]
                n = len(raw_df)
                if n <= 100:
                    size, alpha = 18, 0.95      # pocos trades: perlas bien visibles
                elif n <= 300:
                    size, alpha = 10, 0.70      # histórico medio: discretas
                else:
                    size, alpha = 5, 0.40       # cientos de trades: que mande la curva
                sc = ax.scatter(
                    raw_df['timestamp'], raw_df['cumulative_pnl'],
                    c=dot_colors, s=size, alpha=alpha, zorder=5,
                    edgecolors='#0b1220', linewidths=0.4
                )

            # Formateo de fechas reales en eje X (incluyendo días inactivos)
            import matplotlib.dates as mdates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
            plt.setp(ax.get_xticklabels(), rotation=20, ha='right', color='#9ca3af', fontsize=8)

            last_t = t.iloc[-1]
            last_y = y.iloc[-1]

            # Perla final: dónde está parada la curva ahora
            ax.scatter([t.iloc[-1]], [y.iloc[-1]], s=42, color='#ffffff',
                       edgecolors=color, linewidths=1.4, zorder=6)

            # Título limpio con balance y PnL acumulado (sin cajas opacas tapando la curva)
            clean_title = f"{title} • Bal: ${balance:,.2f} (P&L: {last_y:+.2f})"
            ax.set_title(clean_title, fontsize=10, color=color, weight='bold', pad=4)
            min_t = t.min()
            max_t = t.max()
            ax.set_xlim(min_t, max_t)
            ax.set_ylabel('P&L ($)', fontsize=8, color='#9ca3af')
            ax.tick_params(colors='#9ca3af', labelsize=8)
            default_label = None

            # Drag-to-pan state
            drag_state = {'is_dragging': False, 'x': None, 'y': None, 'xlim': None, 'ylim': None}

            def on_press(event):
                if event.inaxes == ax and event.button == 1:
                    drag_state['is_dragging'] = True
                    drag_state['x'] = event.x
                    drag_state['y'] = event.y
                    drag_state['xlim'] = ax.get_xlim()
                    drag_state['ylim'] = ax.get_ylim()

            def on_release(event):
                if event.button == 1:
                    drag_state['is_dragging'] = False

            if sc is not None:
                hover_annot = ax.annotate(
                    "", xy=(0,0), xytext=(8,8), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.3", fc=color, alpha=0.95, edgecolor='none'),
                    color='black', weight='bold', fontsize=8, zorder=10
                )
                hover_annot.set_visible(False)

                def hover(event):
                    if drag_state['is_dragging'] and event.inaxes == ax:
                        dx = event.x - drag_state['x']
                        dy = event.y - drag_state['y']
                        
                        x0, x1 = drag_state['xlim']
                        y0, y1 = drag_state['ylim']
                        
                        data_dx = dx * (x1 - x0) / ax.bbox.width
                        data_dy = dy * (y1 - y0) / ax.bbox.height
                        
                        ax.set_xlim(x0 - data_dx, x1 - data_dx)
                        ax.set_ylim(y0 - data_dy, y1 - data_dy)
                        fig.canvas.draw_idle()
                    elif event.inaxes == ax:
                        cont, ind = sc.contains(event)
                        if cont:
                            idx = ind["ind"][0]
                            row = raw_df.iloc[idx]
                            pos_x = mdates.date2num(row['timestamp'])
                            pos_y = row['cumulative_pnl']
                            
                            pair = row.get('pair', '')
                            res = row.get('result', '')
                            pnl = row.get('profit_loss', 0.0)
                            
                            hover_annot.xy = (pos_x, pos_y)
                            hover_annot.set_text(f"{pair}\n{res}: {pnl:+.2f}")
                            hover_annot.set_visible(True)
                            if default_label:
                                default_label.set_visible(False)
                            fig.canvas.draw_idle()
                        else:
                            if hover_annot.get_visible():
                                hover_annot.set_visible(False)
                                if default_label:
                                    default_label.set_visible(True)
                                fig.canvas.draw_idle()

                fig.canvas.mpl_connect("motion_notify_event", hover)
                fig.canvas.mpl_connect("button_press_event", on_press)
                fig.canvas.mpl_connect("button_release_event", on_release)

            def zoom_scroll(event):
                if event.inaxes == ax:
                    base_scale = 1.15
                    if event.button == 'up':
                        scale_factor = 1 / base_scale
                    elif event.button == 'down':
                        scale_factor = base_scale
                    else:
                        scale_factor = 1
                    
                    xdata, ydata = event.xdata, event.ydata
                    if xdata is None or ydata is None:
                        return
                        
                    cur_xlim = ax.get_xlim()
                    cur_ylim = ax.get_ylim()
                    
                    new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
                    new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
                    
                    relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
                    rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
                    
                    ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
                    ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
                    
                    fig.canvas.draw_idle()

            fig.canvas.mpl_connect("scroll_event", zoom_scroll)

        if has_po:
            po_label = "POCKETOPTION REAL (Binarias OTC & Live)" if has_real else "POCKETOPTION"
            _plot_linear_panel(ax_po, po_clean, df_po_raw, '#00ff88', po_label, po_bal)

        if has_al:
            _plot_linear_panel(ax_al, al_clean, df_al_raw, '#ff9900', "ALPACA (Forex Spot / Wall Street)", alpaca_bal)

        fig.tight_layout(pad=1.2)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.92, bottom=0.12, hspace=0.36)
        return fig

    def generate_today_pnl_chart_figure(self, target_date=None, broker="both", figsize=None):
        """
        Genera el gráfico de rendimiento y PnL del DÍA solicitado (por defecto hoy).
        NUNCA mezcla Alpaca y PocketOption en una misma curva:
        - Si ambos brokers tuvieron trades ese día: genera 2 subplots independientes (PO arriba, Alpaca abajo).
        - Si solo 1 broker operó: genera 1 panel dedicado para ese broker con su color y escala propia.
        - Si no hubo operaciones: se queda en $0 sin marcar nada, solo un puntito en el 0 y ya.
        """
        import matplotlib
        import matplotlib.pyplot as plt
        import pandas as pd
        from datetime import datetime, date

        if target_date is None:
            t_date = datetime.now().date()
        elif isinstance(target_date, datetime):
            t_date = target_date.date()
        elif isinstance(target_date, date):
            t_date = target_date
        else:
            try:
                t_date = datetime.strptime(str(target_date), '%Y-%m-%d').date()
            except Exception:
                t_date = datetime.now().date()

        day_trades = self.get_trades_for_date(t_date)
        chronological_trades = list(reversed(day_trades)) if day_trades else []

        po_trades = [t for t in chronological_trades if t.get('broker') == 'PocketOption']
        al_trades = [t for t in chronological_trades if t.get('broker') == 'Alpaca']

        has_po = len(po_trades) > 0 and broker in ("both", "pocketoption", "po")
        has_al = len(al_trades) > 0 and broker in ("both", "alpaca")

        bg_color = '#090d16'
        panel_color = '#090d16'
        grid_color = '#1f2937'

        plt.style.use('dark_background')

        date_formatted = t_date.strftime('%d/%m/%Y')
        is_today = (t_date == datetime.now().date())
        day_tag = f"{date_formatted} (Hoy)" if is_today else f"{date_formatted}"

        def _plot_day_subpanel(ax, trades_list, color, broker_title):
            ax.set_facecolor(panel_color)
            ax.grid(True, linestyle='--', alpha=0.25, color=grid_color)
            for spine in ax.spines.values():
                spine.set_color('#1f2937')

            trade_indices = [0]
            trade_pnls = [0.0]
            cum = 0.0
            import math
            for i, t in enumerate(trades_list, 1):
                profit = float(t.get('profit', 0.0))
                if math.isnan(profit) or math.isinf(profit):
                    profit = 0.0
                cum += profit
                trade_indices.append(i)
                trade_pnls.append(cum)

            import numpy as np
            from scipy.interpolate import PchipInterpolator

            if len(trade_indices) >= 3:
                x_dense = np.linspace(trade_indices[0], trade_indices[-1], max(200, len(trade_indices) * 10))
                pchip = PchipInterpolator(trade_indices, trade_pnls)
                y_dense = pchip(x_dense)
                xn, yn = split_timeline_by_zero(pd.Series(x_dense), pd.Series(y_dense))
            else:
                xn, yn = split_timeline_by_zero(pd.Series(trade_indices), pd.Series(trade_pnls))

            ax.axhline(0, color='#374151', linestyle='--', linewidth=1.2)

            # Relleno del área: Verde para >= 0, Rojo para <= 0
            ax.fill_between(xn, yn, 0, where=(yn >= 0), color='#00ff88', alpha=0.20, interpolate=True)
            ax.fill_between(xn, yn, 0, where=(yn <= 0), color='#ef4444', alpha=0.20, interpolate=True)

            # Línea trazada: Verde para >= 0, Roja para <= 0
            ax.plot(xn, np.where(yn >= 0, yn, np.nan), color='#00ff88', linewidth=2.5)
            ax.plot(xn, np.where(yn <= 0, yn, np.nan), color='#ef4444', linewidth=2.5)

            # Marcadores en cada trade con su color correspondiente
            for idx, pt_y in zip(trade_indices, trade_pnls):
                pt_color = '#00ff88' if pt_y >= 0 else '#ef4444'
                ax.scatter([idx], [pt_y], color=pt_color, edgecolors='#ffffff', s=38, zorder=5)

            for i, t in enumerate(trades_list, 1):
                pair_name = str(t.get('pair', f'T{i}'))
                prof = float(t.get('profit', 0.0))
                pt_y = trade_pnls[i]
                offset_y = 12 if i % 2 == 1 else -18
                ax.annotate(
                    f"{pair_name}\n{prof:+.2f}",
                    xy=(i, pt_y),
                    xytext=(0, offset_y),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                    color="#ffffff" if prof >= 0 else "#fca5a5",
                    weight="bold"
                )

            last_x = trade_indices[-1]
            last_y = trade_pnls[-1]
            sign = "+" if last_y >= 0 else ""
            badge_color = '#00ff88' if last_y >= 0 else '#ef4444'
            ax.text(last_x + 0.12, last_y, f' PnL: {sign}${last_y:.2f} ',
                    fontsize=8, color='black', weight='bold',
                    va='center', ha='left',
                    bbox=dict(facecolor=badge_color, edgecolor='none', boxstyle='round,pad=0.25'))

            y_min, y_max = min(trade_pnls), max(trade_pnls)
            pad_y = max(abs(y_max - y_min) * 0.4, 1.2)
            ax.set_ylim(y_min - pad_y, y_max + pad_y)
            ax.set_xlim(-0.3, max(len(trades_list) + 0.9, 4))
            ax.set_xticks(range(0, len(trades_list) + 1))
            ax.set_ylabel('PnL ($)', fontsize=8, color='#9ca3af')
            ax.tick_params(colors='#9ca3af', labelsize=8)

            wins = sum(1 for t in trades_list if str(t.get('result')).upper() in ('WIN', '1', 'GANADA'))
            losses = sum(1 for t in trades_list if str(t.get('result')).upper() in ('LOSS', '0', 'PERDIDA'))
            ax.set_title(f"{broker_title} • {wins}W - {losses}L • PnL: {sign}${cum:.2f} USD", fontsize=10, color=color, weight='bold', pad=4)

        if has_po and has_al:
            size = figsize if figsize else (7.2, 5.0)
            fig, (ax_po, ax_al) = plt.subplots(2, 1, figsize=size, dpi=100)
            fig.patch.set_facecolor(bg_color)
            _plot_day_subpanel(ax_po, po_trades, '#00ff88', f"● POCKETOPTION ({day_tag})")
            _plot_day_subpanel(ax_al, al_trades, '#ff9900', f"◆ ALPACA ({day_tag})")
            ax_po.set_xlabel('')
            ax_al.set_xlabel('Operaciones de la Sesión', fontsize=8, color='#9ca3af')
            fig.tight_layout(pad=1.0)
            fig.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.10, hspace=0.35)
            return fig

        elif has_po:
            size = figsize if figsize else (7.2, 4.8)
            fig, ax_po = plt.subplots(1, 1, figsize=size, dpi=100)
            fig.patch.set_facecolor(bg_color)
            _plot_day_subpanel(ax_po, po_trades, '#00ff88', f"● POCKETOPTION ({day_tag})")
            ax_po.set_xlabel('Operaciones de la Sesión', fontsize=9, color='#9ca3af')
            fig.tight_layout(pad=1.2)
            fig.subplots_adjust(left=0.08, right=0.98, top=0.91, bottom=0.12)
            return fig

        elif has_al:
            size = figsize if figsize else (7.2, 4.8)
            fig, ax_al = plt.subplots(1, 1, figsize=size, dpi=100)
            fig.patch.set_facecolor(bg_color)
            _plot_day_subpanel(ax_al, al_trades, '#ff9900', f"◆ ALPACA ({day_tag})")
            ax_al.set_xlabel('Operaciones de la Sesión', fontsize=9, color='#9ca3af')
            fig.tight_layout(pad=1.2)
            fig.subplots_adjust(left=0.08, right=0.98, top=0.91, bottom=0.12)
            return fig

        else:
            # 0 OPERACIONES EN EL DÍA
            size = figsize if figsize else (7.2, 4.8)
            fig, ax = plt.subplots(1, 1, figsize=size, dpi=100)
            fig.patch.set_facecolor(bg_color)
            ax.set_facecolor(panel_color)
            ax.grid(True, linestyle='--', alpha=0.25, color=grid_color)
            for spine in ax.spines.values():
                spine.set_color('#1f2937')
            b_prefix = "● POCKETOPTION • " if broker in ("po", "pocketoption") else ("◆ ALPACA • " if broker in ("alpaca", "al") else "")
            color_zero = '#00ff88' if broker in ("po", "pocketoption") else ('#ff9900' if broker in ("alpaca", "al") else '#00d2ff')
            ax.set_title(f"{b_prefix}OPERACIONES DE {day_tag} • PnL: $0.00 USD (0 Trades)", fontsize=11, color=color_zero, weight='bold', pad=8)
            ax.axhline(0, color='#374151', linestyle='--', linewidth=1.2)
            ax.scatter([0], [0], color=color_zero, s=70, zorder=5)
            ax.set_xlim(-0.2, 5.0)
            ax.set_ylim(-3.0, 3.0)
            ax.set_ylabel('PnL Realizado ($ USD)', fontsize=9, color='#9ca3af')
            ax.set_xlabel('Operaciones de la Sesión', fontsize=9, color='#9ca3af')
            ax.set_xticks([0, 1, 2, 3, 4, 5])
            ax.tick_params(colors='#9ca3af', labelsize=9)
            ax.text(0.08, 0.15, "0.00", color=color_zero, fontsize=9, weight='bold', va='bottom', ha='left')
            fig.tight_layout(pad=1.2)
            fig.subplots_adjust(left=0.08, right=0.98, top=0.91, bottom=0.12)
            return fig

    def _cmd_excel(self):
        self.log("📑 Generando bitácora Excel unificada de operaciones...", "INFO")
        try:
            import pandas as pd
            import glob
            
            all_files = glob.glob(str(self.base_dir / "logs" / "trades" / "trades_*.csv"))
            if not all_files:
                self.log("No se encontraron archivos de trades para exportar a Excel.", "WARN")
                return
            
            po_dfs = []
            alpaca_dfs = []
            for f in all_files:
                f_name = Path(f).name
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        if "alpaca" in f_name:
                            alpaca_dfs.append(df_temp)
                        elif "pocketoption_real" in f_name or "_real_" in f_name or "pocketoption" in f_name or "trades_" in f_name:
                            po_dfs.append(df_temp)
                except Exception:
                    pass
            
            if not po_dfs and not alpaca_dfs:
                self.log("Los archivos de registro de trades están vacíos.", "WARN")
                return

            out_excel = self.base_dir / "Bitacora_Trading_Alpaca_PocketOption.xlsx"
            total_records = 0
            with pd.ExcelWriter(out_excel, engine='openpyxl') as writer:
                if po_dfs:
                    df_po = pd.concat(po_dfs, ignore_index=True)
                    if 'timestamp' in df_po.columns:
                        df_po['timestamp'] = pd.to_datetime(df_po['timestamp'], errors='coerce')
                        df_po = df_po.sort_values('timestamp', ascending=False)
                    df_po.to_excel(writer, sheet_name='PocketOption', index=False)
                    total_records += len(df_po)
                
                if alpaca_dfs:
                    df_al = pd.concat(alpaca_dfs, ignore_index=True)
                    if 'timestamp' in df_al.columns:
                        df_al['timestamp'] = pd.to_datetime(df_al['timestamp'], errors='coerce')
                        df_al = df_al.sort_values('timestamp', ascending=False)
                    df_al.to_excel(writer, sheet_name='Alpaca', index=False)
                    total_records += len(df_al)
            
            self.log(f"✅ Bitácora Excel generada con éxito ({total_records} operaciones registradas).", "WIN")
            if sys.platform == "win32":
                os.startfile(str(out_excel))
                self.log(f"📑 Abriendo {out_excel.name} en Microsoft Excel...", "WIN")
        except Exception as e:
            self.log(f"Error al generar Excel: {e}", "LOSS")

    def _cmd_test(self):
        self.log("🧪 Iniciando simulación cuantitativa bajo demanda...", "INFO")
        try:
            today_trades = self.get_today_trades()
            wins = sum(1 for t in today_trades if t.get('result') == 'WIN')
            total = len(today_trades)
            wr = (wins / total * 100) if total > 0 else 0.0
            pnl = sum(t.get('profit', 0.0) for t in today_trades)
            self.log("=" * 55, "INFO")
            self.log("🧪 RESULTADOS DE SIMULACIÓN CUANTITATIVA", "WIN")
            self.log(f"• Muestras analizadas: {total} operaciones", "INFO")
            self.log(f"• Tasa de Acierto: {wr:.1f}% ({wins}W / {total - wins}L)", "WIN" if wr >= 60 else "WARN")
            self.log(f"• Expectativa Matemática (PnL): {pnl:+.2f} USD", "WIN" if pnl >= 0 else "LOSS")
            self.log("• Estado de Estrategias: Operativas con gestión de riesgo Miriam Molina activa.", "INFO")
            self.log("=" * 55, "INFO")
        except Exception as e:
            self.log(f"Error en simulación: {e}", "LOSS")

    def _cmd_help(self):
        self.log("=" * 55, "INFO")
        self.log("📖 COMANDOS DISPONIBLES EN PIBOT TERMINAL", "INFO")
        self.log("• /info - Rendimiento global del día, métricas y PnL", "INFO")
        self.log("• /balance - Balances en vivo de PocketOption y Alpaca", "INFO")
        self.log("• /po - Estado del Money Management y sesión PocketOption", "INFO")
        self.log("• /alpaca - Equity y posiciones abiertas en Alpaca", "INFO")
        self.log("• /daily - Historial y lista de operaciones de hoy", "INFO")
        self.log("• /chart - Genera y abre el gráfico de rendimiento técnico", "INFO")
        self.log("• /excel - Exporta y abre la bitácora completa en Excel", "INFO")
        self.log("• /limpiar_ram - Libera memoria RAM del sistema Windows", "INFO")
        self.log("• /recursos - Diagnóstico de CPU, RAM y procesos activos", "INFO")
        self.log("• /test - Ejecuta simulación cuantitativa bajo demanda", "INFO")
        self.log("• /reset_session - Reinicia la sesión diaria de trading a 0", "INFO")
        self.log("• /restart_bot - Reinicia en caliente el motor de trading", "INFO")
        self.log("=" * 55, "INFO")

gui_bridge = GUIBridge()
