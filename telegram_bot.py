import aiohttp
import asyncio
from pathlib import Path

class TelegramNotifier:
    def __init__(self, token, chat_id, feedback_db=None):
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
        self.feedback_db = feedback_db
        self.last_update_id = 0
        self.listening = False

    async def send_message(self, message, reply_to_message_id=None):
        """Envía un mensaje a Telegram de forma asíncrona."""
        if not self.token or not self.chat_id:
            # print("[Telegram] No configurado (Falta Token o Chat ID).")
            return None

        # Preparar payload base
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id

        async def _do_send(current_payload):
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/sendMessage", json=current_payload) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, data = await _do_send(payload)
            
            if status == 200:
                return data.get('result', {}).get('message_id')
            
            # Manejo de Errores
            print(f"[Telegram] Error enviando mensaje (HTML): {status} - {text}")
            
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

    async def notify_open(self, pair, action, strategy, timeframe, amount):
        icon = "🟢" if action == 'BUY' else "🔴"
        direction = "ALZA" if action == 'BUY' else "BAJA"
        pair_emoji = self._get_pair_emoji(pair)
        
        msg = (
            f"{icon} <b>NUEVA OPERACIÓN</b> {icon}\n\n"
            f"<b>Par:</b>{pair_emoji} {pair}\n"
            f"📈 <b>Acción:</b> {direction}\n"
            f"🧠 <b>Estrategia:</b> {strategy}\n"
            f"⏱ <b>Timeframe:</b> {timeframe}\n"
            f"💵 <b>Monto:</b> ${amount}\n"
            f"🕓 <b>Fecha y hora:</b> {self._get_time()}"
        )
        await self.send_message(msg)

    async def notify_close(self, pair, profit, is_win):
        icon = "✅" if is_win else "❌"
        result_text = "GANADA" if is_win else "PERDIDA"
        pair_emoji = self._get_pair_emoji(pair)
        
        msg = (
            f" <b>OPERACIÓN CERRADA</b>\n\n"
            f"<b>Par:</b>{pair_emoji} {pair}\n"
            f"🏆 <b>Resultado:</b> {result_text} {icon}\n"
            f"🤑 <b>Profit:</b> ${profit:.2f}\n\n"
            f"🕓 <b>Fecha y hora:</b> {self._get_time()}"
        )
        message_id = await self.send_message(msg)
        return message_id
    
    async def request_feedback(self):
        """Solicita feedback al usuario."""
        msg = (
            "📝 <b>¿Cómo estuvo el análisis?</b>\n\n"
            "Responde a este mensaje con:\n"
            "• Tu análisis (¿estuvo bien/mal? ¿qué corregir?)\n"
            "• Opcionalmente, envía una imagen del gráfico"
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
        
        # Verificar que el mensaje es del chat correcto
        if str(message.get('chat', {}).get('id')) != str(self.chat_id):
            return
        
        # Verificar si es una respuesta a un mensaje del bot
        reply_to = message.get('reply_to_message')
        if not reply_to:
            return  # Solo procesamos respuestas
        
        replied_message_id = reply_to.get('message_id')
        
        # Extraer texto del feedback
        feedback_text = message.get('text', message.get('caption', ''))
        
        # Verificar si hay imagen
        image_path = None
        if 'photo' in message:
            image_path = await self._download_image(message['photo'])
        
        # Guardar feedback en la base de datos
        if self.feedback_db and (feedback_text or image_path):
            success = self.feedback_db.add_feedback(replied_message_id, feedback_text, image_path)
            if success:
                print(f"[Feedback] ✅ Guardado para mensaje {replied_message_id}")
                await self.send_message("✅ Feedback guardado. ¡Gracias!")
            else:
                print(f"[Feedback] ⚠️ No se encontró operación para mensaje {replied_message_id}")
    
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
