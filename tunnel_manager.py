import os
import re
import sys
import time
import atexit
import threading
import subprocess
from pathlib import Path

class CloudflareTunnelManager:
    _instance = None

    def __init__(self, port=8080):
        self.port = port
        self.process = None
        self.tunnel_url = None
        self.cloudflared_path = Path("bin") / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared")
        self._lock = threading.Lock()
        atexit.register(self.stop)

    @classmethod
    def get_instance(cls, port=8080):
        if cls._instance is None:
            cls._instance = cls(port=port)
        return cls._instance

    def start(self):
        with self._lock:
            if self.tunnel_url and self.process and self.process.poll() is None:
                return self.tunnel_url

            if not self.cloudflared_path.exists():
                print(f"[Tunnel] AVISO: {self.cloudflared_path} no encontrado. Modo tunel desactivado.")
                return None

            try:
                # Matar instancias previas de cloudflared si quedaron huerfanas
                if sys.platform == "win32":
                    subprocess.run("taskkill /f /im cloudflared.exe", shell=True, capture_output=True)

                cmd = [str(self.cloudflared_path.resolve()), "tunnel", "--url", f"http://127.0.0.1:{self.port}"]
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Leer stdout para extraer la URL https://*.trycloudflare.com
                start_time = time.time()
                while time.time() - start_time < 20:
                    line = self.process.stdout.readline()
                    if not line and self.process.poll() is not None:
                        break
                    match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                    if match:
                        self.tunnel_url = match.group(0)
                        print(f"[Tunnel] [OK] Cloudflare Tunnel activo: {self.tunnel_url}")
                        Path("biometric_url.txt").write_text(f"{self.tunnel_url}/biometric", encoding="utf-8")
                        break

                if not self.tunnel_url:
                    print("[Tunnel] AVISO: No se pudo obtener la URL de Cloudflare Tunnel en 20s.")
                    return None

                # Hilo en segundo plano para consumir el buffer y evitar bloqueos
                def _drain_output():
                    while self.process and self.process.poll() is None:
                        try:
                            l = self.process.stdout.readline()
                            if not l: break
                        except Exception:
                            break

                t = threading.Thread(target=_drain_output, daemon=True)
                t.start()

                return self.tunnel_url

            except Exception as e:
                print(f"[Tunnel] ERROR iniciando Cloudflare Tunnel: {e}")
                return None

    def get_biometric_url(self):
        if not self.tunnel_url:
            self.start()
        return f"{self.tunnel_url}/biometric" if self.tunnel_url else None

    def stop(self):
        with self._lock:
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None
                self.tunnel_url = None
                try:
                    p = Path("biometric_url.txt")
                    if p.exists(): p.unlink()
                except Exception:
                    pass
                print("[Tunnel] Cloudflare Tunnel detenido.")

tunnel_manager = CloudflareTunnelManager.get_instance()
