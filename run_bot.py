import subprocess
import sys
import time
import os
import psutil

# Forzar encoding UTF-8 en Windows para evitar crashes por emojis en stdout/stderr
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

BOT_SCRIPT = "main.py"
PIBOT_SCRIPT = "pibot_service.py"
WEB_SERVER_SCRIPT = "web_server.py"
RESTART_EXIT_CODE = 5

def ensure_web_server_running(web_proc=None):
    """Asegura que el servidor Web / Telegram Mini App esté siempre activo en puerto 8080."""
    try:
        if web_proc is not None and web_proc.poll() is None:
            return web_proc

        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                cmd = " ".join(p.info.get('cmdline') or [])
                if WEB_SERVER_SCRIPT in cmd and p.pid != os.getpid():
                    return None
            except Exception:
                pass

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen([sys.executable, "-u", WEB_SERVER_SCRIPT],
                                stdout=open("web_server.log", "a", encoding="utf-8", buffering=1),
                                stderr=subprocess.STDOUT,
                                creationflags=creationflags)
        print(f"[Supervisor] 🚀 Telegram Mini App WebServer iniciado ({WEB_SERVER_SCRIPT}).")
        return proc
    except Exception as e:
        print(f"[Supervisor] Error lanzando {WEB_SERVER_SCRIPT}: {e}")
        return None

def ensure_pibot_running(pibot_proc=None):
    """Asegura que el servicio pibot_service.py (@pi_gui_bot) esté siempre activo en segundo plano."""
    try:
        # 1. Chequear si el proceso hijo que lanzamos sigue vivo
        if pibot_proc is not None and pibot_proc.poll() is None:
            return pibot_proc

        # 2. Chequear si ya hay otra instancia de pibot_service.py corriendo en Windows
        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                cmd = " ".join(p.info.get('cmdline') or [])
                if PIBOT_SCRIPT in cmd and p.pid != os.getpid():
                    return None  # Ya está activo externamente
            except Exception:
                pass

        # 3. Si no está corriendo, lanzarlo de inmediato en segundo plano
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen([sys.executable, "-u", PIBOT_SCRIPT],
                                stdout=open("pibot_service.log", "a", encoding="utf-8", buffering=1),
                                stderr=subprocess.STDOUT,
                                creationflags=creationflags)
        return proc
    except Exception as e:
        print(f"[Supervisor] Error lanzando {PIBOT_SCRIPT}: {e}")
        return None

def ensure_single_instance():
    """Evita que se ejecuten dos instancias simultáneas del supervisor o del bot."""
    current_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.info['pid'] == current_pid:
                continue
            cmdline = p.info.get('cmdline') or []
            if any(arg.endswith('run_bot.py') for arg in cmdline):
                print(f"[Supervisor] ⚠️ Ya hay una instancia de run_bot.py activa (PID {p.info['pid']}).")
                print("[Supervisor] Cancelando inicio para no duplicar operaciones.")
                sys.exit(0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

# ============================================================
# FILTRO GUI: solo las líneas que contienen estas palabras se
# muestran en la consola de la GUI. TODO se sigue guardando
# completo en bot_output.log (no se pierde nada).
# ============================================================
GUI_KEYWORDS = (
    "Instancia Paper Trial",       # 🧪 preparación del explorador
    "[PAPER] ✅",                  # trade paper ganado
    "[PAPER] ❌",                  # trade paper perdido
    "[PAPER] 🤝",                  # trade paper empatado
    "[ERR]", "ERROR",              # solo errores graves
)

def is_gui_relevant(line):
    """True si la línea merece aparecer en la GUI (además del archivo)."""
    return any(k in line for k in GUI_KEYWORDS)


def run_bot_with_tee(args):
    """Lanza main.py: TODO va a bot_output.log; solo lo importante a la GUI."""
    with open("bot_output.log", "a", encoding="utf-8", buffering=1) as logf:
        process = subprocess.Popen(
            [sys.executable, "-u", BOT_SCRIPT] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for line in iter(process.stdout.readline, ''):
            logf.write(line)               # → archivo (histórico completo, siempre)
            if is_gui_relevant(line):      # → GUI (solo lo relevante)
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception:
                    pass
        process.stdout.close()
        process.wait()
        return process.returncode

def main():
    ensure_single_instance()
    print(f"--- SUPERVISOR DE BOT INICIADO ---")
    print(f"Controlando: {BOT_SCRIPT}, {PIBOT_SCRIPT} y {WEB_SERVER_SCRIPT}")
    print(f"Para reiniciar el bot externamente, crea un archivo llamado 'restart.signal'")
    
    # Limpiar cualquier killapp.flag residual previo al inicio
    try:
        if os.path.exists("killapp.flag"):
            os.remove("killapp.flag")
    except Exception:
        pass
    
    pibot_proc = None
    web_proc = None
    
    while True:
        # Asegurar que el bot de control remoto (PiBot) y el WebServer estén siempre vivos
        pibot_proc = ensure_pibot_running(pibot_proc)
        web_proc = ensure_web_server_running(web_proc)

        print(f"\n[Supervisor] Iniciando {BOT_SCRIPT}...")
        
        # Ejecutar el bot usando el mismo intérprete de Python actual
        try:
            exit_code = run_bot_with_tee(sys.argv[1:])
            print(f"[Supervisor] Bot finalizado con código: {exit_code}")
            
            if os.path.exists("killapp.flag"):
                print("[Supervisor] 🛑 Killapp detectado. Apagando supervisor por completo...")
                try:
                    os.remove("killapp.flag")
                except Exception:
                    pass
                break

            if exit_code == RESTART_EXIT_CODE:
                print("[Supervisor] ✨ Solicitud de reinicio detectada. Reiniciando en 2 segundos...")
                time.sleep(2)
                continue # Vuelve al inicio del while para relanzar
            
            # Si el código no es 5 (ej: error 1, o cierre manual 0), salimos del supervisor también
            if exit_code != 0:
                print("[Supervisor] ⚠️ El bot se cerró con error. Esperando 10 segundos antes de reintentar por seguridad...")
                time.sleep(10)
                continue # Reintentar incluso si falla, para robustez (opcional, o break para salir)
            else:
                print("[Supervisor] Bot cerrado (Killapp/Manual). Apagando supervisor.")
                break
                
        except KeyboardInterrupt:
            print("\n[Supervisor] Interrupción de teclado. Cerrando...")
            break
        except Exception as e:
            print(f"[Supervisor] Error crítico lanzando el bot: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
