"""
PiBot Trading Terminal Launcher (.pyw)
Permite iniciar la aplicación gráfica nativa en Windows sin consola de comandos.
"""
import sys
import os
from pathlib import Path

# Fijar directorio de trabajo al del script
base_dir = Path(__file__).resolve().parent
os.chdir(str(base_dir))

from gui_app import TradingTerminalApp, acquire_gui_single_instance_lock

if __name__ == "__main__":
    try:
        if not acquire_gui_single_instance_lock():
            sys.exit(0)
        app = TradingTerminalApp()
        app.mainloop()
    except Exception as e:
        import traceback
        with open("gui_crash.log", "w") as f:
            f.write(traceback.format_exc())
        raise
