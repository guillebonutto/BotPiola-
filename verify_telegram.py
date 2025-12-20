import asyncio
import aiohttp
import sys

async def verify_telegram(token, chat_id):
    if not token or not chat_id:
        print("Error: Token y Chat ID son requeridos.")
        return

    # Limpiar token
    token = token.strip()
    if token.lower().startswith('bot'):
        token = token[3:]
    
    if not token:
        print("❌ Error: El token quedó vacío después de limpiar.")
        return

    base_url = f"https://api.telegram.org/bot{token}"
    
    print(f"Probando token: {token[:6]}...{token[-4:]}")
    print(f"URL Base: {base_url}")
    print(f"Chat ID: {chat_id}")

    async with aiohttp.ClientSession() as session:
        # 1. Probar getMe
        try:
            async with session.get(f"{base_url}/getMe") as resp:
                status = resp.status
                text = await resp.text()
                if status == 200:
                    data = await resp.json()
                    bot_user = data.get('result', {}).get('username')
                    print(f"✅ Token Válido! Bot: @{bot_user}")
                elif status == 404:
                    print(f"❌ Error 404: No encontrado. Esto sugiere que el TOKEN '{token}' no existe en los servidores de Telegram.")
                    return
                elif status == 401:
                    print(f"❌ Error 401: No autorizado. El token existe pero es incorrecto o expiró.")
                    return
                else:
                    print(f"❌ Error en Token (getMe): {status} - {text}")
                    return
        except Exception as e:
            print(f"❌ Error de conexión: {e}")
            return

        # 2. Probar sendMessage
        payload = {
            'chat_id': chat_id,
            'text': "🧪 Prueba de conexión del BotPiola-",
            'parse_mode': 'HTML'
        }
        async with session.post(f"{base_url}/sendMessage", json=payload) as resp:
            status = resp.status
            text = await resp.text()
            if status == 200:
                print("✅ Mensaje enviado con éxito al Chat ID!")
            else:
                print(f"❌ Error enviando mensaje: {status} - {text}")

if __name__ == "__main__":
    token = input("Introduce el Token de Telegram: ").strip()
    chat_id = input("Introduce el Chat ID de Telegram: ").strip()
    
    asyncio.run(verify_telegram(token, chat_id))
