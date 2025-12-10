import aiohttp
import asyncio

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, message):
        """Envía un mensaje a Telegram de forma asíncrona."""
        if not self.token or not self.chat_id:
            print("[Telegram] No configurado (Falta Token o Chat ID).")
            return

        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload) as response:
                    if response.status == 200:
                        # print("[Telegram] Mensaje enviado correctamente.")
                        pass
                    else:
                        print(f"[Telegram] Error enviando mensaje: {response.status}")
                        text = await response.text()
                        print(f"[Telegram] Respuesta: {text}")
        except Exception as e:
            print(f"[Telegram] Excepción al enviar: {e}")

    async def notify_open(self, pair, action, strategy, duration, amount):
        icon = "🟢" if action == 'BUY' else "🔴"
        direction = "ALZA (Buy)" if action == 'BUY' else "BAJA (Sell)"
        msg = (
            f"{icon} **NUEVA OPERACIÓN** {icon}\n\n"
            f"💰 **Par:** {pair}\n"
            f"📈 **Acción:** {direction}\n"
            f"🧠 **Estrategia:** {strategy}\n"
            f"⏱ **Duración:** {duration} seg\n"
            f"💵 **Monto:** ${amount}\n"
            f"🕓 **Hora:** {self._get_time()}"
        )
        await self.send_message(msg)

    async def notify_close(self, pair, profit, is_win):
        icon = "✅" if is_win else "❌"
        result_text = "GANADA" if is_win else "PERDIDA"
        
        msg = (
            f"{icon} **OPERACIÓN CERRADA** {icon}\n\n"
            f"💰 **Par:** {pair}\n"
            f"🏆 **Resultado:** {result_text}\n"
            f"🤑 **Profit:** ${profit}\n"
            f"🕓 **Hora:** {self._get_time()}"
        )
        await self.send_message(msg)

    def _get_time(self):
        from datetime import datetime, timezone, timedelta
        # Hora local aproximada (UTC-3 para Argentina/Uruguay por defecto, o UTC)
        # Ajustar según necesidad del usuario
        tz = timezone(timedelta(hours=-3)) 
        return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
