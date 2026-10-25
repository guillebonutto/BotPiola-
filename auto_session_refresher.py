import asyncio
import json
import re
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

CONFIG_FILE = Path("config.json")

async def refresh_pocketoption_session(email, password, headless=True):
    print("=" * 70)
    print("INICIANDO AUTO-LOGIN Y RENOVACION AUTOMATICA DE SESION (POCKET OPTION)")
    print(f"Usuario: {email}")
    print("=" * 70)

    auth_payload = None
    captured_cookies = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # Intercept websocket messages to capture 42["auth", ...]
        async def on_websocket(ws):
            nonlocal auth_payload
            print(f"[WS] WebSocket detectado: {ws.url}")
            
            def on_frame_sent(payload):
                nonlocal auth_payload
                if isinstance(payload, str) and '42["auth"' in payload:
                    print("[WS] 🔥 MENSAJE DE AUTENTICACION CAPTURADO:")
                    print(payload[:120] + "...")
                    auth_payload = payload
                    
            ws.on("framesent", on_frame_sent)

        page.on("websocket", on_websocket)

        print("1. Navegando a la página de login...")
        try:
            await page.goto("https://pocketoption.com/es/login", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Advertencia durante carga: {e}")

        print("2. Completando credenciales...")
        # Fill email
        await page.fill('input[type="email"], input[name="email"], #email', email)
        await page.wait_for_timeout(500)
        # Fill password
        await page.fill('input[type="password"], input[name="password"], #password', password)
        await page.wait_for_timeout(800)

        print("3. Enviando formulario de inicio de sesión...")
        submit_btn = page.locator('button[type="submit"], button:has-text("Iniciar sesión"), .btn-green-light')
        await submit_btn.first.click()

        print("4. Esperando respuesta del servidor y carga del gabinete...")
        for i in range(25):
            await page.wait_for_timeout(1000)
            if auth_payload:
                print(f"-> Token de sesión obtenido vía WebSocket en el segundo {i+1}!")
                break
            
            # Check if redirected to cabinet / trading room
            if "cabinet" in page.url or "trade" in page.url:
                print(f"-> Sesión iniciada con éxito en {page.url}")

        cookies = await context.cookies()
        captured_cookies = cookies
        await browser.close()

    # Si se capturó auth_payload directamente
    final_ssid = None
    if auth_payload:
        final_ssid = auth_payload
    else:
        # Reconstruir desde cookies si existe cookie de session
        print("Buscando cookie de sesión entre cookies capturadas...")
        for c in captured_cookies:
            if c['name'] == 'session' or 'session' in c['name'].lower():
                val = urllib.parse.unquote(c['value'])
                print(f"Cookie encontrada: {c['name']} = {val[:40]}...")
                # Formato standard de Pocket Option
                final_ssid = f'42["auth",{{\"session\":\"{val}\",\"isDemo\":0,\"uid\":72378748,\"platform\":2,\"isFastHistory\":true,\"isOptimized\":true}}]'
                break

    if not final_ssid:
        print("[ERROR] No se pudo obtener el token de sesión. Verifica captcha o credenciales.")
        return False

    print("\n5. Validando token obtenido con API de Pocket Option...")
    api = PocketOptionAsync(final_ssid)
    conn = await api.connect()
    if conn:
        bal = await api.balance()
        print(f"✅ ¡CONEXIÓN EXITOSA! Saldo Real verificado: ${bal} USD")
        
        # Actualizar config.json
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            
        cfg['ssid'] = final_ssid
        cfg['credentials'] = {
            "email": email,
            "password": password
        }
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
            
        print("✅ [config.json] Archivo actualizado exitosamente con nuevo SSID.")
        
        # Enviar restart signal
        with open("restart.signal", "w") as f:
            f.write("restart")
        print("🚀 Señal de reinicio enviada. Bot de Pocket Option 100% ACTIVO.")
        return True
    else:
        print("[WARN] Token capturado pero API rechazó handshake. Reintentando...")
        return False

if __name__ == '__main__':
    email = "guillekname@gmail.com"
    pwd = "fF#Lc36wN!KAQ7&"
    asyncio.run(refresh_pocketoption_session(email, pwd, headless=True))
