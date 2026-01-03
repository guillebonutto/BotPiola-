import aiohttp
import asyncio
import io
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Configurar matplotlib para backend no interactivo
plt.switch_backend('Agg')

class TelegramNotifier:
    def __init__(self, token, chat_id, owner_id=None, feedback_db=None, get_balance_callback=None, get_stats_callback=None):
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
        self.last_update_id = 0
        self.listening = False
        self.logs_dir = Path("logs/trades")

    async def send_message(self, message, reply_to_message_id=None, target_chat_id=None):
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

        async def _do_send(current_payload):
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/sendMessage", json=current_payload) as response:
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
        """Envía una foto a Telegram de forma asíncrona."""
        dest_chat_id = target_chat_id if target_chat_id else self.chat_id

        if not self.token or not dest_chat_id:
            return None

        data = aiohttp.FormData()
        data.add_field('chat_id', str(dest_chat_id))
        data.add_field('photo', photo_buffer, filename='chart.png', content_type='image/png')
        if caption:
            data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')

        async def _do_send_photo(current_data):
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/sendPhoto", data=current_data) as response:
                    return response.status, await response.text(), await response.json() if response.status == 200 else {}

        try:
            status, text, data = await _do_send_photo(data)
            
            # --- MANEJO DE RATE LIMIT (429) ---
            if status == 429:
                retry_after = data.get('parameters', {}).get('retry_after', 30)
                print(f"[Telegram] ⏳ Rate limit alcanzado en foto. Esperando {retry_after}s...")
                await asyncio.sleep(retry_after + 1)
                # Re-crear FormData porque aiohttp no permite reusarlo si ya se leyó
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
        text = message.get('text', '').lower()
        chat_type = message.get('chat', {}).get('type', 'private')
        is_command = text.startswith('/')

        # --- VERIFICACIÓN DE SEGURIDAD (OWNER ONLY) ---
        # Solo verificamos si es un comando o si es un chat privado
        # Esto evita responder "Acceso Denegado" a cada mensaje de un grupo
        if self.owner_ids and user_id not in self.owner_ids:
            if is_command or chat_type == 'private':
                # Si alguien más intenta usarlo, el bot le responde y te avisa a ti
                await self.send_message("❌ Acceso denegado. Este bot es privado.")
                await self.send_message(
                    message=f"🚨 <b>Intento de acceso no autorizado:</b>\nUser: {user_name}\nID: {user_id}\nTexto: {text}",
                    target_chat_id=self.owner_ids
                )
                return
            else:
                # En grupos, ignoramos silenciosamente si no es el owner y no es comando
                return

        # --- DETECTOR DE AMENAZAS ---
        threat_keywords = ["hacked", "hackeado", "token"]
        if any(kw in text for kw in threat_keywords):
             await self.send_message(
                message=f"⚠️ <b>ALERTA DE SEGURIDAD</b>\nEl usuario {user_id} ({user_name}) mencionó términos sensibles: <i>{text}</i>",
                target_chat_id=self.owner_ids
            )

        # Verificar que el mensaje es del chat correcto (o es uno de los owners)
        if str(message.get('chat', {}).get('id')) != str(self.chat_id) and user_id not in self.owner_ids:
            return

        # --- COMANDOS ---
        chat_id = message.get('chat', {}).get('id')
        cmd_parts = text.split()
        full_cmd = cmd_parts[0] if cmd_parts else ""
        # Limpiar nombre del bot si existe (ej: /info@botname -> /info)
        cmd = full_cmd.split('@')[0] if '@' in full_cmd else full_cmd
        
        if cmd.startswith('/'):
            print(f"[Telegram] Comando recibido: {cmd} en chat {chat_id}")

        if cmd == "/balance":
            await self._handle_balance(chat_id)
            return
        elif cmd == "/info":
            await self._handle_info(chat_id)
            return
        elif cmd == "/info_details" or cmd == "/range_stats":
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_info_details(chat_id, start_dt, end_dt)
            return
        elif cmd == "/range_detailed":
            start_dt, end_dt = self._parse_date_range(text)
            await self._handle_range_detailed(chat_id, start_dt, end_dt)
            return

        # Verificar si es una respuesta a un mensaje del bot
        reply_to = message.get('reply_to_message')
        if not reply_to:
            # Si es uno de los owners y no es reply, podemos darle un saludo o ayuda
            if user_id in self.owner_ids and text == "/start":
                await self.send_message("Hola Jefe. Sistema de defensa activo.")
            return  
        
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

    async def _handle_balance(self, chat_id):
        """Manejar comando /balance."""
        balance = "Desconocido"
        if self.get_balance_callback:
            try:
                # El callback puede ser asíncrono o síncrono
                if asyncio.iscoroutinefunction(self.get_balance_callback):
                    balance = await self.get_balance_callback()
                else:
                    balance = self.get_balance_callback()
            except Exception as e:
                balance = f"Error: {e}"
        
        if isinstance(balance, (int, float)):
            msg = f"💰 <b>Balance Actual:</b> ${balance:.2f}"
        else:
            msg = f"💰 <b>Balance Actual:</b> {balance}"
        
        await self.send_message(msg, target_chat_id=chat_id)

    async def _handle_info(self, chat_id):
        """Manejar comando /info (estadísticas + gráfico)."""
        await self.send_message("⏳ Generando reporte histórico...", target_chat_id=chat_id)
        
        # 1. Obtener balance actual primero (asíncrono)
        balance = 0.0
        if self.get_balance_callback:
            try:
                if asyncio.iscoroutinefunction(self.get_balance_callback):
                    balance = await self.get_balance_callback()
                else:
                    balance = self.get_balance_callback()
            except Exception as e:
                print(f"[Telegram] Error obteniendo balance para reporte: {e}")

        # 2. Obtener estadísticas pasándole el balance
        stats = self._get_stats(current_balance=balance)
        
        # 3. Generar gráfico
        chart_buffer = self._generate_chart()
        
        # 4. Enviar mensaje con estadísticas
        start_date = stats.get('start_date', 'N/A')
        
        msg = (
            f"<b>📊 REPORTE HISTÓRICO</b>\n"
            f"<i>Desde: {start_date}</i>\n\n"
            f"<b>💰 Balance Actual:</b> ${stats['balance']:.2f}\n\n"
            f"<b>🏆 GLOBAL (Todo el historial)</b>\n"
            f"• Trades: {stats['total_trades']}\n"
            f"• Winrate: {stats['total_winrate']:.1f}%\n"
            f"• P&L: {stats['total_pnl']:+.2f}\n\n"
            f"<b>📅 HOY</b>\n"
            f"• Trades: {stats['today_trades']}\n"
            f"• Winrate: {stats['today_winrate']:.1f}%\n"
            f"• P&L: {stats['today_pnl']:+.2f}\n\n"
            f"<i>Generado (UTC-3): {self._get_time()}</i>"
        )
        
        if chart_buffer:
            await self.send_photo(chart_buffer, caption=msg, target_chat_id=chat_id)
        else:
            await self.send_message(msg, target_chat_id=chat_id)

    def _get_stats(self, current_balance=0.0):
        """Calcular estadísticas desde los logs."""
        stats = {
            'balance': current_balance,
            'today_trades': 0,
            'today_winrate': 0.0,
            'today_pnl': 0.0,
            'total_trades': 0,
            'total_winrate': 0.0,
            'total_pnl': 0.0,
            'start_date': 'N/A'
        }
        
        # Cargar trades
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                return stats
            
            dfs = []
            for f in all_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty and not df_temp.isna().all().all():
                        dfs.append(df_temp)
                except Exception:
                    continue
            
            if not dfs:
                return stats
                
            df = pd.concat(dfs, ignore_index=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filtrar completados
            completed = df[df['result'].isin(['WIN', 'LOSS'])]
            
            if len(completed) > 0:
                stats['start_date'] = completed['timestamp'].min().strftime('%d/%m/%Y')
                stats['total_trades'] = len(completed)
                wins = len(completed[completed['result'] == 'WIN'])
                stats['total_winrate'] = (wins / len(completed)) * 100
                if 'profit_loss' in completed.columns:
                    stats['total_pnl'] = completed['profit_loss'].sum()
            
            # Trades de hoy
            today = datetime.now().date()
            df_today = completed[completed['timestamp'].dt.date == today]
            
            if len(df_today) > 0:
                stats['today_trades'] = len(df_today)
                wins_today = len(df_today[df_today['result'] == 'WIN'])
                stats['today_winrate'] = (wins_today / len(df_today)) * 100
                if 'profit_loss' in df_today.columns:
                    stats['today_pnl'] = df_today['profit_loss'].sum()
                    
        except Exception as e:
            print(f"[Telegram] Error calculando stats: {e}")
        
        return stats

    def _generate_chart(self):
        """Generar gráfico de balance/P&L acumulado."""
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                return None
            
            dfs = []
            for f in all_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty and not df_temp.isna().all().all():
                        dfs.append(df_temp)
                except Exception:
                    continue
            
            if not dfs:
                return None
                
            df = pd.concat(dfs, ignore_index=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Filtrar completados con P&L
            if 'profit_loss' not in df.columns:
                return None
            
            df = df[df['result'].isin(['WIN', 'LOSS'])].copy()
            
            if len(df) == 0:
                return None
            
            # Calcular P&L acumulado
            df['cumulative_pnl'] = df['profit_loss'].cumsum()
            
            # Crear gráfico
            plt.figure(figsize=(10, 5))
            plt.style.use('dark_background') # Estilo premium
            
            # Graficar línea principal
            plt.plot(df['timestamp'], df['cumulative_pnl'], label='P&L Acumulado', color='#00ff88', linewidth=2)
            
            # Relleno suave
            plt.fill_between(df['timestamp'], df['cumulative_pnl'], alpha=0.2, color='#00ff88')
            
            # Línea de cero (breakeven)
            plt.axhline(y=0, color='white', linestyle='--', alpha=0.3, linewidth=1)
            
            # Títulos y etiquetas
            plt.title(f'Crecimiento de la Cuenta (Total: ${df["cumulative_pnl"].iloc[-1]:.2f})', fontsize=12, color='white')
            plt.xlabel('Fecha', fontsize=10, color='white')
            plt.ylabel('Ganancia Neta ($)', fontsize=10, color='white')
            
            # Grid suave
            plt.grid(True, alpha=0.1, linestyle='--')
            
            # Formato de fechas
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            plt.gcf().autofmt_xdate()
            
            plt.tight_layout()
            
            # Guardar en buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plt.close()
            
            return buf
        except Exception as e:
            print(f"[Telegram] Error generando gráfico: {e}")
            return None

    async def _handle_info_details(self, chat_id, start_dt=None, end_dt=None):
        """Manejar comando /info_details (desglose por par y estrategia)."""
        if start_dt and end_dt:
            await self.send_message(f"⏳ Generando desglose detallado para el rango:\n{start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}", target_chat_id=chat_id)
        else:
            await self.send_message("⏳ Generando desglose detallado de hoy...", target_chat_id=chat_id)
        
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                await self.send_message("❌ No hay datos suficientes para generar el desglose.", target_chat_id=chat_id)
                return
            
            dfs = []
            for f in all_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        dfs.append(df_temp)
                except: continue
            
            if not dfs:
                await self.send_message("❌ No hay datos suficientes.", target_chat_id=chat_id)
                return
                
            df_all = pd.concat(dfs, ignore_index=True)
            df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], errors='coerce')
            df_all = df_all.dropna(subset=['timestamp'])
            
            if df_all.empty:
                await self.send_message("❌ No hay datos válidos en los logs.", target_chat_id=chat_id)
                return
                
            # Rango de días total (Actividad)
            first_day = df_all['timestamp'].min().strftime('%d/%m/%Y')
            last_day = df_all['timestamp'].max().strftime('%d/%m/%Y')
            
            if start_dt and end_dt:
                # Filtrar por rango personalizado
                df = df_all[(df_all['timestamp'] >= start_dt) & (df_all['timestamp'] <= end_dt) & (df_all['result'].isin(['WIN', 'LOSS']))].copy()
                msg = f"📊 <b>REPORTE PERSONALIZADO</b>\n"
                msg += f"🕒 <b>Rango:</b> {start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}\n"
            else:
                # Filtrar por HOY
                today = datetime.now().date()
                df = df_all[(df_all['timestamp'].dt.date == today) & (df_all['result'].isin(['WIN', 'LOSS']))].copy()
                msg = f"📅 <b>REPORTE DE HOY ({today.strftime('%d/%m/%Y')})</b>\n"
                if not df.empty:
                    start_time = df['timestamp'].min().strftime('%H:%M')
                    end_time = df['timestamp'].max().strftime('%H:%M')
                    msg += f"🕒 <b>Rango horario:</b> {start_time} - {end_time}\n"
            
            msg += f"🗓 <b>Actividad total:</b> {first_day} al {last_day}\n\n"
            
            if df.empty:
                msg += "❌ No se registraron operaciones completadas en este periodo."
                await self.send_message(msg, target_chat_id=chat_id)
                return

            # 1. Desglose por Par
            msg += "<b>📊 DESGLOSE POR PAR</b>\n"
            pair_stats = df.groupby('pair').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for pair, row in pair_stats.iterrows():
                msg += f"• <b>{pair}</b>: {row['count']} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"
            
            # 2. Desglose por Estrategia
            msg += "\n<b>🧠 DESGLOSE POR ESTRATEGIA</b>\n"
            # Limpiar nombres de patrones
            df['strategy_clean'] = df['pattern_detected'].apply(lambda x: str(x).split(':')[0] if ':' in str(x) else str(x))
            
            strat_stats = df.groupby('strategy_clean').agg({
                'result': lambda x: (x == 'WIN').sum() / len(x) * 100,
                'profit_loss': 'sum',
                'trade_id': 'count'
            }).rename(columns={'trade_id': 'count', 'result': 'winrate', 'profit_loss': 'pnl'})
            
            for strat, row in strat_stats.iterrows():
                msg += f"• <b>{strat}</b>: {row['count']} tr | {row['winrate']:.1f}% WR | {row['pnl']:+.2f}$\n"
            
            # 3. Detalle de Operaciones
            msg += "\n<b>📝 DETALLE DE OPERACIONES</b>\n"
            # Ordenar por hora descendente
            df_sorted = df.sort_values('timestamp', ascending=False)
            for _, row in df_sorted.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌" if row['result'] == 'LOSS' else "⏳"
                pnl_str = f"{row['profit_loss']:+.2f}$" if row['result'] in ['WIN', 'LOSS'] else "---"
                
                # Mostrar siempre en UTC-3 para el usuario
                local_ts = row['timestamp'] - timedelta(hours=3)
                
                # Si es un rango de varios días, mostrar fecha corta
                if start_dt and end_dt and (end_dt - start_dt).days >= 1:
                    time_str = local_ts.strftime('%d/%m %H:%M')
                else:
                    time_str = local_ts.strftime('%H:%M')
                    
                strat = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                msg += f"{res_icon} <b>{row['pair']}</b> | {pnl_str} | {strat} | {time_str}\n"

            await self.send_message(msg, target_chat_id=chat_id)
            
        except Exception as e:
            print(f"[Telegram] Error en info_details: {e}")
            await self.send_message(f"❌ Error generando detalles: {e}", target_chat_id=chat_id)

    async def _handle_range_detailed(self, chat_id, start_dt=None, end_dt=None):
        """Manejar comando /range_detailed (últimos 10 trades o rango)."""
        try:
            all_files = glob.glob(str(self.logs_dir / "trades_*.csv"))
            if not all_files:
                await self.send_message("❌ No hay historial de trades.", target_chat_id=chat_id)
                return
            
            # Ordenar archivos por fecha (descendente)
            all_files.sort(reverse=True)
            
            dfs = []
            for f in all_files:
                try:
                    df_temp = pd.read_csv(f)
                    if not df_temp.empty:
                        dfs.append(df_temp)
                        if not start_dt and len(pd.concat(dfs)) >= 20: # Suficiente para los últimos 10
                            break
                except: continue
            
            if not dfs:
                await self.send_message("❌ No hay datos.", target_chat_id=chat_id)
                return
                
            df = pd.concat(dfs, ignore_index=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if start_dt and end_dt:
                # Filtrar por rango
                trades_to_show = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)].sort_values('timestamp', ascending=False)
                msg = f"<b>📝 OPERACIONES EN RANGO</b>\n"
                msg += f"🕒 {start_dt.strftime('%d/%m/%Y %H:%M')} - {end_dt.strftime('%d/%m/%Y %H:%M')}\n\n"
            else:
                # Últimos 10
                trades_to_show = df.sort_values('timestamp', ascending=False).head(10)
                msg = "<b>📝 ÚLTIMOS 10 TRADES</b>\n\n"
            
            if trades_to_show.empty:
                msg += "❌ No se encontraron operaciones en este rango."
                await self.send_message(msg, target_chat_id=chat_id)
                return

            for _, row in trades_to_show.iterrows():
                res_icon = "✅" if row['result'] == 'WIN' else "❌" if row['result'] == 'LOSS' else "⏳"
                pnl_str = f"{row['profit_loss']:+.2f}$" if row['result'] in ['WIN', 'LOSS'] else "---"
                
                # Mostrar siempre en UTC-3 para el usuario
                local_ts = row['timestamp'] - timedelta(hours=3)
                
                # Formato de hora/fecha
                if start_dt and end_dt and (end_dt - start_dt).days >= 1:
                    time_str = local_ts.strftime('%d/%m %H:%M')
                else:
                    time_str = local_ts.strftime('%H:%M')
                
                # Limpiar nombre estrategia
                strat = str(row['pattern_detected']).split(':')[0] if ':' in str(row['pattern_detected']) else str(row['pattern_detected'])
                
                msg += f"{res_icon} <b>{row['pair']}</b> | {pnl_str} | {strat} | {time_str}\n"
            
            await self.send_message(msg, target_chat_id=chat_id)
            
        except Exception as e:
            print(f"[Telegram] Error en range_detailed: {e}")
            await self.send_message(f"❌ Error: {e}", target_chat_id=chat_id)
