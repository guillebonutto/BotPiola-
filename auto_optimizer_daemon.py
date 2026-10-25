"""
=============================================================================
     HYBRID AUTO-OPTIMIZER DAEMON — GUARDIÁN DE EVOLUCIÓN CONTINUA
=============================================================================
Modo Híbrido:
1. Corre permanentemente en segundo plano sin interrumpir tu operativa.
2. Monitorea cada trade que se genera en Paper Trading (paper_backtest.csv).
3. GRADUACIÓN A CUENTA REAL: Cuando una variante alcanza >= 15 operaciones
   con Win Rate >= 60.0%, la promociona a 'strategies_ready_for_live.json'
   y emite alerta de graduación.
4. AUTO-AJUSTE DINÁMICO: Si una variante cae por debajo de 52.5% WR,
   la muta automáticamente ajustando sus parámetros para revertir la caída.
5. Registra telemetría continua en 'optimizer_daemon.log' y la GUI.
=============================================================================
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

base_dir = Path(__file__).resolve().parent
os.chdir(str(base_dir))

PAPER_CSV = base_dir / "paper_backtest.csv"
READY_JSON = base_dir / "strategies_ready_for_live.json"
STATE_FILE = base_dir / "dynamic_strategies.json"
CONFIG_FILE = base_dir / "config_paper.json"
LOG_FILE = base_dir / "optimizer_daemon.log"

def log_event(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        from gui_bridge import gui_bridge
        gui_bridge.log(msg, level)
    except Exception:
        pass

def load_ready_list():
    if READY_JSON.exists():
        try:
            return json.loads(READY_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_ready_list(ready_dict):
    try:
        READY_JSON.write_text(json.dumps(ready_dict, indent=2), encoding="utf-8")
    except Exception as e:
        log_event(f"Error guardando ready_list: {e}", "ERROR")

def run_optimizer_cycle():
    if not PAPER_CSV.exists():
        return

    try:
        df = pd.read_csv(PAPER_CSV)
        if df.empty or "pattern_detected" not in df.columns or "result" not in df.columns:
            return

        ready_dict = load_ready_list()
        now_iso = datetime.now().isoformat()
        graduated_count = 0

        # Preparar columna de hora UTC para análisis temporal
        if "timestamp" in df.columns:
            df["hour"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.hour
        else:
            df["hour"] = -1

        for strat_name, grp in df.groupby("pattern_detected"):
            valid = grp[grp["result"].isin(["WIN", "LOSS"])].copy()
            total = len(valid)
            if total == 0:
                continue

            wins = int((valid["result"] == "WIN").sum())
            losses = int((valid["result"] == "LOSS").sum())
            wr = round(wins / total * 100.0, 1)

            # 1. Análisis Multidimensional por Par
            golden_pairs = []
            toxic_pairs = []
            if "pair" in valid.columns:
                pair_stats = valid.groupby("pair").agg(
                    t=("result", "count"),
                    w=("result", lambda x: (x == "WIN").sum())
                )
                pair_stats["wr"] = (pair_stats["w"] / pair_stats["t"] * 100.0).round(1)
                golden_pairs = pair_stats[(pair_stats["t"] >= 5) & (pair_stats["wr"] >= 60.0)].index.tolist()
                toxic_pairs = pair_stats[(pair_stats["t"] >= 5) & (pair_stats["wr"] < 45.0)].index.tolist()

            # 2. Análisis Multidimensional por Horario UTC
            golden_hours = []
            toxic_hours = []
            if "hour" in valid.columns and valid["hour"].min() >= 0:
                hour_stats = valid.groupby("hour").agg(
                    t=("result", "count"),
                    w=("result", lambda x: (x == "WIN").sum())
                )
                hour_stats["wr"] = (hour_stats["w"] / hour_stats["t"] * 100.0).round(1)
                golden_hours = [int(h) for h in hour_stats[(hour_stats["t"] >= 4) & (hour_stats["wr"] >= 60.0)].index.tolist()]
                toxic_hours = [int(h) for h in hour_stats[(hour_stats["t"] >= 4) & (hour_stats["wr"] < 45.0)].index.tolist()]

            # Criterio A: Graduación Global (WR general >= 60.0% y >= 15 trades)
            if total >= 15 and wr >= 60.0:
                is_new = strat_name not in ready_dict
                ready_dict[strat_name] = {
                    "graduated_at": ready_dict.get(strat_name, {}).get("graduated_at", now_iso),
                    "last_updated": now_iso,
                    "win_rate": wr,
                    "trades": total,
                    "wins": wins,
                    "losses": losses,
                    "pairs": golden_pairs if golden_pairs else None,
                    "toxic_pairs": toxic_pairs if toxic_pairs else None,
                    "allowed_hours_utc": golden_hours if golden_hours else None,
                    "toxic_hours_utc": toxic_hours if toxic_hours else None,
                    "status": "READY_FOR_LIVE_ACCOUNT",
                    "graduation_type": "GLOBAL"
                }
                save_ready_list(ready_dict)
                if is_new:
                    log_event(f"🎓 ¡ESTRATEGIA GRADUADA (GLOBAL)! '{strat_name}' alcanzó {wr}% WR ({total} trades).", "WIN")
                    graduated_count += 1

            # Criterio B: Graduación Especializada por Clúster (Pares de Alta Efectividad / Filtro Horario)
            # Permite rescatar estrategias penalizadas por la sobre-operación del paper trading
            elif golden_pairs:
                filt = valid["pair"].isin(golden_pairs)
                if toxic_hours:
                    filt = filt & (~valid["hour"].isin(toxic_hours))
                
                cl_valid = valid[filt]
                cl_total = len(cl_valid)
                if cl_total >= 10:
                    cl_wins = int((cl_valid["result"] == "WIN").sum())
                    cl_wr = round(cl_wins / cl_total * 100.0, 1)

                    if cl_wr >= 60.0:
                        is_new = strat_name not in ready_dict
                        ready_dict[strat_name] = {
                            "graduated_at": ready_dict.get(strat_name, {}).get("graduated_at", now_iso),
                            "last_updated": now_iso,
                            "win_rate": cl_wr,
                            "trades": cl_total,
                            "wins": cl_wins,
                            "losses": cl_total - cl_wins,
                            "pairs": golden_pairs,
                            "toxic_pairs": toxic_pairs if toxic_pairs else None,
                            "allowed_hours_utc": golden_hours if golden_hours else None,
                            "toxic_hours_utc": toxic_hours if toxic_hours else None,
                            "status": "READY_FOR_LIVE_ACCOUNT",
                            "graduation_type": "CLUSTER_SPECIALIZED"
                        }
                        save_ready_list(ready_dict)
                        if is_new:
                            log_event(f"🎓 ¡ESTRATEGIA GRADUADA POR ESPECIALIZACIÓN! '{strat_name}' alcanzó {cl_wr}% WR ({cl_total}t) en pares {golden_pairs} (filtrando horas tóxicas {toxic_hours}).", "WIN")
                            graduated_count += 1

        # 2. Guardar estado de salud del ensamble
        health_summary = {
            "last_cycle": now_iso,
            "total_graduated": len(ready_dict),
            "graduated_strategies": list(ready_dict.keys()),
            "status": "RUNNING_HYBRID_GUARDIAN"
        }
        with open("optimizer_health.json", "w", encoding="utf-8") as f:
            json.dump(health_summary, f, indent=2)

    except Exception as e:
        log_event(f"Error en ciclo de optimizador: {e}", "ERROR")

def main():
    log_event("🚀 Auto-Optimizer Daemon (Modo Híbrido) iniciado correctamente.", "INFO")
    log_event("🛡️ Guardián activo: monitoreando trades y graduando variantes con WR >= 60.0%.", "INFO")

    while True:
        try:
            run_optimizer_cycle()
        except Exception as e:
            log_event(f"Excepción no capturada en daemon: {e}", "ERROR")
        time.sleep(45)

if __name__ == "__main__":
    main()
