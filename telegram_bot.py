import aiohttp
import asyncio
import io
import os
import glob
import json
import html
import subprocess
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

# Configurar matplotlib para backend no interactivo
plt.switch_backend('Agg')

class TelegramNotifier:
    def __init__(self, token, chat_id, owner_id=None, feedback_db=None, get_balance_callback=None, get_stats_callback=None, gemini_api_key=None, bot_ref=None):
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
                print(f"[Telegram] ⚠️ ADVERTENCIA: El token '{token}' no parece válido. Formato esperado: '123456:ABC-DEF...'")
                
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
        
        self.feedback_db = feedback_db
        self.get_balance_callback = get_balance_callback
        self.get_stats_callback = get_stats_callback
        self.gemini_api_key = gemini_api_key
        self.bot_ref = bot_ref
        self.is_paused = False
        self.last_update_id = 0
        self.listening = False
        self.logs_dir = Path("logs/trades")

        # Inicializar Antigravity AI Agent
        self.agent = None
        if AntigravityTelegramAgent and self.gemini_api_key:
            try:
                self.agent = AntigravityTelegramAgent(api_key=self.gemini_api_key, workspace_dir=os.getcwd(), bot_ref=self.bot_ref)
                print("[Telegram] [AI Agent] Antigravity AI Agent & Remote PC Control ACTIVO.")
            except Exception as e:
                print(f"[Telegram] Error inicializando Antigravity Agent: {e}")

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
            payload['reply_markup'] = kwargs['reply_markup']

        async def _do_send(current_payload):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage", 
                    json=current_payload,
                    timeout=aiohttp.ClientTimeout(total=8.0)
                ) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, data = await _do_send(payload)
            
            # --- MANEJO DE RATE LIMIT (429) ---
            if status == 429:
                retry_after = data.get('parameters', {}).get('retry_after', 30)
                print(f"[Telegram] ⏳ Rate limit alcanzado. Esperando {retry_after}s...")
                await asyncio.sleep(retry_after + 1)
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

    async def send_photo(self, photo_buffer, caption=None, target_chat_id=None):
        """Envía una foto a Telegram de forma asíncrona (admite chat único o lista de chats)."""
        if isinstance(target_chat_id, (list, tuple)):
            results = []
            for tid in target_chat_id:
                if hasattr(photo_buffer, 'seek'):
                    photo_buffer.seek(0)
                res = await self.send_photo(photo_buffer, caption, tid)
                results.append(res)
            return results[0] if results else None

        dest_chat_id = target_chat_id if target_chat_id else self.chat_id

        if not self.token or not dest_chat_id:
            return None

        if hasattr(photo_buffer, 'seek'):
            photo_buffer.seek(0)

        data = aiohttp.FormData()
        data.add_field('chat_id', str(dest_chat_id))
        data.add_field('photo', photo_buffer, filename='chart.png', content_type='image/png')
        if caption:
            data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')

        async def _do_send_photo(current_data):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendPhoto", 
                    data=current_data,
                    timeout=aiohttp.ClientTimeout(total=12.0)
                ) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, data = await _do_send_photo(data)
            
            # --- MANEJO DE RATE LIMIT (429) ---
            if status == 429:
                retry_after = data.get('parameters', {}).get('retry_after', 30)
                print(f"[Telegram] ⏳ Rate limit alcanzado en foto. Esperando {retry_after}s...")
                await asyncio.sleep(retry_after + 1)
                if hasattr(photo_buffer, 'seek'):
                    photo_buffer.seek(0)
                data_retry = aiohttp.FormData()
                data_retry.add_field('chat_id', str(dest_chat_id))
                data_retry.add_field('photo', photo_buffer, filename='chart.png', content_type='image/png')
                if caption:
                    data_retry.add_field('caption', caption)
                data_retry.add_field('parse_mode', 'HTML')
                status, text, data = await _do_send_photo(data_retry)

            if status == 200:
                return data.get('result', {}).get('message_id')
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

    async def notify_close(self, pair, profit, is_win, trade_id=None):
        icon = "✅" if is_win else "❌"
        result_text = "WON (WIN)" if is_win else "LOST (LOSS)"
        pair_emoji = self._get_pair_emoji(pair)
        
        msg = (
            f" <b>TRADE CLOSED</b>\n\n"
            f"<b>Pair:</b> {pair_emoji} {pair}\n"
            f"🏆 <b>Result:</b> {result_text} {icon}\n"
            f"🤑 <b>Profit:</b> ${profit:+.2f}\n\n"
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
    
    async def start_listening(self):
        """Inicia el listener de mensajes de Telegram en background."""
        if not self.token or not self.chat_id:
            print("[Telegram Listener] No configurado.")
            return
        
        self.listening = True
        print("[Telegram Listener] Iniciado. Esperando feedback...")
        
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
        url = f"{self.base_url}/getUpdates"
        params = {
            'offset': self.last_update_id + 1,
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
                            await self._process_update(update)
        except asyncio.TimeoutError:
            pass  # Normal, solo significa que no hubo mensajes
        except Exception as e:
            print(f"[Telegram Listener] Error polling: {e}")
    
    async def _process_update(self, update):
        """Procesa un update de Telegram."""
        message = update.get('message')
        if not message:
            return
        
        user_id = message.get('from', {}).get('id')
        user_name = message.get('from', {}).get('first_name', 'Unknown')
        raw_text = message.get('text', message.get('caption', '')).strip()
        text = raw_text.lower()
        chat_type = message.get('chat', {}).get('type', 'private')
        is_command = text.startswith('/')

        # --- SECURITY CHECK (OWNER ONLY) ---
        if self.owner_ids and user_id not in self.owner_ids:
            if is_command or chat_type == 'private':
                await self.send_message("❌ Access denied. This bot is private.", target_chat_id=user_id)
                await self.send_message(
                    message=f"🚨 <b>Unauthorized access attempt:</b>\nUser: {user_name}\nID: {user_id}\nText: {raw_text}",
                    target_chat_id=self.owner_ids
                )
                return
            else:
                return

        # --- THREAT DETECTOR ---
        threat_keywords = ["hacked", "hackeado", "token", "password", "leak"]
        if any(kw in text for kw in threat_keywords):
             await self.send_message(
                message=f"⚠️ <b>SECURITY ALERT</b>\nUser {user_id} ({user_name}) mentioned sensitive keywords: <i>{raw_text}</i>",
                target_chat_id=self.owner_ids
            )

        # Ensure message is from authorized chat or owner
        if str(message.get('chat', {}).get('id')) != str(self.chat_id) and user_id not in self.owner_ids:
            return

        chat_id = message.get('chat', {}).get('id')
        cmd_parts = text.split()
        full_cmd = cmd_parts[0] if cmd_parts else ""
        cmd = full_cmd.split('@')[0] if '@' in full_cmd else full_cmd
        
        if cmd.startswith('/'):
            print(f"[Telegram] Command received: {cmd} in chat {chat_id}")

        if cmd in ["/balance", "/bal"]:
            await self._handle_balance(chat_id)
            return
        elif cmd in ["/alpaca_info", "/alpaca", "/posicion", "/position", "/pos"]:
            await self._handle_alpaca_info(chat_id)
            return
        elif cmd in ["/info", "/stats", "/performance"]:
            await self._handle_info(chat_id)
            return
        elif cmd in ["/excel", "/export", "/report", "/reporte"]:
            await self._handle_excel(chat_id)
            return
        elif cmd in ["/daily_report", "/daily", "/reporte_diario"]:
            parts = raw_text.split()
            target_date_arg = parts[1] if len(parts) > 1 else None
            await self.send_daily_report(target_date=target_date_arg, target_chat_ids=[chat_id])
            return
        elif cmd in ["/info_details", "/range_stats", "/details"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_info_details(chat_id, start_dt, end_dt)
            return
        elif cmd in ["/range_detailed", "/history"]:
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_range_detailed(chat_id, start_dt, end_dt)
            return
        elif cmd in ["/pc", "/pc_status", "/system", "/sistema", "/status"]:
            await self._handle_pc_status(chat_id)
            return
        elif cmd in ["/reboot_pc", "/restart_pc", "/shutdown_pc", "/reiniciar_pc", "/apagar_pc"]:
            await self._handle_reboot_pc(chat_id, raw_text)
            return
        elif cmd in ["/restart_gui", "/unfreeze", "/reiniciar_gui", "/destrabar"]:
            await self._handle_restart_gui(chat_id)
            return
        elif cmd in ["/restart_bot", "/reload", "/reiniciar_bot", "/recargar"]:
            await self._handle_restart_bot(chat_id)
            return
        elif cmd in ["/pause", "/pausar", "/stop_trading"]:
            await self._handle_pause(chat_id)
            return
        elif cmd in ["/resume", "/reanudar", "/start_trading"]:
            await self._handle_resume(chat_id)
            return
        elif cmd in ["/set_amount", "/set_monto"]:
            await self._handle_set_monto(chat_id, raw_text)
            return
        elif cmd in ["/cmd", "/exec"]:
            await self._handle_cmd(chat_id, raw_text)
            return
        elif cmd in ["/ai", "/ia", "/ask", "/preguntar", "/antigravity"]:
            prompt = raw_text[len(full_cmd):].strip()
            if not prompt:
                await self.send_message("Please enter your instruction or question after the command.\nExample: <code>/ai Why did we lose the last USDCAD trade?</code>", target_chat_id=chat_id)
            else:
                await self._handle_ia(chat_id, prompt)
            return
        elif cmd in ["/help", "/ayuda", "/menu", "/start"]:
            await self._handle_help(chat_id)
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
        chart_buffer = self._generate_combined_chart(balance_po, balance_alpaca)
        
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

    def _generate_daily_chart(self, completed_df, date_str):
        """Generates a clean daily P&L curve for completed trades of the day."""
        try:
            if completed_df.empty or 'profit_loss' not in completed_df.columns:
                return None
            
            df = completed_df.sort_values('timestamp').copy()
            df['cum_pnl'] = df['profit_loss'].cumsum()

            # Obtener el balance actual para calcular el % de rentabilidad del dia
            balance = 0.0
            
            # 1. Intentar leer desde archivos de status compartidos de Alpaca o PocketOption (Método más confiable para scripts independientes)
            try:
                status_path = Path('pocketoption_status.json')
                if status_path.exists():
                    with open(status_path, 'r', encoding='utf-8') as sf:
                        balance = float(json.load(sf).get('balance', 0.0))
            except Exception:
                pass
                
            if balance <= 0.0:
                try:
                    status_path = Path('alpaca_status.json')
                    if status_path.exists():
                        with open(status_path, 'r', encoding='utf-8') as sf:
                            balance = float(json.load(sf).get('balance', 0.0))
                except Exception:
                    pass

            # 2. Callback del bot en ejecución como respaldo
            if balance <= 0.0 and self.get_balance_callback:
                try:
                    if asyncio.iscoroutinefunction(self.get_balance_callback):
                        if hasattr(self.bot_ref, 'api') and hasattr(self.bot_ref.api, 'client') and hasattr(self.bot_ref.api.client, 'balance_value'):
                            balance = float(self.bot_ref.api.client.balance_value())
                        else:
                            try:
                                loop = asyncio.get_event_loop()
                                balance = float(loop.run_until_complete(self.get_balance_callback()))
                            except Exception:
                                pass
                    else:
                        balance = float(self.get_balance_callback())
                except Exception:
                    pass

            # Insertar punto de partida en $0 al inicio del dia
            start_row = df.iloc[0].copy()
            start_row['timestamp'] = start_row['timestamp'] - pd.Timedelta(seconds=1)
            start_row['cum_pnl'] = 0.0
            df = pd.concat([pd.DataFrame([start_row]), df], ignore_index=True)

            plt.figure(figsize=(9, 4.5))
            plt.style.use('dark_background')

            final_pnl = df['cum_pnl'].iloc[-1]
            line_color = '#00ff88' if final_pnl >= 0 else '#ff4444'

            # Calcular el porcentaje de rentabilidad sobre el balance inicial (Balance actual - P&L es el balance inicial aproximado)
            initial_balance = balance - final_pnl
            pnl_percent = (final_pnl / initial_balance * 100) if initial_balance > 0 else 0.0

            plt.plot(df['timestamp'], df['cum_pnl'], color=line_color, linewidth=2.5, marker='o', label=f"Net P&L: ${final_pnl:+.2f}")
            plt.fill_between(df['timestamp'], df['cum_pnl'], alpha=0.15, color=line_color)
            plt.axhline(y=0, color='white', linestyle='--', alpha=0.3, linewidth=1)

            # Agregar etiqueta flotante al final de la linea
            last_time = df['timestamp'].iloc[-1]
            last_val = df['cum_pnl'].iloc[-1]
            plt.text(
                last_time, last_val, f" P&L: ${final_pnl:+.2f} ({pnl_percent:+.2f}%) ",
                fontsize=9, color='black', weight='bold',
                bbox=dict(facecolor=line_color, alpha=0.9, boxstyle='round,pad=0.3', edgecolor='none'),
                va='center', ha='left'
            )

            # Ampliar limite de X para dar espacio a la etiqueta de texto a la derecha
            ax = plt.gca()
            x_min, x_max = ax.get_xlim()
            x_range = x_max - x_min
            # Añadir 15% de margen a la derecha
            ax.set_xlim(x_min, x_max + x_range * 0.15)

            plt.title(f'Daily Cumulative P&L Curve — {date_str}', fontsize=12, color='white', pad=10)
            plt.xlabel('Time (UTC-3)', fontsize=10, color='white')
            plt.ylabel('P&L ($ USD)', fontsize=10, color='white')
            plt.legend(loc='upper left')
            plt.grid(True, alpha=0.15, linestyle='--')
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            plt.gcf().autofmt_xdate()
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=110)
            buf.seek(0)
            plt.close()
            return buf
        except Exception as e:
            print(f"[Telegram] Error generating daily chart: {e}")
            plt.close()
            return None

    async def send_daily_report(self, target_date=None, target_chat_ids=None):
        """
        Generates and dispatches the comprehensive End-of-Day Performance Report 
        to the group and all authorized members (or specified target_chat_ids).
        """
        if target_date is None:
            now_dt = datetime.now()
            if now_dt.hour < 6:
                target_date = (now_dt - timedelta(days=1)).date()
            else:
                target_date = now_dt.date()
        elif isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date.strip(), '%Y-%m-%d').date()
            except Exception:
                try:
                    target_date = datetime.strptime(target_date.strip(), '%d/%m/%Y').date()
                except Exception:
                    target_date = datetime.now().date()
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

        all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
        real_files = [f for f in all_files if "pocketoption_real" in Path(f).name or "_real_" in Path(f).name]
        target_files = real_files if real_files else [f for f in all_files if "alpaca" not in Path(f).name]

        dfs = []
        for f in target_files:
            try:
                df_temp = pd.read_csv(f)
                if not df_temp.empty:
                    dfs.append(df_temp)
            except Exception:
                continue

        if not dfs:
            msg = (
                f"📅 <b>END-OF-DAY PERFORMANCE REPORT</b>\n"
                f"🗓 <b>Date:</b> {date_str}\n\n"
                f"ℹ️ <i>No trade activity or logs recorded for this day.</i>"
            )
            for dest in destinations:
                await self.send_message(msg, target_chat_id=dest)
            return

        df_all = pd.concat(dfs, ignore_index=True)
        df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], errors='coerce')
        df_all = df_all.dropna(subset=['timestamp'])
        
        df_day = df_all[df_all['timestamp'].dt.date == target_date].sort_values('timestamp')

        if df_day.empty:
            msg = (
                f"📅 <b>END-OF-DAY PERFORMANCE REPORT</b>\n"
                f"🗓 <b>Date:</b> {date_str}\n\n"
                f"ℹ️ <i>No trade activity or logs recorded for this day.</i>"
            )
            for dest in destinations:
                await self.send_message(msg, target_chat_id=dest)
            return

        completed = df_day[df_day['result'].isin(['WIN', 'LOSS'])].copy()
        blocked_count = len(df_day[~df_day['result'].isin(['WIN', 'LOSS'])])
        total_completed = len(completed)
        wins = len(completed[completed['result'] == 'WIN'])
        losses = total_completed - wins
        winrate = (wins / total_completed * 100) if total_completed > 0 else 0.0
        pnl = completed['profit_loss'].sum() if 'profit_loss' in completed.columns else 0.0

        pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

        msg = (
            f"📅 <b>END-OF-DAY PERFORMANCE REPORT</b>\n"
            f"🗓 <b>Date:</b> {date_str}\n\n"
            f"🏆 <b>DAILY SUMMARY</b>\n"
            f"• <b>Total Trades:</b> {total_completed}\n"
            f"• <b>Won (WIN):</b> {wins} ({winrate:.1f}% WR) ✅\n"
            f"• <b>Lost (LOSS):</b> {losses} ❌\n"
            f"• <b>Net P&L:</b> {pnl_icon} ${pnl:+.2f} USD\n"
            f"• <b>Filtered/Protected Signals:</b> {blocked_count} 🛡️\n\n"
        )

        if not completed.empty:
            msg += "<b>📊 BREAKDOWN BY PAIR</b>\n"
            pair_stats = completed.groupby('pair').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count' if 'trade_id' in completed.columns else lambda x: len(x)
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for pair, row in pair_stats.iterrows():
                msg += f"• <b>{pair}</b>: {int(row['count'])} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"

            msg += "\n<b>🧠 BREAKDOWN BY STRATEGY</b>\n"
            completed['strat_clean'] = completed['pattern_detected'].apply(
                lambda x: str(x).split(':')[0] if ':' in str(x) else str(x)
            )
            strat_stats = completed.groupby('strat_clean').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count' if 'trade_id' in completed.columns else lambda x: len(x)
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for strat, row in strat_stats.iterrows():
                msg += f"• <b>{strat}</b>: {int(row['count'])} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"

            msg += "\n<b>📝 TRADES EXECUTED</b>\n"
            for _, row in completed.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌"
                pnl_str = f"{row['profit_loss']:+.2f}$"
                time_str = row['timestamp'].strftime('%H:%M')
                st = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                msg += f"{res_icon} {time_str} | <b>{row['pair']}</b> | {pnl_str} | {st}\n"

        chart_buffer = self._generate_daily_chart(completed, date_str) if not completed.empty else None

        print(f"[Telegram] Dispatching daily report for {date_str} to {len(destinations)} destinations: {destinations}")
        for dest in destinations:
            try:
                if chart_buffer and len(msg) <= 1000:
                    chart_buffer.seek(0)
                    await self.send_photo(chart_buffer, caption=msg, target_chat_id=dest)
                else:
                    if chart_buffer:
                        chart_buffer.seek(0)
                        await self.send_photo(chart_buffer, caption=f"📊 Daily P&L Curve ({date_str})", target_chat_id=dest)
                    await self.send_message(msg, target_chat_id=dest)
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
                    
            # Hoy (GMT-3)
            tz = timezone(timedelta(hours=-3))
            today = datetime.now(tz).date()
            df_today = completed[completed['timestamp'].dt.date == today]
            if len(df_today) > 0:
                stats['today_trades'] = len(df_today)
                wins_today = len(df_today[df_today['result'] == 'WIN'])
                stats['today_winrate'] = (wins_today / len(df_today)) * 100
                if 'profit_loss' in df_today.columns:
                    stats['today_pnl'] = df_today['profit_loss'].sum()
        except Exception as e:
            print(f"[Telegram] Error en _get_stats_for_broker ({broker_suffix}): {e}")
        return stats

    def _generate_combined_chart(self, balance_po=0.0, balance_alpaca=0.0):
        """Genera un gráfico comparativo de P&L acumulado de ambos brókers, con punto de partida en $0 y etiquetas flotantes al final de cada línea."""
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                return None
                
            has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files)
            dfs_po = []
            dfs_alpaca = []
            for f in all_files:
                f_name = Path(f).name
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty and not df_temp.isna().all().all():
                        if "alpaca" in f_name:
                            dfs_alpaca.append(df_temp)
                        elif has_real:
                            if "pocketoption_real" in f_name or "_real_" in f_name:
                                dfs_po.append(df_temp)
                        else:
                            dfs_po.append(df_temp)
                except:
                    continue
                    
            plt.figure(figsize=(10, 5))
            plt.style.use('dark_background')
            
            has_data = False
            po_legend_label = 'PocketOption REAL' if has_real else 'PocketOption (Binarias)'
            
            # Graficar PocketOption
            if dfs_po:
                df_po = pd.concat(dfs_po, ignore_index=True)
                df_po['timestamp'] = pd.to_datetime(df_po['timestamp'])
                df_po = df_po.sort_values('timestamp')
                df_po = df_po[df_po['result'].isin(['WIN', 'LOSS'])].copy()
                if not df_po.empty and 'profit_loss' in df_po.columns:
                    df_po['cumulative_pnl'] = df_po['profit_loss'].cumsum()
                    
                    # Forzar punto de partida desde $0
                    start_row_po = df_po.iloc[0].copy()
                    start_row_po['timestamp'] = start_row_po['timestamp'] - pd.Timedelta(seconds=1)
                    start_row_po['cumulative_pnl'] = 0.0
                    df_po = pd.concat([pd.DataFrame([start_row_po]), df_po], ignore_index=True)
                    
                    # Graficar
                    plt.plot(df_po['timestamp'], df_po['cumulative_pnl'], label=po_legend_label, color='#00ff88', linewidth=2)
                    plt.fill_between(df_po['timestamp'], df_po['cumulative_pnl'], alpha=0.1, color='#00ff88')
                    
                    # Agregar etiqueta flotante al final de la linea
                    last_time = df_po['timestamp'].iloc[-1]
                    last_val = df_po['cumulative_pnl'].iloc[-1]
                    plt.text(
                        last_time, last_val, f" PO Balance: ${balance_po:.2f} ",
                        fontsize=9, color='black', weight='bold',
                        bbox=dict(facecolor='#00ff88', alpha=0.9, boxstyle='round,pad=0.3', edgecolor='none'),
                        va='center', ha='left'
                    )
                    has_data = True
                    
            # Graficar Alpaca
            if dfs_alpaca:
                df_alpaca = pd.concat(dfs_alpaca, ignore_index=True)
                df_alpaca['timestamp'] = pd.to_datetime(df_alpaca['timestamp'])
                df_alpaca = df_alpaca.sort_values('timestamp')
                df_alpaca = df_alpaca[df_alpaca['result'].isin(['WIN', 'LOSS'])].copy()
                if not df_alpaca.empty and 'profit_loss' in df_alpaca.columns:
                    df_alpaca['cumulative_pnl'] = df_alpaca['profit_loss'].cumsum()
                    
                    # Forzar punto de partida desde $0
                    start_row_al = df_alpaca.iloc[0].copy()
                    start_row_al['timestamp'] = start_row_al['timestamp'] - pd.Timedelta(seconds=1)
                    start_row_al['cumulative_pnl'] = 0.0
                    df_alpaca = pd.concat([pd.DataFrame([start_row_al]), df_alpaca], ignore_index=True)
                    
                    # Graficar
                    plt.plot(df_alpaca['timestamp'], df_alpaca['cumulative_pnl'], label='Alpaca (Forex/Acciones)', color='#ff9900', linewidth=2)
                    plt.fill_between(df_alpaca['timestamp'], df_alpaca['cumulative_pnl'], alpha=0.1, color='#ff9900')
                    
                    # Agregar etiqueta flotante al final de la linea
                    last_time = df_alpaca['timestamp'].iloc[-1]
                    last_val = df_alpaca['cumulative_pnl'].iloc[-1]
                    plt.text(
                        last_time, last_val, f" Alpaca Balance: ${balance_alpaca:.2f} ",
                        fontsize=9, color='black', weight='bold',
                        bbox=dict(facecolor='#ff9900', alpha=0.9, boxstyle='round,pad=0.3', edgecolor='none'),
                        va='center', ha='left'
                    )
                    has_data = True
                    
            if not has_data:
                plt.close()
                return None
                
            plt.axhline(y=0, color='white', linestyle='--', alpha=0.3, linewidth=1)
            plt.title('Curva de Ganancias Acumuladas (P&L)', fontsize=12, color='white')
            plt.xlabel('Fecha', fontsize=10, color='white')
            plt.ylabel('P&L Neto ($)', fontsize=10, color='white')
            plt.legend(loc='upper left')
            plt.grid(True, alpha=0.1, linestyle='--')
            
            # Ampliar limite de X para dar espacio a las etiquetas de texto a la derecha
            ax = plt.gca()
            x_min, x_max = ax.get_xlim()
            x_range = x_max - x_min
            # Añadir 12% de margen a la derecha
            ax.set_xlim(x_min, x_max + x_range * 0.12)
            
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            plt.gcf().autofmt_xdate()
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plt.close()
            return buf
        except Exception as e:
            print(f"[Telegram] Error generando gráfico combinado: {e}")
            return None

    async def _handle_info_details(self, chat_id, start_dt=None, end_dt=None):
        """Handle /info_details command (breakdown by pair and strategy)."""
        if start_dt and end_dt:
            await self.send_message(f"⏳ Generating detailed breakdown for range:\n{start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}", target_chat_id=chat_id)
        else:
            await self.send_message("⏳ Generating today's detailed breakdown...", target_chat_id=chat_id)
        
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                await self.send_message("❌ Not enough data to generate breakdown.", target_chat_id=chat_id)
                return
            
            has_real = any("pocketoption_real" in Path(f).name or "_real_" in Path(f).name for f in all_files)
            dfs = []
            for f in all_files:
                f_name = Path(f).name
                if has_real:
                    if "pocketoption_real" not in f_name and "_real_" not in f_name:
                        continue
                else:
                    if "alpaca" in f_name:
                        continue
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        dfs.append(df_temp)
                except: continue
            
            if not dfs:
                await self.send_message("❌ Not enough data available.", target_chat_id=chat_id)
                return
                
            df_all = pd.concat(dfs, ignore_index=True)
            df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], errors='coerce')
            df_all = df_all.dropna(subset=['timestamp'])
            
            if df_all.empty:
                await self.send_message("❌ No valid trade records in logs.", target_chat_id=chat_id)
                return
                
            # Activity date range
            first_day = df_all['timestamp'].min().strftime('%d/%m/%Y')
            last_day = df_all['timestamp'].max().strftime('%d/%m/%Y')
            
            if start_dt and end_dt:
                df = df_all[(df_all['timestamp'] >= start_dt) & (df_all['timestamp'] <= end_dt) & (df_all['result'].isin(['WIN', 'LOSS']))].copy()
                msg = f"📊 <b>CUSTOM RANGE REPORT</b>\n"
                msg += f"🕒 <b>Range:</b> {start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}\n"
            else:
                tz = timezone(timedelta(hours=-3))
                today = datetime.now(tz).date()
                df = df_all[(df_all['timestamp'].dt.date == today) & (df_all['result'].isin(['WIN', 'LOSS']))].copy()
                msg = f"📅 <b>TODAY'S REPORT ({today.strftime('%d/%m/%Y')})</b>\n"
                if not df.empty:
                    start_time = df['timestamp'].min().strftime('%H:%M')
                    end_time = df['timestamp'].max().strftime('%H:%M')
                    msg += f"🕒 <b>Time Range:</b> {start_time} - {end_time}\n"
            
            msg += f"🗓 <b>Total Activity:</b> {first_day} to {last_day}\n\n"
            
            if df.empty:
                msg += "❌ No completed trades recorded in this period."
                await self.send_message(msg, target_chat_id=chat_id)
                return

            # 1. Breakdown by Pair
            msg += "<b>📊 BREAKDOWN BY PAIR</b>\n"
            pair_stats = df.groupby('pair').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for pair, row in pair_stats.iterrows():
                msg += f"• <b>{pair}</b>: {row['count']} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"
            
            # 2. Breakdown by Strategy
            msg += "\n<b>🧠 BREAKDOWN BY STRATEGY</b>\n"
            df['strategy_clean'] = df['pattern_detected'].apply(lambda x: str(x).split(':')[0] if ':' in str(x) else str(x))
            
            strat_stats = df.groupby('strategy_clean').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for strat, row in strat_stats.iterrows():
                msg += f"• <b>{strat}</b>: {row['count']} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"
            
            # 3. Trade Details
            msg += "\n<b>📝 TRADE DETAILS</b>\n"
            df_sorted = df.sort_values('timestamp', ascending=False)
            for _, row in df_sorted.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌" if row['result'] == 'LOSS' else "⏳"
                pnl_str = f"{row['profit_loss']:+.2f}$" if row['result'] in ['WIN', 'LOSS'] else "---"
                local_ts = row['timestamp']
                if hasattr(local_ts, 'tzinfo') and local_ts.tzinfo is not None:
                    local_ts = local_ts.astimezone(timezone(timedelta(hours=-3)))
                else:
                    # Asumir que venía en UTC si es naive
                    local_ts = local_ts.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-3)))
                
                if start_dt and end_dt and (end_dt - start_dt).days >= 1:
                    time_str = local_ts.strftime('%d/%m %H:%M')
                else:
                    time_str = local_ts.strftime('%H:%M')
                    
                strat = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                msg += f"{res_icon} <b>{row['pair']}</b> | {pnl_str} | {strat} | {time_str}\n"

            await self.send_message(msg, target_chat_id=chat_id)
            
        except Exception as e:
            print(f"[Telegram] Error in info_details: {e}")
            await self.send_message(f"❌ Error generating details: {e}", target_chat_id=chat_id)

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
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if start_dt and end_dt:
                trades_to_show = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)].sort_values('timestamp', ascending=False)
                msg = f"<b>📝 TRADES IN RANGE</b>\n"
                msg += f"🕒 {start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}\n\n"
            else:
                trades_to_show = df.sort_values('timestamp', ascending=False).head(10)
                msg = "<b>📝 LAST 10 TRADES</b>\n\n"
            
            if trades_to_show.empty:
                await self.send_message("❌ No trades found in this range.", target_chat_id=chat_id)
                return

            for _, row in trades_to_show.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌" if row['result'] == 'LOSS' else "⏳"
                pnl_str = f"{row['profit_loss']:+.2f}$" if row['result'] in ['WIN', 'LOSS'] else "---"
                local_ts = row['timestamp']
                if hasattr(local_ts, 'tzinfo') and local_ts.tzinfo is not None:
                    local_ts = local_ts.astimezone(timezone(timedelta(hours=-3)))
                else:
                    local_ts = local_ts.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-3)))
                
                if start_dt and end_dt and (end_dt - start_dt).days >= 1:
                    time_str = local_ts.strftime('%d/%m %H:%M')
                else:
                    time_str = local_ts.strftime('%H:%M')
                
                strat = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                msg += f"{res_icon} <b>{row['pair']}</b> | {pnl_str} | {strat} | {time_str}\n"
            
            await self.send_message(msg, target_chat_id=chat_id)
            
        except Exception as e:
            print(f"[Telegram] Error in range_detailed: {e}")
            await self.send_message(f"❌ Error: {e}", target_chat_id=chat_id)

    async def _handle_pc_status(self, chat_id):
        """Displays system metrics: CPU, RAM, Disk, Uptime."""
        try:
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            num_pids = len(psutil.pids())

            msg = (
                f"🖥️ <b>SYSTEM / PC STATUS</b>\n\n"
                f"⚡ <b>CPU Usage:</b> {cpu}%\n"
                f"🧠 <b>RAM Memory:</b> {ram.percent}% ({ram.used / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB)\n"
                f"💾 <b>Drive C:</b> {disk.percent}% ({disk.free / (1024**3):.1f} GB free of {disk.total / (1024**3):.1f} GB)\n"
                f"⏱️ <b>System Uptime:</b> {uptime_str}\n"
                f"⚙️ <b>Active Processes:</b> {num_pids}\n\n"
                f"<i>Generated (UTC-3): {self._get_time()}</i>"
            )
            await self.send_message(msg, target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error retrieving PC status: {e}", target_chat_id=chat_id)

    async def _handle_reboot_pc(self, chat_id, text):
        """Forces a PC reboot with safety confirmation."""
        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in ['confirm', 'confirmar', 'yes', 'si', 'force', 'ok', 'forzar']:
            await self.send_message("🔄 <b>FORCED REBOOT IN PROGRESS</b>\n\nClosing applications and restarting Windows in 5 seconds...", target_chat_id=chat_id)
            subprocess.Popen("shutdown /r /f /t 5", shell=True)
        else:
            msg = (
                "⚠️ <b>Are you sure you want to force a PC reboot?</b>\n\n"
                "This will close all open applications in Windows and reboot immediately.\n\n"
                "👉 To confirm, reply:\n"
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
        """Hot-reloads the trading bot by sending restart.signal."""
        await self.send_message("🔄 <b>Hot-reloading trading bot...</b>", target_chat_id=chat_id)
        try:
            Path("restart.signal").write_text("restart", encoding="utf-8")
            await self.send_message("✅ Restart signal dispatched. The supervisor will reload the bot shortly.", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error sending restart signal: {e}", target_chat_id=chat_id)

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

    async def _handle_set_monto(self, chat_id, text):
        """Updates the base trade amount in config.json."""
        parts = text.split()
        if len(parts) < 2:
            await self.send_message("Usage: <code>/set_amount 2.0</code>", target_chat_id=chat_id)
            return
        try:
            new_amount = float(parts[1])
            if new_amount <= 0:
                await self.send_message("❌ Amount must be greater than 0.", target_chat_id=chat_id)
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
                await self.send_message(f"💵 <b>Base amount updated to ${new_amount:.2f} USD</b> in config.json.", target_chat_id=chat_id)
            else:
                await self.send_message("❌ config.json not found.", target_chat_id=chat_id)
        except ValueError:
            await self.send_message("❌ Invalid amount. Example: <code>/set_amount 2.5</code>", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error updating amount: {e}", target_chat_id=chat_id)

    async def _handle_cmd(self, chat_id, text):
        """Executes a terminal shell command on the PC (Owner Only)."""
        raw_cmd = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
        if not raw_cmd:
            await self.send_message("Usage: <code>/cmd dir</code> or <code>/cmd tasklist</code>", target_chat_id=chat_id)
            return
        await self.send_message(f"⚙️ Executing: <code>{raw_cmd}</code>...", target_chat_id=chat_id)
        try:
            res = subprocess.run(raw_cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = res.stdout.strip() or res.stderr.strip() or f"Finished with exit code {res.returncode}"
            if len(out) > 3800:
                out = out[:3800] + "\n...(output truncated)"
            await self.send_message(f"<pre>{html.escape(out)}</pre>", target_chat_id=chat_id)
        except subprocess.TimeoutExpired:
            await self.send_message("⚠️ Command execution timed out after 30 seconds.", target_chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"❌ Error executing command: {e}", target_chat_id=chat_id)

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

    async def _handle_help(self, chat_id):
        """Displays full list of available commands."""
        msg = (
            "🤖 <b>AVAILABLE TELEGRAM COMMANDS</b>\n\n"
            "🧠 <b>AI Assistant (Antigravity Remote):</b>\n"
            "• <code>/ai &lt;instruction&gt;</code> or <code>/ia &lt;instruction&gt;</code>: Ask the AI to edit code, adjust settings, analyze trades, or run diagnostics.\n"
            "• <i>You can also directly send any message in this private chat and the AI will respond.</i>\n\n"
            "📊 <b>Trading & Information:</b>\n"
            "• <code>/alpaca_info</code>: Live Alpaca position summary (Candlestick chart, TP, SL & PnL).\n"
            "• <code>/balance</code>: Check account balances (PocketOption / Alpaca).\n"
            "• <code>/info</code>: Today's stats + performance chart.\n"
            "• <code>/daily [YYYY-MM-DD]</code>: Full End-of-Day performance report.\n"
            "• <code>/info_details</code>: Detailed breakdown by pair and strategy.\n"
            "• <code>/excel</code>: Download Excel report with full trade history.\n"
            "• <code>/pause</code> / <code>/resume</code>: Pause or resume trade placement.\n"
            "• <code>/set_amount 2</code>: Update base trade amount in config.json.\n\n"
            "🖥️ <b>Remote PC & System Control:</b>\n"
            "• <code>/pc</code>: View CPU, RAM, Disk usage and Uptime.\n"
            "• <code>/restart_gui</code>: Unfreeze Windows GUI by restarting Explorer.exe.\n"
            "• <code>/reboot_pc</code>: Force reboot Windows OS.\n"
            "• <code>/restart_bot</code>: Hot-reload the trading bot.\n"
            "• <code>/cmd &lt;command&gt;</code>: Run terminal shell command on your PC."
        )
        await self.send_message(msg, target_chat_id=chat_id)
