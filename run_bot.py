import subprocess
import sys
import time
import os

BOT_SCRIPT = "main.py"
RESTART_EXIT_CODE = 5

def main():
    print(f"--- SUPERVISOR DE BOT INICIADO ---")
    print(f"Controlando: {BOT_SCRIPT}")
    print(f"Para reiniciar el bot externamente, crea un archivo llamado 'restart.signal'")
    
    while True:
        print(f"\n[Supervisor] Iniciando {BOT_SCRIPT}...")
        
        # Ejecutar el bot usando el mismo intérprete de Python actual
        try:
            # sys.executable asegura que usamos el mismo python que lanzó este script
            process = subprocess.run([sys.executable, BOT_SCRIPT])
            
            exit_code = process.returncode
            print(f"[Supervisor] Bot finalizado con código: {exit_code}")
            
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
                print("[Supervisor] Bot cerrado manualmente. Apagando supervisor.")
                break
                
        except KeyboardInterrupt:
            print("\n[Supervisor] Interrupción de teclado. Cerrando...")
            break
        except Exception as e:
            print(f"[Supervisor] Error crítico lanzando el bot: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
