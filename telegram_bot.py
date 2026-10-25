import aiohttp
import asyncio
import io
import os
import glob
import json
import html
import subprocess
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone, timedelta
from pathlib import Path
import psutil

try:
    from telegram_agent import AntigravityTelegramAgent
except ImportError:
    AntigravityTelegramAgent = None

try:
    from comment_generator import comment_generator
except ImportError:
    comment_generator = None

# Configurar matplotlib para backend no interactivo
plt.switch_backend('Agg')

class TelegramNotifier:
    BUTTON_MAP = {
        "📈 info hoy": "/info",
        "📈 info": "/info",
        "info hoy": "/info",
        "info": "/info",
        "stats": "/info",
        "estadisticas": "/info",
        "estadísticas": "/info",
        "💰 balances": "/balance",
        "💰 balance": "/balance",
        "balances": "/balance",
        "balance": "/balance",
        "📊 gráfico": "/chart",
        "📊 grafico": "/chart",
        "gráfico": "/chart",
        "grafico": "/chart",
        "chart": "/chart",
        "velas": "/chart",
        "foto": "/chart",
        "🧪 simulación": "/test",
        "🧪 simulacion": "/test",
        "simulación": "/test",
        "simulacion": "/test",
        "test": "/test",
        "backtest": "/test",
        "🟢 pocketoption": "/po",
        "pocketoption": "/po",
        "po": "/po",
        "🔸 alpaca": "/alpaca_info",
        "alpaca": "/alpaca_info",
        "alpaca info": "/alpaca_info",
        "📅 cierre": "/daily",
        "cierre": "/daily",
        "daily": "/daily",
        "reporte": "/daily",
        "🔄 reiniciar bot": "/reiniciar_bot",
        "reiniciar bot": "/reiniciar_bot",
        "restart bot": "/reiniciar_bot",
        "📑 excel": "/excel",
        "excel": "/excel",
        "planilla": "/excel",
        "🛠️ menú pc": "/pc",
        "🛠️ menu pc": "/pc",
        "menú pc": "/pc",
        "menu pc": "/pc",
        "pc": "/pc",
        "sistema": "/pc",
        "🧹 limpiar ram": "/limpiar_ram",
        "limpiar ram": "/limpiar_ram",
        "optimizar ram": "/limpiar_ram",
        "📊 recursos pc": "/recursos",
        "recursos pc": "/recursos",
        "recursos": "/recursos",
        "tareas": "/recursos",
        "🖥️ destrabar gui": "/restart_gui",
        "destrabar gui": "/restart_gui",
        "destrabar": "/restart_gui",
        "⚡ reiniciar pc": "/reboot_pc",
        "reiniciar pc": "/reboot_pc",
        "🔙 volver a trading": "/back",
        "volver a trading": "/back",
        "volver": "/back",
        "back": "/back",
        "inicio": "/back",
        "menu": "/back",
        "pausa": "/pause",
        "pausar": "/pause",
        "detener": "/pause",
        "reanudar": "/resume",
        "continuar": "/resume",
        "ayuda": "/help",
        "help": "/help"
    }


    MAIN_COMMANDS_PUBLIC = [
        {"command": "info", "description": "📈 Rendimiento global del día y gráfico P&L"},
        {"command": "po", "description": "🟢 Detalle y métricas PocketOption"},
        {"command": "alpaca", "description": "🔸 Estado y posiciones en vivo Alpaca"},
        {"command": "balance", "description": "💰 Balances de PocketOption y Alpaca"},
        {"command": "daily", "description": "📅 Resumen diario de operaciones"},
        {"command": "excel", "description": "📑 Exportar historial a Excel"},
        {"command": "chart", "description": "📊 Foto y gráfico técnico PocketOption"},
        {"command": "test", "description": "🧪 Simulación cuantitativa bajo demanda"},
        {"command": "restart_bot", "description": "🔄 Reiniciar proceso del bot"}
    ]

    MAIN_COMMANDS_PRIVATE = [
        {"command": "info", "description": "📈 Rendimiento global del día y gráfico P&L"},
        {"command": "po", "description": "🟢 Detalle y métricas PocketOption"},
        {"command": "alpaca", "description": "🔸 Estado y posiciones en vivo Alpaca"},
        {"command": "balance", "description": "💰 Balances de PocketOption y Alpaca"},
        {"command": "daily", "description": "📅 Resumen diario de operaciones"},
        {"command": "excel", "description": "📑 Exportar historial a Excel"},
        {"command": "chart", "description": "📊 Foto y gráfico técnico PocketOption"},
        {"command": "test", "description": "🧪 Simulación cuantitativa bajo demanda"},
        {"command": "restart_bot", "description": "🔄 Reiniciar proceso del bot"},
        {"command": "pc", "description": "🛠️ Herramientas de sistema y PC"}
    ]

    PC_SUBMENU_COMMANDS = [
        {"command": "limpiar_ram", "description": "🧹 Liberar memoria RAM del sistema"},
        {"command": "recursos", "description": "📊 Monitor de CPU, RAM y procesos activos"},
        {"command": "restart_gui", "description": "🖥️ Reiniciar interfaz gráfica (Explorer)"},
        {"command": "reboot_pc", "description": "⚡ Reiniciar equipo Windows"},
        {"command": "back", "description": "🔙 Volver al menú principal de trading"}
    ]

    PC_COMMANDS = {
        "/cmd", "/exec",
        "/reboot_pc", "/restart_pc", "/shutdown_pc", "/reiniciar_pc", "/apagar_pc",
        "/kill", "/terminar", "/cerrar_proceso",
        "/kill_app", "/cerrar_app", "/cerrar_navegador",
        "/limpiar_ram", "/clean_ram", "/optimizar_ram",
        "/restart_gui", "/unfreeze", "/reiniciar_gui", "/destrabar",
        "/pc", "/pc_status", "/system", "/sistema",
        "/recursos", "/top", "/tareas", "/drenaje", "/task_manager", "/diagnostico",
        "/killapp", "/standby", "/dormir", "/apagar_bot",
        "/auth", "/biometria", "/faceid", "/huella", "/desbloquear",
        "/lock", "/bloquear", "/cerrar_sesion",
        "/reset_face",
        "/set_amount", "/set_monto"
    }

    def __init__(self, token, chat_id, owner_id=None, feedback_db=None, get_balance_callback=None, get_stats_callback=None, gemini_api_key=None, bot_ref=None, security_pin=None):
        # Sanitize token
        if token:
            # Eliminar prefijo 'bot' si existe (case insensitive)
            if token.lower().startswith('bot'):
                token = token[3:]
            # Limpiar espacios y caracteres extraños
            token = token.strip()
            
            # Validación simple de formato (números:caracteres)
            import re
            if not re.match(r'^\d+:[A-Za-z0-9_-]+$', token):
                print(f"[Telegram] [!] ADVERTENCIA: El token '{token}' no parece válido. Formato esperado: '123456:ABC-DEF...'")
                
            self.token = token
            masked = f"{self.token[:4]}...{self.token[-4:]}" if len(self.token) > 8 else "***"
            print(f"[Telegram] Configurado con token: {masked}")
            self.base_url = f"https://api.telegram.org/bot{self.token}"
        else:
            self.token = None
            print("[Telegram] Token no proporcionado.")
            self.base_url = ""

        self.chat_id = chat_id
        
        # Procesar owner_id (puede ser int, str, o lista/tupla de ellos)
        self.owner_ids = []
        if owner_id:
            if isinstance(owner_id, (list, tuple)):
                self.owner_ids = [int(i) for i in owner_id]
            elif isinstance(owner_id, str) and ',' in owner_id:
                self.owner_ids = [int(i.strip()) for i in owner_id.split(',')]
            else:
                self.owner_ids = [int(owner_id)]

        # Dueño de la PC física (Guille: 913843638). Solo este ID tiene acceso a comandos de PC
        self.pc_owner_id = 913843638
        if self.owner_ids and 913843638 in self.owner_ids:
            self.pc_owner_id = 913843638
        elif self.owner_ids:
            self.pc_owner_id = self.owner_ids[0]
        
        # Sesiones biométricas activas (Telegram Mini App BiometricManager): user_id -> timestamp_expiracion
        self.biometric_sessions = {}
        self.biometric_session_duration = 1800  # 30 minutos de acceso desbloqueado tras validar rostro/huella

        # Control anti-spam y blacklist automática de intrusos
        self.unauthorized_attempts = {}  # user_id -> list of timestamps
        self.last_intrusion_alert = {}   # user_id -> timestamp
        self.blacklisted_users = set()   # set of blacklisted user_ids

        # Control dinámico de menús de comandos (Trading vs Herramientas PC)
        self.pc_menu_active_chats = {}  # chat_id -> timestamp_expiracion
        self.pc_menu_timeout = 300      # 5 minutos de inactividad antes de volver al menú de trading

        self.feedback_db = feedback_db
        self.get_balance_callback = get_balance_callback
        self.get_stats_callback = get_stats_callback
        self.gemini_api_key = gemini_api_key
        self.bot_ref = bot_ref
        self.is_paused = False
        self.bot_start_time = time.time()
        self.last_update_id = 0
        try:
            offset_file = Path(".telegram_offset")
            if offset_file.exists():
                self.last_update_id = int(offset_file.read_text(encoding="utf-8").strip())
        except Exception:
            pass
        self.listening = False
        self.logs_dir = Path("logs/trades")
        
        # Registro anti-duplicados y anti-spam de notificaciones de cierre
        self._sent_close_trade_ids = set()
        self._recent_close_notifications = {} # (pair, round(profit, 2)): timestamp

        # Inicializar Antigravity AI Agent
        self.agent = None
        if AntigravityTelegramAgent and self.gemini_api_key:
            try:
                self.agent = AntigravityTelegramAgent(api_key=self.gemini_api_key, workspace_dir=os.getcwd(), bot_ref=self.bot_ref)
                print("[Telegram] [AI Agent] Antigravity AI Agent & Remote PC Control ACTIVO.")
            except Exception as e:
                print(f"[Telegram] Error inicializando Antigravity Agent: {e}")

        # Asegurar carpetas y memes por defecto
        self._ensure_default_memes()

    def is_biometric_unlocked(self, user_id):
        """Verifica si el usuario tiene una sesión biométrica activa no expirada."""
        if not user_id:
            return False
        exp = self.biometric_sessions.get(int(user_id), 0)
        return time.time() < exp

    def get_biometric_url(self):
        """Obtiene la URL pública HTTPS de Cloudflare Tunnel para la Mini App."""
        url_file = Path("biometric_url.txt")
        if url_file.exists():
            try:
                url = url_file.read_text(encoding="utf-8").strip()
                if url.startswith("https://"):
                    return url
            except Exception:
                pass
        try:
            from tunnel_manager import tunnel_manager
            return tunnel_manager.get_biometric_url()
        except Exception as e:
            print(f"[Telegram Biometrics] Error obteniendo URL de túnel: {e}")
            return None

    def get_biometric_keyboard(self):
        """Genera el ReplyKeyboardMarkup con el botón que abre la Mini App Biométrica."""
        url = self.get_biometric_url()
        if not url:
            return None
        return {
            "keyboard": [
                [
                    {
                        "text": "🛡️ Desbloquear con Rostro / Huella",
                        "web_app": {"url": url}
                    }
                ]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def get_webapp_url(self):
        """Obtiene la URL pública HTTPS para la Telegram Mini App Dashboard."""
        try:
            from tunnel_manager import tunnel_manager
            url = tunnel_manager.start()
            if url:
                return f"{url}/"
        except Exception as e:
            print(f"[Telegram MiniApp] Error obteniendo URL de túnel: {e}")
        return None

    def get_webapp_inline_keyboard(self):
        """Genera un InlineKeyboardMarkup con el botón de la Mini App."""
        url = self.get_webapp_url()
        if not url:
            return None
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "📱 Abrir Dashboard (Mini App)",
                        "web_app": {"url": url}
                    }
                ]
            ]
        }

    def get_main_keyboard(self, user_id=None, is_private=True):
        """Genera el ReplyKeyboardMarkup principal con botones táctiles rápidos."""
        is_pc_owner = bool(self.pc_owner_id and user_id and int(user_id) == self.pc_owner_id)
        
        url = self.get_webapp_url()
        rows = []
        # Telegram solo permite botones web_app en chats privados (en grupos causa error 400 Bad Request)
        if url and is_private:
            rows.append([{"text": "📱 Dashboard (Mini App)", "web_app": {"url": url}}])

        row1 = [
            {"text": "📈 Info Hoy"},
            {"text": "💰 Balances"},
            {"text": "📊 Gráfico"}
        ]
        row2 = [
            {"text": "🟢 PocketOption"},
            {"text": "🔸 Alpaca"},
            {"text": "🧪 Simulación"}
        ]
        if is_pc_owner:
            row3 = [
                {"text": "🔄 Reiniciar Bot"},
                {"text": "🛠️ Menú PC"},
                {"text": "📑 Excel"}
            ]
        else:
            row3 = [
                {"text": "🔄 Reiniciar Bot"},
                {"text": "📑 Excel"}
            ]
            
        rows.extend([row1, row2, row3])
        return {
            "keyboard": rows,
            "resize_keyboard": True,
            "is_persistent": True
        }

    def get_pc_keyboard(self):
        """Genera el ReplyKeyboardMarkup con herramientas de PC exclusivas para Guille."""
        return {
            "keyboard": [
                [{"text": "🧹 Limpiar RAM"}, {"text": "📊 Recursos PC"}],
                [{"text": "🖥️ Destrabar GUI"}, {"text": "⚡ Reiniciar PC"}],
                [{"text": "🔙 Volver a Trading"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    async def send_message(self, message, reply_to_message_id=None, target_chat_id=None, **kwargs):
        """Envía un mensaje a Telegram de forma asíncrona."""
        # Si target_chat_id es una lista/tupla, enviar a todos
        if isinstance(target_chat_id, (list, tuple)):
            results = []
            for tid in target_chat_id:
                res = await self.send_message(message, reply_to_message_id, tid)
                results.append(res)
            return results[0] if results else None

        dest_chat_id = target_chat_id if target_chat_id else self.chat_id

        if not self.token or not dest_chat_id:
            # print("[Telegram] No configurado (Falta Token o Chat ID).")
            return None

        # Preparar payload base
        payload = {
            'chat_id': dest_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id

        if 'reply_markup' in kwargs:
            rm = kwargs['reply_markup']
            # Sanitizar reply_markup para grupos: Telegram prohíbe Web App buttons en grupos
            if isinstance(rm, dict) and 'keyboard' in rm:
                try:
                    dest_int = int(dest_chat_id)
                    if dest_int < 0: # Grupo o supergrupo
                        cleaned_kb = []
                        for row in rm.get('keyboard', []):
                            filtered_row = [btn for btn in row if 'web_app' not in btn]
                            if filtered_row:
                                cleaned_kb.append(filtered_row)
                        rm = dict(rm)
                        rm['keyboard'] = cleaned_kb
                except Exception:
                    pass
            payload['reply_markup'] = rm

        async def _do_send(current_payload):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage", 
                    json=current_payload,
                    timeout=aiohttp.ClientTimeout(total=8.0)
                ) as response:
                    try:
                        res_json = await response.json()
                    except Exception:
                        res_json = {}
                    return response.status, await response.text(), res_json

        try:
            status, text, data = await _do_send(payload)
            
            # --- MANEJO DE RATE LIMIT (429) ---
            if status == 429:
                retry_after = min(int(data.get('parameters', {}).get('retry_after', 2)), 10)
                print(f"[Telegram] ⏳ Rate limit alcanzado ({status}). Esperando {retry_after}s...")
                await asyncio.sleep(retry_after + 0.5)
                status, text, data = await _do_send(payload) # Reintento

            if status == 200:
                return data.get('result', {}).get('message_id')
            
            # Manejo de Errores
            print(f"[Telegram] Error enviando mensaje (HTML): {status} - {text}")
            
            # --- MANEJO ESPECÍFICO DE CHAT NOT FOUND ---
            if status == 400 and "chat not found" in text.lower():
                print(f"[Telegram] ❌ ERROR: El Chat ID '{dest_chat_id}' no es válido o el bot no ha sido iniciado allí.")
                print(f"[Telegram] 💡 TIP: Asegúrate de que el ID sea correcto y de haber enviado /start al bot en ese chat.")
                return None

            # Reintento automágico en Texto Plano (si falló por formato, ej 400 Bad Request)
            if status == 400 and "parse" in text.lower():
                print("[Telegram] Intentando re-enviar como Texto Plano...")
                payload.pop('parse_mode') # Quitar modo HTML
                
                status_retry, text_retry, data_retry = await _do_send(payload)
                if status_retry == 200:
                    print("[Telegram] ✅ Reenvio exitoso en Texto Plano.")
                    return data_retry.get('result', {}).get('message_id')
                else:
                    print(f"[Telegram] Falló reenvio en Texto Plano: {status_retry}")
            
            return None
            
        except Exception as e:
            print(f"[Telegram] Excepción al enviar: {e}")
            return None

    async def send_photo(self, photo_buffer, caption=None, target_chat_id=None, reply_markup=None):
        """Envía una foto a Telegram de forma asíncrona (admite chat único o lista de chats, Path, str o BytesIO)."""
        if isinstance(target_chat_id, (list, tuple)):
            results = []
            for tid in target_chat_id:
                if hasattr(photo_buffer, 'seek'):
                    photo_buffer.seek(0)
                res = await self.send_photo(photo_buffer, caption, tid, reply_markup=reply_markup)
                results.append(res)
            return results[0] if results else None

        dest_chat_id = target_chat_id if target_chat_id else self.chat_id

        if not self.token or not dest_chat_id:
            return None

        def _build_form_data():
            d = aiohttp.FormData()
            d.add_field('chat_id', str(dest_chat_id))
            if isinstance(photo_buffer, str) and (photo_buffer.startswith("http://") or photo_buffer.startswith("https://")):
                d.add_field('photo', photo_buffer)
            elif isinstance(photo_buffer, (str, Path)):
                p = Path(photo_buffer)
                if not p.exists():
                    return None
                ext = p.suffix.lower()
                mime = 'image/jpeg' if ext in ['.jpg', '.jpeg'] else ('image/webp' if ext == '.webp' else 'image/png')
                with open(p, 'rb') as f:
                    content = f.read()
                d.add_field('photo', content, filename=p.name, content_type=mime)
            elif hasattr(photo_buffer, 'seek'):
                photo_buffer.seek(0)
                d.add_field('photo', photo_buffer, filename='chart.png', content_type='image/png')
            elif isinstance(photo_buffer, bytes):
                d.add_field('photo', photo_buffer, filename='photo.png', content_type='image/png')
            else:
                return None

            if caption:
                d.add_field('caption', caption)
            d.add_field('parse_mode', 'HTML')
            if reply_markup:
                d.add_field('reply_markup', json.dumps(reply_markup))
            return d

        data = _build_form_data()
        if not data:
            return None

        async def _do_send_photo(current_data):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendPhoto", 
                    data=current_data,
                    timeout=aiohttp.ClientTimeout(total=12.0)
                ) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, data_res = await _do_send_photo(data)
            
            # --- MANEJO DE RATE LIMIT (429) ---
            if status == 429:
                retry_after = data_res.get('parameters', {}).get('retry_after', 30)
                print(f"[Telegram] ⏳ Rate limit alcanzado en foto. Esperando {retry_after}s...")
                await asyncio.sleep(retry_after + 1)
                data_retry = _build_form_data()
                if data_retry:
                    status, text, data_res = await _do_send_photo(data_retry)

            if status == 200:
                return data_res.get('result', {}).get('message_id')
            else:
                print(f"[Telegram] Error enviando foto: {status} - {text}")
                return None
        except Exception as e:
            print(f"[Telegram] Excepción al enviar foto: {e}")
            return None

    async def send_document(self, document_buffer, filename="report.xlsx", caption=None, target_chat_id=None):
        """Envía un archivo/documento a Telegram de forma asíncrona (admite chat único o lista de chats)."""
        if isinstance(target_chat_id, (list, tuple)):
            results = []
            for tid in target_chat_id:
                if hasattr(document_buffer, 'seek'):
                    document_buffer.seek(0)
                res = await self.send_document(document_buffer, filename, caption, tid)
                results.append(res)
            return results[0] if results else None

        dest_chat_id = target_chat_id if target_chat_id else self.chat_id

        if not self.token or not dest_chat_id:
            return None

        if hasattr(document_buffer, 'seek'):
            document_buffer.seek(0)

        data = aiohttp.FormData()
        data.add_field('chat_id', str(dest_chat_id))
        data.add_field('document', document_buffer, filename=filename, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if caption:
            data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')

        async def _do_send_doc(current_data):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendDocument", 
                    data=current_data,
                    timeout=aiohttp.ClientTimeout(total=15.0)
                ) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, res_data = await _do_send_doc(data)
            if status == 200:
                return res_data.get('result', {}).get('message_id')
            else:
                print(f"[Telegram] Error enviando documento: {status} - {text}")
                return None
        except Exception as e:
            print(f"[Telegram] Excepción enviando documento: {e}")
            return None

    async def delete_message(self, chat_id, message_id):
        """Elimina un mensaje de un chat (si el bot tiene permisos de administrador)."""
        if not self.token or not chat_id or not message_id:
            return False
        try:
            url = f"{self.base_url}/deleteMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, 
                    json={'chat_id': str(chat_id), 'message_id': int(message_id)}, 
                    timeout=aiohttp.ClientTimeout(total=5.0)
                ) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        print(f"[Telegram] Aviso: No se pudo borrar mensaje {message_id} en {chat_id}: HTTP {response.status} - {err_text}")
                    return response.status == 200
        except Exception as e:
            print(f"[Telegram] Excepción borrando mensaje {message_id} en {chat_id}: {e}")
            return False

    async def notify_open(self, pair, action, strategy, timeframe, amount):
        icon = "🟢" if action == 'BUY' else "🔴"
        direction = "CALL (BUY)" if action == 'BUY' else "PUT (SELL)"
        pair_emoji = self._get_pair_emoji(pair)
        
        msg = (
            f"{icon} <b>NEW TRADE OPENED</b> {icon}\n\n"
            f"<b>Pair:</b> {pair_emoji} {pair}\n"
            f"📈 <b>Action:</b> {direction}\n"
            f"🧠 <b>Strategy:</b> {strategy}\n"
            f"⏱ <b>Timeframe:</b> {timeframe}s\n"
            f"💵 <b>Amount:</b> ${amount:.2f}\n"
            f"🕓 <b>Date & Time (UTC-3):</b> {self._get_time()}"
        )
        await self.send_message(msg)

    def _ensure_default_memes(self):
        """Descarga y asegura memes icónicos (DiCaprio, Stonks, Cheems, Harold) en assets/memes/{win|loss}."""
        try:
            base_dir = Path("assets/memes")
            win_dir = base_dir / "win"
            loss_dir = base_dir / "loss"
            win_dir.mkdir(parents=True, exist_ok=True)
            loss_dir.mkdir(parents=True, exist_ok=True)

            valid_exts = {'.png', '.jpg', '.jpeg', '.webp'}
            win_files = [f for f in win_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
            loss_files = [f for f in loss_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]

            import urllib.request
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

            def download_img(url, dest_path):
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        if resp.status == 200:
                            data = resp.read()
                            if len(data) > 1000:
                                dest_path.write_bytes(data)
                                print(f"[Memes] ✅ Meme descargado: {dest_path.name}")
                                return True
                except Exception as e:
                    pass
                return False

            if not win_files:
                download_img("https://i.imgflip.com/1ur9b0.jpg", win_dir / "dicaprio_cheers.jpg")
                download_img("https://i.imgflip.com/30b1gx.jpg", win_dir / "stonks.jpg")
                download_img("https://i.imgflip.com/3si4.jpg", win_dir / "success_kid.jpg")

            if not loss_files:
                download_img("https://i.imgflip.com/46e43q.png", loss_dir / "cheems_sad.png")
                download_img("https://i.imgflip.com/21uy0f.jpg", loss_dir / "harold_pain.jpg")
                download_img("https://i.imgflip.com/1c1uej.jpg", loss_dir / "crying_cat.jpg")

        except Exception as e:
            print(f"[Telegram Memes] Aviso inicializando memes: {e}")

    async def _get_random_meme(self, is_win):
        """Obtiene un meme aleatorio de assets/memes/{win|loss} o una URL de respaldo."""
        import random
        subfolder = "win" if is_win else "loss"
        memes_dir = Path("assets/memes") / subfolder
        if memes_dir.exists():
            valid_exts = {'.png', '.jpg', '.jpeg', '.webp'}
            files = [f for f in memes_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
            if files:
                return random.choice(files)

        fallback_urls = {
            "win": [
                "https://i.imgflip.com/1ur9b0.jpg",
                "https://i.imgflip.com/30b1gx.jpg",
            ],
            "loss": [
                "https://i.imgflip.com/46e43q.png",
                "https://i.imgflip.com/21uy0f.jpg",
            ]
        }
        urls = fallback_urls.get(subfolder, [])
        return random.choice(urls) if urls else None

    async def notify_close(self, pair, profit, is_win, trade_id=None):
        now_ts = time.time()
        
        # 1. Filtro anti-duplicado por trade_id
        if trade_id:
            trade_id_str = str(trade_id)
            if trade_id_str in self._sent_close_trade_ids:
                print(f"[Telegram] [WARN] Notificacion duplicada bloqueada para trade_id {trade_id_str}")
                return None
            self._sent_close_trade_ids.add(trade_id_str)
            
        # 2. Filtro anti-spam temporal (mismo par y mismo PnL en menos de 60 segundos)
        pair_profit_key = (pair, round(profit, 2))
        last_sent = self._recent_close_notifications.get(pair_profit_key, 0)
        if now_ts - last_sent < 60:
            print(f"[Telegram] [WARN] Anti-Spam: Notificacion identica bloqueada para {pair} (${profit:+.2f}) en ventana de 60s")
            return None
        self._recent_close_notifications[pair_profit_key] = now_ts

        icon = "✅" if is_win else "❌"
        result_text = "WON (WIN)" if is_win else "LOST (LOSS)"
        pair_emoji = self._get_pair_emoji(pair)
        
        # Generar comentario dinámico (IA o frase estoica)
        bot_comment = None
        if comment_generator:
            try:
                bot_comment = await comment_generator.generate_close_comment(
                    pair, profit, is_win, api_key=self.gemini_api_key
                )
            except Exception as e:
                print(f"[Telegram] [CommentGen] Aviso generando comentario dinámico: {e}")
                
        comment_section = f"💬 <i>\"{bot_comment}\"</i>\n\n" if bot_comment else ""

        msg = (
            f" <b>TRADE CLOSED</b>\n\n"
            f"<b>Pair:</b> {pair_emoji} {pair}\n"
            f"🏆 <b>Result:</b> {result_text} {icon}\n"
            f"🤑 <b>Profit:</b> ${profit:+.2f}\n\n"
            f"{comment_section}"
            f"🕓 <b>Date & Time (UTC-3):</b> {self._get_time()}"
        )
        
        # Add feedback buttons if trade_id is available
        reply_markup = None
        if trade_id:
            reply_markup = {
                'inline_keyboard': [[
                    {'text': '👍 Good', 'callback_data': f'fb_{trade_id}_good'},
                    {'text': '👎 Bad', 'callback_data': f'fb_{trade_id}_bad'},
                    {'text': '📝 Comment', 'callback_data': f'fb_{trade_id}_comment'}
                ]]
            }

        message_id = await self.send_message(msg, reply_markup=reply_markup)
        return message_id
    
    async def request_feedback(self):
        """Requests feedback from user."""
        msg = (
            "📝 <b>How was the analysis?</b>\n\n"
            "Reply to this message with:\n"
            "• Your analysis (good/bad, what to improve?)\n"
            "• Optionally, attach a chart screenshot"
        )
        message_id = await self.send_message(msg)
        return message_id

    @staticmethod
    def _get_pair_emoji(pair):
        """Obtener emoji para el par de monedas."""
        emojis = {
            'EUR': '🇪🇺',
            'USD': '🇺🇸',
            'GBP': '🇬🇧',
            'JPY': '🇯🇵',
            'AUD': '🇦🇺',
            'CAD': '🇨🇦',
            'CHF': '🇨🇭',
            'MXN': '🇲🇽',
            'COP': '🇨🇴',
        }
        
        # Extraer monedas base y cotizada
        if '_otc' in pair:
            pair = pair.replace('_otc', '')
        
        if len(pair) >= 6:
            base = pair[:3]
            quote = pair[3:6]
            return f"{emojis.get(base, '💱')}/{emojis.get(quote, '💱')}"
        
        return '💱'

    def _get_time(self):
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=-3)) 
        return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

    def _parse_date_range(self, text):
        """Parsea un rango de fechas del texto del comando."""
        # Formato: /comando DD/MM/YYYY HH:MM DD/MM/YYYY HH:MM
        import re
        pattern = r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2})'
        matches = re.findall(pattern, text)
        if len(matches) >= 2:
            try:
                start_dt = datetime.strptime(matches[0], '%d/%m/%Y %H:%M')
                end_dt = datetime.strptime(matches[1], '%d/%m/%Y %H:%M')
                return start_dt, end_dt
            except:
                return None, None
        return None, None

    async def register_bot_commands(self):
        """Registra la configuración oficial de comandos en Telegram vía setMyCommands para el menú '/'."""
        url = f"{self.base_url}/setMyCommands"

        # 1. Comandos públicos (grupos y default)
        public_scopes = [
            {"type": "default"},
            {"type": "all_group_chats"}
        ]
        if self.chat_id:
            try:
                cid = int(self.chat_id)
                if cid < 0:
                    public_scopes.append({"type": "chat", "chat_id": cid})
            except Exception:
                pass

        for scope in public_scopes:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json={"commands": self.MAIN_COMMANDS_PUBLIC, "scope": scope}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        res = await response.json()
                        if res.get("ok"):
                            print(f"[Telegram Bot] [OK] Comandos públicos registrados en setMyCommands (Scope: {scope['type']}).")
            except Exception as e:
                print(f"[Telegram Bot] Error en setMyCommands público para scope {scope}: {e}")

        # 2. Comandos privados (all_private_chats y chats específicos de owners)
        private_scopes = [
            {"type": "all_private_chats"}
        ]
        if self.owner_ids:
            for oid in self.owner_ids:
                private_scopes.append({"type": "chat", "chat_id": oid})

        for scope in private_scopes:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json={"commands": self.MAIN_COMMANDS_PRIVATE, "scope": scope}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        res = await response.json()
                        if res.get("ok"):
                            print(f"[Telegram Bot] [OK] Comandos privados registrados en setMyCommands (Scope: {scope['type']}).")
            except Exception as e:
                print(f"[Telegram Bot] Error en setMyCommands privado para scope {scope}: {e}")

    async def _set_chat_commands(self, chat_id, commands):
        """Aplica una lista de comandos al chat_id especificado vía setMyCommands."""
        if not self.token or not chat_id:
            return False
        url = f"{self.base_url}/setMyCommands"
        scope = {"type": "chat", "chat_id": int(chat_id)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"commands": commands, "scope": scope}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    res = await resp.json()
                    return res.get("ok", False)
        except Exception as e:
            print(f"[Telegram Bot] Error seteando comandos para chat {chat_id}: {e}")
            return False

    async def set_main_commands(self, chat_id):
        """Restaura el menú principal según sea chat privado del dueño de la PC u otros usuarios."""
        is_pc_owner = (self.pc_owner_id and int(chat_id) == self.pc_owner_id)
        cmds = self.MAIN_COMMANDS_PRIVATE if is_pc_owner else self.MAIN_COMMANDS_PUBLIC
        return await self._set_chat_commands(chat_id, cmds)

    async def set_pc_commands(self, chat_id):
        """Activa el submenú de herramientas de PC."""
        return await self._set_chat_commands(chat_id, self.PC_SUBMENU_COMMANDS)

    async def _check_pc_menu_expirations(self):
        """Comprueba si expiró el tiempo de inactividad del menú PC para algún chat."""
        if not self.pc_menu_active_chats:
            return
        now = time.time()
        expired = [cid for cid, exp in list(self.pc_menu_active_chats.items()) if now > exp]
        for cid in expired:
            try:
                del self.pc_menu_active_chats[cid]
                await self.set_main_commands(cid)
                await self.send_message(
                    "⏱️ <i>Menú de herramientas PC finalizado por inactividad. Se restauró el menú principal de trading en <code>/</code>.</i>",
                    target_chat_id=cid
                )
            except Exception as e:
                print(f"[Telegram Bot] Error al restaurar menú tras expiración para {cid}: {e}")

    async def update_menu_button(self):
        """Actualiza el botón de Menú persistente en Telegram con la nueva URL de Cloudflare."""
        url = self.get_webapp_url()
        if not url:
            return
        
        api_url = f"https://api.telegram.org/bot{self.token}/setChatMenuButton"
        payload = {
            "menu_button": {
                "type": "web_app",
                "text": "📱 Mini App",
                "web_app": {"url": url}
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    print(f"[Telegram Bot] Botón de menú web persistente actualizado. Status: {response.status}")
        except Exception as e:
            print(f"[Telegram Bot] Error actualizando botón de menú web persistente: {e}")

    async def start_listening(self):
        """Inicia el listener de mensajes de Telegram en background."""
        if not self.token or not self.chat_id:
            print("[Telegram Listener] No configurado.")
            return
        
        self.listening = True
        print("[Telegram Listener] Iniciado. Esperando feedback...")
        
        # Enviar mensaje de reinicio para actualizar el teclado WebApp con la nueva URL de Cloudflare
        try:
            kb = self.get_biometric_keyboard()
            if kb:
                asyncio.create_task(self.send_message(
                    "⚡ <b>Sistema Iniciado / Reiniciado</b>\n\nEl sistema está en línea. Se ha actualizado tu conexión segura con la Mini App.",
                    target_chat_id=self.chat_id,
                    reply_markup=kb
                ))
        except Exception as e:
            print(f"[Telegram Bot] Aviso enviando saludo inicial: {e}")
        
        # Registrar automáticamente los comandos oficiales en segundo plano sin demorar el inicio del polling
        try:
            asyncio.create_task(self.register_bot_commands())
            asyncio.create_task(self.update_menu_button())
        except Exception as ce:
            print(f"[Telegram Bot] Aviso registrando comandos/menu: {ce}")
        
        # Cargar offset persistente si aún está en 0
        if self.last_update_id == 0:
            try:
                offset_file = Path(".telegram_offset")
                if offset_file.exists():
                    self.last_update_id = int(offset_file.read_text(encoding="utf-8").strip())
            except Exception:
                pass

        while self.listening:
            try:
                await self._poll_updates()
                await asyncio.sleep(2)  # Poll cada 2 segundos
            except Exception as e:
                print(f"[Telegram Listener] Error: {e}")
                await asyncio.sleep(5)
    
    def stop_listening(self):
        """Detiene el listener."""
        self.listening = False
    
    async def _poll_updates(self):
        """Obtiene nuevos mensajes de Telegram."""
        # Verificar expiraciones de submenú PC
        try:
            await self._check_pc_menu_expirations()
        except Exception as e:
            print(f"[Telegram Bot] Error en _check_pc_menu_expirations: {e}")

        url = f"{self.base_url}/getUpdates"
        params = {
            'offset': (self.last_update_id + 1) if self.last_update_id > 0 else 0,
            'timeout': 30
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as response:
                    if response.status == 200:
                        data = await response.json()
                        updates = data.get('result', [])
                        
                        for update in updates:
                            self.last_update_id = update['update_id']
                            try:
                                Path(".telegram_offset").write_text(str(self.last_update_id), encoding="utf-8")
                            except Exception:
                                pass
                            asyncio.create_task(self._process_update(update))
        except asyncio.TimeoutError:
            pass  # Normal, solo significa que no hubo mensajes
        except Exception as e:
            print(f"[Telegram Listener] Error polling: {e}")
    
    async def _handle_callback_query(self, cb):
        """Maneja las pulsaciones de botones inline (Feedback de trades, etc.)."""
        cb_id = cb.get('id')
        user = cb.get('from', {})
        user_id = user.get('id')
        user_name = user.get('first_name', 'Usuario')
        data = cb.get('data', '')
        message = cb.get('message', {})
        chat = message.get('chat', {})
        chat_id = chat.get('id', self.chat_id)
        msg_id = message.get('message_id')

        # Responder a Telegram para quitar animación de carga del botón
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            payload = {'callback_query_id': cb_id}
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as e:
            print(f"[Telegram Callback] Error contestando callback query: {e}")

        # Procesar feedback de trades: fb_{trade_id}_{reaction}
        if data.startswith('fb_'):
            parts = data.split('_')
            if len(parts) >= 3:
                trade_id = parts[1]
                reaction = parts[2]
                rx_icon = "👍" if reaction == "good" else ("👎" if reaction == "bad" else "📝")
                rx_label = "Positivo (Good)" if reaction == "good" else ("Negativo (Bad)" if reaction == "bad" else "Comentario")
                
                if self.feedback_db:
                    try:
                        self.feedback_db.add_feedback(
                            message_id=msg_id or trade_id,
                            feedback_text=f"Inline Feedback: {reaction.upper()} ({rx_icon})",
                            image_path=None
                        )
                    except Exception as e:
                        print(f"[Telegram Feedback] Error guardando feedback: {e}")

                status_msg = f"{rx_icon} <b>Feedback registrado ({user_name}):</b> {rx_label} para la operación <code>{trade_id}</code>."
                await self.send_message(status_msg, target_chat_id=chat_id)
                print(f"[Telegram Callback] Feedback guardado: {reaction} para trade {trade_id}")
        elif data:
            # Soporte completo para botones inline que ejecutan comandos
            cb_cmd = data
            if cb_cmd.startswith('cmd_'):
                cb_cmd = cb_cmd[4:]
            norm_cb = cb_cmd.lower().replace('️', '').replace('︎', '').strip()
            if norm_cb in self.BUTTON_MAP:
                cb_cmd = self.BUTTON_MAP[norm_cb]
            elif not cb_cmd.startswith('/'):
                cb_cmd = f"/{cb_cmd}"

            fake_msg = {
                'from': user,
                'chat': chat,
                'message_id': msg_id,
                'text': cb_cmd
            }
            await self._process_update({'message': fake_msg})

    async def _process_update(self, update):
        """Procesa un update de Telegram."""
        callback_query = update.get('callback_query')
        if callback_query:
            await self._handle_callback_query(callback_query)
            return

        message = update.get('message')
        if not message:
            return
        
        user_id = message.get('from', {}).get('id')
        user_name = message.get('from', {}).get('first_name', 'Unknown')
        user_handle = message.get('from', {}).get('username')
        user_tag = f"@{user_handle}" if user_handle else user_name
        raw_text = message.get('text', message.get('caption', '')).strip()
        text = raw_text.lower()
        chat_type = message.get('chat', {}).get('type', 'private')
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        is_group = chat_type in ['group', 'supergroup']

        # Normalizar y mapear inmediatamente botones táctiles rápidos (antes del filtro de grupo)
        clean_text = text.strip()
        norm_text = clean_text.replace('️', '').replace('︎', '').strip()
        matched_cmd = self.BUTTON_MAP.get(clean_text) or self.BUTTON_MAP.get(norm_text)
        if matched_cmd:
            cmd = matched_cmd
            full_cmd = matched_cmd
            raw_text = matched_cmd
            is_command = True
        else:
            is_command = text.startswith('/')
            cmd_parts = text.split()
            full_cmd = cmd_parts[0] if cmd_parts else ""
            cmd = full_cmd.split('@')[0] if '@' in full_cmd else full_cmd

        # --- SECURITY CHECK ---
        # Usuarios autorizados: Dueños configurados (Guille, Cococo) o miembros del grupo oficial de trading
        is_owner = bool(self.owner_ids and user_id in self.owner_ids)
        is_official_group = bool(self.chat_id and str(chat_id) == str(self.chat_id))
        is_authorized = is_owner or is_official_group

        if not is_authorized:
            # 1. Si el usuario ya fue puesto en la lista negra, descartar en silencio total
            if user_id in self.blacklisted_users:
                if is_group and message_id:
                    await self.delete_message(chat_id, message_id)
                return

            if is_command or chat_type == 'private':
                now = time.time()
                # Borrar el comando del grupo de inmediato para no dejar registro
                if is_group and message_id:
                    await self.delete_message(chat_id, message_id)

                # Monitorear frecuencia de intentos (en ventana móvil de 60 segundos)
                attempts = [t for t in self.unauthorized_attempts.get(user_id, []) if now - t <= 60]
                attempts.append(now)
                self.unauthorized_attempts[user_id] = attempts

                # Si hizo 3 o más intentos en 60 segundos -> Blacklist automática permanente
                if len(attempts) >= 3:
                    self.blacklisted_users.add(user_id)
                    print(f"[Telegram Security] [BLACKLIST] {user_name} ({user_id}) bloqueado.")
                    await self.send_message(
                        message=f"🛡️ <b>BLACKLIST AUTOMÁTICA DE INTRUSO:</b>\n"
                                f"El usuario {user_name} ({user_tag} | <code>{user_id}</code>) intentó 3 comandos en menos de 1 minuto y ha sido <b>añadido a la lista negra</b>. Sus mensajes futuros serán descartados en silencio.",
                        target_chat_id=self.pc_owner_id
                    )
                    return

                # Cooldown de alertas (máximo 1 alerta cada 5 minutos por usuario no autorizado)
                last_alert = self.last_intrusion_alert.get(user_id, 0)
                if now - last_alert >= 300:
                    self.last_intrusion_alert[user_id] = now
                    print(f"[Telegram Security] [BLOQUEADO] Usuario NO autorizado: {user_name} ({user_id}) -> '{raw_text}'")
                    await self.send_message(
                        message=f"🚨 <b>Intento de comando NO autorizado:</b>\n"
                                f"👤 <b>Usuario:</b> {user_name} ({user_tag})\n"
                                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                                f"💬 <b>Chat:</b> {chat_type} (<code>{chat_id}</code>)\n"
                                f"⌨️ <b>Comando:</b> <code>{raw_text}</code>",
                        target_chat_id=self.pc_owner_id
                    )
                return
            else:
                # Mensaje común en grupo (no comando) de usuario no autorizado: ignorar
                return

        # Si es un grupo pero el mensaje no empieza con '/', no es un comando para el bot: ignorar
        if is_group and not is_command:
            return

        # --- RECEPCIÓN DE AUTENTICACIÓN DE MINI APP BIOMÉTRICA (ANDROID FACE/HUELLA) ---
        web_app_data = message.get('web_app_data')
        if web_app_data:
            try:
                payload = json.loads(web_app_data.get('data', '{}'))
                if payload.get('verified') is True:
                    self.biometric_sessions[int(user_id)] = time.time() + self.biometric_session_duration
                    bio_type = payload.get('type', 'biometric')
                    if bio_type in ['guille_face_recognition', 'guille_face_enrolled']:
                        bio_label = "Reconocimiento Facial Exclusivo de Guille"
                    elif bio_type == 'fingerprint':
                        bio_label = "Huella Digital"
                    else:
                        bio_label = "Sensor Biométrico"
                    print(f"[Telegram Biometrics] [OK] Sesión autorizada para {user_name} ({user_id}) vía {bio_label}.")
                    await self.send_message(
                        f"🔓 <b>IDENTIDAD VERIFICADA EXITOSAMENTE</b>\n\n"
                        f"✅ Autenticación confirmada vía <b>{bio_label}</b> en tu celular.\n"
                        f"⏱️ Sesión administrativa desbloqueada por <b>30 minutos</b>.\n\n"
                        f"Ya puedes ejecutar los comandos protegidos:\n"
                        f"• <code>/cmd &lt;comando&gt;</code> (Consola remota)\n"
                        f"• <code>/set_amount &lt;monto&gt;</code> (Ajuste de capital)\n"
                        f"• <code>/reboot_pc confirm</code> (Reinicio del sistema)\n\n"
                        f"<i>Para bloquear inmediatamente la sesión, escribe /lock.</i>",
                        target_chat_id=chat_id,
                        reply_markup={"remove_keyboard": True}
                    )
                    return
                else:
                    await self.send_message(
                        "❌ <b>Verificación biométrica no superada.</b> Toca el botón para reintentar.",
                        target_chat_id=chat_id,
                        reply_markup=self.get_biometric_keyboard()
                    )
                    return
            except Exception as e:
                print(f"[Telegram Biometrics] Error procesando web_app_data: {e}")
                return

        # --- DETECTOR DE AMENAZAS / PALABRAS SENSIBLES ---
        threat_keywords = ["hacked", "hackeado", "token", "password", "leak"]
        if any(kw in text for kw in threat_keywords):
            await self.send_message(
                message=f"⚠️ <b>SECURITY ALERT</b>\nUser {user_id} ({user_name}) mentioned sensitive keywords: <i>{raw_text}</i>",
                target_chat_id=self.owner_ids
            )

        # Botones táctiles rápidos ya fueron mapeados al inicio de _process_update
        if cmd.startswith('/'):
            print(f"[Telegram] Comando recibido: {cmd} de {user_name} ({user_id}) en {chat_type} {chat_id}")
            # Si el comando proviene de un grupo de Telegram, borrarlo de inmediato para mantener el chat limpio
            if is_group and message_id:
                asyncio.create_task(self.delete_message(chat_id, message_id))

        # --- FILTRO DE SEGURIDAD EXCLUSIVO: COMANDOS DE PC SOLO PARA GUILLE ---
        if cmd in self.PC_COMMANDS:
            if user_id != self.pc_owner_id:
                print(f"[Telegram Security] [PC BLOCKED] {user_name} ({user_id}) intentó ejecutar comando de PC: {cmd}")
                await self.send_message(
                    "🔒 <b>ACCESO RESTRINGIDO: COMANDO DE PC</b>\n\n"
                    "Este comando pertenece al control del sistema y hardware de la computadora de Guille y solo puede ser ejecutado por él.",
                    target_chat_id=chat_id if is_group else user_id
                )
                if is_group and message_id:
                    await self.delete_message(chat_id, message_id)
                return

        # REGLA DE SEGURIDAD CRÍTICA:
        # En grupos, la respuesta a CUALQUIER comando se envía ÚNICAMENTE por privado al usuario autorizado (user_id).
        # Jamás se responde al chat del grupo con información sensible de cuentas, balances o trades.
        response_target = user_id if is_group else chat_id

        # Notificar en el grupo que la respuesta fue enviada por privado y borrar el comando del chat público
        async def _notify_private_sent():
            if is_group:
                if message_id:
                    await self.delete_message(chat_id, message_id)
                notice_id = await self.send_message(
                    f"🔒 <i>{user_tag}, te envié la respuesta por privado por seguridad.</i>\n"
                    f"<i>(Si aún no abriste chat privado con el bot, abrilo y tocá /start para recibir mensajes).</i>",
                    target_chat_id=chat_id
                )
                if notice_id:
                    async def _auto_delete():
                        await asyncio.sleep(12)
                        await self.delete_message(chat_id, notice_id)
                    asyncio.create_task(_auto_delete())

        if cmd in ["/chart", "/grafico", "/foto", "/velas"]:
            await self._handle_chart(response_target, raw_text, user_id=user_id)
            await _notify_private_sent()
            return
        elif cmd in ["/test", "/backtest", "/simular", "/simulacion"]:
            await self._handle_test(response_target, raw_text, user_id=user_id)
            await _notify_private_sent()
            return
        elif cmd in ["/balance", "/bal"]:
            await self._handle_balance(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/alpaca_info", "/alpaca", "/posicion", "/position", "/pos"]:
            await self._handle_alpaca_info(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/info", "/stats", "/performance"]:
            await self._handle_info(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/excel", "/export", "/report", "/reporte"]:
            await self._handle_excel(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/daily_report", "/daily", "/reporte_diario"]:
            parts = raw_text.split()
            target_date_arg = parts[1] if len(parts) > 1 else None
            await self.send_daily_report(target_date=target_date_arg, target_chat_ids=[response_target])
            await _notify_private_sent()
            return
        elif cmd in ["/detail_info", "/info_details", "/details", "/detail", "/range_stats", "/detalles"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_info_details(response_target, start_dt, end_dt, broker="both")
            await _notify_private_sent()
            return
        elif cmd in ["/detail_po", "/po", "/info_po", "/po_info", "/detail_info_po", "/info_details_po", "/details_po", "/po_details", "/po_detail"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_info_details(response_target, start_dt, end_dt, broker="pocketoption")
            await _notify_private_sent()
            return
        elif cmd in ["/detail_alpaca", "/info_alpaca", "/detail_info_alpaca", "/info_details_alpaca", "/details_alpaca", "/alpaca_details", "/alpaca_detail"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_info_details(response_target, start_dt, end_dt, broker="alpaca")
            await _notify_private_sent()
            return
        elif cmd in ["/range_detailed", "/history"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_range_detailed(response_target, start_dt, end_dt)
            await _notify_private_sent()
            return
        elif cmd in ["/pc", "/pc_status", "/system", "/sistema", "/status"]:
            await self._handle_pc_status(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/back", "/volver", "/inicio", "/main", "/menu"]:
            await self._handle_back_to_main(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/killapp", "/standby", "/dormir", "/apagar_bot"]:
            await self._handle_manual_killapp(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/recursos", "/top", "/tareas", "/drenaje", "/task_manager", "/diagnostico"]:
            if response_target in self.pc_menu_active_chats:
                self.pc_menu_active_chats[response_target] = time.time() + self.pc_menu_timeout
            await self._handle_resources(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/kill", "/terminar", "/cerrar_proceso"]:
            await self._handle_kill_pid(response_target, raw_text, user_id)
            await _notify_private_sent()
            return
        elif cmd in ["/kill_app", "/cerrar_app", "/cerrar_navegador"]:
            await self._handle_kill_app(response_target, raw_text, user_id)
            await _notify_private_sent()
            return
        elif cmd in ["/limpiar_ram", "/clean_ram", "/optimizar_ram"]:
            if response_target in self.pc_menu_active_chats:
                self.pc_menu_active_chats[response_target] = time.time() + self.pc_menu_timeout
            await self._handle_clean_ram(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/reboot_pc", "/restart_pc", "/shutdown_pc", "/reiniciar_pc", "/apagar_pc"]:
            if response_target in self.pc_menu_active_chats:
                self.pc_menu_active_chats[response_target] = time.time() + self.pc_menu_timeout
            if not self.is_biometric_unlocked(user_id):
                kb = self.get_biometric_keyboard()
                await self.send_message(
                    "🔒 <b>AUTENTICACIÓN REQUERIDA</b>\n\n"
                    "Reiniciar o apagar la PC requiere confirmación biométrica con el sensor de tu celular (Rostro o Huella).\n\n"
                    "👇 <b>Toca el botón para verificar tu identidad:</b>",
                    target_chat_id=response_target,
                    reply_markup=kb
                )
                await _notify_private_sent()
                return
            await self._handle_reboot_pc(response_target, raw_text, message_id=message_id, origin_chat_id=chat_id)
            await _notify_private_sent()
            return
        elif cmd in ["/restart_gui", "/unfreeze", "/reiniciar_gui", "/destrabar"]:
            if response_target in self.pc_menu_active_chats:
                self.pc_menu_active_chats[response_target] = time.time() + self.pc_menu_timeout
            await self._handle_restart_gui(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/restart_bot", "/reload", "/reiniciar_bot", "/recargar"]:
            msg_date = message.get('date', 0)
            if msg_date and msg_date < (self.bot_start_time - 15):
                print(f"[Telegram] ⚠️ Descartando comando de reinicio viejo (date: {msg_date} < start: {self.bot_start_time})")
                return
            await self._handle_restart_bot(chat_id)
            return
        elif cmd in ["/reset_session", "/nueva_sesion", "/reiniciar_sesion"]:
            if self.bot_ref and hasattr(self.bot_ref, 'mm') and self.bot_ref.mm is not None:
                self.bot_ref.mm.reset_session()
                self.bot_ref.is_retired = False
                await self.send_message(
                    "🔄 <b>SESIÓN DE TRADING REINICIADA</b>\n\n"
                    "• Score y PnL de sesión reseteados a 0.\n"
                    "• Estado: <b>Activo</b> (Buscando nuevas señales).\n"
                    "• Capital base y niveles de interés compuesto restablecidos.",
                    target_chat_id=response_target
                )
            else:
                try:
                    Path('reset_session.signal').touch()
                    await self.send_message("🔄 <b>Señal de reinicio de sesión enviada al bot.</b>", target_chat_id=response_target)
                except Exception as e:
                    await self.send_message(f"❌ Error al reiniciar sesión: {e}", target_chat_id=response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/pause", "/pausar", "/stop_trading"]:
            await self._handle_pause(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/resume", "/reanudar", "/start_trading"]:
            await self._handle_resume(response_target)
            await _notify_private_sent()
            return
        elif cmd in ["/set_amount", "/set_monto"]:
            if not self.is_biometric_unlocked(user_id):
                kb = self.get_biometric_keyboard()
                await self.send_message(
                    "🔒 <b>AUTENTICACIÓN REQUERIDA</b>\n\n"
                    "Modificar el capital por operación requiere confirmación biométrica con tu celular.\n\n"
                    "👇 <b>Toca el botón para desbloquear:</b>",
                    target_chat_id=response_target,
                    reply_markup=kb
                )
                await _notify_private_sent()
                return
            await self._handle_set_monto(response_target, raw_text, message_id=message_id, origin_chat_id=chat_id)
            await _notify_private_sent()
            return
        elif cmd in ["/cmd", "/exec"]:
            if not self.is_biometric_unlocked(user_id):
                kb = self.get_biometric_keyboard()
                await self.send_message(
                    "🔒 <b>AUTENTICACIÓN REQUERIDA</b>\n\n"
                    "La consola remota de Windows está protegida con biometría. Confirma con tu rostro o huella en tu celular.\n\n"
                    "👇 <b>Toca el botón para desbloquear:</b>",
                    target_chat_id=response_target,
                    reply_markup=kb
                )
                await _notify_private_sent()
                return
            await self._handle_cmd(response_target, raw_text, message_id=message_id, origin_chat_id=chat_id)
            await _notify_private_sent()
            return
        elif cmd in ["/auth", "/biometria", "/faceid", "/huella", "/desbloquear"]:
            if self.is_biometric_unlocked(user_id):
                mins = max(1, int((self.biometric_sessions.get(int(user_id), 0) - time.time()) / 60))
                await self.send_message(
                    f"🔓 <b>SESIÓN BIOMÉTRICA ACTIVA</b>\n\n"
                    f"Tu sesión administrativa ya está desbloqueada por <b>{mins} minutos</b> más.\n"
                    f"Para bloquear de inmediato, escribe <code>/lock</code>.",
                    target_chat_id=response_target,
                    reply_markup={"remove_keyboard": True}
                )
            else:
                kb = self.get_biometric_keyboard()
                if kb:
                    await self.send_message(
                        "🛡️ <b>DESBLOQUEO BIOMÉTRICO (ROSTRO / HUELLA)</b>\n\n"
                        "Toca el botón inferior para escanear tu rostro o huella en tu celular y desbloquear los comandos protegidos (<code>/cmd</code>, <code>/set_amount</code>, <code>/reboot_pc</code>) por 30 minutos.",
                        target_chat_id=response_target,
                        reply_markup=kb
                    )
                else:
                    await self.send_message(
                        "⚠️ <i>Iniciando túnel seguro para la Mini App biométrica... Por favor reintenta en unos segundos.</i>",
                        target_chat_id=response_target
                    )
            await _notify_private_sent()
            return
        elif cmd in ["/lock", "/bloquear", "/cerrar_sesion"]:
            self.biometric_sessions[int(user_id)] = 0
            await self.send_message(
                "🔒 <b>SESIÓN BLOQUEADA</b>\n\n"
                "La sesión administrativa ha sido cerrada. Los comandos protegidos volverán a solicitar verificación biométrica.",
                target_chat_id=response_target,
                reply_markup={"remove_keyboard": True}
            )
            await _notify_private_sent()
            return
        elif cmd in ["/reset_face", "/cambiar_rostro", "/recalibrar_rostro"]:
            if not self.is_biometric_unlocked(user_id):
                kb = self.get_biometric_keyboard()
                await self.send_message(
                    "🔒 <b>Sesión bloqueada</b>: Primero debes verificar tu identidad actual para recalibrar tu rostro.",
                    target_chat_id=response_target,
                    reply_markup=kb
                )
            else:
                from pathlib import Path
                for f in [Path("master_face_features.enc"), Path("master_face_features.npy"), Path("master_face.jpg")]:
                    if f.exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
                await self.send_message(
                    "📸 <b>ROSTRO MAESTRO REINICIADO</b>\n\n"
                    "Se ha eliminado la plantilla biométrica anterior. La próxima vez que toques el botón de desbloqueo, registrarás tu nuevo rostro maestro.",
                    target_chat_id=response_target,
                    reply_markup=self.get_biometric_keyboard()
                )
            await _notify_private_sent()
            return
        elif cmd in ["/ai", "/ia", "/ask", "/preguntar", "/antigravity"]:
            prompt = raw_text[len(full_cmd):].strip()
            if not prompt:
                await self.send_message("Please enter your instruction or question after the command.\nExample: <code>/ai Why did we lose the last USDCAD trade?</code>", target_chat_id=response_target)
            else:
                await self._handle_ia(response_target, prompt)
            await _notify_private_sent()
            return
        elif cmd in ["/help", "/ayuda", "/menu", "/start"]:
            await self._handle_help(response_target)
            await _notify_private_sent()
            return
        elif is_command:
            await self.send_message(f"❓ Comando no reconocido: <code>{cmd}</code>. Usa /help para ver la lista completa.", target_chat_id=response_target)
            await _notify_private_sent()
            return

        # If it's a private chat and not a command, treat the whole message as an AI prompt
        if chat_type == 'private':
            if raw_text:
                await self._handle_ia(chat_id, raw_text)
            return

        # Check if message is a reply (for feedback in group chat)
        reply_to = message.get('reply_to_message')
        if not reply_to:
            return  
        
        replied_message_id = reply_to.get('message_id')
        
        # Extract feedback text
        feedback_text = message.get('text', message.get('caption', ''))
        
        # Check if image attached
        image_path = None
        if 'photo' in message:
            image_path = await self._download_image(message['photo'])
        
        # Save feedback to DB
        handled_as_feedback = False
        if self.feedback_db and (feedback_text or image_path):
            handled_as_feedback = self.feedback_db.add_feedback(replied_message_id, feedback_text, image_path)
            if handled_as_feedback:
                print(f"[Feedback] Saved for message {replied_message_id}")
                await self.send_message("✅ Feedback saved. Thank you!", target_chat_id=chat_id)
            else:
                print(f"[Feedback] No trade found for message {replied_message_id}")
        
    async def _download_image(self, photos):
        """Descarga la imagen enviada por el usuario."""
        # Telegram envía varias resoluciones, tomamos la más grande
        photo = max(photos, key=lambda p: p.get('file_size', 0))
        file_id = photo['file_id']
        
        try:
            # Obtener ruta del archivo
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getFile"
                params = {'file_id': file_id}
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        file_path = data['result']['file_path']
                        
                        # Descargar imagen
                        download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                        async with session.get(download_url) as img_response:
                            if img_response.status == 200:
                                # Guardar en carpeta feedback_images
                                images_dir = Path('feedback_images')
                                images_dir.mkdir(exist_ok=True)
                                
                                # Nombre único basado en timestamp
                                from datetime import datetime
                                filename = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_id[:8]}.jpg"
                                save_path = images_dir / filename
                                
                                with open(save_path, 'wb') as f:
                                    f.write(await img_response.read())
                                
                                print(f"[Feedback] Imagen guardada: {save_path}")
                                return str(save_path)
        except Exception as e:
            print(f"[Feedback] Error descargando imagen: {e}")
        
        return None

    async def _handle_balance(self, chat_id):
        """Handle /balance command (shows balances for PocketOption and Alpaca)."""
        balance_po = "Unknown"
        if self.get_balance_callback:
            try:
                if asyncio.iscoroutinefunction(self.get_balance_callback):
                    balance_po = await self.get_balance_callback()
                else:
                    balance_po = self.get_balance_callback()
            except Exception as e:
                balance_po = f"Error: {e}"
                
        # Attempt to read Alpaca balance from shared status file
        balance_alpaca = None
        try:
            status_path = Path('alpaca_status.json')
            if status_path.exists():
                with open(status_path, 'r', encoding='utf-8') as sf:
                    shared = json.load(sf)
                    balance_alpaca = shared.get('balance')
        except Exception:
            pass
            
        msg = "💰 <b>CURRENT BALANCES</b>\n\n"
        if isinstance(balance_po, (int, float)):
            msg += f"🟢 <b>PocketOption (Binary Options):</b> ${balance_po:.2f}\n"
        else:
            msg += f"🟢 <b>PocketOption (Binary Options):</b> {balance_po}\n"
            
        if balance_alpaca is not None:
            if isinstance(balance_alpaca, (int, float)):
                msg += f"🔸 <b>Alpaca (Forex/Stocks):</b> ${balance_alpaca:.2f}\n"
            else:
                msg += f"🔸 <b>Alpaca (Forex/Stocks):</b> {balance_alpaca}\n"
            try:
                status_path = Path('alpaca_status.json')
                if status_path.exists():
                    with open(status_path, 'r', encoding='utf-8') as sf:
                        shared = json.load(sf)
                        inv_cap = shared.get('invested_capital')
                        max_inv = shared.get('max_invested_capital')
                        open_ops = shared.get('open_trades_count', len(shared.get('active_trades', {})))
                        if inv_cap is not None:
                            max_str = f" / Max: ${max_inv:,.2f}" if max_inv else ""
                            msg += f"   📊 <i>Invertido: ${inv_cap:,.2f}{max_str} ({open_ops} ops activas)</i>\n"
            except Exception:
                pass
        else:
            msg += f"🔸 <b>Alpaca (Forex/Stocks):</b> Disconnected / No Data\n"
            
        await self.send_message(msg, target_chat_id=chat_id)

    async def _handle_info(self, chat_id):
        """Handle /info command (statistics for both brokers + performance chart)."""
        await self.send_message("⏳ Generating dual performance report...", target_chat_id=chat_id)
        
        # 1. PocketOption balance
        balance_po = 0.0
        if self.get_balance_callback:
            try:
                if asyncio.iscoroutinefunction(self.get_balance_callback):
                    balance_po = await self.get_balance_callback()
                else:
                    balance_po = self.get_balance_callback()
                if not isinstance(balance_po, (int, float)):
                    balance_po = 0.0
            except Exception:
                pass

        # 2. Alpaca balance
        balance_alpaca = 0.0
        try:
            status_path = Path('alpaca_status.json')
            if status_path.exists():
                with open(status_path, 'r', encoding='utf-8') as sf:
                    shared = json.load(sf)
                    balance_alpaca = float(shared.get('balance', 0.0))
        except Exception:
            pass

        # Detect live logs
        all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
        has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files)
        po_suffix = "pocketoption_real" if has_real else "config"
        po_label = "POCKETOPTION REAL (Binary Options)" if has_real else "POCKETOPTION (Binary Options)"

        # 3. Calculate stats per broker
        stats_po = self._get_stats_for_broker(po_suffix)
        stats_alpaca = self._get_stats_for_broker("alpaca")
        
        # 4. Generate combined chart
        chart_buffer = self._generate_combined_chart(balance_po, balance_alpaca, only_today=False)
        
        msg = (
            f"<b>📊 DUAL PERFORMANCE REPORT</b>\n\n"
            f"🟢 <b>{po_label}</b>\n"
            f"• Balance: ${balance_po:.2f}\n"
            f"• Today: {stats_po['today_trades']} trades | {stats_po['today_winrate']:.1f}% WR | {stats_po['today_pnl']:+.2f} USD\n"
            f"• Total: {stats_po['trades']} trades | {stats_po['winrate']:.1f}% WR | {stats_po['pnl']:+.2f} USD\n\n"
            f"🔸 <b>ALPACA (Forex Spot)</b>\n"
            f"• Balance: ${balance_alpaca:.2f}\n"
            f"• Today: {stats_alpaca['today_trades']} trades | {stats_alpaca['today_winrate']:.1f}% WR | {stats_alpaca['today_pnl']:+.2f} USD\n"
            f"• Total: {stats_alpaca['trades']} trades | {stats_alpaca['winrate']:.1f}% WR | {stats_alpaca['pnl']:+.2f} USD\n\n"
            f"🏆 <b>GLOBAL</b>\n"
            f"• Total Trades: {stats_po['trades'] + stats_alpaca['trades']}\n"
            f"• Net P&L: {stats_po['pnl'] + stats_alpaca['pnl']:+.2f} USD\n\n"
            f"<i>Generated (UTC-3): {self._get_time()}</i>\n"
            f"💡 <i>Use /excel to download the spreadsheet with full breakdown.</i>"
        )
        
        if chart_buffer:
            await self.send_photo(chart_buffer, caption=msg, target_chat_id=chat_id)
        else:
            await self.send_message(msg, target_chat_id=chat_id)

    def _generate_alpaca_trade_chart(self, candles, trade_info):
        """
        Genera un gráfico de velas de alta definición estilo market_replay_ui con indicadores,
        líneas horizontales de TP (verde neón), SL (rojo carmesí), Entrada (cian) y Precio Actual (dorado).
        """
        try:
            if not candles:
                return None

            df = pd.DataFrame(candles)
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            
            # Calcular indicadores
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['sma200'] = df['close'].rolling(window=200, min_periods=10).mean()

            # Configuración de figura con estilo oscuro premium
            plt.style.use('dark_background')
            fig, (ax_main, ax_rsi) = plt.subplots(
                2, 1, 
                figsize=(12, 6.8), 
                gridspec_kw={'height_ratios': [3.5, 1]},
                dpi=120
            )
            
            # Colores base
            bg_color = '#0e131a'
            panel_color = '#151b24'
            grid_color = '#222b38'
            fig.patch.set_facecolor(bg_color)
            ax_main.set_facecolor(panel_color)
            ax_rsi.set_facecolor(panel_color)

            # Extraer variables de trade
            symbol = trade_info.get('symbol', 'ASSET')
            side = trade_info.get('side', 'BUY').upper()
            entry_price = float(trade_info.get('entry_price', df['close'].iloc[-1]))
            curr_price = float(trade_info.get('current_price', df['close'].iloc[-1]))
            tp_price = float(trade_info.get('take_profit', entry_price * 1.025))
            sl_price = float(trade_info.get('stop_loss', entry_price * 0.985))
            qty = trade_info.get('qty', 1.0)
            pnl_usd = float(trade_info.get('unrealized_pl', (curr_price - entry_price) * qty if side in ['BUY', 'LONG'] else (entry_price - curr_price) * qty))
            pnl_pct = (pnl_usd / (entry_price * qty)) * 100 if entry_price * qty > 0 else 0.0

            # 1. Dibujar Velas Japonesas
            x_indices = np.arange(len(df))
            candle_width = 0.6
            wick_width = 1.2
            
            up_candles = df['close'] >= df['open']
            down_candles = df['close'] < df['open']

            # Color verde vibrante y rojo carmesí estilo market_replay_ui
            color_up = '#00e676'
            color_down = '#ff3366'

            # Dibujar mechas
            ax_main.vlines(x_indices[up_candles], df.loc[up_candles, 'low'], df.loc[up_candles, 'high'], color=color_up, linewidth=wick_width, alpha=0.9)
            ax_main.vlines(x_indices[down_candles], df.loc[down_candles, 'low'], df.loc[down_candles, 'high'], color=color_down, linewidth=wick_width, alpha=0.9)

            # Dibujar cuerpos
            ax_main.bar(x_indices[up_candles], df.loc[up_candles, 'close'] - df.loc[up_candles, 'open'], bottom=df.loc[up_candles, 'open'], color=color_up, width=candle_width, alpha=0.95)
            ax_main.bar(x_indices[down_candles], df.loc[down_candles, 'open'] - df.loc[down_candles, 'close'], bottom=df.loc[down_candles, 'close'], color=color_down, width=candle_width, alpha=0.95)

            # 2. Indicadores
            ax_main.plot(x_indices, df['ema20'], color='#2979ff', linewidth=1.4, label='EMA 20', alpha=0.85)
            ax_main.plot(x_indices, df['ema50'], color='#ff9100', linewidth=1.4, label='EMA 50', alpha=0.85)
            if not df['sma200'].isna().all():
                ax_main.plot(x_indices, df['sma200'], color='#b388ff', linewidth=1.6, label='SMA 200', linestyle=':', alpha=0.85)

            # 3. Líneas Horizontales de Trade
            # TAKE PROFIT (Verde Neón)
            if tp_price > 0:
                ax_main.axhline(y=tp_price, color='#00e676', linestyle='--', linewidth=2.0, alpha=0.95)
                tp_pct_calc = abs((tp_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                ax_main.text(
                    len(df) - 1, tp_price, 
                    f" [TP] ${tp_price:.2f} (+{tp_pct_calc:.2f}%)", 
                    color='#00e676', fontsize=9.5, fontweight='bold', va='center',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#0b2e1b', edgecolor='#00e676', alpha=0.9)
                )

            # STOP LOSS / TRAILING (Rojo Intenso)
            if sl_price > 0:
                ax_main.axhline(y=sl_price, color='#ff3366', linestyle='--', linewidth=2.0, alpha=0.95)
                sl_pct_calc = abs((entry_price - sl_price) / entry_price) * 100 if entry_price > 0 else 0
                ax_main.text(
                    len(df) - 1, sl_price, 
                    f" [SL] ${sl_price:.2f} (-{sl_pct_calc:.2f}%)", 
                    color='#ff3366', fontsize=9.5, fontweight='bold', va='center',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#330e17', edgecolor='#ff3366', alpha=0.9)
                )

            # PRECIO DE ENTRADA (Azul Cian)
            if entry_price > 0:
                ax_main.axhline(y=entry_price, color='#00e5ff', linestyle=':', linewidth=1.8, alpha=0.9)
                ax_main.text(
                    0, entry_price, 
                    f" [ENTRY] ${entry_price:.2f} ({side})", 
                    color='#00e5ff', fontsize=9, fontweight='bold', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#082530', edgecolor='#00e5ff', alpha=0.85)
                )

            # PRECIO ACTUAL (Dorado / Blanco resaltado)
            ax_main.axhline(y=curr_price, color='#ffd600', linestyle='-', linewidth=1.5, alpha=0.85)
            pnl_sign = "+" if pnl_usd >= 0 else ""
            ax_main.text(
                len(df) - 1, curr_price, 
                f" [LIVE] ${curr_price:.2f} ({pnl_sign}${pnl_usd:.2f} / {pnl_sign}{pnl_pct:.2f}%)", 
                color='#ffd600', fontsize=9.5, fontweight='bold', va='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='#2b2505', edgecolor='#ffd600', alpha=0.95)
            )

            # Marcador en la última vela
            ax_main.plot(len(df) - 1, curr_price, marker='o', markersize=6, color='#ffd600', markeredgecolor='white')

            # Configuración de límites y título
            all_prices = [df['low'].min(), df['high'].max(), entry_price, curr_price]
            if tp_price > 0: all_prices.append(tp_price)
            if sl_price > 0: all_prices.append(sl_price)
            min_p, max_p = min(all_prices), max(all_prices)
            padding = (max_p - min_p) * 0.1
            ax_main.set_ylim(min_p - padding, max_p + padding)
            ax_main.set_xlim(-1, len(df) + 12)

            # Formateo de Ejes
            ax_main.grid(True, color=grid_color, linestyle='--', alpha=0.6)
            step = max(1, len(df) // 6)
            ax_main.set_xticks(x_indices[::step])
            ax_main.set_xticklabels([df['datetime'].iloc[i].strftime('%H:%M\n%d/%m') for i in x_indices[::step]], fontsize=8.5, color='#8899a6')
            ax_main.tick_params(axis='y', colors='#8899a6', labelsize=9)

            # Título superior estilizado
            side_label = "LONG (BUY)" if side in ["BUY", "LONG"] else "SHORT (SELL)"
            status_text = f"PnL: {pnl_sign}${pnl_usd:.2f} ({pnl_sign}{pnl_pct:.2f}%)"
            ax_main.set_title(
                f"ALPACA LIVE POSITION: {symbol}  |  {side_label}  |  {status_text}",
                fontsize=12.5, color='white', fontweight='bold', pad=12
            )
            ax_main.legend(loc='upper left', framealpha=0.7, facecolor='#161d27', edgecolor='#2d3748', fontsize=8.5)

            # 4. Panel Inferior de RSI (14)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)

            ax_rsi.plot(x_indices, rsi, color='#9c27b0', linewidth=1.5, label='RSI (14)')
            ax_rsi.axhline(70, color='#ff3366', linestyle=':', alpha=0.7, linewidth=1)
            ax_rsi.axhline(30, color='#00e676', linestyle=':', alpha=0.7, linewidth=1)
            ax_rsi.fill_between(x_indices, 70, 30, color='#9c27b0', alpha=0.08)
            ax_rsi.set_ylim(10, 90)
            ax_rsi.set_xlim(-1, len(df) + 12)
            ax_rsi.grid(True, color=grid_color, linestyle='--', alpha=0.6)
            ax_rsi.set_xticks([])
            ax_rsi.tick_params(axis='y', colors='#8899a6', labelsize=8)
            current_rsi = rsi.iloc[-1]
            ax_rsi.text(len(df) - 1, current_rsi, f" RSI: {current_rsi:.1f}", color='#ce93d8', fontsize=8.5, fontweight='bold', va='center')

            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            plt.close()
            return buf
        except Exception as chart_err:
            print(f"[Telegram] Error generando gráfico de Alpaca: {chart_err}")
            plt.close()
            return None

    async def _handle_alpaca_info(self, chat_id):
        """Genera un resumen detallado de la cuenta y posición activa de Alpaca con gráfico estilo market_replay_ui."""
        await self.send_message("⏳ Obteniendo estado y posición en vivo de Alpaca...", target_chat_id=chat_id)
        try:
            # 1. Cargar credenciales de Alpaca
            alpaca_cfg_path = Path("config_alpaca.json")
            if not alpaca_cfg_path.exists():
                await self.send_message("❌ No se encontró el archivo <code>config_alpaca.json</code>.", target_chat_id=chat_id)
                return

            with open(alpaca_cfg_path, 'r', encoding='utf-8') as f:
                alpaca_cfg = json.load(f)

            key = alpaca_cfg.get('alpaca_key_id')
            secret = alpaca_cfg.get('alpaca_secret_key')
            base_url = "https://paper-api.alpaca.markets" if alpaca_cfg.get('alpaca_paper', True) else "https://api.alpaca.markets"
            headers = {
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "Content-Type": "application/json"
            }

            account_data = {}
            positions = []
            
            async with aiohttp.ClientSession(headers=headers) as session:
                # Consultar Cuenta
                async with session.get(f"{base_url}/v2/account", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        account_data = await r.json()
                    else:
                        await self.send_message(f"⚠️ Error conectando a Alpaca API (HTTP {r.status}).", target_chat_id=chat_id)
                        return

                # Consultar Posiciones
                async with session.get(f"{base_url}/v2/positions", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        positions = await r.json()

            portfolio_val = float(account_data.get('portfolio_value', 0.0))
            cash_val = float(account_data.get('cash', 0.0))
            buying_power = float(account_data.get('buying_power', 0.0))

            # Caso 1: No hay posiciones abiertas
            if not positions:
                last_trade_info = ""
                try:
                    import sqlite3
                    conn = sqlite3.connect("feedback_config_alpaca.db")
                    c = conn.cursor()
                    c.execute("SELECT pair, action, strategy, amount, result, profit, timestamp FROM trades ORDER BY id DESC LIMIT 1")
                    row = c.fetchone()
                    if row:
                        icon = "🟢 WIN" if row[4] == 'win' else "🔴 LOSS"
                        last_trade_info = f"\n\n🕒 <b>Último Trade Cerrado:</b>\n• {row[0]} ({row[1]}) | {row[2]}\n• Resultado: {icon} ({row[5]:+.2f} USD)\n• Fecha: {row[6]}"
                    conn.close()
                except Exception:
                    pass

                msg = (
                    "📊 <b>ESTADO DE CUENTA ALPACA</b>\n\n"
                    f"💼 <b>Portfolio Value:</b> ${portfolio_val:,.2f} USD\n"
                    f"💵 <b>Efectivo Disponible:</b> ${cash_val:,.2f} USD\n"
                    f"⚡ <b>Poder de Compra:</b> ${buying_power:,.2f} USD\n\n"
                    f"ℹ️ <b>Posiciones Abiertas:</b> <i>Ninguna en este momento (Bot escaneando el mercado).</i>"
                    f"{last_trade_info}\n\n"
                    f"<i>Generado: {self._get_time()}</i>"
                )
                await self.send_message(msg, target_chat_id=chat_id)
                return

            # Caso 2: Hay posiciones abiertas
            for pos in positions:
                sym = pos.get('symbol', 'ASSET')
                qty = float(pos.get('qty', 0.0))
                side_raw = pos.get('side', 'long').upper()
                side = "BUY (LONG)" if side_raw == 'LONG' else "SELL (SHORT)"
                entry_price = float(pos.get('avg_entry_price', 0.0))
                current_price = float(pos.get('current_price', 0.0))
                market_val = float(pos.get('market_value', 0.0))
                unrealized_pl = float(pos.get('unrealized_pl', 0.0))
                unrealized_plpc = float(pos.get('unrealized_plpc', 0.0)) * 100

                # Descargar velas para el gráfico
                from broker_alpaca import download_yahoo_candles
                candles = await download_yahoo_candles(sym, 900, 50)
                
                # 1. Consultar si hay datos del trade en alpaca_status.json o bot_ref
                shared_active = {}
                try:
                    status_path = Path('alpaca_status.json')
                    if status_path.exists():
                        with open(status_path, 'r', encoding='utf-8') as sf:
                            shared_data = json.load(sf)
                            shared_active = shared_data.get('active_trades', {})
                except Exception:
                    pass

                matched_trade = None
                if self.bot_ref and hasattr(self.bot_ref, 'api') and hasattr(self.bot_ref.api, 'active_trades'):
                    for t in self.bot_ref.api.active_trades.values():
                        if t.get('symbol') == sym:
                            matched_trade = t
                            break

                if not matched_trade and shared_active:
                    for t in shared_active.values():
                        if t.get('symbol') == sym:
                            matched_trade = t
                            break

                if matched_trade and matched_trade.get('take_profit') and matched_trade.get('stop_loss'):
                    tp_price = float(matched_trade['take_profit'])
                    sl_price = float(matched_trade['stop_loss'])
                else:
                    # Cálculo exacto basado en el dimensionamiento de riesgo de config_alpaca.json
                    risk_usd = float(alpaca_cfg.get('trading', {}).get('risk_per_trade_usd', 10.0))
                    tp_mult = float(alpaca_cfg.get('trading', {}).get('take_profit_atr_multiplier', 2.0))
                    sl_mult = float(alpaca_cfg.get('trading', {}).get('stop_loss_atr_multiplier', 1.2))

                    if qty > 0 and risk_usd > 0:
                        dist_sl = risk_usd / qty
                        dist_tp = (tp_mult / sl_mult) * dist_sl
                    else:
                        dist_sl = entry_price * 0.015
                        dist_tp = entry_price * 0.020

                    if side_raw == 'LONG':
                        tp_price = round(entry_price + dist_tp, 2)
                        sl_price = round(entry_price - dist_sl, 2)
                    else:
                        tp_price = round(entry_price - dist_tp, 2)
                        sl_price = round(entry_price + dist_sl, 2)

                if side_raw == 'LONG':
                    dist_to_tp = tp_price - current_price
                    dist_to_sl = current_price - sl_price
                else:
                    dist_to_tp = current_price - tp_price
                    dist_to_sl = sl_price - current_price

                dist_tp_pct = (dist_to_tp / current_price) * 100 if current_price > 0 else 0.0
                dist_sl_pct = (dist_to_sl / current_price) * 100 if current_price > 0 else 0.0

                trade_data = {
                    "symbol": sym,
                    "side": side_raw,
                    "qty": qty,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "take_profit": tp_price,
                    "stop_loss": sl_price,
                    "unrealized_pl": unrealized_pl
                }

                chart_buf = self._generate_alpaca_trade_chart(candles, trade_data)

                pnl_icon = "🟢" if unrealized_pl >= 0 else "🔴"
                pnl_sign = "+" if unrealized_pl >= 0 else ""
                
                caption = (
                    f"📊 <b>POSICIÓN ACTIVA EN ALPACA: {sym}</b>\n\n"
                    f"🎯 <b>Dirección:</b> <code>{side}</code>\n"
                    f"📦 <b>Cantidad:</b> <code>{qty} acciones</code> (${market_val:,.2f})\n"
                    f"🔵 <b>Precio Entrada:</b> <code>${entry_price:.2f}</code>\n"
                    f"⚡ <b>Precio Actual:</b> <code>${current_price:.2f}</code>\n\n"
                    f"{pnl_icon} <b>PnL Flotante:</b> <b>{pnl_sign}${unrealized_pl:.2f} USD ({pnl_sign}{unrealized_plpc:.2f}%)</b>\n\n"
                    f"🟢 <b>Take Profit (TP):</b> <code>${tp_price:.2f}</code> <i>(a {dist_to_tp:+.2f}$ / {dist_tp_pct:+.2f}%)</i>\n"
                    f"🔴 <b>Stop Loss (SL):</b> <code>${sl_price:.2f}</code> <i>(a {dist_to_sl:+.2f}$ / {dist_sl_pct:+.2f}%)</i>\n\n"
                    f"💼 <b>Cuenta:</b> Portfolio: <code>${portfolio_val:,.2f}</code> | Cash: <code>${cash_val:,.2f}</code>\n"
                    f"<i>Actualizado: {self._get_time()}</i>"
                )

                if chart_buf:
                    await self.send_photo(chart_buf, caption=caption, target_chat_id=chat_id)
                else:
                    await self.send_message(caption, target_chat_id=chat_id)

        except Exception as e:
            print(f"[Telegram] Error en _handle_alpaca_info: {e}")
            await self.send_message(f"❌ Error obteniendo info de Alpaca: {e}", target_chat_id=chat_id)

    def _calculate_trade_points(self, pair_str, entry, close):
        """Calcula los puntos de diferencia de forma universal y coherente según la clase de activo."""
        diff = abs(close - entry)
        p_lower = str(pair_str or '').lower()
        if 'btc' in p_lower or 'crypto' in p_lower:
            pts = int(round(diff))
            unit = "pts"
        elif 'cop' in p_lower:
            pts = int(round(diff * 10))
            unit = "pts"
        elif 'jpy' in p_lower or 'inr' in p_lower:
            pts = int(round(diff * 1000))
            unit = "pts"
        elif entry < 5.0:  # Forex estándar (EURUSD, USDCHF, GBPUSD, AUDCAD, etc.)
            pts = int(round(diff * 100000))
            unit = "pts"
        else:  # Acciones (#AAPL, #TSLA, etc.)
            pts = int(round(diff * 100))
            unit = "cents"
        return pts, unit

    def _parse_timeframe_to_interval(self, tf_raw):
        """Convierte cualquier formato de timeframe (900, '900', '15m', '15min', '300s') a (interval_sec, tf_display_str)"""
        if not tf_raw:
            return 300, "5m"
        s = str(tf_raw).strip().lower()
        if s in ['60', '1', '1m', '1min', '60s', 'm1']:
            return 60, "1m"
        elif s in ['900', '15', '15m', '15min', '900s', 'm15']:
            return 900, "15m"
        elif s in ['1800', '30', '30m', '30min', '1800s', 'm30']:
            return 1800, "30m"
        elif s in ['3600', '60m', '1h', '60min', '3600s', 'h1']:
            return 3600, "1h"
        elif s in ['300', '5', '5m', '5min', '300s', 'm5']:
            return 300, "5m"
        try:
            digits = ''.join(filter(str.isdigit, s))
            if digits:
                val = int(digits)
                if val in [60, 300, 900, 1800, 3600]:
                    return val, f"{val//60}m"
                elif val == 1:
                    return 60, "1m"
                elif val == 5:
                    return 300, "5m"
                elif val == 15:
                    return 900, "15m"
                elif val == 30:
                    return 1800, "30m"
                elif val == 60:
                    return 3600, "1h"
        except Exception:
            pass
        return 300, "5m"

    def _get_po_trades_for_chart(self, pair=None):
        """
        Obtiene el trade más reciente de cada par operado en Pocket Option.
        Si se especifica pair: devuelve solo el último trade de ese par.
        Si pair es None: devuelve el último trade de CADA par operado hoy (o en el historial reciente).
        """
        trades_by_pair = {}

        # 1. Cargar desde CSVs de Pocket Option (fuente de verdad inmediata de ejecución)
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            po_files = [f for f in all_files if "pocketoption_real" in Path(f).name or "_real_" in Path(f).name]
            if not po_files:
                po_files = [f for f in all_files if "alpaca" not in Path(f).name]
            po_files.sort(reverse=True)

            tz = timezone(timedelta(hours=-3))
            today_str = datetime.now(tz).strftime('%Y%m%d')

            target_files = [f for f in po_files if today_str in Path(f).name]
            if not target_files:
                target_files = po_files[:3]

            for f in target_files:
                try:
                    tdf = pd.read_csv(f)
                    if tdf.empty:
                        continue
                    tdf = tdf.loc[:, ~tdf.columns.duplicated()].copy()
                    tdf.columns = [str(c).lower().strip() for c in tdf.columns]
                    if 'pair' not in tdf.columns or 'result' not in tdf.columns:
                        continue
                    tdf = tdf[tdf['result'].str.upper().isin(['WIN', 'LOSS'])].copy()
                    if tdf.empty:
                        continue

                    for _, r in tdf.iterrows():
                        p = str(r.get('pair') or '').strip()
                        if not p or p.lower() in ['none', 'nan', '']:
                            continue
                        if pair and p.upper() != pair.upper():
                            continue
                        if p not in trades_by_pair:
                            trades_by_pair[p] = {
                                'trade_id': str(r.get('trade_id') or ''),
                                'timestamp': str(r.get('timestamp') or ''),
                                'pair': p,
                                'action': str(r.get('decision') or r.get('action') or 'CALL').upper(),
                                'strategy': str(r.get('pattern_detected') or r.get('strategy') or 'Algorítmica'),
                                'timeframe': r.get('timeframe'),
                                'amount': r.get('amount'),
                                'open_price': r.get('price') or r.get('open_price'),
                                'close_price': r.get('close_price'),
                                'result': str(r.get('result') or 'WIN').upper(),
                                'profit': float(r.get('profit_loss') or r.get('profit') or 0.0)
                            }
                except Exception as fe:
                    print(f"[Telegram Chart] Error leyendo CSV {f}: {fe}")
        except Exception as e:
            print(f"[Telegram Chart] Error en scan de CSVs: {e}")

        # 2. Complementar con SQLite feedback.db (para capturar cualquier trade adicional)
        try:
            import sqlite3
            db_file = "feedback.db"
            if Path(db_file).exists():
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                try:
                    # Sanar TODOS los registros corruptos en feedback.db universalmente (donde se sumó profit en dólares al precio forex)
                    c.execute("""
                        UPDATE trades 
                        SET close_price = NULL 
                        WHERE close_price IS NOT NULL 
                          AND open_price IS NOT NULL 
                          AND open_price > 0 
                          AND ABS(close_price - open_price) / open_price > 0.025
                    """)
                    conn.commit()
                except Exception:
                    pass

                if pair:
                    c.execute("""
                        SELECT trade_id, timestamp, pair, action, strategy, timeframe, amount, open_price, close_price, result, profit
                        FROM trades
                        WHERE UPPER(pair) = ? AND lower(result) IN ('win', 'loss')
                        ORDER BY id DESC LIMIT 1
                    """, (pair.upper(),))
                    rows = c.fetchall()
                else:
                    tz = timezone(timedelta(hours=-3))
                    today_iso = datetime.now(tz).strftime('%Y-%m-%d')
                    c.execute("""
                        SELECT trade_id, timestamp, pair, action, strategy, timeframe, amount, open_price, close_price, result, profit
                        FROM trades
                        WHERE lower(result) IN ('win', 'loss') AND timestamp LIKE ?
                        ORDER BY id DESC
                    """, (f"{today_iso}%",))
                    rows = c.fetchall()
                    if not rows and not trades_by_pair:
                        c.execute("""
                            SELECT trade_id, timestamp, pair, action, strategy, timeframe, amount, open_price, close_price, result, profit
                            FROM trades
                            WHERE lower(result) IN ('win', 'loss')
                            ORDER BY id DESC LIMIT 25
                        """)
                        rows = c.fetchall()
                conn.close()

                for row in rows:
                    d = dict(row)
                    p = str(d.get('pair') or '').strip()
                    op = float(d.get('open_price') or 0.0)
                    cp = float(d.get('close_price') or 0.0)
                    # Blindaje general contra valores corruptos de DB
                    if op > 0 and cp > 0 and abs(cp - op) / op > 0.025:
                        d['close_price'] = None
                    if p and p not in trades_by_pair:
                        trades_by_pair[p] = d
                    elif p and p in trades_by_pair:
                        for k in ['timeframe', 'open_price', 'close_price', 'action', 'strategy']:
                            if not trades_by_pair[p].get(k) and d.get(k):
                                trades_by_pair[p][k] = d[k]
        except Exception as dbe:
            print(f"[Telegram Chart] Error consultando SQLite feedback.db: {dbe}")

        return list(trades_by_pair.values())

    def _get_latest_po_trade(self, pair=None):
        """Obtiene la información del trade más reciente de PocketOption."""
        trades = self._get_po_trades_for_chart(pair=pair)
        return trades[0] if trades else None

    def _generate_po_trade_chart(self, df, trade_info=None, pair_name="EURUSD_otc", tf_display="5m"):
        """
        Genera un gráfico de velas de alta definición para Pocket Option con estilo oscuro premium,
        Bandas de Bollinger 2.5 dev, EMAs (20, 50, SMA 200), oscilador RSI (14) en panel inferior,
        centrado milimétricamente en la operación realizada, en hora local UTC-3 (Argentina),
        con niveles reales de entrada, salida, trayectoria del precio y resultado exacto (puntos y USD).
        Blindado contra distorsiones de escala, valores atípicos y desalineaciones de temporalidad.
        """
        fig = None
        try:
            if df is None or df.empty or len(df) < 10:
                return None

            df = df.copy()
            # Deduplicar columnas inmediatamente por si venían duplicadas de CSV o API
            df = df.loc[:, ~df.columns.duplicated()].copy()
            df.columns = [str(c).lower().strip() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()].copy()

            # Asegurar columnas requeridas y tipos numéricos
            for col in ['open', 'high', 'low', 'close']:
                if col not in df.columns:
                    match = next((c for c in df.columns if col in c), None)
                    if match:
                        df[col] = df[match]
                    else:
                        return None
                col_data = df[col]
                if isinstance(col_data, pd.DataFrame):
                    col_data = col_data.iloc[:, 0]
                df[col] = pd.to_numeric(col_data, errors='coerce')

            df = df.dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)
            if len(df) < 10:
                return None

            # Normalizar timestamp / datetime a DatetimeIndex
            if 'datetime' not in df.columns:
                ts_col = next((c for c in ['timestamp', 'time', 'date'] if c in df.columns), None)
                if ts_col:
                    raw_ts = df[ts_col]
                    if isinstance(raw_ts, pd.DataFrame):
                        raw_ts = raw_ts.iloc[:, 0]
                    try:
                        if pd.api.types.is_numeric_dtype(raw_ts):
                            df['datetime'] = pd.to_datetime(raw_ts, unit='s', utc=True)
                        else:
                            df['datetime'] = pd.to_datetime(raw_ts, utc=True)
                    except Exception:
                        pass

                if 'datetime' not in df.columns or df['datetime'].isna().all():
                    df['datetime'] = pd.date_range(end=datetime.now(), periods=len(df), freq='5min')
                else:
                    df['datetime'] = df['datetime'].bfill().ffill()

            # CONVERSIÓN A HORA LOCAL UTC-3 (Argentina / Pocket Option UI)
            tz_arg = timezone(timedelta(hours=-3))
            try:
                if hasattr(df['datetime'].dt, 'tz') and df['datetime'].dt.tz is not None:
                    df['datetime'] = df['datetime'].dt.tz_convert(tz_arg)
                else:
                    df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(tz_arg)
            except Exception:
                try:
                    df['datetime'] = df['datetime'] - pd.Timedelta(hours=3)
                except Exception:
                    pass

            # Optimización: si hay más de 350 velas, recortar a 350 para calcular indicadores rápido
            if len(df) > 350:
                df = df.tail(350).copy().reset_index(drop=True)

            # Extraer close como Series limpia para cálculos
            close_s = df['close'].iloc[:, 0] if isinstance(df['close'], pd.DataFrame) else df['close']

            # Indicadores Cuantitativos sobre serie completa
            df['bb_mid'] = close_s.rolling(window=20, min_periods=2).mean()
            df['bb_std'] = close_s.rolling(window=20, min_periods=2).std().fillna(0.0)
            df['bb_upper'] = df['bb_mid'] + 2.5 * df['bb_std']
            df['bb_lower'] = df['bb_mid'] - 2.5 * df['bb_std']

            df['ema20'] = close_s.ewm(span=20, adjust=False).mean()
            df['ema50'] = close_s.ewm(span=50, adjust=False).mean()
            df['sma200'] = close_s.rolling(window=200, min_periods=5).mean()

            # RSI (14)
            delta = close_s.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=2).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=2).mean()
            rs = gain / loss.replace(0, np.nan)
            df['rsi'] = (100 - (100 / (1 + rs))).fillna(50.0)

            # Rellenar valores de indicadores para evitar NaNs
            df['bb_mid'] = df['bb_mid'].bfill().ffill().fillna(df['close'])
            df['bb_upper'] = df['bb_upper'].bfill().ffill().fillna(df['close'] * 1.001)
            df['bb_lower'] = df['bb_lower'].bfill().ffill().fillna(df['close'] * 0.999)
            df['ema20'] = df['ema20'].bfill().ffill().fillna(df['close'])
            df['ema50'] = df['ema50'].bfill().ffill().fillna(df['close'])
            df['rsi'] = df['rsi'].bfill().ffill().fillna(50.0)

            # Extraer datos del trade si existen
            has_trade = False
            entry_price = 0.0
            close_price = None
            action = "BUY"
            result = ""
            profit = 0.0
            strat = "Estrategia Cuantitativa"
            trade_dt = None
            trade_tf_sec = 300

            if trade_info and isinstance(trade_info, dict):
                try:
                    raw_entry = trade_info.get('open_price') or trade_info.get('entry_price') or trade_info.get('price')
                    if raw_entry is not None and str(raw_entry).lower() not in ['none', 'null', 'nan', '']:
                        entry_price = float(raw_entry)
                        if entry_price > 0 and np.isfinite(entry_price):
                            has_trade = True

                    raw_close = trade_info.get('close_price')
                    if raw_close is not None and str(raw_close).lower() not in ['none', 'null', 'nan', '']:
                        close_price = float(raw_close)

                    raw_act = str(trade_info.get('action') or trade_info.get('decision') or 'BUY').upper()
                    action = 'BUY' if raw_act in ['BUY', 'CALL'] else 'SELL'
                    result = str(trade_info.get('result') or '').upper()

                    raw_profit = trade_info.get('profit') or trade_info.get('profit_loss')
                    if raw_profit is not None and str(raw_profit).lower() not in ['none', 'null', 'nan', '']:
                        profit = float(raw_profit)

                    strat = str(trade_info.get('strategy') or trade_info.get('pattern_detected') or 'Algorítmica')

                    raw_tf = trade_info.get('timeframe')
                    if raw_tf:
                        trade_tf_sec, _ = self._parse_timeframe_to_interval(raw_tf)

                    raw_ts = trade_info.get('timestamp')
                    if raw_ts:
                        parsed_ts = pd.to_datetime(raw_ts)
                        if hasattr(df['datetime'].dt, 'tz') and df['datetime'].dt.tz is not None:
                            if parsed_ts.tzinfo is None:
                                parsed_ts = parsed_ts.tz_localize(df['datetime'].dt.tz)
                            else:
                                parsed_ts = parsed_ts.tz_convert(df['datetime'].dt.tz)
                        else:
                            if parsed_ts.tzinfo is not None:
                                parsed_ts = parsed_ts.tz_localize(None)
                        trade_dt = parsed_ts
                except Exception as ex:
                    print(f"[Telegram Chart] Error procesando trade_info: {ex}")

            # Calcular intervalo entre velas del DataFrame
            candle_interval_sec = trade_tf_sec
            if len(df) >= 2:
                try:
                    diff_s = abs((df['datetime'].iloc[1] - df['datetime'].iloc[0]).total_seconds())
                    if diff_s > 0:
                        candle_interval_sec = int(diff_s)
                except Exception:
                    pass

            # VERIFICAR SI EL TRADE ESTÁ REALMENTE DENTRO DEL RANGO DE TIEMPO DE LAS VELAS
            entry_idx = None
            if has_trade and trade_dt is not None and len(df) > 0:
                df_start = df['datetime'].iloc[0]
                df_end = df['datetime'].iloc[-1]
                margin = pd.Timedelta(seconds=candle_interval_sec * 8)

                if (df_start - margin) <= trade_dt <= (df_end + margin):
                    # El trade está dentro del rango visible
                    try:
                        time_diffs = (trade_dt - df['datetime']).dt.total_seconds()
                        valid_idx = np.where(time_diffs >= -30)[0]
                        if len(valid_idx) > 0:
                            entry_idx = int(valid_idx[-1])
                        else:
                            entry_idx = int(np.argmin(np.abs(time_diffs)))
                    except Exception as ie:
                        print(f"[Telegram Chart] Error indexando vela de trade: {ie}")
                        entry_idx = None
                else:
                    # El trade es de otra fecha/hora no presente en este dataset de velas
                    print(f"[Telegram Chart] Trade timestamp {trade_dt} fuera de rango [{df_start} - {df_end}]. Mostrando velas en vivo.")
                    has_trade = False
                    entry_idx = None

            candles_span = max(1, round(trade_tf_sec / candle_interval_sec))
            if entry_idx is not None:
                exit_idx = min(len(df) - 1, entry_idx + max(0, candles_span - 1))
            else:
                entry_idx = max(0, len(df) - 3)
                exit_idx = len(df) - 1

            # ENCUADRE ROBUSTO: Mostrar siempre una ventana óptima de ~40 velas
            total_candles = len(df)
            desired_candles = min(42, total_candles)

            if has_trade and entry_idx is not None and total_candles > 42:
                ideal_start = entry_idx - int(desired_candles * 0.45)
                start_w = max(0, ideal_start)
                end_w = start_w + desired_candles
                if end_w > total_candles:
                    end_w = total_candles
                    start_w = max(0, end_w - desired_candles)

                df = df.iloc[start_w:end_w].copy().reset_index(drop=True)
                entry_idx = entry_idx - start_w
                exit_idx = max(0, min(len(df) - 1, exit_idx - start_w))
            else:
                if len(df) > 42:
                    df = df.tail(42).copy().reset_index(drop=True)
                entry_idx = max(0, len(df) - 3)
                exit_idx = len(df) - 1

            # Asegurar índices seguros
            entry_idx = max(0, min(entry_idx, len(df) - 1))
            exit_idx = max(0, min(exit_idx, len(df) - 1))

            opens = df['open'].to_numpy(dtype=float)
            highs = df['high'].to_numpy(dtype=float)
            lows = df['low'].to_numpy(dtype=float)
            closes = df['close'].to_numpy(dtype=float)

            candle_entry_open = float(opens[entry_idx])
            candle_exit_close = float(closes[exit_idx])

            # SANITIZACIÓN UNIVERSAL DE PRECIOS (Protección total contra corrupción y distorsión de escala)
            # 1. Entrada: si está ausente o desfasada > 0.8% del open de la vela, ajustar al open
            if entry_price <= 0 or not np.isfinite(entry_price) or abs(entry_price - candle_entry_open) / candle_entry_open > 0.008:
                entry_price = candle_entry_open

            # 2. Salida: debe ser un precio de mercado coherente con entry_price (desviación < 0.8%)
            if (close_price is None or close_price <= 0 or not np.isfinite(close_price) or
                abs(close_price - entry_price) / entry_price > 0.008 or
                close_price == entry_price):
                close_price = candle_exit_close

            # Calcular tick mínimo realista según tipo de activo
            if 'btc' in pair_name.lower() or 'crypto' in pair_name.lower():
                min_tick = 5.0
            elif 'cop' in pair_name.lower():
                min_tick = 0.5
            elif 'jpy' in pair_name.lower() or 'inr' in pair_name.lower():
                min_tick = 0.008
            elif entry_price < 5.0:  # Forex estándar (5 decimales)
                min_tick = 0.00008
            else:  # Acciones (#AAPL, #TSLA, etc.)
                min_tick = 0.05

            if result == 'WIN':
                if action == 'BUY' and close_price <= entry_price:
                    close_price = max(candle_exit_close, entry_price + min_tick)
                elif action == 'SELL' and close_price >= entry_price:
                    close_price = min(candle_exit_close, entry_price - min_tick)
            elif result == 'LOSS':
                if action == 'BUY' and close_price >= entry_price:
                    close_price = min(candle_exit_close, entry_price - min_tick)
                elif action == 'SELL' and close_price <= entry_price:
                    close_price = max(candle_exit_close, entry_price + min_tick)

            # Preparar Figura Matplotlib
            plt.style.use('dark_background')
            fig, (ax_main, ax_rsi) = plt.subplots(
                2, 1, 
                figsize=(12.5, 7.0), 
                gridspec_kw={'height_ratios': [3.5, 1]},
                dpi=120
            )

            bg_color = '#0b0e14'
            panel_color = '#121721'
            grid_color = '#1c2433'
            fig.patch.set_facecolor(bg_color)
            ax_main.set_facecolor(panel_color)
            ax_rsi.set_facecolor(panel_color)

            x_indices = np.arange(len(df))
            candle_width = 0.58
            wick_width = 1.2

            up_mask = closes >= opens
            down_mask = ~up_mask

            # Dibujar Velas Japonesas
            if np.any(up_mask):
                ax_main.vlines(x_indices[up_mask], lows[up_mask], highs[up_mask], color='#00e676', linewidth=wick_width, alpha=0.9)
                ax_main.bar(x_indices[up_mask], closes[up_mask] - opens[up_mask], bottom=opens[up_mask], color='#00e676', width=candle_width, alpha=0.95)

            if np.any(down_mask):
                ax_main.vlines(x_indices[down_mask], lows[down_mask], highs[down_mask], color='#ff3366', linewidth=wick_width, alpha=0.9)
                ax_main.bar(x_indices[down_mask], opens[down_mask] - closes[down_mask], bottom=closes[down_mask], color='#ff3366', width=candle_width, alpha=0.95)

            # Bandas de Bollinger (2.5 dev)
            bb_up_vals = df['bb_upper'].to_numpy(dtype=float)
            bb_low_vals = df['bb_lower'].to_numpy(dtype=float)
            bb_mid_vals = df['bb_mid'].to_numpy(dtype=float)

            ax_main.plot(x_indices, bb_up_vals, color='#00e5ff', linestyle='--', linewidth=1.1, alpha=0.8, label='Bollinger (2.5 dev)')
            ax_main.plot(x_indices, bb_low_vals, color='#00e5ff', linestyle='--', linewidth=1.1, alpha=0.8)
            ax_main.plot(x_indices, bb_mid_vals, color='#4fc3f7', linestyle=':', linewidth=0.9, alpha=0.6, label='SMA 20')
            ax_main.fill_between(x_indices, bb_up_vals, bb_low_vals, color='#00e5ff', alpha=0.04)

            # Medias Móviles
            ax_main.plot(x_indices, df['ema20'].to_numpy(dtype=float), color='#2979ff', linewidth=1.3, alpha=0.85, label='EMA 20')
            ax_main.plot(x_indices, df['ema50'].to_numpy(dtype=float), color='#ff9100', linewidth=1.3, alpha=0.85, label='EMA 50')
            if not df['sma200'].isna().all():
                sma200_series = df['sma200'].bfill().ffill().fillna(df['close'])
                ax_main.plot(x_indices, sma200_series.to_numpy(dtype=float), color='#b388ff', linestyle=':', linewidth=1.4, alpha=0.75, label='SMA 200')

            # Rango de precios local
            p_min_local = float(np.nanmin(lows))
            p_max_local = float(np.nanmax(highs))
            p_range = max(p_max_local - p_min_local, 0.0005)

            pts = None
            pts_unit = "pts"

            # DIBUJAR OVERLAY DEL TRADE (Solo si el trade está validado y dentro del rango)
            if has_trade:
                trade_res_color = '#00e676' if result == 'WIN' else '#ff3366'
                trade_res_bg = '#092b1a' if result == 'WIN' else '#2f0d16'

                # 1. Zona sombreada durante la duración real
                ax_main.axvspan(entry_idx - 0.45, exit_idx + 0.45, color=trade_res_color, alpha=0.09, zorder=1)

                # 2. Segmento horizontal del nivel de entrada
                seg_start = max(0, entry_idx - 2)
                seg_end = min(len(df) - 1, exit_idx + 3)
                ax_main.hlines(
                    y=entry_price, xmin=seg_start, xmax=seg_end,
                    colors='#00e5ff', linestyles='--', linewidth=1.5, alpha=0.9, zorder=5
                )
                ax_main.text(
                    seg_start, entry_price, 
                    f" ENTRY: ${entry_price:.5f} ", 
                    color='#00e5ff', fontsize=8.5, fontweight='bold', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.25', facecolor='#09232d', edgecolor='#00e5ff', alpha=0.9)
                )

                # 3. Marcador y Flecha de Entrada
                act_color = '#00e676' if action == 'BUY' else '#ff3366'
                if action == 'BUY':
                    ax_main.annotate(
                        f"▲ BUY ENTRY\n${entry_price:.5f}",
                        xy=(entry_idx, entry_price),
                        xytext=(entry_idx, lows[entry_idx] - p_range * 0.07),
                        arrowprops=dict(arrowstyle='->', color='#00e676', lw=1.8),
                        color='#00e676', fontsize=9, fontweight='bold', ha='center', va='top',
                        bbox=dict(boxstyle='round,pad=0.25', facecolor='#112117', edgecolor='#00e676', alpha=0.9),
                        zorder=7
                    )
                else:
                    ax_main.annotate(
                        f"▼ SELL ENTRY\n${entry_price:.5f}",
                        xy=(entry_idx, entry_price),
                        xytext=(entry_idx, highs[entry_idx] + p_range * 0.07),
                        arrowprops=dict(arrowstyle='->', color='#ff3366', lw=1.8),
                        color='#ff3366', fontsize=9, fontweight='bold', ha='center', va='bottom',
                        bbox=dict(boxstyle='round,pad=0.25', facecolor='#2c1117', edgecolor='#ff3366', alpha=0.9),
                        zorder=7
                    )

                # 4. Trayectoria entre Entrada y Salida (Manejo milimétrico si la duración es 1 sola vela)
                if entry_idx == exit_idx:
                    x_start = entry_idx - 0.28
                    x_end = entry_idx + 0.28
                else:
                    x_start = entry_idx
                    x_end = exit_idx

                ax_main.plot(
                    [x_start, x_end], [entry_price, close_price],
                    color=trade_res_color, linestyle='-', linewidth=2.2, alpha=0.9, zorder=6
                )

                # 5. Marcadores en puntos exactos de apertura y cierre
                ax_main.plot(x_start, entry_price, marker='o', markersize=6.5, color=act_color, markeredgecolor='white', markeredgewidth=1.3, zorder=6)
                ax_main.plot(x_end, close_price, marker='o', markersize=7.5, color=trade_res_color, markeredgecolor='white', markeredgewidth=1.4, zorder=6)

                pts, pts_unit = self._calculate_trade_points(pair_name, entry_price, close_price)
                is_win_pts = (close_price >= entry_price if action == 'BUY' else close_price <= entry_price)
                pts_sign = "+" if is_win_pts else "-"
                pnl_str = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"
                res_icon = "✅" if result == 'WIN' else "❌"

                badge_text = f" {res_icon} {result}: {pnl_str} USD ({pts_sign}{pts} {pts_unit})\n Cierre: ${close_price:.5f} "
                y_badge_pos = close_price + (p_range * 0.04 if result == 'WIN' else -p_range * 0.04)
                va_pos = 'bottom' if result == 'WIN' else 'top'

                ax_main.text(
                    x_end + 0.4, y_badge_pos,
                    badge_text,
                    color=trade_res_color, fontsize=9.5, fontweight='bold', va=va_pos, ha='left',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=trade_res_bg, edgecolor=trade_res_color, alpha=0.95),
                    zorder=7
                )
            else:
                curr_price = float(closes[-1]) if len(closes) > 0 else 1.0
                ax_main.axhline(y=curr_price, color='#ffd600', linestyle='-', linewidth=1.4, alpha=0.85)
                ax_main.text(
                    len(df) - 1, curr_price, 
                    f" [LIVE] ${curr_price:.5f} ", 
                    color='#ffd600', fontsize=9.5, fontweight='bold', va='center',
                    bbox=dict(boxstyle='round,pad=0.25', facecolor='#2b2505', edgecolor='#ffd600', alpha=0.95)
                )
                ax_main.plot(len(df) - 1, curr_price, marker='o', markersize=5, color='#ffd600', markeredgecolor='white')

            # Límites de precio con padding seguro anclados estrictamente a las velas japonesas (protección total de escala)
            p_min = float(np.nanmin(lows))
            p_max = float(np.nanmax(highs))
            if has_trade:
                p_min = min(p_min, entry_price, close_price)
                p_max = max(p_max, entry_price, close_price)
            if p_min == p_max:
                p_min *= 0.999
                p_max *= 1.001
            padding = max((p_max - p_min) * 0.12, min_tick * 4)
            ax_main.set_ylim(p_min - padding, p_max + padding)
            ax_main.set_xlim(-1, len(df) + 4)

            ax_main.grid(True, color=grid_color, linestyle='--', alpha=0.6)

            # Formateo del Eje X con Horario Local UTC-3
            step = max(1, len(df) // 6)
            x_ticks = x_indices[::step]
            x_labels = []
            for i in x_ticks:
                try:
                    dt_val = df['datetime'].iloc[i]
                    if hasattr(dt_val, 'strftime'):
                        x_labels.append(dt_val.strftime('%H:%M'))
                    else:
                        x_labels.append(str(dt_val)[11:16])
                except Exception:
                    x_labels.append(str(i))
            ax_main.set_xticks(x_ticks)
            ax_main.set_xticklabels(x_labels, fontsize=8.5, color='#8899a6')
            ax_main.tick_params(axis='y', colors='#8899a6', labelsize=9)
            ax_main.set_xlabel("Horario Local / Pocket Option (UTC-3)", fontsize=8.5, color='#8899a6', labelpad=5)

            pnl_title = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"
            if has_trade and result:
                title_status = f"{action} ({result} {pnl_title})"
                title_strat = strat
            else:
                title_status = f"LIVE ${closes[-1]:.5f}"
                title_strat = "ANÁLISIS TÉCNICO EN VIVO"

            ax_main.set_title(
                f"POCKET OPTION: {pair_name} ({tf_display})  |  {title_strat}  |  {title_status}",
                fontsize=11, color='white', fontweight='bold', pad=10
            )
            ax_main.legend(loc='upper left', framealpha=0.7, facecolor='#161d27', edgecolor='#2d3748', fontsize=8)

            # Panel Inferior de RSI (14)
            rsi_vals = df['rsi'].to_numpy(dtype=float)
            ax_rsi.plot(x_indices, rsi_vals, color='#ab47bc', linewidth=1.5, label='RSI (14)')
            ax_rsi.axhline(70, color='#ff3366', linestyle=':', alpha=0.7, linewidth=1)
            ax_rsi.axhline(30, color='#00e676', linestyle=':', alpha=0.7, linewidth=1)
            ax_rsi.fill_between(x_indices, 70, 30, color='#ab47bc', alpha=0.08)
            ax_rsi.set_ylim(10, 90)
            ax_rsi.set_xlim(-1, len(df) + 4)
            ax_rsi.grid(True, color=grid_color, linestyle='--', alpha=0.6)
            ax_rsi.set_xticks([])
            ax_rsi.tick_params(axis='y', colors='#8899a6', labelsize=8)
            last_rsi = float(rsi_vals[-1]) if len(rsi_vals) > 0 else 50.0
            if not np.isfinite(last_rsi):
                last_rsi = 50.0
            ax_rsi.text(len(df) - 1, last_rsi, f" RSI: {last_rsi:.1f}", color='#ce93d8', fontsize=8.5, fontweight='bold', va='center')

            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            buf.has_trade = has_trade
            buf.trade_entry_price = entry_price if has_trade else None
            buf.trade_close_price = close_price if has_trade else None
            buf.trade_points = pts if has_trade else None
            buf.trade_points_unit = pts_unit if has_trade else None
            return buf
        except Exception as err:
            import traceback
            t_err = traceback.format_exc()
            try:
                Path("chart_render_error.log").write_text(f"{err}\n{t_err}", encoding="utf-8")
            except Exception:
                pass
            print(f"[Telegram Chart] Error generando gráfico PO: {err}\n{t_err}")
            return None
        finally:
            if fig is not None:
                try:
                    plt.close(fig)
                except Exception:
                    pass

    async def _render_and_send_single_chart(self, chat_id, pair, interval, tf_display, trade_info=None):
        """Descarga velas, genera y envía la imagen del gráfico de un activo específico."""
        try:
            df = pd.DataFrame()
            
            # Si el trade tiene timestamp histórico, buscar velas que cubran ese momento con exactitud UTC
            end_time_ts = None
            if trade_info and isinstance(trade_info, dict) and trade_info.get('timestamp'):
                try:
                    ts_val = str(trade_info['timestamp']).strip()
                    ts_clean = ts_val.replace('T', ' ').split('.')[0]
                    if ts_clean.isdigit():
                        t_ts_epoch = int(ts_clean)
                    else:
                        dt_naive = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
                        dt_local = dt_naive.replace(tzinfo=timezone(timedelta(hours=-3)))
                        t_ts_epoch = int(dt_local.timestamp())
                    end_time_ts = t_ts_epoch + int(30 * interval)
                except Exception as ex_ts:
                    print(f"[Telegram Chart] Error calculando epoch de trade: {ex_ts}")
                    end_time_ts = None

            if self.bot_ref and hasattr(self.bot_ref, 'fetch_data'):
                try:
                    if end_time_ts:
                        df = await self.bot_ref.fetch_data(pair, interval, end_time=end_time_ts)
                    if df is None or df.empty or len(df) < 10:
                        df = await self.bot_ref.fetch_data(pair, interval)
                except Exception as fe:
                    print(f"[Telegram Chart] Error fetch_data para {pair}: {fe}")

            if df is None or df.empty or len(df) < 10:
                csv_candidates = [
                    Path(f"historical_data/{pair}_{interval}s.csv"),
                    Path(f"historical_data/{pair.upper()}_{interval}s.csv"),
                    Path(f"historical_data/{pair.lower()}_{interval}s.csv"),
                    Path(f"historical_data/{pair}_900s.csv"),
                    Path(f"historical_data/{pair}_300s.csv"),
                    Path(f"historical_data/{pair}_60s.csv"),
                ]
                for p_cand in csv_candidates:
                    if p_cand.exists():
                        try:
                            df = pd.read_csv(p_cand)
                            df = df.loc[:, ~df.columns.duplicated()].copy()
                            df.columns = [c.capitalize() for c in df.columns]
                            if len(df) >= 10:
                                break
                        except Exception:
                            pass

            if df is None or df.empty or len(df) < 10:
                await self.send_message(
                    f"⚠️ No hay suficientes datos de velas para graficar <b>{pair}</b> ({tf_display}).",
                    target_chat_id=chat_id
                )
                return False

            # Deduplicar columnas
            df = df.loc[:, ~df.columns.duplicated()].copy()

            # Renderizar gráfico en hilo de fondo
            buf = await asyncio.to_thread(
                self._generate_po_trade_chart,
                df, trade_info, pair, tf_display
            )

            if not buf:
                err_detail = ""
                err_file = Path("chart_render_error.log")
                if err_file.exists():
                    try:
                        err_detail = f" ({err_file.read_text(encoding='utf-8').splitlines()[0]})"
                    except Exception:
                        pass
                await self.send_message(f"❌ Error al renderizar la imagen de {pair}{err_detail}.", target_chat_id=chat_id)
                return False

            # Armar caption técnico con series desduplicadas
            df_cap = df.copy()
            df_cap.columns = [str(c).lower().strip() for c in df_cap.columns]
            df_cap = df_cap.loc[:, ~df_cap.columns.duplicated()].copy()

            close_s = df_cap['close'].iloc[:, 0] if isinstance(df_cap['close'], pd.DataFrame) else df_cap['close']
            curr_price = float(close_s.iloc[-1]) if len(close_s) > 0 else 0.0

            try:
                bb_mid = float(close_s.rolling(20, min_periods=2).mean().iloc[-1])
                bb_std = float(close_s.rolling(20, min_periods=2).std().fillna(0.0).iloc[-1])
                bb_upper = float(bb_mid + 2.5 * bb_std)
                bb_lower = float(bb_mid - 2.5 * bb_std)
            except Exception:
                bb_mid, bb_upper, bb_lower = curr_price, curr_price * 1.002, curr_price * 0.998

            try:
                delta = close_s.diff()
                gain = (delta.where(delta > 0, 0)).rolling(14, min_periods=2).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=2).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi_val = float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])
            except Exception:
                rsi_val = 50.0

            actual_has_trade = getattr(buf, 'has_trade', False)

            if actual_has_trade:
                act = str(trade_info.get('action') or trade_info.get('decision') or 'CALL').upper()
                act_icon = "🟢" if act in ['CALL', 'BUY'] else "🔴"
                res = str(trade_info.get('result') or 'WIN').upper()
                pnl = 0.0
                try:
                    raw_pnl = trade_info.get('profit') or trade_info.get('profit_loss')
                    if raw_pnl is not None and str(raw_pnl).lower() not in ['none', 'null', 'nan', '']:
                        pnl = float(raw_pnl)
                except Exception:
                    pass
                res_badge = "✅ <b>WIN</b>" if res == 'WIN' else "❌ <b>LOSS</b>"
                pnl_str = f"+${pnl:.2f} USD" if pnl >= 0 else f"-${abs(pnl):.2f} USD"
                strat_name = trade_info.get('strategy') or trade_info.get('pattern_detected') or 'Algorítmica'
                ts_str = str(trade_info.get('timestamp') or '')
                if len(ts_str) >= 16:
                    ts_clean = ts_str.replace('T', ' ')
                    time_badge = f" | 🕒 {ts_clean[11:16]} (UTC-3)"
                else:
                    time_badge = ""

                plotted_entry = getattr(buf, 'trade_entry_price', None) or float(trade_info.get('open_price') or 0.0)
                plotted_close = getattr(buf, 'trade_close_price', None)
                plotted_pts = getattr(buf, 'trade_points', None)
                plotted_unit = getattr(buf, 'trade_points_unit', 'pts')

                close_line = ""
                if plotted_close is not None and plotted_pts is not None:
                    is_win_pts = (plotted_close >= plotted_entry if act in ['CALL', 'BUY'] else plotted_close <= plotted_entry)
                    pts_sign = "+" if is_win_pts else "-"
                    close_line = f"• <b>Cierre:</b> 🏁 <code>{plotted_close:.5f}</code> ({pts_sign}{plotted_pts} {plotted_unit})\n"

                caption = (
                    f"📊 <b>FOTO DEL TRADE: {pair} ({tf_display}){time_badge}</b>\n\n"
                    f"• <b>Estrategia:</b> {strat_name}\n"
                    f"• <b>Operación:</b> {act_icon} <b>{act}</b> @ <code>{plotted_entry:.5f}</code>\n"
                    f"{close_line}"
                    f"• <b>Resultado:</b> {res_badge} (<b>{pnl_str}</b>)\n"
                    f"• <b>RSI (14):</b> <code>{rsi_val:.1f}</code>\n"
                    f"• <b>Bandas de Bollinger 2.5:</b> [<code>{bb_lower:.5f}</code> - <code>{bb_upper:.5f}</code>]"
                )
            else:
                last_trade_note = ""
                if trade_info and isinstance(trade_info, dict) and trade_info.get('result'):
                    act_raw = str(trade_info.get('action') or trade_info.get('decision') or 'BUY').upper()
                    act_i = "🟢" if act_raw in ['BUY', 'CALL'] else "🔴"
                    res_raw = str(trade_info.get('result') or 'WIN').upper()
                    res_b = "✅ WIN" if res_raw == 'WIN' else "❌ LOSS"
                    pnl_raw = float(trade_info.get('profit') or trade_info.get('profit_loss') or 0.0)
                    pnl_s = f"+${pnl_raw:.2f}" if pnl_raw >= 0 else f"-${abs(pnl_raw):.2f}"
                    ts_raw = str(trade_info.get('timestamp') or '')
                    time_note = f" (Fecha: {ts_raw[:16]})" if ts_raw else ""
                    last_trade_note = (
                        f"\n\n🕒 <b>Última Operación Registrada:</b>\n"
                        f"• {act_i} <b>{act_raw}</b> -> {res_b} (<b>{pnl_s} USD</b>){time_note}\n"
                        f"• <b>Estrategia:</b> {trade_info.get('strategy') or trade_info.get('pattern_detected') or 'Algorítmica'}\n"
                        f"ℹ️ <i>Las velas de esa operación ya no están en la memoria del broker; mostrando gráfico actual en vivo.</i>"
                    )

                caption = (
                    f"📊 <b>ANÁLISIS TÉCNICO EN VIVO: {pair} ({tf_display})</b>\n\n"
                    f"• <b>Precio Actual:</b> <code>${curr_price:.5f}</code>\n"
                    f"• <b>RSI (14):</b> <code>{rsi_val:.1f}</code>\n"
                    f"• <b>Bandas Bollinger (2.5 dev):</b>\n"
                    f"  - Sup: <code>{bb_upper:.5f}</code> | Inf: <code>{bb_lower:.5f}</code>\n"
                    f"  - Media: <code>{bb_mid:.5f}</code>"
                    f"{last_trade_note}"
                )

            await self.send_photo(buf, caption=caption, target_chat_id=chat_id)
            return True

        except Exception as err:
            import traceback
            print(f"[Telegram Chart] Error procesando {pair}: {err}\n{traceback.format_exc()}")
            await self.send_message(f"❌ Error procesando {pair}: {err}", target_chat_id=chat_id)
            return False

    async def _handle_chart(self, chat_id, raw_text="", user_id=None):
        """Manejador bajo demanda para generar y enviar la foto del trade o análisis técnico de Pocket Option."""
        parts = raw_text.strip().split()
        target_pair = None
        target_tf = None

        if len(parts) > 1:
            arg1 = parts[1].strip()
            if arg1.lower() not in ['all', 'todos', 'last', 'ultimo', 'reciente']:
                target_pair = arg1
                if not target_pair.endswith('_otc') and not target_pair.startswith('#'):
                    if len(target_pair) == 6:
                        target_pair = f"{target_pair}_otc"
                    elif target_pair.isalpha() and len(target_pair) <= 5:
                        target_pair = f"#{target_pair}_otc"

                if len(parts) > 2:
                    target_tf = parts[2].strip()

        # CASO 1: Un par específico solicitado
        if target_pair:
            trades = self._get_po_trades_for_chart(pair=target_pair)
            trade_info = trades[0] if trades else None

            if target_tf:
                interval, tf_display = self._parse_timeframe_to_interval(target_tf)
            elif trade_info and trade_info.get('timeframe'):
                interval, tf_display = self._parse_timeframe_to_interval(trade_info.get('timeframe'))
            else:
                interval, tf_display = 300, "5m"

            tf_full = f"{tf_display} ({interval}s)"
            await self.send_message(
                f"📸 <i>Generando gráfico técnico para <b>{target_pair}</b> ({tf_full})...</i>",
                target_chat_id=chat_id
            )
            await self._render_and_send_single_chart(chat_id, target_pair, interval, tf_full, trade_info=trade_info)
            return

        # CASO 2: /chart sin argumentos o /chart all -> Gráficos de TODOS los pares operados en su respectiva temporalidad
        all_trades = self._get_po_trades_for_chart(pair=None)

        if not all_trades:
            await self.send_message(
                "📸 <i>Sin operaciones registradas recientemente. Generando análisis en vivo de EURUSD_otc (5m)...</i>",
                target_chat_id=chat_id
            )
            await self._render_and_send_single_chart(chat_id, "EURUSD_otc", 300, "5m (300s)", trade_info=None)
            return

        count = len(all_trades)
        header_text = (
            f"📸 <b>Generando gráficos de los pares operados ({count} {'activo' if count == 1 else 'activos'})...</b>\n"
            f"<i>Cada par se renderiza en la temporalidad exacta en que fue ejecutado.</i>"
        )
        await self.send_message(header_text, target_chat_id=chat_id)

        sent_count = 0
        for t_info in all_trades[:8]:
            p_name = t_info.get('pair')
            interval, tf_display = self._parse_timeframe_to_interval(t_info.get('timeframe'))
            tf_full = f"{tf_display} ({interval}s)"
            ok = await self._render_and_send_single_chart(chat_id, p_name, interval, tf_full, trade_info=t_info)
            if ok:
                sent_count += 1
            await asyncio.sleep(0.6)

        if sent_count > 1:
            await self.send_message(
                f"✅ <i>Se enviaron los gráficos de {sent_count} pares operados en sus respectivas temporalidades.\n"
                f"💡 Tip: Para auditar un par puntual escribe <code>/chart &lt;par&gt; [tf]</code>.</i>",
                target_chat_id=chat_id,
                reply_markup=self.get_main_keyboard(user_id or chat_id)
            )

    async def _handle_excel(self, chat_id):
        """Generates an Excel file (.xlsx) with live trades and summary statistics and sends it via Telegram."""
        await self.send_message("📊 Generating LIVE account Excel report...", target_chat_id=chat_id)
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            real_files = [f for f in all_files if "pocketoption_real" in Path(f).name or "_real_" in Path(f).name]
            target_files = real_files if real_files else [f for f in all_files if "alpaca" not in Path(f).name]

            if not target_files:
                await self.send_message("⚠️ No LIVE trade records found to export to Excel.", target_chat_id=chat_id)
                return

            dfs = []
            for f in target_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        dfs.append(df_temp)
                except:
                    continue

            if not dfs:
                await self.send_message("⚠️ The trade log files are empty.", target_chat_id=chat_id)
                return

            df_all = pd.concat(dfs, ignore_index=True)
            if 'timestamp' in df_all.columns:
                df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], errors='coerce')
                df_all = df_all.sort_values('timestamp', ascending=False)

            # Generate Excel in memory with BytesIO
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Sheet 1: Trades
                df_all.to_excel(writer, sheet_name='Trades Live', index=False)
                
                # Sheet 2: Summary
                summary_data = []
                completed = df_all[df_all['result'].isin(['WIN', 'LOSS'])] if 'result' in df_all.columns else df_all
                total_trades = len(completed)
                wins = len(completed[completed['result'] == 'WIN']) if 'result' in completed.columns else 0
                winrate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                pnl = completed['profit_loss'].sum() if 'profit_loss' in completed.columns else 0.0

                summary_data.append({'Metric': 'Total Trades', 'Value': total_trades})
                summary_data.append({'Metric': 'Won (WIN)', 'Value': wins})
                summary_data.append({'Metric': 'Lost (LOSS)', 'Value': total_trades - wins})
                summary_data.append({'Metric': 'Win Rate %', 'Value': f"{winrate:.2f}%"})
                summary_data.append({'Metric': 'Net P&L (USD)', 'Value': f"${pnl:.2f}"})

                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='Summary', index=False)

            output.seek(0)
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"Trading_Report_LIVE_{now_str}.xlsx"

            caption = (
                f"📊 <b>LIVE ACCOUNT EXCEL REPORT</b>\n\n"
                f"• Total Trades: {len(completed)}\n"
                f"• Win Rate: {winrate:.1f}%\n"
                f"• Net P&L: ${pnl:+.2f} USD\n"
                f"<i>Attached: Excel spreadsheet with detailed trade history.</i>"
            )

            await self.send_document(output, filename=filename, caption=caption, target_chat_id=chat_id)
        except Exception as e:
            print(f"[Telegram] Error generating Excel: {e}")
            await self.send_message(f"❌ Error generating Excel: {e}", target_chat_id=chat_id)

    def _plot_daily_panel(self, ax, df, label, balance):
        """Dibuja un panel de curva de P&L diario con puntos, rellenos y anotaciones."""
        panel_color = '#151b24'
        grid_color = '#222b38'
        spine_color = '#30363d'
        text_muted = '#8b949e'
        accent_green = '#00ff88'
        accent_red = '#ff4466'

        df = df.sort_values('timestamp').copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['cum_pnl'] = df['profit_loss'].cumsum()

        total_trades = len(df)
        wins = int((df['result'] == 'WIN').sum()) if 'result' in df.columns else 0
        losses = total_trades - wins
        winrate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        final_pnl = float(df['cum_pnl'].iloc[-1])
        primary_color = accent_green if final_pnl >= 0 else accent_red

        t_first = df['timestamp'].iloc[0]
        t_last = df['timestamp'].iloc[-1]
        time_span = t_last - t_first
        lead_delta = pd.Timedelta(minutes=20) if time_span.total_seconds() < 1800 else max(pd.Timedelta(minutes=15), min(pd.Timedelta(hours=1), time_span * 0.12))

        timeline_times = [t_first - lead_delta] + df['timestamp'].tolist()
        timeline_pnl = [0.0] + df['cum_pnl'].tolist()

        ax.set_facecolor(panel_color)
        ax.grid(True, linestyle='--', alpha=0.3, color=grid_color)
        for spine in ax.spines.values():
            spine.set_color(spine_color)
            spine.set_linewidth(1)

        ax.axhline(y=0, color='#ffffff', linestyle='--', alpha=0.35, linewidth=1.1, zorder=2)
        ax.plot(timeline_times, timeline_pnl, color=primary_color, linewidth=2.4, zorder=3, alpha=0.95)

        ax.fill_between(
            timeline_times, timeline_pnl, 0,
            where=np.array(timeline_pnl) >= 0,
            interpolate=True, color=accent_green, alpha=0.15, zorder=2
        )
        ax.fill_between(
            timeline_times, timeline_pnl, 0,
            where=np.array(timeline_pnl) <= 0,
            interpolate=True, color=accent_red, alpha=0.15, zorder=2
        )

        for idx, row in df.iterrows():
            t = row['timestamp']
            p = row['cum_pnl']
            res = row.get('result', '')
            trade_pnl = float(row.get('profit_loss', 0.0))
            m_color = accent_green if res == 'WIN' else (accent_red if res == 'LOSS' else '#ffcc00')
            ax.scatter(t, p, color=m_color, edgecolors='#ffffff', s=55, linewidth=1.2, zorder=4)
            if total_trades <= 10:
                ax.annotate(
                    f"{trade_pnl:+.2f}$",
                    (t, p),
                    xytext=(0, 10 if trade_pnl >= 0 else -14),
                    textcoords="offset points",
                    fontsize=8, color=m_color, weight='bold', ha='center', zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor=panel_color, edgecolor=m_color, alpha=0.85, lw=0.7)
                )

        badge_color = accent_green if final_pnl >= 0 else accent_red
        initial_balance = balance - final_pnl if balance > 0 else balance
        pct_str = f" ({(final_pnl / initial_balance * 100):+.2f}%)" if initial_balance > 0 else ""
        ax.annotate(
            f" Net P&L: ${final_pnl:+.2f}{pct_str} ",
            xy=(t_last, final_pnl),
            xytext=(12, 0),
            textcoords="offset points",
            fontsize=9, fontweight='bold',
            color='black' if final_pnl >= 0 else '#ffffff',
            va='center', ha='left', zorder=6,
            bbox=dict(boxstyle='round,pad=0.4', facecolor=badge_color, edgecolor='none', alpha=0.95)
        )

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.tick_params(colors=text_muted, labelsize=8.5)
        ax.set_ylabel('P&L ($ USD)', fontsize=9, color=text_muted, labelpad=8)

        x_min, x_max = ax.get_xlim()
        ax.set_xlim(x_min, x_max + (x_max - x_min) * 0.22)
        y_min, y_max = ax.get_ylim()
        y_pad = max(abs(y_max - y_min) * 0.25, 0.4)
        ax.set_ylim(y_min - y_pad * 0.5, y_max + y_pad * 0.5)

        stat_text = f"Trades: {total_trades}  |  Win Rate: {winrate:.1f}% ({wins}W - {losses}L)  |  Net: ${final_pnl:+.2f}"
        ax.set_title(f"{label}  —  {stat_text}", fontsize=10.5, fontweight='bold', color='#ffffff', pad=8)

    def _generate_daily_chart(self, completed_po, completed_al, date_str):
        """Generates a clean, premium daily P&L curve for completed trades of the day (dual panels if both operate)."""
        try:
            has_po = completed_po is not None and not completed_po.empty and 'profit_loss' in completed_po.columns
            has_al = completed_al is not None and not completed_al.empty and 'profit_loss' in completed_al.columns

            if not has_po and not has_al:
                return None

            balance_po = 0.0
            try:
                sp = Path('pocketoption_status.json')
                if sp.exists():
                    with open(sp, 'r', encoding='utf-8') as sf:
                        balance_po = float(json.load(sf).get('balance', 0.0))
            except Exception:
                pass

            balance_al = 0.0
            try:
                sp = Path('alpaca_status.json')
                if sp.exists():
                    with open(sp, 'r', encoding='utf-8') as sf:
                        balance_al = float(json.load(sf).get('balance', 0.0))
            except Exception:
                pass

            bg_color = '#0e131a'
            plt.style.use('dark_background')

            if has_po and has_al:
                fig, (ax_po, ax_al) = plt.subplots(2, 1, figsize=(11, 8.2), dpi=130)
                fig.patch.set_facecolor(bg_color)
                self._plot_daily_panel(ax_po, completed_po, "POCKETOPTION REAL (Binarias)", balance_po)
                self._plot_daily_panel(ax_al, completed_al, "ALPACA (Wall Street Stocks)", balance_al)
            elif has_po:
                fig, ax_po = plt.subplots(1, 1, figsize=(11, 5.2), dpi=130)
                fig.patch.set_facecolor(bg_color)
                self._plot_daily_panel(ax_po, completed_po, "POCKETOPTION REAL (Binarias)", balance_po)
            else:
                fig, ax_al = plt.subplots(1, 1, figsize=(11, 5.2), dpi=130)
                fig.patch.set_facecolor(bg_color)
                self._plot_daily_panel(ax_al, completed_al, "ALPACA (Wall Street Stocks)", balance_al)

            fig.suptitle(f"REPORTE DIARIO DE RENDIMIENTO — {date_str}", fontsize=13, fontweight='bold', color='#ffffff', y=0.98)
            fig.tight_layout(rect=[0, 0, 1, 0.96])

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=130, facecolor=bg_color, edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return buf
        except Exception as e:
            print(f"[Telegram] Error generating daily chart: {e}")
            plt.close('all')
            return None

    async def send_daily_report(self, target_date=None, target_chat_ids=None):
        """
        Generates and dispatches the comprehensive End-of-Day Performance Report 
        to the group and all authorized members (or specified target_chat_ids).
        """
        tz_arg = timezone(timedelta(hours=-3))
        now_dt = datetime.now(tz_arg)

        if target_date is None:
            # Por defecto el día actual de la sesión (hoy en UTC-3)
            target_date = now_dt.date()
        elif isinstance(target_date, str):
            clean_arg = target_date.strip().lower()
            if clean_arg in ["hoy", "today"]:
                target_date = now_dt.date()
            elif clean_arg in ["ayer", "yesterday", "prev"]:
                target_date = (now_dt - timedelta(days=1)).date()
            else:
                try:
                    target_date = datetime.strptime(clean_arg, '%Y-%m-%d').date()
                except Exception:
                    try:
                        target_date = datetime.strptime(clean_arg, '%d/%m/%Y').date()
                    except Exception:
                        target_date = now_dt.date()
        elif isinstance(target_date, datetime):
            target_date = target_date.date()

        date_str = target_date.strftime('%d/%m/%Y')

        if target_chat_ids is not None:
            if isinstance(target_chat_ids, (list, tuple)):
                destinations = list(dict.fromkeys(target_chat_ids))
            else:
                destinations = [target_chat_ids]
        else:
            # Send strictly to authorized members (owner_ids) privately, NEVER to the public/shared group
            destinations = list(dict.fromkeys(self.owner_ids if self.owner_ids else ([self.chat_id] if self.chat_id else [])))

        if not destinations:
            print("[Telegram Daily Report] No destinations configured.")
            return None

        # 1. Cargar operaciones consolidadas (SQLite + CSV)
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        completed_po = self._load_broker_trades("pocketoption", start_dt, end_dt)
        completed_al = self._load_broker_trades("alpaca", start_dt, end_dt)

        # Si ninguno tuvo operaciones en el día
        if completed_po.empty and completed_al.empty:
            msg = (
                f"📅 <b>END-OF-DAY PERFORMANCE REPORT</b>\n"
                f"🗓 <b>Date:</b> {date_str}\n\n"
                f"ℹ️ <i>No trade activity recorded for either broker on this day.</i>"
            )
            for dest in destinations:
                await self.send_message(msg, target_chat_id=dest)
            return

        has_po = not completed_po.empty
        has_al = not completed_al.empty

        msg = f"📅 <b>END-OF-DAY PERFORMANCE REPORT</b>\n🗓 <b>Date:</b> {date_str}\n\n"

        if has_po:
            tot_po = len(completed_po)
            wins_po = int((completed_po['result'] == 'WIN').sum())
            losses_po = tot_po - wins_po
            wr_po = (wins_po / tot_po * 100) if tot_po > 0 else 0.0
            pnl_po = float(completed_po['profit_loss'].sum()) if tot_po > 0 else 0.0
            pnl_icon_po = "🟢" if pnl_po > 0 else ("🔴" if pnl_po < 0 else "⚪")

            section_header = "🟢 <b>POCKETOPTION</b>\n" if has_al else ""
            msg += (
                f"{section_header}"
                f"🏆 <b>DAILY SUMMARY</b>\n"
                f"• <b>Total Trades:</b> {tot_po}\n"
                f"• <b>Won (WIN):</b> {wins_po} ({wr_po:.1f}% WR) ✅\n"
                f"• <b>Lost (LOSS):</b> {losses_po} ❌\n"
                f"• <b>Net P&L:</b> {pnl_icon_po} ${pnl_po:+.2f} USD\n\n"
            )

            msg += "<b>📊 BREAKDOWN BY PAIR</b>\n"
            pair_stats_po = completed_po.groupby('pair').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)
            for p, r in pair_stats_po.iterrows():
                msg += f"• <b>{p}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$\n"

            msg += "\n<b>🧠 BREAKDOWN BY STRATEGY</b>\n"
            completed_po_strat = completed_po.copy()
            completed_po_strat['strat_clean'] = completed_po_strat['pattern_detected'].apply(
                lambda x: str(x).split(':')[0] if ':' in str(x) else str(x)
            )
            strat_stats_po = completed_po_strat.groupby('strat_clean').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)
            for s, r in strat_stats_po.iterrows():
                msg += f"• <b>{s}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$\n"

            msg += "\n<b>📝 TRADES EXECUTED</b>\n"
            for _, r in completed_po.iterrows():
                icon = "✅" if r['result'] == 'WIN' else "❌"
                st = str(r.get('pattern_detected', 'Estrategia')).split(':')[0][:24].strip()
                t_str = r['timestamp'].strftime('%H:%M')
                msg += f"{icon} {t_str} | <b>{r['pair']}</b> | {r['profit_loss']:+.2f}$ | {st}\n"

        if has_al:
            tot_al = len(completed_al)
            wins_al = int((completed_al['result'] == 'WIN').sum())
            losses_al = tot_al - wins_al
            wr_al = (wins_al / tot_al * 100) if tot_al > 0 else 0.0
            pnl_al = float(completed_al['profit_loss'].sum()) if tot_al > 0 else 0.0
            pnl_icon_al = "🟢" if pnl_al > 0 else ("🔴" if pnl_al < 0 else "⚪")

            section_header = "\n═══════════════════════\n\n🔸 <b>ALPACA</b>\n" if has_po else ""
            msg += (
                f"{section_header}"
                f"🏆 <b>DAILY SUMMARY</b>\n"
                f"• <b>Total Trades:</b> {tot_al}\n"
                f"• <b>Won (WIN):</b> {wins_al} ({wr_al:.1f}% WR) ✅\n"
                f"• <b>Lost (LOSS):</b> {losses_al} ❌\n"
                f"• <b>Net P&L:</b> {pnl_icon_al} ${pnl_al:+.2f} USD\n\n"
            )

            msg += "<b>📊 BREAKDOWN BY SYMBOL</b>\n"
            pair_stats_al = completed_al.groupby('pair').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)
            for p, r in pair_stats_al.iterrows():
                msg += f"• <b>{p}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$\n"

            msg += "\n<b>🧠 BREAKDOWN BY STRATEGY</b>\n"
            completed_al_strat = completed_al.copy()
            completed_al_strat['strat_clean'] = completed_al_strat['pattern_detected'].apply(
                lambda x: str(x).split(':')[0] if ':' in str(x) else str(x)
            )
            strat_stats_al = completed_al_strat.groupby('strat_clean').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)
            for s, r in strat_stats_al.iterrows():
                msg += f"• <b>{s}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$\n"

            msg += "\n<b>📝 TRADES EXECUTED</b>\n"
            for _, r in completed_al.iterrows():
                icon = "✅" if r['result'] == 'WIN' else "❌"
                st = str(r.get('strategy', r.get('pattern_detected', 'Bracket'))).split(':')[0][:20].strip()
                t_str = r['timestamp'].strftime('%H:%M')
                msg += f"{icon} {t_str} | <b>{r['pair']}</b> ({r.get('decision', 'TRADE')}) | {r['profit_loss']:+.2f}$ | {st}\n"

        # Generar gráfico dual con subplots separados estilo /info
        chart_buffer = self._generate_daily_chart(completed_po, completed_al, date_str)

        print(f"[Telegram] Dispatching daily report for {date_str} to {len(destinations)} destinations: {destinations}")
        for dest in destinations:
            try:
                if chart_buffer and len(msg) <= 1000:
                    chart_buffer.seek(0)
                    await self.send_photo(chart_buffer, caption=msg, target_chat_id=dest)
                else:
                    if chart_buffer:
                        chart_buffer.seek(0)
                        await self.send_photo(chart_buffer, caption=f"📊 Daily Performance Curves ({date_str})", target_chat_id=dest)
                        await asyncio.sleep(0.5)
                    if len(msg) <= 3800:
                        await self.send_message(msg, target_chat_id=dest)
                    else:
                        parts = [msg[i:i+3800] for i in range(0, len(msg), 3800)]
                        for p in parts:
                            await self.send_message(p, target_chat_id=dest)
                            await asyncio.sleep(0.4)
            except Exception as send_err:
                print(f"[Telegram] Error sending daily report to {dest}: {send_err}")

    def _get_stats_for_broker(self, broker_suffix="config"):
        """Calcula estadísticas para un bróker específico basándose en el prefijo del CSV."""
        stats = {
            'trades': 0,
            'winrate': 0.0,
            'pnl': 0.0,
            'today_trades': 0,
            'today_winrate': 0.0,
            'today_pnl': 0.0
        }
        try:
            # Si es Alpaca, consultar SQLite (feedback_config_alpaca.db) como fuente de máxima prioridad
            if broker_suffix == "alpaca":
                try:
                    import sqlite3
                    db_path = Path("feedback_config_alpaca.db")
                    if db_path.exists():
                        conn_al = sqlite3.connect(db_path)
                        c = conn_al.cursor()
                        c.execute("SELECT count(*), sum(case when lower(result)='win' then 1 else 0 end), sum(profit) FROM trades WHERE lower(result) IN ('win', 'loss')")
                        row = c.fetchone()
                        if row and row[0]:
                            stats['trades'] = int(row[0])
                            wins = int(row[1] or 0)
                            stats['winrate'] = (wins / stats['trades']) * 100.0
                            stats['pnl'] = float(row[2] or 0.0)

                        tz = timezone(timedelta(hours=-3))
                        today_str = datetime.now(tz).strftime('%Y-%m-%d')
                        c.execute("SELECT count(*), sum(case when lower(result)='win' then 1 else 0 end), sum(profit) FROM trades WHERE lower(result) IN ('win', 'loss') AND (close_timestamp LIKE ? OR (close_timestamp IS NULL AND timestamp LIKE ?))", (f"{today_str}%", f"{today_str}%"))
                        row_t = c.fetchone()
                        if row_t and row_t[0]:
                            stats['today_trades'] = int(row_t[0])
                            wins_t = int(row_t[1] or 0)
                            stats['today_winrate'] = (wins_t / stats['today_trades']) * 100.0
                            stats['today_pnl'] = float(row_t[2] or 0.0)
                        conn_al.close()
                        return stats
                except Exception as e_sql:
                    print(f"[Telegram] Error leyendo stats de Alpaca SQLite: {e_sql}")

            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                return stats
                
            dfs = []
            for f in all_files:
                f_name = Path(f).name
                if broker_suffix == "alpaca":
                    if "alpaca" not in f_name:
                        continue
                elif broker_suffix in ["pocketoption_real", "real"]:
                    if "pocketoption_real" not in f_name and "_real_" not in f_name:
                        continue
                elif broker_suffix in ["pocketoption_demo", "demo"]:
                    if "real" in f_name or "alpaca" in f_name:
                        continue
                else:
                    has_real = any("pocketoption_real" in Path(x).name or "_real_" in Path(x).name for x in all_files)
                    if has_real:
                        if "pocketoption_real" not in f_name and "_real_" not in f_name:
                            continue
                    else:
                        if "alpaca" in f_name:
                            continue
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty and not df_temp.isna().all().all():
                        dfs.append(df_temp)
                except:
                    continue
                    
            if not dfs:
                return stats
                
            df = pd.concat(dfs, ignore_index=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            completed = df[df['result'].isin(['WIN', 'LOSS'])]
            
            if len(completed) > 0:
                stats['trades'] = len(completed)
                wins = len(completed[completed['result'] == 'WIN'])
                stats['winrate'] = (wins / len(completed)) * 100
                if 'profit_loss' in completed.columns:
                    stats['pnl'] = completed['profit_loss'].sum()
                    
            # Hoy (UTC-3) usando la fuente unificada (SQLite + CSV)
            broker_target = "alpaca" if broker_suffix == "alpaca" else "pocketoption"
            df_today = self._load_broker_trades(broker_target)
            if not df_today.empty:
                stats['today_trades'] = len(df_today)
                wins_today = len(df_today[df_today['result'] == 'WIN'])
                stats['today_winrate'] = (wins_today / len(df_today)) * 100
                if 'profit_loss' in df_today.columns:
                    stats['today_pnl'] = float(df_today['profit_loss'].sum())
        except Exception as e:
            print(f"[Telegram] Error en _get_stats_for_broker ({broker_suffix}): {e}")
        return stats

    def _generate_combined_chart(self, balance_po=0.0, balance_alpaca=0.0, broker="both", only_today=False):
        """Genera un gráfico comparativo de P&L acumulado de ambos brókers, con punto de partida en $0 y etiquetas flotantes al final de cada línea."""
        try:
            dfs_po = []
            dfs_alpaca = []

            # Prioridad 1: Cargar Alpaca directamente desde feedback_config_alpaca.db
            if broker in ["both", "alpaca", "al"]:
                try:
                    import sqlite3
                    db_p = Path("feedback_config_alpaca.db")
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
                except Exception as sqle:
                    print(f"[Telegram] Error leyendo SQLite Alpaca para gráfico: {sqle}")

            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files) if all_files else False

            for f in all_files:
                f_name = Path(f).name
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty and not df_temp.isna().all().all():
                        if "alpaca" in f_name:
                            # Solo agregar de CSV si no se cargó de SQLite
                            if not dfs_alpaca:
                                dfs_alpaca.append(df_temp)
                        elif has_real:
                            if "pocketoption_real" in f_name or "_real_" in f_name:
                                dfs_po.append(df_temp)
                        else:
                            dfs_po.append(df_temp)
                except:
                    continue

            if not dfs_po and not dfs_alpaca:
                return None
                    
            def _build_timeline(df_raw):
                if df_raw is None or df_raw.empty:
                    return None
                df_sorted = df_raw.dropna(subset=['timestamp']).sort_values('timestamp').copy()
                if df_sorted.empty:
                    return None
                if 'cumulative_pnl' not in df_sorted.columns:
                    if 'profit_loss' in df_sorted.columns:
                        df_sorted['profit_loss'] = pd.to_numeric(df_sorted['profit_loss'], errors='coerce').fillna(0)
                        df_sorted['cumulative_pnl'] = df_sorted['profit_loss'].cumsum()
                    else:
                        return None

                # Normalizar timestamps a tz-naive de forma universal
                s_ts = df_sorted['timestamp'].astype(str).str.replace('T', ' ').str.replace('Z', '')
                df_sorted['timestamp'] = pd.to_datetime(s_ts.str.slice(0, 19), errors='coerce')
                df_sorted = df_sorted.dropna(subset=['timestamp'])
                if df_sorted.empty:
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
                dfs_po = [df.dropna(how='all') for df in dfs_po if not df.empty]
                if dfs_po:
                    df_po = pd.concat(dfs_po, ignore_index=True)
                    s_po = df_po['timestamp'].astype(str).str.replace('T', ' ').str.replace('Z', '')
                    df_po['timestamp'] = pd.to_datetime(s_po.str.slice(0, 19), errors='coerce')
                    df_po = df_po.dropna(subset=['timestamp'])
                    if only_today:
                        today_str = (pd.Timestamp.utcnow() - pd.Timedelta(hours=3)).strftime('%Y-%m-%d')
                        df_po = df_po[df_po['timestamp'].dt.strftime('%Y-%m-%d') == today_str]
                    df_po = df_po.sort_values('timestamp')
                    df_po = df_po[df_po['result'].isin(['WIN', 'LOSS'])].copy()
                    if not df_po.empty and 'profit_loss' in df_po.columns:
                        df_po['profit_loss'] = pd.to_numeric(df_po['profit_loss'], errors='coerce').fillna(0.0)
                        df_po['cumulative_pnl'] = df_po['profit_loss'].cumsum()
                        df_po_raw = df_po.copy()
                        po_clean = _build_timeline(df_po)

            al_clean = None
            df_al_raw = None
            if dfs_alpaca and broker in ["both", "alpaca", "al"]:
                dfs_alpaca = [df.dropna(how='all') for df in dfs_alpaca if not df.empty]
                if dfs_alpaca:
                    df_al = pd.concat(dfs_alpaca, ignore_index=True)
                    s_al = df_al['timestamp'].astype(str).str.replace('T', ' ').str.replace('Z', '')
                    df_al['timestamp'] = pd.to_datetime(s_al.str.slice(0, 19), errors='coerce')
                    df_al = df_al.dropna(subset=['timestamp'])
                    if only_today:
                        today_str = (pd.Timestamp.utcnow() - pd.Timedelta(hours=3)).strftime('%Y-%m-%d')
                        df_al = df_al[df_al['timestamp'].dt.strftime('%Y-%m-%d') == today_str]
                    df_al = df_al.sort_values('timestamp')
                    df_al = df_al[df_al['result'].isin(['WIN', 'LOSS'])].copy()
                    if not df_al.empty and 'profit_loss' in df_al.columns:
                        df_al['profit_loss'] = pd.to_numeric(df_al['profit_loss'], errors='coerce').fillna(0.0)
                        df_al['cumulative_pnl'] = df_al['profit_loss'].cumsum()
                        df_al_raw = df_al.copy()
                        al_clean = _build_timeline(df_al)

            has_po = po_clean is not None and not po_clean.empty
            has_al = al_clean is not None and not al_clean.empty

            if not has_po and not has_al:
                return None

            bg_color = '#0e131a'
            panel_color = '#151b24'
            grid_color = '#222b38'

            plt.style.use('dark_background')

            if has_po and has_al:
                fig, (ax_po, ax_al) = plt.subplots(2, 1, figsize=(11, 7.8), dpi=120)
                axes = [ax_po, ax_al]
            elif has_po:
                fig, ax_po = plt.subplots(1, 1, figsize=(11, 4.8), dpi=120)
                axes = [ax_po]
                ax_al = None
            else:
                fig, ax_al = plt.subplots(1, 1, figsize=(11, 4.8), dpi=120)
                axes = [ax_al]
                ax_po = None

            fig.patch.set_facecolor(bg_color)

            for ax in axes:
                ax.set_facecolor(panel_color)
                ax.grid(True, linestyle='--', alpha=0.3, color=grid_color)
                ax.axhline(y=0, color='#ffffff', linestyle='--', alpha=0.3, linewidth=1)
                ax.tick_params(colors='#8b949e', labelsize=8.5, labelbottom=True)
                for spine in ax.spines.values():
                    spine.set_color('#30363d')

            def _setup_trade_panel(ax, clean_df, raw_df, color, title, balance, is_bottom=False):
                t = clean_df['timestamp']
                y = clean_df['cumulative_pnl']

                # Gráfico lineal común suave, claro y continuo respetando todos los días calendario
                ax.plot(t, y, label=title, color=color, linewidth=2.4)
                ax.fill_between(t, y, alpha=0.15, color=color)

                # Puntos para cada operación ejecutada
                if raw_df is not None and not raw_df.empty:
                    profits = raw_df['profit_loss'].astype(float).values
                    dot_colors = ['#00ff88' if p >= 0 else '#ef4444' for p in profits]
                    ax.scatter(raw_df['timestamp'], raw_df['cumulative_pnl'], c=dot_colors, s=16, alpha=0.9, zorder=5, edgecolors='black', linewidths=0.3)

                # Formateo de fechas reales en eje X (incluyendo días inactivos y fines de semana)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
                plt.setp(ax.get_xticklabels(), rotation=20, ha='right', color='#8b949e', fontsize=8.5)

                last_t = t.iloc[-1]
                last_y = y.iloc[-1]
                ax.text(
                    last_t, last_y, f' Bal: ${balance:.2f} (P&L: {last_y:+.2f} USD) ',
                    fontsize=8.5, color='black', weight='bold',
                    bbox=dict(facecolor=color, alpha=0.95, boxstyle='round,pad=0.3', edgecolor='none'),
                    va='center', ha='left'
                )

                x_min, x_max = ax.get_xlim()
                ax.set_xlim(x_min, x_max + max(0.5, (x_max - x_min) * 0.22))
                ax.set_title(title, fontsize=11, color=color, weight='bold', pad=6)
                ax.set_ylabel('P&L ($)', fontsize=9, color='#8b949e')
                if is_bottom:
                    ax.set_xlabel('Tiempo / Fecha (Días Calendario)', fontsize=9, color='#8b949e')

            if has_po:
                po_label = 'POCKETOPTION REAL (Opciones Binarias)' if has_real else 'POCKETOPTION (Binarias)'
                _setup_trade_panel(ax_po, po_clean, df_po_raw, '#00ff88', po_label, balance_po, is_bottom=(not has_al))

            if has_al:
                _setup_trade_panel(ax_al, al_clean, df_al_raw, '#ff9900', 'ALPACA (Forex Spot / Acciones)', balance_alpaca, is_bottom=True)

            fig.suptitle('CURVAS DE RENDIMIENTO (CALENDARIO LINEAL CONTINUO)', fontsize=12, color='#ffffff', weight='bold', y=0.98)
            fig.tight_layout(rect=[0, 0, 1, 0.96])
            
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=120, facecolor=bg_color, edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return buf
        except Exception as e:
            print(f"[Telegram] Error generando gráfico combinado: {e}")
            plt.close('all')
            return None

    def _load_broker_trades(self, broker="pocketoption", start_dt=None, end_dt=None):
        """Carga operaciones cerradas (WIN/LOSS) de SQLite con fallback a CSV."""
        db_file = "feedback_config_alpaca.db" if broker == "alpaca" else "feedback.db"
        tz = timezone(timedelta(hours=-3))
        today_str = datetime.now(tz).strftime('%Y-%m-%d')
        
        rows = []
        # 1. Intentar desde SQLite
        try:
            import sqlite3
            if Path(db_file).exists():
                conn = sqlite3.connect(db_file)
                c = conn.cursor()
                if start_dt and end_dt:
                    s_iso = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                    e_iso = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                    query = """
                        SELECT trade_id, timestamp, pair, strategy, result, profit, close_timestamp 
                        FROM trades 
                        WHERE lower(result) IN ('win', 'loss')
                          AND (
                              (close_timestamp IS NOT NULL AND replace(close_timestamp, 'T', ' ') BETWEEN ? AND ?)
                              OR (close_timestamp IS NULL AND replace(timestamp, 'T', ' ') BETWEEN ? AND ?)
                          )
                        ORDER BY id DESC
                    """
                    c.execute(query, (s_iso, e_iso, s_iso, e_iso))
                else:
                    query = """
                        SELECT trade_id, timestamp, pair, strategy, result, profit, close_timestamp 
                        FROM trades 
                        WHERE lower(result) IN ('win', 'loss')
                          AND (close_timestamp LIKE ? OR (close_timestamp IS NULL AND timestamp LIKE ?))
                        ORDER BY id DESC
                    """
                    c.execute(query, (f"{today_str}%", f"{today_str}%"))
                db_rows = c.fetchall()
                conn.close()
                for r in db_rows:
                    ts_str = r[6] or r[1]
                    try:
                        ts_clean = str(ts_str).replace('T', ' ')
                        dt_val = datetime.fromisoformat(ts_clean[:19])
                    except Exception:
                        dt_val = datetime.now(tz)
                    rows.append({
                        'trade_id': str(r[0]) if r[0] else None,
                        'timestamp': dt_val,
                        'pair': str(r[2]),
                        'strategy': str(r[3] or 'Manual'),
                        'result': str(r[4]).upper(),
                        'profit_loss': float(r[5] or 0.0)
                    })
        except Exception as e:
            print(f"[Telegram] Error cargando de SQLite ({db_file}): {e}")

        df_db = pd.DataFrame(rows) if rows else pd.DataFrame()

        # 2. Complementar con CSV (Doble fuente sincronizada)
        df_csv = pd.DataFrame()
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            dfs = []
            for f in all_files:
                f_name = Path(f).name
                if broker == "alpaca":
                    if "alpaca" not in f_name:
                        continue
                else:
                    has_real = any("pocketoption_real" in Path(x).name or "_real_" in Path(x).name for x in all_files)
                    if has_real:
                        if "pocketoption_real" not in f_name and "_real_" not in f_name:
                            continue
                    else:
                        if "alpaca" in f_name:
                            continue
                try:
                    temp = pd.read_csv(f)
                    if not temp.empty:
                        dfs.append(temp)
                except Exception:
                    continue
            if dfs:
                df_raw = pd.concat(dfs, ignore_index=True)
                df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp'], errors='coerce')
                df_raw = df_raw.dropna(subset=['timestamp'])
                df_raw = df_raw[df_raw['result'].isin(['WIN', 'LOSS'])].copy()
                if 'strategy' not in df_raw.columns and 'pattern_detected' in df_raw.columns:
                    df_raw['strategy'] = df_raw['pattern_detected']
                if start_dt and end_dt:
                    df_csv = df_raw[(df_raw['timestamp'] >= start_dt) & (df_raw['timestamp'] <= end_dt)]
                else:
                    today_d = datetime.now(tz).date()
                    df_csv = df_raw[df_raw['timestamp'].dt.date == today_d]
        except Exception as csve:
            print(f"[Telegram] Error en lectura CSV: {csve}")

        # 3. Consolidación y deduplicación inteligente
        if not df_db.empty and not df_csv.empty:
            cols = ['trade_id', 'timestamp', 'pair', 'strategy', 'result', 'profit_loss']
            for c_name in cols:
                if c_name not in df_db.columns: df_db[c_name] = None
                if c_name not in df_csv.columns: df_csv[c_name] = None
            combined = pd.concat([df_db[cols], df_csv[cols]], ignore_index=True)
            has_id = combined['trade_id'].notna() & (combined['trade_id'] != '') & (combined['trade_id'] != 'None')
            with_id = combined[has_id].drop_duplicates(subset=['trade_id'], keep='first')
            without_id = combined[~has_id].drop_duplicates(subset=['pair', 'result'], keep='first')
            final_df = pd.concat([with_id, without_id], ignore_index=True).sort_values(by='timestamp', ascending=False)
            final_df['pattern_detected'] = final_df['strategy']
            return final_df
        elif not df_db.empty:
            df_db['pattern_detected'] = df_db['strategy']
            return df_db.sort_values(by='timestamp', ascending=False)
        elif not df_csv.empty:
            df_csv['pattern_detected'] = df_csv['strategy']
            return df_csv.sort_values(by='timestamp', ascending=False)

        return pd.DataFrame()

    def _format_broker_breakdown(self, df, broker_name, broker_icon, max_trades=15, is_range=False):
        """Genera el bloque de texto con el desglose detallado de un broker."""
        if df.empty:
            return f"{broker_icon} <b>{broker_name}</b>\n<i>Sin operaciones cerradas en este período.</i>\n"

        total = len(df)
        wins = len(df[df['result'] == 'WIN'])
        losses = len(df[df['result'] == 'LOSS'])
        wr = (wins / total) * 100 if total > 0 else 0.0
        pnl = df['profit_loss'].sum()

        lines = [
            f"{broker_icon} <b>{broker_name}</b>",
            f"• <b>Resumen:</b> {total} ops ({wins}W - {losses}L) | {wr:.1f}% WR | {pnl:+.2f} USD\n",
            "<b>📊 Desglose por Activo:</b>"
        ]

        pair_stats = df.groupby('pair').agg({
            'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
            'profit_loss': 'sum',
            'timestamp': 'count'
        }).rename(columns={'timestamp': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)

        for p, r in pair_stats.iterrows():
            lines.append(f"  • <b>{p}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$")

        lines.append("\n<b>🧠 Desglose por Estrategia:</b>")
        df_copy = df.copy()
        df_copy['strat_clean'] = df_copy['strategy'].apply(lambda x: str(x).split(':')[0][:26].strip())
        st_stats = df_copy.groupby('strat_clean').agg({
            'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
            'profit_loss': 'sum',
            'timestamp': 'count'
        }).rename(columns={'timestamp': 'count', 'result': 'winrate', 'profit_loss': 'pnl'}).sort_values('pnl', ascending=False)

        for s, r in st_stats.iterrows():
            lines.append(f"  • <b>{s}</b>: {int(r['count'])} tr | {r['winrate']:.1f}% WR | {r['pnl']:+.2f}$")

        trades_shown = min(total, max_trades)
        lines.append(f"\n<b>📝 Operaciones Recientes ({trades_shown}/{total}):</b>")
        for _, r in df_copy.head(max_trades).iterrows():
            icon = "✅" if r['result'] == 'WIN' else "❌"
            ts_val = r['timestamp']
            time_str = ts_val.strftime('%d/%m %H:%M') if is_range else ts_val.strftime('%H:%M')
            lines.append(f"  {icon} <b>{r['pair']}</b> | {r['profit_loss']:+.2f}$ | {r['strat_clean']} | {time_str}")

        return "\n".join(lines) + "\n"

    async def _handle_info_details(self, chat_id, start_dt=None, end_dt=None, broker="both"):
        """Maneja los comandos de desglose detallado: /detail_info (ambos), /detail_po y /detail_alpaca."""
        tz = timezone(timedelta(hours=-3))
        today_date = datetime.now(tz).strftime('%d/%m/%Y')
        is_range = bool(start_dt and end_dt)

        if is_range:
            range_header = (
                f"📊 <b>REPORTE DETALLADO POR RANGO</b>\n"
                f"🕒 <b>Período:</b> {start_dt.strftime('%d/%m/%Y %H:%M')} a {end_dt.strftime('%d/%m/%Y %H:%M')}\n\n"
            )
            await self.send_message(f"⏳ Generando desglose detallado ({start_dt.strftime('%d/%m')} - {end_dt.strftime('%d/%m')})...", target_chat_id=chat_id)
        else:
            range_header = f"📅 <b>REPORTE DETALLADO DE HOY ({today_date})</b>\n\n"
            await self.send_message("⏳ Generando desglose detallado de hoy...", target_chat_id=chat_id)

        try:
            # Helper local para enviar con foto si aplica
            async def _send_with_chart(text_msg, broker_filter):
                chart_buf = None
                if not is_range:
                    balance_po = 0.0
                    try:
                        if asyncio.iscoroutinefunction(self.get_balance_callback):
                            balance_po = await self.get_balance_callback()
                        else:
                            balance_po = self.get_balance_callback()
                        if not isinstance(balance_po, (int, float)):
                            balance_po = 0.0
                    except Exception:
                        pass
                    
                    balance_alpaca = 0.0
                    try:
                        status_path = Path('alpaca_status.json')
                        if status_path.exists():
                            with open(status_path, 'r', encoding='utf-8') as sf:
                                shared = json.load(sf)
                                balance_alpaca = float(shared.get('balance', 0.0))
                    except Exception:
                        pass
                    
                    chart_buf = self._generate_combined_chart(balance_po=balance_po, balance_alpaca=balance_alpaca, broker=broker_filter, only_today=False)
                
                if chart_buf:
                    if len(text_msg) <= 1024:
                        await self.send_photo(chart_buf, caption=text_msg, target_chat_id=chat_id)
                    else:
                        await self.send_message(text_msg, target_chat_id=chat_id)
                        await self.send_photo(chart_buf, caption="📈 Gráfico de Rendimiento", target_chat_id=chat_id)
                else:
                    if len(text_msg) <= 3800:
                        await self.send_message(text_msg, target_chat_id=chat_id)
                    else:
                        parts = text_msg.split("\n\n")
                        curr = ""
                        for p in parts:
                            if len(curr) + len(p) < 3800:
                                curr += p + "\n\n"
                            else:
                                await self.send_message(curr, target_chat_id=chat_id)
                                await asyncio.sleep(0.5)
                                curr = p + "\n\n"
                        if curr:
                            await self.send_message(curr, target_chat_id=chat_id)

            # Caso 1: Solo PocketOption
            if broker == "pocketoption":
                df_po = self._load_broker_trades("pocketoption", start_dt, end_dt)
                body = self._format_broker_breakdown(df_po, "POCKETOPTION (Opciones Binarias)", "🟢", max_trades=25, is_range=is_range)
                msg = range_header + body + f"\n<i>Generado: {self._get_time()}</i>"
                await _send_with_chart(msg, "pocketoption")
                return

            # Caso 2: Solo Alpaca
            if broker == "alpaca":
                df_al = self._load_broker_trades("alpaca", start_dt, end_dt)
                if df_al.empty and not is_range:
                    stats_al = self._get_stats_for_broker("alpaca")
                    recent_al = []
                    try:
                        import sqlite3
                        conn_al = sqlite3.connect("feedback_config_alpaca.db")
                        c_al = conn_al.cursor()
                        c_al.execute("SELECT timestamp, pair, action, result, profit, strategy FROM trades WHERE lower(result) IN ('win', 'loss') ORDER BY id DESC LIMIT 6")
                        recent_al = c_al.fetchall()
                        conn_al.close()
                    except: pass
                    
                    extra = (
                        f"• <b>Hoy:</b> 0 operaciones cerradas <i>(Mercado abre 9:30 AM EDT)</i>\n"
                        f"• <b>Historial Total:</b> {stats_al['trades']} ops | {stats_al['winrate']:.1f}% WR | {stats_al['pnl']:+.2f} USD\n"
                    )
                    if recent_al:
                        extra += "\n<b>📝 Últimas Operaciones Cerradas:</b>\n"
                        for tr in recent_al:
                            icon = "✅" if str(tr[3]).lower() == 'win' else "❌"
                            ts_str = str(tr[0]).replace('T', ' ')[:16]
                            extra += f"  {icon} <b>{tr[1]}</b> ({tr[2]}) | {float(tr[4] or 0):+.2f}$ | {ts_str}\n"
                    body = f"🔸 <b>ALPACA (Stocks & Forex)</b>\n{extra}"
                else:
                    body = self._format_broker_breakdown(df_al, "ALPACA (Stocks & Forex)", "🔸", max_trades=25, is_range=is_range)
                
                # Agregar posiciones abiertas
                alpaca_stat = {}
                status_path = Path('alpaca_status.json')
                if status_path.exists():
                    try:
                        with open(status_path, 'r', encoding='utf-8') as sf:
                            alpaca_stat = json.load(sf)
                    except: pass
                active_trades = alpaca_stat.get('active_trades', {})
                if active_trades and not is_range:
                    body += "\n📈 <b>POSICIONES EN CURSO:</b>\n"
                    for sym, t in active_trades.items():
                        body += f"   • {sym}: {t.get('action', 'BUY')} @ ${t.get('entry_price', 0):.2f}\n"

                msg = range_header + body + f"\n<i>Generado: {self._get_time()}</i>"
                await _send_with_chart(msg, "alpaca")
                return

            # Caso 3: Ambos brokers (detail_info)
            df_po = self._load_broker_trades("pocketoption", start_dt, end_dt)
            df_al = self._load_broker_trades("alpaca", start_dt, end_dt)

            sec_po = self._format_broker_breakdown(df_po, "POCKETOPTION (Opciones Binarias)", "🟢", max_trades=10, is_range=is_range)
            sec_al = self._format_broker_breakdown(df_al, "ALPACA (Stocks & Forex)", "🔸", max_trades=10, is_range=is_range)

            # Consolidado Dual
            tot_po = len(df_po)
            tot_al = len(df_al)
            tot_all = tot_po + tot_al
            wins_all = (len(df_po[df_po['result'] == 'WIN']) if not df_po.empty else 0) + (len(df_al[df_al['result'] == 'WIN']) if not df_al.empty else 0)
            losses_all = tot_all - wins_all
            wr_all = (wins_all / tot_all * 100) if tot_all > 0 else 0.0
            pnl_all = (df_po['profit_loss'].sum() if not df_po.empty else 0.0) + (df_al['profit_loss'].sum() if not df_al.empty else 0.0)

            sec_summary = (
                f"🏆 <b>CONSOLIDADO DUAL GLOBAL</b>\n"
                f"• <b>Operaciones Totales:</b> {tot_all} ops ({wins_all}W - {losses_all}L)\n"
                f"• <b>Win Rate Global:</b> {wr_all:.1f}% WR\n"
                f"• <b>PnL Neto Combinado:</b> {pnl_all:+.2f} USD\n\n"
                f"💡 <i>Tip: Usa /detail_po o /detail_alpaca para ver el desglose individual extendido de cada uno.</i>\n"
                f"<i>Generado: {self._get_time()}</i>"
            )

            full_msg = range_header + sec_po + "\n" + sec_al + "\n" + sec_summary
            await _send_with_chart(full_msg, "both")

        except Exception as e:
            print(f"[Telegram] Error en _handle_info_details: {e}")
            import traceback
            await self.send_message(f"❌ Error generando reporte detallado: {e}", target_chat_id=chat_id)

    async def _handle_range_detailed(self, chat_id, start_dt=None, end_dt=None):
        """Handle /range_detailed command (last 10 trades or range)."""
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                await self.send_message("❌ No trade history found.", target_chat_id=chat_id)
                return
            
            has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files)
            if has_real:
                all_files = [f for f in all_files if "pocketoption_real" in Path(f).name or "_real_" in Path(f).name]
            
            all_files.sort(reverse=True)
            
            dfs = []
            for f in all_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        dfs.append(df_temp)
                        if not start_dt and len(pd.concat(dfs)) >= 20:
                            break
                except: continue
            
            if not dfs:
                await self.send_message("❌ No data available.", target_chat_id=chat_id)
                return
                
            df = pd.concat(dfs, ignore_index=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])
            
            # Filtrar solo trades cerrados con resultado
            df_completed = df[df['result'].isin(['WIN', 'LOSS'])].copy()
            if df_completed.empty:
                await self.send_message("❌ No completed trades recorded.", target_chat_id=chat_id)
                return
            
            if start_dt and end_dt:
                trades_to_show = df_completed[(df_completed['timestamp'] >= start_dt) & (df_completed['timestamp'] <= end_dt)].sort_values('timestamp', ascending=False)
                msg = f"<b>📝 TRADES IN RANGE</b>\n"
                msg += f"🕒 {start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}\n\n"
            else:
                trades_to_show = df_completed.sort_values('timestamp', ascending=False).head(10)
                msg = "<b>📝 LAST 10 TRADES</b>\n\n"
            
            if trades_to_show.empty:
                await self.send_message("❌ No trades found in this range.", target_chat_id=chat_id)
                return

            tz = timezone(timedelta(hours=-3))
            today = datetime.now(tz).date()
            yesterday = today - timedelta(days=1)

            for _, row in trades_to_show.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌"
                pnl_str = f"{row['profit_loss']:+.2f}$"
                ts_val = row['timestamp']
                if ts_val.tzinfo is not None:
                    local_ts = ts_val.tz_convert(tz)
                else:
                    local_ts = ts_val
                
                trade_date = local_ts.date()
                if trade_date == today:
                    date_prefix = "Hoy "
                elif trade_date == yesterday:
                    date_prefix = "Ayer "
                else:
                    date_prefix = local_ts.strftime('%d/%m ')
                    
                time_str = f"{date_prefix}{local_ts.strftime('%H:%M')}"
                strat = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                msg += f"{res_icon} <b>{row['pair']}</b> | {pnl_str} | {strat} | {time_str}\n"
            
            await self.send_message(msg, target_chat_id=chat_id)
            
        except Exception as e:
            print(f"[Telegram] Error in range_detailed: {e}")
            await self.send_message(f"❌ Error: {e}", target_chat_id=chat_id)

    async def _handle_manual_killapp(self, chat_id):
        """Maneja el comando /killapp manual para apagar el bot de forma segura y liberar recursos."""
        await self.send_message("⏳ Evaluando estado del bot y posiciones abiertas para Killapp seguro...", target_chat_id=chat_id)
        try:
            # Obtener datos de Alpaca
            alpaca_cfg_path = Path("config_alpaca.json")
            positions = []
            if alpaca_cfg_path.exists():
                with open(alpaca_cfg_path, 'r', encoding='utf-8') as f:
                    alpaca_cfg = json.load(f)
                key = alpaca_cfg.get('alpaca_key_id')
                secret = alpaca_cfg.get('alpaca_secret_key')
                base_url = "https://paper-api.alpaca.markets" if alpaca_cfg.get('alpaca_paper', True) else "https://api.alpaca.markets"
                headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(f"{base_url}/v2/positions", timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            positions = await r.json()

            # PnL de hoy de Alpaca
            import sqlite3
            pnl_alpaca_today = 0.0
            today_str = datetime.now().strftime('%Y-%m-%d')
            try:
                conn_al = sqlite3.connect("feedback_config_alpaca.db")
                rows = conn_al.execute("SELECT profit FROM trades WHERE (close_timestamp LIKE ? OR (close_timestamp IS NULL AND timestamp LIKE ?)) AND lower(result) IN ('win', 'loss')", (f"{today_str}%", f"{today_str}%")).fetchall()
                pnl_alpaca_today = round(sum(float(r[0]) for r in rows), 2)
                conn_al.close()
            except Exception: pass

            # PnL de hoy de PocketOption
            pnl_po_today = 0.0
            try:
                conn_po = sqlite3.connect("feedback.db")
                rows_po = conn_po.execute("SELECT profit FROM trades WHERE timestamp LIKE ? AND lower(result) IN ('win', 'loss')", (f"{today_str}%",)).fetchall()
                pnl_po_today = round(sum(float(r[0]) for r in rows_po), 2)
                conn_po.close()
            except Exception: pass

            pos_lines = []
            for p in positions:
                sym = p.get('symbol', 'UNKNOWN')
                qty = float(p.get('qty', 1.0))
                side = p.get('side', 'long').upper()
                entry = float(p.get('avg_entry_price', 0.0))
                current = float(p.get('current_price', 0.0))
                upl = float(p.get('unrealized_pl', 0.0))
                dist_entry = abs(current - entry) / current * 100 if current > 0 else 0.0
                pos_lines.append(f"  • <b>{sym}</b> ({side}, {abs(qty):g} acc) | Flotante: ${upl:+.2f} USD\n    Actual: ${current:.2f} | Entrada: ${entry:.2f} (Var: {dist_entry:.2f}%)")

            msg = (
                "🛑 <b>KILLAPP EJECUTADO MANUALMENTE</b>\n\n"
                f"🟢 <b>PocketOption:</b> PnL Hoy: ${pnl_po_today:+.2f} USD\n"
                f"🔸 <b>Alpaca:</b> PnL Realizado Hoy: ${pnl_alpaca_today:+.2f} USD\n\n"
            )
            if pos_lines:
                msg += "📋 <b>Posiciones Abiertas en Custodia (Alpaca Cloud):</b>\n" + "\n".join(pos_lines) + "\n\n"
                msg += "🛡️ <i>Tus posiciones tienen órdenes bracket activas en los servidores de Alpaca.</i>\n\n"
            else:
                msg += "ℹ️ <i>No quedan posiciones abiertas en ningún broker.</i>\n\n"

            msg += (
                "🔒 <i>El bot de trading se ha detenido y los recursos están liberados.\n"
                "Ya puedes apagar la PC tranquilamente esta noche.\n"
                "Mañana a las 06:00 AM se encenderá automáticamente vía Wake On LAN.</i>"
            )
            await self.send_message(msg, target_chat_id=chat_id)
            await asyncio.sleep(2)

            with open("killapp.flag", "w", encoding="utf-8") as kf:
                kf.write(f"{datetime.now().isoformat()} - Manual Telegram Killapp")

            import os
            os._exit(0)

        except Exception as e:
            print(f"[Telegram] Error en manual killapp: {e}")
            await self.send_message(f"❌ Error ejecutando Killapp: {e}", target_chat_id=chat_id)

    async def _handle_pc_status(self, chat_id):
        """Displays system metrics: CPU, RAM, Disk, Uptime and enables the PC tools menu."""
        try:
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            num_pids = len(psutil.pids())

            msg = (
                f"🖥️ <b>ESTADO DE LA COMPUTADORA / SISTEMA</b>\n\n"
                f"⚡ <b>Uso CPU:</b> {cpu}%\n"
                f"🧠 <b>Memoria RAM:</b> {ram.percent}% ({ram.used / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB)\n"
                f"💾 <b>Disco C:</b> {disk.percent}% ({disk.free / (1024**3):.1f} GB libre de {disk.total / (1024**3):.1f} GB)\n"
                f"⏱️ <b>Tiempo encendida:</b> {uptime_str}\n"
                f"⚙️ <b>Procesos activos:</b> {num_pids}\n\n"
                f"🛠️ <b>HERRAMIENTAS DE PC HABILITADAS EN '/'</b>\n"
                f"• <code>/limpiar_ram</code> — Liberar memoria RAM del sistema\n"
                f"• <code>/recursos</code> — Monitor de tareas pesadas y drenaje\n"
                f"• <code>/restart_gui</code> — Reiniciar escritorio de Windows\n"
                f"• <code>/reboot_pc</code> — Reiniciar equipo Windows\n"
                f"• <code>/back</code> — Volver al menú principal de trading\n\n"
                f"<i>(Vuelve automáticamente a trading tras 5 min de inactividad o con /back)</i>\n"
                f"<i>Generado: {self._get_time()}</i>"
            )
            await self.send_message(msg, target_chat_id=chat_id, reply_markup=self.get_pc_keyboard())

            # Activar menú de herramientas de PC en el autocompletado '/'
            await self.set_pc_commands(chat_id)
            self.pc_menu_active_chats[chat_id] = time.time() + self.pc_menu_timeout
        except Exception as e:
            await self.send_message(f"❌ Error obteniendo estado de PC: {e}", target_chat_id=chat_id)

    async def _handle_back_to_main(self, chat_id, user_id=None):
        """Restaura el menú principal de trading en el autocompletado '/' y en la botonera."""
        if chat_id in self.pc_menu_active_chats:
            del self.pc_menu_active_chats[chat_id]
        await self.set_main_commands(chat_id)
        msg = (
            "🔙 <b>Menú principal de trading restaurado.</b>\n\n"
            "Toca los botones del teclado rápido o escribe <code>/</code> para ver tus comandos de trading:\n"
            "• <code>/info</code> — Rendimiento global y gráfico\n"
            "• <code>/po</code> — Detalle PocketOption\n"
            "• <code>/alpaca</code> — Detalle y posiciones Alpaca\n"
            "• <code>/balance</code> — Saldo en brokers\n"
            "• <code>/daily</code> — Resumen diario\n"
            "• <code>/excel</code> — Exportar a Excel\n"
            "• <code>/test</code> — Simulación cuantitativa bajo demanda\n"
            "• <code>/restart_bot</code> — Reiniciar proceso del bot\n"
            "• <code>/pc</code> — Herramientas del sistema"
        )
        await self.send_message(msg, target_chat_id=chat_id, reply_markup=self.get_main_keyboard(user_id or chat_id))

    async def _handle_resources(self, chat_id):
        """Diagnostica qué aplicaciones y tareas están drenando CPU y RAM, y clasifica si se pueden eliminar."""
        await self.send_message("🔍 <i>Analizando procesos y consumo de recursos en Windows...</i>", target_chat_id=chat_id)
        try:
            SYSTEM_CRITICAL_NAMES = {
                'system', 'system idle process', 'registry', 'smss.exe', 'csrss.exe',
                'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'fontdrvhost.exe',
                'dwm.exe', 'msmpeng.exe', 'spoolsv.exe', 'searchindexer.exe', 'runtimebroker.exe',
                'winlogon.exe', 'memory compression', 'ctfmon.exe', 'audiodg.exe'
            }
            BOT_PIDS = {os.getpid(), os.getppid()}

            cpu_total = psutil.cpu_percent(interval=0.4)
            ram = psutil.virtual_memory()

            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    p_name = p.info['name'] or 'Unknown'
                    p_pid = p.info['pid']
                    rss_mb = round(p.info['memory_info'].rss / (1024 * 1024), 1) if p.info['memory_info'] else 0
                    procs.append({'pid': p_pid, 'name': p_name, 'ram_mb': rss_mb})
                except Exception:
                    pass

            apps = {}
            for p in procs:
                n = p['name'].lower()
                if n not in apps:
                    apps[n] = {'name': p['name'], 'count': 0, 'total_ram': 0.0, 'pids': []}
                apps[n]['count'] += 1
                apps[n]['total_ram'] += p['ram_mb']
                apps[n]['pids'].append(p['pid'])

            top_apps = sorted(apps.values(), key=lambda x: x['total_ram'], reverse=True)[:6]
            top_pids = sorted(procs, key=lambda x: x['ram_mb'], reverse=True)[:5]

            lines = []
            lines.append("📊 <b>DIAGNÓSTICO DE RECURSOS Y DRENAJE (PC)</b>\n")
            lines.append(f"⚡ <b>Uso de CPU:</b> {cpu_total}%")
            lines.append(f"🧠 <b>Memoria RAM:</b> {ram.percent}% ({ram.used/(1024**3):.1f} GB usados de {ram.total/(1024**3):.1f} GB)")
            lines.append(f"💾 <b>RAM Libre:</b> {ram.available/(1024**3):.1f} GB disponibles\n")

            if ram.percent >= 70:
                lines.append("⚠️ <b>ALERTA DE RENDIMIENTO:</b> Tu PC tiene alto consumo de RAM (>70%). Esto causa que Windows empiece a congelar la pantalla y retrase el bot.\n")

            lines.append("🚨 <b>APLICACIONES QUE MÁS DRENAN MEMORIA:</b>")
            for a in top_apps:
                nl = a['name'].lower()
                clean_name = nl.replace('.exe', '')
                ram_gb_val = a['total_ram'] / 1024.0
                if a['total_ram'] >= 1024:
                    ram_str = f"{a['total_ram']:,.0f} MB ({ram_gb_val:.1f} GB)"
                else:
                    ram_str = f"{a['total_ram']:,.0f} MB"

                if nl in SYSTEM_CRITICAL_NAMES:
                    badge = "🔴 <b>CRÍTICO DE WINDOWS (NO TOCAR)</b>"
                    action = "<i>Procesos vitales del núcleo del sistema operativo.</i>"
                elif 'python' in nl and any(pid in BOT_PIDS for pid in a['pids']):
                    badge = "🤖 <b>BOT DE TRADING (NO TOCAR)</b>"
                    action = "<i>Proceso activo del bot. Usar /restart_bot si deseas reiniciarlo.</i>"
                elif nl in ['explorer.exe']:
                    badge = "🟡 <b>INTERFAZ DE WINDOWS</b>"
                    action = "<i>Escritorio y barra de tareas. Si se tilda usa /restart_gui.</i>"
                elif nl in ['antigravity ide.exe', 'code.exe', 'cursor.exe', 'language_server_windows_x64.exe', 'pyrefly.exe']:
                    badge = "🟡 <b>ENTORNO DE PROGRAMACIÓN</b>"
                    action = "<i>IDE de desarrollo. Seguro de cerrar solo si no estás programando.</i>"
                elif nl in ['chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe']:
                    badge = "🟢 <b>SEGURO PARA CERRAR (Navegador)</b>"
                    action = f"👉 Para cerrar todas sus pestañas: <code>/kill_app {clean_name}</code>"
                elif nl in ['discord.exe', 'spotify.exe', 'steam.exe', 'telegram.exe', 'epicgameslauncher.exe']:
                    badge = "🟢 <b>SEGURO PARA CERRAR (App secundaria)</b>"
                    action = f"👉 Para cerrarla: <code>/kill_app {clean_name}</code>"
                else:
                    badge = "🟢 <b>SEGURO PARA CERRAR</b>"
                    action = f"👉 Para cerrar: <code>/kill_app {clean_name}</code>"

                lines.append(f"• <b>{a['name']}</b> ({a['count']} proc): <code>{ram_str}</code>\n  {badge}\n  {action}\n")

            lines.append("⚡ <b>TOP 5 PROCESOS INDIVIDUALES (PID):</b>")
            for p in top_pids:
                nl = p['name'].lower()
                can_kill = nl not in SYSTEM_CRITICAL_NAMES and p['pid'] not in BOT_PIDS and nl != 'explorer.exe'
                tag = f"🟢 Seguro -&gt; <code>/kill {p['pid']}</code>" if can_kill else "🔴 Protegido"
                lines.append(f"• <code>PID {p['pid']}</code> | {p['name']} | {p['ram_mb']} MB | {tag}")

            lines.append("\n💡 <b>HERRAMIENTAS RÁPIDAS PARA DESTILDAR LA PC:</b>")
            lines.append("• <code>/kill_app chrome</code>: Cierra todas las pestañas de Chrome")
            lines.append("• <code>/kill_app msedge</code>: Cierra todas las pestañas de Edge")
            lines.append("• <code>/kill &lt;pid&gt;</code>: Cierra un proceso puntual por su PID")
            lines.append("• <code>/limpiar_ram</code>: Purga cachés en memoria RAM")
            lines.append("• <code>/restart_gui</code>: Destraba la pantalla reiniciando Explorer")

            msg = "\n".join(lines)
            await self.send_message(msg, target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error diagnosticando recursos: {e}", target_chat_id=chat_id)

    async def _handle_kill_pid(self, chat_id, text, user_id):
        """Termina un proceso individual por su PID con salvaguardas de seguridad."""
        parts = text.strip().split()
        if len(parts) < 2:
            await self.send_message(
                "❓ <b>Uso del comando:</b> <code>/kill &lt;PID&gt;</code>\n"
                "Ejemplo: <code>/kill 17568</code>\n\n"
                "<i>Tip: Escribe /recursos para ver qué PIDs consumen más memoria y si son seguros de cerrar.</i>",
                target_chat_id=chat_id
            )
            return

        try:
            pid = int(parts[1])
        except ValueError:
            await self.send_message("❌ El PID debe ser un número entero. Ejemplo: <code>/kill 17568</code>", target_chat_id=chat_id)
            return

        if pid in [0, 4]:
            await self.send_message("❌ <b>PROHIBIDO:</b> Los PIDs 0 y 4 pertenecen al Kernel de Windows. Matarlos causaría un pantallazo azul inmediato.", target_chat_id=chat_id)
            return

        if pid in [os.getpid(), os.getppid()]:
            await self.send_message("🤖 <b>PROCESO DEL BOT:</b> Este PID pertenece al bot en ejecución. Para reiniciarlo usa <code>/restart_bot</code>.", target_chat_id=chat_id)
            return

        if not psutil.pid_exists(pid):
            await self.send_message(f"⚠️ El proceso con PID <code>{pid}</code> ya no está activo.", target_chat_id=chat_id)
            return

        try:
            p = psutil.Process(pid)
            p_name = p.name()
            nl = p_name.lower()
            CRITICAL = {'csrss.exe', 'smss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe', 'winlogon.exe'}
            if nl in CRITICAL:
                await self.send_message(f"❌ <b>ACCESO DENEGADO:</b> <code>{p_name}</code> es un proceso crítico de Windows. No se puede terminar por seguridad.", target_chat_id=chat_id)
                return

            rss_mb = round(p.memory_info().rss / (1024*1024), 1) if p.memory_info() else 0
            p.terminate()
            try:
                p.wait(timeout=2)
            except psutil.TimeoutExpired:
                p.kill()

            await self.send_message(
                f"✅ <b>PROCESO TERMINADO</b>\n\n"
                f"• <b>Programa:</b> <code>{p_name}</code>\n"
                f"• <b>PID:</b> <code>{pid}</code>\n"
                f"• <b>Memoria liberada:</b> ~{rss_mb} MB\n\n"
                f"<i>Usa /recursos para verificar el estado actualizado de la memoria.</i>",
                target_chat_id=chat_id
            )
        except Exception as e:
            await self.send_message(f"❌ No se pudo terminar el proceso PID {pid}: {e}", target_chat_id=chat_id)

    async def _handle_kill_app(self, chat_id, text, user_id):
        """Cierra todas las instancias de un programa (ej: chrome, msedge, discord)."""
        parts = text.strip().split()
        if len(parts) < 2:
            await self.send_message(
                "❓ <b>Uso del comando:</b> <code>/kill_app &lt;nombre&gt;</code>\n\n"
                "Ejemplos comunes:\n"
                "• <code>/kill_app chrome</code> (Cierra todas las pestañas de Chrome)\n"
                "• <code>/kill_app msedge</code> (Cierra todas las pestañas de Edge)\n"
                "• <code>/kill_app discord</code> (Cierra Discord)\n\n"
                "<i>Usa /recursos para ver las aplicaciones que más RAM están consumiendo.</i>",
                target_chat_id=chat_id
            )
            return

        target_name = parts[1].strip().lower()
        if not target_name.endswith('.exe'):
            target_exe = target_name + '.exe'
        else:
            target_exe = target_name

        CRITICAL = {'csrss.exe', 'smss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe', 'winlogon.exe', 'explorer.exe', 'system', 'registry'}
        if target_exe in CRITICAL:
            await self.send_message(f"❌ <b>ACCESO DENEGADO:</b> <code>{target_exe}</code> es un componente crítico de Windows. Si necesitas destrabar la pantalla usa <code>/restart_gui</code>.", target_chat_id=chat_id)
            return

        if target_exe == 'python.exe':
            await self.send_message("🤖 <b>PROTEGIDO:</b> Para reiniciar el bot de trading usa <code>/restart_bot</code>.", target_chat_id=chat_id)
            return

        found_count = 0
        total_ram = 0.0
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                if (p.info['name'] or '').lower() == target_exe:
                    found_count += 1
                    if p.info['memory_info']:
                        total_ram += p.info['memory_info'].rss
            except:
                pass

        if found_count == 0:
            await self.send_message(f"ℹ️ No se encontraron procesos activos para <code>{target_exe}</code>.", target_chat_id=chat_id)
            return

        ram_freed_mb = round(total_ram / (1024*1024), 1)
        ram_freed_gb = ram_freed_mb / 1024.0

        try:
            subprocess.run(f"taskkill /f /im {target_exe}", shell=True, capture_output=True, text=True)
            ram_display = f"{ram_freed_mb} MB ({ram_freed_gb:.1f} GB)" if ram_freed_mb >= 1024 else f"{ram_freed_mb} MB"
            await self.send_message(
                f"🧹 <b>APLICACIÓN CERRADA CON ÉXITO</b>\n\n"
                f"• <b>Programa:</b> <code>{target_exe}</code>\n"
                f"• <b>Procesos cerrados:</b> {found_count}\n"
                f"• <b>Memoria RAM liberada:</b> ~{ram_display}\n\n"
                f"<i>Tu PC ha recuperado recursos para el bot. Escribe /recursos para revisar el estado.</i>",
                target_chat_id=chat_id
            )
        except Exception as e:
            await self.send_message(f"❌ Error al cerrar {target_exe}: {e}", target_chat_id=chat_id)

    async def _handle_clean_ram(self, chat_id):
        """Purga cachés y optimiza la memoria RAM en segundo plano sin cerrar programas."""
        import gc, ctypes
        await self.send_message("🧹 <i>Optimizando memoria RAM del sistema...</i>", target_chat_id=chat_id)
        before_ram = psutil.virtual_memory().used
        
        # 1. Recolección de basura en Python
        gc.collect()
        
        # 2. Vaciado de working set en Windows
        try:
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except Exception:
            pass

        await asyncio.sleep(1)
        after_ram = psutil.virtual_memory().used
        freed_mb = max(0, round((before_ram - after_ram) / (1024*1024), 1))
        current_mem = psutil.virtual_memory()

        await self.send_message(
            f"✅ <b>MEMORIA OPTIMIZADA</b>\n\n"
            f"• <b>RAM Actual en Uso:</b> {current_mem.percent}% ({current_mem.used / (1024**3):.1f} GB)\n"
            f"• <b>RAM Disponible:</b> {current_mem.available / (1024**3):.1f} GB\n"
            f"• <b>Caché interna liberada:</b> ~{freed_mb} MB\n\n"
            f"<i>Si el consumo sigue alto, escribe /recursos para ver qué navegador o tarea está drenando tu PC.</i>",
            target_chat_id=chat_id
        )

    async def _handle_reboot_pc(self, chat_id, text, message_id=None, origin_chat_id=None):
        """Forces a PC reboot with safety confirmation."""
        if message_id and origin_chat_id:
            await self.delete_message(origin_chat_id, message_id)

        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in ['confirm', 'confirmar', 'yes', 'si', 'force', 'ok', 'forzar']:
            await self.send_message("🔄 <b>REINICIO FORZADO EN PROGRESO</b>\n\nCerrando aplicaciones y reiniciando Windows en 5 segundos...", target_chat_id=chat_id)
            subprocess.Popen("shutdown /r /f /t 5", shell=True)
        else:
            msg = (
                "⚠️ <b>¿Estás seguro de que deseas forzar el reinicio de la PC?</b>\n\n"
                "Esto cerrará todas las aplicaciones de Windows y reiniciará el equipo inmediatamente.\n\n"
                "👉 Para confirmar, envía:\n"
                "<code>/reboot_pc confirm</code>"
            )
            await self.send_message(msg, target_chat_id=chat_id)

    async def _handle_restart_gui(self, chat_id):
        """Restarts Windows Explorer to unfreeze the desktop interface without turning off the PC."""
        await self.send_message("🖥️ Restarting Windows GUI (Explorer.exe)...", target_chat_id=chat_id)
        try:
            subprocess.Popen("taskkill /f /im explorer.exe && start explorer.exe", shell=True)
            await asyncio.sleep(2)
            await self.send_message("✅ <b>Windows GUI successfully restarted.</b>\nIf the screen or Remote Desktop was frozen, it should now respond.", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error restarting GUI: {e}", target_chat_id=chat_id)

    async def _handle_restart_bot(self, chat_id):
        """Hot-reloads the trading bot by notifying the supervisor via exit code 5."""
        await self.send_message("🔄 <b>Reiniciando el bot de trading...</b>\nEl supervisor recargará el proceso en 2 segundos.", target_chat_id=chat_id)
        try:
            # Confirmar expresamente el update con la API de Telegram para sacarlo de la cola
            if self.last_update_id and self.base_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        ack_url = f"{self.base_url}/getUpdates"
                        await session.get(ack_url, params={'offset': self.last_update_id + 1, 'timeout': 0}, timeout=aiohttp.ClientTimeout(total=5))
                except Exception as ack_err:
                    print(f"[Telegram] Aviso confirmando offset antes de salir: {ack_err}")

            # Guardar el offset confirmado en disco
            try:
                Path(".telegram_offset").write_text(str(self.last_update_id), encoding="utf-8")
            except Exception:
                pass

            import sys
            await asyncio.sleep(1.0)
            sys.exit(5)
        except Exception as e:
            await self.send_message(f"❌ Error al reiniciar el bot: {e}", target_chat_id=chat_id)

    async def _handle_pause(self, chat_id):
        """Pauses placing new trades."""
        if hasattr(self, 'bot_ref') and self.bot_ref:
            self.bot_ref.is_paused = True
        self.is_paused = True
        await self.send_message("⏸️ <b>BOT PAUSED</b>\nNo new trades will be placed until you send /resume.", target_chat_id=chat_id)

    async def _handle_resume(self, chat_id):
        """Resumes bot trading operations."""
        if hasattr(self, 'bot_ref') and self.bot_ref:
            self.bot_ref.is_paused = False
        self.is_paused = False
        await self.send_message("▶️ <b>BOT RESUMED</b>\nTrading operations are now active.", target_chat_id=chat_id)

    async def _handle_set_monto(self, chat_id, text, message_id=None, origin_chat_id=None):
        """Updates the base trade amount in config.json."""
        if message_id and origin_chat_id:
            await self.delete_message(origin_chat_id, message_id)

        parts = text.split()
        if len(parts) < 2:
            await self.send_message("👉 <b>Uso:</b> <code>/set_amount 2.0</code>", target_chat_id=chat_id)
            return

        try:
            new_amount = float(parts[1])
            if new_amount <= 0:
                await self.send_message("❌ El monto debe ser mayor a 0.", target_chat_id=chat_id)
                return
            if new_amount > 25.0:
                await self.send_message("⚠️ <b>Seguridad de Capital:</b> El monto no puede superar $25.00 USD por operación.", target_chat_id=chat_id)
                return

            config_path = Path("config.json")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if "trading" in cfg and isinstance(cfg["trading"], dict):
                    cfg["trading"]["amount"] = new_amount
                cfg["amount"] = new_amount
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
                await self.send_message(f"💵 <b>Monto base actualizado a ${new_amount:.2f} USD</b> en config.json.", target_chat_id=chat_id)
            else:
                await self.send_message("❌ config.json no encontrado.", target_chat_id=chat_id)
        except ValueError:
            await self.send_message("❌ Monto inválido. Ejemplo: <code>/set_amount 2.5</code>", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error actualizando monto: {e}", target_chat_id=chat_id)

    async def _handle_cmd(self, chat_id, text, message_id=None, origin_chat_id=None):
        """Executes a terminal shell command on the PC (Owner Only)."""
        raw_cmd = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
        if not raw_cmd:
            await self.send_message("👉 <b>Uso:</b> <code>/cmd dir</code> o <code>/cmd tasklist</code>", target_chat_id=chat_id)
            return

        await self.send_message(f"⚙️ <b>Ejecutando:</b> <code>{raw_cmd}</code>...", target_chat_id=chat_id)
        try:
            res = subprocess.run(raw_cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = res.stdout.strip() or res.stderr.strip() or f"Finished with exit code {res.returncode}"
            if len(out) > 3800:
                out = out[:3800] + "\n...(output truncated)"
            await self.send_message(f"<pre>{html.escape(out)}</pre>", target_chat_id=chat_id)
        except subprocess.TimeoutExpired:
            await self.send_message("⚠️ El comando superó el límite de tiempo de 30 segundos.", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error ejecutando comando: {e}", target_chat_id=chat_id)

    async def _handle_ia(self, chat_id, prompt):
        """Processes a query or instruction with the Antigravity AI Agent."""
        if not self.agent:
            await self.send_message("❌ AI module is not configured (missing gemini_api_key).", target_chat_id=chat_id)
            return
        await self.send_message("🧠 <i>Antigravity is analyzing your request...</i>", target_chat_id=chat_id)
        try:
            reply = await self.agent.process_message(prompt)
            MAX_LEN = 4000
            if len(reply) <= MAX_LEN:
                await self.send_message(reply, target_chat_id=chat_id)
            else:
                for i in range(0, len(reply), MAX_LEN):
                    await self.send_message(reply[i:i+MAX_LEN], target_chat_id=chat_id)
                    await asyncio.sleep(0.5)
        except Exception as e:
            await self.send_message(f"❌ Error communicating with AI: {e}", target_chat_id=chat_id)

    async def _handle_test(self, chat_id, raw_text, user_id=None):
        """Ejecuta una simulación rápida (backtest bajo demanda) sobre las últimas velas de un par."""
        parts = raw_text.strip().split()
        if len(parts) < 2 or parts[1].lower() in ['help', 'ayuda', '?']:
            help_msg = (
                "🧪 <b>MODO SIMULACIÓN / BACKTEST BAJO DEMANDA</b>\n\n"
                "Evalúa cualquier par y estrategia sobre las últimas 300-500 velas históricas en tiempo real.\n\n"
                "👉 <b>Sintaxis:</b>\n"
                "<code>/test &lt;par&gt; [timeframe] [estrategia]</code>\n\n"
                "💡 <b>Ejemplos rápidos:</b>\n"
                "• <code>/test BTCUSD_otc 5m WaveTrend</code>\n"
                "• <code>/test EURUSD_otc 1m all</code>\n"
                "• <code>/test #MSFT_otc 5m SMC</code>\n"
                "• <code>/test AUDUSD_otc 15m Fibonacci</code>\n\n"
                "⏱️ <b>Timeframes:</b> <code>1m</code> (60s), <code>5m</code> (300s), <code>15m</code> (900s), <code>1h</code> (3600s)\n\n"
                "🧠 <b>Estrategias clave:</b>\n"
                "• <code>WaveTrend</code> (WaveTrend + Keltner)\n"
                "• <code>Hybrid</code> (HYBRID Ultra-Sniper)\n"
                "• <code>Bollinger</code> (Bollinger Extreme + RSI)\n"
                "• <code>Engulfing</code> (Price Action Envolvente)\n"
                "• <code>TTM</code> (TTM Volatility Squeeze)\n"
                "• <code>Donchian</code> (Expert Vision Donchian)\n"
                "• <code>Divergence</code> (RSI Divergence + Pivot)\n"
                "• <code>SMC</code> (Smart Money Concepts)\n"
                "• <code>Fibonacci</code> (Fibonacci Master Sniper)\n"
                "• <code>Chartist</code> (Chartist Master)\n"
                "• <code>all</code> (Evaluar todas las estrategias activas)"
            )
            await self.send_message(help_msg, target_chat_id=chat_id, reply_markup=self.get_main_keyboard(user_id or chat_id))
            return

        raw_pair = parts[1].strip()
        pair = raw_pair
        if not pair.endswith('_otc') and not pair.startswith('#'):
            if len(pair) == 6:
                pair = f"{pair}_otc"
            elif pair.isalpha() and len(pair) <= 5:
                pair = f"#{pair}_otc"

        tf_str = parts[2].lower() if len(parts) > 2 else "5m"
        interval = 300
        if tf_str in ['1m', '60', '60s', 'm1']:
            interval = 60
            tf_display = "1m (60s)"
        elif tf_str in ['5m', '300', '300s', 'm5']:
            interval = 300
            tf_display = "5m (300s)"
        elif tf_str in ['15m', '900', '900s', 'm15']:
            interval = 900
            tf_display = "15m (900s)"
        elif tf_str in ['30m', '1800', '1800s', 'm30']:
            interval = 1800
            tf_display = "30m (1800s)"
        elif tf_str in ['1h', '3600', '3600s', 'h1']:
            interval = 3600
            tf_display = "1h (3600s)"
        else:
            tf_display = f"{tf_str} -> 5m (300s)"
            interval = 300

        strat_query = parts[3].lower() if len(parts) > 3 else "all"

        await self.send_message(
            f"⏳ <b>Iniciando simulación cuantitativa en {pair} ({tf_display})...</b>\n"
            f"Descargando velas recientes y ejecutando análisis...",
            target_chat_id=chat_id
        )

        try:
            df = pd.DataFrame()
            if self.bot_ref and hasattr(self.bot_ref, 'fetch_data'):
                try:
                    df = await self.bot_ref.fetch_data(pair, interval)
                except Exception as e:
                    print(f"[Telegram Simulation] fetch_data error: {e}")

            if df is None or df.empty or len(df) < 100:
                csv_path = Path(f"historical_data/{pair}_{interval}s.csv")
                if csv_path.exists():
                    try:
                        df = pd.read_csv(csv_path)
                        df.columns = [c.capitalize() for c in df.columns]
                        if 'Timestamp' in df.columns:
                            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', errors='coerce', utc=True)
                    except Exception as csve:
                        print(f"[Telegram Simulation] Fallback CSV error: {csve}")

            if df is None or df.empty or len(df) < 100:
                await self.send_message(
                    f"⚠️ <b>Datos insuficientes para {pair}:</b>\n"
                    f"El broker no devolvió suficientes velas recientes para {pair} en {tf_display}.\n"
                    f"Verifica si el activo está abierto o intenta con otro par (ej: <code>BTCUSD_otc</code>).",
                    target_chat_id=chat_id,
                    reply_markup=self.get_main_keyboard(user_id or chat_id)
                )
                return

            from analysis import MarketAnalyzer
            from patterns import PatternRecognizer
            analyzer = self.bot_ref.analyzer if (self.bot_ref and hasattr(self.bot_ref, 'analyzer')) else MarketAnalyzer()
            patterns = self.bot_ref.pattern_recognizer if (self.bot_ref and hasattr(self.bot_ref, 'pattern_recognizer')) else PatternRecognizer()

            df_calc = analyzer.compute_indicators(df)
            df_calc = patterns.find_candlestick_patterns(df_calc)
            df_calc = patterns.find_chart_patterns(df_calc)

            available_strats = []
            if self.bot_ref and hasattr(self.bot_ref, 'strategies') and self.bot_ref.strategies:
                available_strats = self.bot_ref.strategies
            else:
                from strategy_wavetrend_keltner import StrategyWaveTrendKeltner
                from strategy_hybrid_sniper import StrategyHybridSniper
                from strategy_bollinger_rsi import StrategyBollingerRSI
                from strategy_price_action_engulfing import StrategyPriceActionEngulfing
                from strategy_ttm_squeeze import StrategyTTMSqueeze
                from strategy_expert_vision import StrategyExpertVision
                from strategy_divergence_pivot import StrategyDivergencePivot
                from strategy_smart_money_smc import StrategySmartMoneySMC
                from strategy_fibonacci_master import StrategyFibonacciMasterSniper
                from strategy_chartist_patterns import StrategyChartistPatterns
                available_strats = [
                    StrategyWaveTrendKeltner(bypass_filter=True),
                    StrategyHybridSniper(bypass_filter=True),
                    StrategyBollingerRSI(bypass_filter=True),
                    StrategyPriceActionEngulfing(bypass_filter=True),
                    StrategyTTMSqueeze(bypass_filter=True),
                    StrategyExpertVision(bypass_filter=True),
                    StrategyDivergencePivot(bypass_filter=True),
                    StrategySmartMoneySMC(bypass_filter=True),
                    StrategyFibonacciMasterSniper(bypass_filter=True),
                    StrategyChartistPatterns(bypass_filter=True)
                ]

            target_strats = []
            if strat_query == 'all':
                target_strats = available_strats
            else:
                for s in available_strats:
                    s_name_lower = s.name.lower()
                    if strat_query in s_name_lower or any(word in s_name_lower for word in strat_query.split()):
                        target_strats.append(s)

                if not target_strats:
                    target_strats = available_strats

            sim_results = []
            start_idx = min(150, len(df_calc) // 2)

            for strat in target_strats:
                wins = 0
                losses = 0

                for i in range(start_idx, len(df_calc) - 1):
                    sub_df = df_calc.iloc[:i+1]
                    try:
                        action, reason, dur = strat.get_signal(sub_df)
                    except Exception:
                        continue

                    if action in ['BUY', 'SELL']:
                        curr_c = df_calc.iloc[i]
                        next_c = df_calc.iloc[i+1]
                        entry_p = curr_c['Close']
                        exit_p = next_c['Close']

                        is_win = False
                        if action == 'BUY' and exit_p > entry_p:
                            is_win = True
                        elif action == 'SELL' and exit_p < entry_p:
                            is_win = True

                        if is_win:
                            wins += 1
                        else:
                            losses += 1

                total_t = wins + losses
                wr = (wins / total_t * 100) if total_t > 0 else 0.0
                pnl = round(wins * 0.85 - losses * 1.0, 2)

                sim_results.append({
                    'name': strat.name,
                    'trades': total_t,
                    'wins': wins,
                    'losses': losses,
                    'winrate': wr,
                    'pnl': pnl
                })

            sim_results.sort(key=lambda x: (x['winrate'], x['trades']), reverse=True)

            total_candles = len(df_calc)
            candle_start = df_calc.iloc[0]['Timestamp'].strftime('%d/%m %H:%M') if ('Timestamp' in df_calc.columns and hasattr(df_calc.iloc[0]['Timestamp'], 'strftime')) else 'N/A'
            candle_end = df_calc.iloc[-1]['Timestamp'].strftime('%d/%m %H:%M') if ('Timestamp' in df_calc.columns and hasattr(df_calc.iloc[-1]['Timestamp'], 'strftime')) else 'N/A'

            msg_lines = [
                f"🧪 <b>RESULTADOS DE SIMULACIÓN (BACKTEST)</b>",
                f"📊 <b>Activo:</b> <code>{pair}</code> | ⏱️ <b>Timeframe:</b> {tf_display}",
                f"🕯️ <b>Velas evaluadas:</b> {total_candles} ({candle_start} a {candle_end})\n"
            ]

            if strat_query != 'all' and len(sim_results) == 1:
                r = sim_results[0]
                blocks_green = int(round(r['winrate'] / 10))
                blocks_red = 10 - blocks_green
                progress_bar = "🟩" * blocks_green + "🟥" * blocks_red

                verdict = "✅ <b>APTO PARA WHITELIST (WR ≥ 70%)</b>" if r['winrate'] >= 70.0 and r['trades'] >= 3 else "⚠️ <b>NO RECOMENDADO (WR &lt; 70% o pocas muestras)</b>"

                msg_lines.append(f"🧠 <b>Estrategia:</b> <code>{r['name']}</code>")
                msg_lines.append(f"• <b>Win Rate:</b> <b>{r['winrate']:.1f}%</b> ({r['wins']}W - {r['losses']}L)")
                msg_lines.append(f"  {progress_bar}")
                msg_lines.append(f"• <b>Operaciones totales:</b> {r['trades']}")
                msg_lines.append(f"• <b>PnL Estimado ($1 base / 85% pay):</b> <b>{r['pnl']:+.2f} USD</b>\n")
                msg_lines.append(f"🎯 <b>Veredicto:</b> {verdict}")
            else:
                msg_lines.append("🏆 <b>RANKING DE ESTRATEGIAS EN ESTE PAR:</b>\n")
                for idx, r in enumerate(sim_results[:8]):
                    status_icon = "🟢" if r['winrate'] >= 70.0 and r['trades'] >= 3 else ("🟡" if r['winrate'] >= 55.0 else "🔴")
                    strat_short = r['name'].split('(')[0].strip()
                    pnl_str = f"{r['pnl']:+.2f}$"
                    msg_lines.append(
                        f"{status_icon} <b>{idx+1}. {strat_short}</b>\n"
                        f"   • WR: <b>{r['winrate']:.1f}%</b> ({r['wins']}W - {r['losses']}L | {r['trades']} tr) | PnL: {pnl_str}"
                    )

                best = sim_results[0] if sim_results else None
                if best and best['trades'] >= 3 and best['winrate'] >= 70.0:
                    msg_lines.append(f"\n💡 <i>Mejor opción: <b>{best['name']}</b> con {best['winrate']:.1f}% WR.</i>")
                else:
                    msg_lines.append("\n💡 <i>Ninguna estrategia superó el 70% de WR de forma contundente en estas velas.</i>")

            full_report = "\n".join(msg_lines)
            await self.send_message(full_report, target_chat_id=chat_id, reply_markup=self.get_main_keyboard(user_id or chat_id))

        except Exception as sim_err:
            print(f"[Telegram Simulation] Error en simulación: {sim_err}")
            await self.send_message(
                f"❌ Error ejecutando simulación: {sim_err}",
                target_chat_id=chat_id,
                reply_markup=self.get_main_keyboard(user_id or chat_id)
            )

    async def _handle_help(self, chat_id, user_id=None):
        """Displays full list of available commands."""
        msg = (
            "🤖 <b>MENÚ DE COMANDOS DEL BOT & CONTROL DE PC</b>\n\n"
            "📊 <b>Diagnóstico de PC & Drenaje de Recursos:</b>\n"
            "• <code>/recursos</code>: Analiza tareas pesadas, qué drena CPU/RAM y si se pueden cerrar.\n"
            "• <code>/limpiar_ram</code>: Optimiza memoria RAM y vacía cachés del sistema.\n"
            "• <code>/kill_app &lt;app&gt;</code>: Cierra todas las pestañas de un navegador (ej: <code>/kill_app chrome</code> o <code>/kill_app msedge</code>).\n"
            "• <code>/kill &lt;pid&gt;</code>: Termina un proceso individual puntual por su PID.\n"
            "• <code>/pc</code>: Ver estado general de CPU, RAM, Disco C y Uptime.\n"
            "• <code>/restart_gui</code>: Destraba la pantalla reiniciando el explorador de Windows.\n"
            "• <code>/restart_bot</code>: Recargar y reiniciar el bot de trading.\n"
            "• <code>/reboot_pc confirm</code>: Forzar reinicio de Windows (Protegido por Biometría).\n"
            "• <code>/cmd &lt;comando&gt;</code>: Consola remota de Windows (Protegido por Biometría).\n\n"
            "🛡️ <b>Seguridad Biométrica Facial (1:1):</b>\n"
            "• <code>/auth</code>: Desbloquear comandos protegidos mediante el escaneo facial en tu celular (30 min).\n"
            "• <code>/lock</code>: Cerrar la sesión administrativa de inmediato.\n"
            "• <code>/reset_face</code>: Borrar plantilla maestra y recalibrar rostro.\n\n"
            "📈 <b>Trading y Operaciones:</b>\n"
            "• <code>/chart [par] [tf]</code>: Foto y gráfico técnico de PocketOption (Velas, Bollinger 2.5, EMAs, RSI y marcas de entrada).\n"
            "• <code>/balance</code>: Ver balances actuales (PocketOption y Alpaca).\n"
            "• <code>/info</code>: Resumen del día con gráfico combinado de P&L.\n"
            "• <code>/detail_info</code>: Desglose detallado completo de AMBOS brokers (pares, estrategias y trades).\n"
            "• <code>/detail_po</code>: Desglose detallado exclusivo de PocketOption.\n"
            "• <code>/detail_alpaca</code>: Desglose detallado exclusivo de Alpaca.\n"
            "• <code>/alpaca_info</code>: Estado de posiciones en vivo de Alpaca (gráfico de velas con TP/SL).\n"
            "• <code>/daily [YYYY-MM-DD]</code>: Reporte integral de cierre diario.\n"
            "• <code>/excel</code>: Descargar planilla Excel con historial completo.\n"
            "• <code>/test &lt;par&gt; &lt;tf&gt; [strat]</code>: Simulación cuantitativa bajo demanda (Backtest rápido).\n"
            "• <code>/pause</code> / <code>/resume</code>: Pausar o reanudar operativa automática.\n"
            "• <code>/set_amount 2.0</code>: Modificar monto por operación (Protegido por Biometría).\n"
            "• <code>/killapp</code>: Cierre nocturno seguro y liberación de recursos para apagar la PC.\n\n"
            "🧠 <b>Asistente de IA (Mentor Remoto):</b>\n"
            "• <code>/ai &lt;pregunta&gt;</code>: Consultar a la IA sobre trades, mercado o código.\n"
            "• <i>En chat privado puedes escribir directamente y la IA te responderá.</i>\n\n"
            "💡 <i>Tip: Toca los botones de la botonera inferior para acceder a las funciones con un toque.</i>"
        )
        await self.send_message(msg, target_chat_id=chat_id, reply_markup=self.get_main_keyboard(user_id or chat_id))
