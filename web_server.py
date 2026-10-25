import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from aiohttp import web
import socket
import struct

# Forzar encoding UTF-8 en Windows para evitar crashes por emojis en stdout/stderr
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Importar Tunnel Manager existente
from tunnel_manager import tunnel_manager

PROJECT_DIR = Path(__file__).parent.resolve()
WEB_APP_DIR = PROJECT_DIR / "web_app"
CONFIG_FILE = PROJECT_DIR / "config.json"
STATUS_FILE = PROJECT_DIR / "pocketoption_status.json"
LOGS_TRADES_DIR = PROJECT_DIR / "logs" / "trades"

def get_argentina_date_str():
    tz = timezone(timedelta(hours=-3))
    return datetime.now(tz).strftime("%Y%m%d")

async def handle_index(request):
    """Servir la página principal de la Mini App (Trading Dashboard)"""
    dashboard = PROJECT_DIR / "templates" / "index.html"
    if dashboard.exists():
        return web.FileResponse(dashboard)
    return web.Response(text="Trading Dashboard not found", content_type="text/html", status=404)

async def handle_pibot(request):
    """Servir la página del PiBot Control Panel"""
    control_panel = WEB_APP_DIR / "control_panel.html"
    if control_panel.exists():
        return web.FileResponse(control_panel)
    return web.Response(text="PiBot Telegram Mini App Dashboard not found", content_type="text/html", status=404)

async def handle_biometric(request):
    """Servir la página de autenticación biométrica de Telegram"""
    bio_path = WEB_APP_DIR / "biometric.html"
    if bio_path.exists():
        return web.FileResponse(bio_path)
    return web.Response(text="<h1>Biometric Auth page not found</h1>", content_type="text/html", status=404)

async def handle_face_status(request):
    try:
        from face_verifier import face_verifier
        return web.json_response({"enrolled": face_verifier.is_enrolled()})
    except Exception as e:
        return web.json_response({"enrolled": False, "error": str(e)})

async def handle_enroll_face(request):
    try:
        data = await request.json()
        img_data = data.get("image")
        if not img_data:
            return web.json_response({"success": False, "error": "Falta la imagen."}, status=400)
        from face_verifier import face_verifier
        res = face_verifier.enroll_face(img_data)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_verify_face(request):
    try:
        data = await request.json()
        img_data = data.get("image")
        if not img_data:
            return web.json_response({"verified": False, "error": "Falta la imagen."}, status=400)
        from face_verifier import face_verifier
        res = face_verifier.verify_face(img_data)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"verified": False, "error": str(e)}, status=500)

async def handle_api_status(request):
    """Retornar estado del bot, balance y resumen del día"""
    balance = 0.0
    last_updated = ""
    if STATUS_FILE.exists():
        try:
            data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            balance = data.get("balance", 0.0)
            last_updated = data.get("last_updated", "")
        except Exception:
            pass

    date_str = request.query.get("date", get_argentina_date_str())
    trades_today = await get_trades_for_date(date_str)
    
    total_trades = len(trades_today)
    wins = sum(1 for t in trades_today if str(t.get("result", "")).upper() in ["WIN", "PROFIT", "GANADA"])
    losses = sum(1 for t in trades_today if str(t.get("result", "")).upper() in ["LOSS", "PERDIDA", "PERDIDO"])
    pnl = sum(float(t.get("profit", 0.0)) for t in trades_today)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    return web.json_response({
        "status": "online",
        "balance": round(balance, 2),
        "last_updated": last_updated,
        "date": date_str,
        "summary": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "pnl": round(pnl, 2)
        }
    })

def _load_csv_file(filepath, trades_list, broker_name):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                result_str = str(row.get("result", "")).upper()
                profit_val = 0.0
                try:
                    profit_val = float(row.get("profit") or row.get("profit_loss") or 0.0)
                except Exception:
                    profit_val = 0.0
                
                amt = 1.0
                try:
                    amt = float(row.get("amount") or 1.0)
                except Exception:
                    amt = 1.0
                
                if profit_val == 0.0 and broker_name == "pocketoption":
                    if any(k in result_str for k in ["WIN", "PROFIT", "GANADA"]):
                        profit_val = amt * 0.85
                    elif any(k in result_str for k in ["LOSS", "PERDIDA", "PERDIDO"]):
                        profit_val = -amt

                pair_name = row.get("pair") or row.get("symbol") or ""
                action_name = row.get("action") or row.get("decision") or row.get("direction") or "BUY"
                strategy_name = row.get("strategy") or row.get("pattern_detected") or "Estrategia Activa"
                trades_list.append({
                    "timestamp": row.get("timestamp", ""),
                    "pair": pair_name,
                    "action": action_name,
                    "amount": amt,
                    "result": result_str,
                    "profit": round(profit_val, 2),
                    "strategy": strategy_name,
                    "broker": broker_name
                })
    except Exception as e:
        print(f"[WebServer] Error leyendo {filepath.name}: {e}")

async def get_trades_for_date(date_str):
    """Leer trades desde CSVs de logs para una fecha dada separando por broker"""
    trades = []
    po_files = [
        LOGS_TRADES_DIR / f"trades_pocketoption_real_{date_str}.csv",
        LOGS_TRADES_DIR / f"trades_pocketoption_{date_str}.csv",
        LOGS_TRADES_DIR / f"trades_{date_str}.csv"
    ]
    alpaca_files = [
        LOGS_TRADES_DIR / f"trades_config_alpaca_{date_str}.csv"
    ]
    
    for filepath in po_files:
        if filepath.exists():
            _load_csv_file(filepath, trades, "pocketoption")

    for filepath in alpaca_files:
        if filepath.exists():
            _load_csv_file(filepath, trades, "alpaca")

    return trades

async def handle_api_trades(request):
    """Retornar historial de trades de una fecha específica o de hoy"""
    date_str = request.query.get("date", get_argentina_date_str())
    trades = await get_trades_for_date(date_str)
    return web.json_response({
        "date": date_str,
        "count": len(trades),
        "trades": trades
    })

async def handle_api_stats(request):
    """Obtener las estadísticas de trading (Win Rate, Profit, etc) desde SQLite (PocketOption y Alpaca)"""
    try:
        import pandas as pd
        import sqlite3
        
        # 1. Cargar PocketOption desde feedback.db
        po_trades = pd.DataFrame()
        if os.path.exists('feedback.db'):
            try:
                conn_po = sqlite3.connect('feedback.db')
                po_trades = pd.read_sql_query("SELECT * FROM trades WHERE result != 'PENDING'", conn_po)
                conn_po.close()
            except Exception as e:
                print(f"[WebServer] Error leyendo feedback.db: {e}")
                
        # 2. Cargar Alpaca desde feedback_config_alpaca.db
        alpaca_trades = pd.DataFrame()
        if os.path.exists('feedback_config_alpaca.db'):
            try:
                conn_al = sqlite3.connect('feedback_config_alpaca.db')
                alpaca_trades = pd.read_sql_query("SELECT * FROM trades WHERE result != 'PENDING'", conn_al)
                conn_al.close()
            except Exception as e:
                print(f"[WebServer] Error leyendo feedback_config_alpaca.db: {e}")

        def calc_stats(df):
            if df is None or df.empty:
                return {'win_rate': 0, 'total_profit': 0, 'total_trades': 0, 'equity_curve': {'labels': [], 'data': []}}
            tt = len(df)
            w = len(df[df['result'].str.lower() == 'win'])
            wr = (w / tt) * 100 if tt > 0 else 0
            tp = float(df['profit'].sum())
            df = df.copy()
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
            df = df.sort_values('timestamp')
            df['cumulative_profit'] = df['profit'].cumsum()
            eq = {
                'labels': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist(),
                'data': [round(x, 2) for x in df['cumulative_profit'].tolist()]
            }
            return {'win_rate': round(wr, 1), 'total_profit': round(tp, 2), 'total_trades': tt, 'equity_curve': eq}

        po_stats = calc_stats(po_trades)
        alpaca_stats = calc_stats(alpaca_trades)

        # Unificar todos los trades para recent_trades y strategy_stats
        all_dfs = []
        if not po_trades.empty:
            df_p = po_trades.copy()
            df_p['broker'] = 'PocketOption'
            all_dfs.append(df_p)
        if not alpaca_trades.empty:
            df_a = alpaca_trades.copy()
            df_a['broker'] = 'Alpaca'
            all_dfs.append(df_a)

        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined['timestamp_dt'] = pd.to_datetime(combined['timestamp'], format='mixed')
            combined = combined.sort_values('timestamp_dt')
            
            strategy_stats = combined.groupby('strategy')['result'].apply(lambda x: (x.str.lower() == 'win').mean() * 100).to_dict()
            
            recent = combined.tail(35).copy()
            recent_trades = []
            for _, r in recent.iterrows():
                t_str = r['timestamp_dt'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['timestamp_dt']) else str(r['timestamp'])
                act = str(r.get('action') or 'BUY').upper()
                recent_trades.append({
                    'timestamp': t_str,
                    'pair': str(r.get('pair', '')),
                    'action': act,
                    'result': str(r.get('result', '')).lower(),
                    'profit': round(float(r.get('profit', 0.0)), 2),
                    'broker': str(r.get('broker', ''))
                })
        else:
            strategy_stats = {}
            recent_trades = []

        return web.json_response({
            'pocketoption': po_stats,
            'alpaca': alpaca_stats,
            'strategy_stats': strategy_stats,
            'recent_trades': recent_trades
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_config_get(request):
    """Obtener configuración actual del bot"""
    if CONFIG_FILE.exists():
        try:
            config_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            safe_config = {
                "pairs_with_timeframe": config_data.get("trading", {}).get("pairs_with_timeframe", {}),
                "enabled_strategies": config_data.get("trading", {}).get("enabled_strategies", []),
                "pairs": config_data.get("trading", {}).get("pairs", []),
                "amount": config_data.get("trading", {}).get("amount", 1.0),
                "daily_stop_loss": config_data.get("trading", {}).get("daily_stop_loss", -4.0),
                "daily_take_profit": config_data.get("trading", {}).get("daily_take_profit", 5.0),
                "money_management": config_data.get("trading", {}).get("money_management", {})
            }
            return web.json_response(safe_config)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    return web.json_response({"error": "config.json not found"}, status=404)

async def handle_api_config_post(request):
    """Actualizar configuración desde la Mini App"""
    try:
        payload = await request.json()
        if not CONFIG_FILE.exists():
            return web.json_response({"error": "config.json no existe"}, status=404)
        
        config_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        trading_cfg = config_data.get("trading", {})

        if "amount" in payload:
            trading_cfg["amount"] = float(payload["amount"])
        if "daily_stop_loss" in payload:
            trading_cfg["daily_stop_loss"] = float(payload["daily_stop_loss"])
        if "daily_take_profit" in payload:
            trading_cfg["daily_take_profit"] = float(payload["daily_take_profit"])
        if "pairs" in payload and isinstance(payload["pairs"], list):
            trading_cfg["pairs"] = payload["pairs"]
        if "pairs_with_timeframe" in payload and isinstance(payload["pairs_with_timeframe"], dict):
            trading_cfg["pairs_with_timeframe"] = payload["pairs_with_timeframe"]
        if "money_management" in payload and isinstance(payload["money_management"], dict):
            trading_cfg["money_management"].update(payload["money_management"])

        config_data["trading"] = trading_cfg
        CONFIG_FILE.write_text(json.dumps(config_data, indent=4), encoding="utf-8")
        
        print("[WebServer] Configuración actualizada correctamente desde Mini App.")
        return web.json_response({"status": "success", "message": "Configuración guardada"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def handle_api_tunnel_url(request):
    """Obtener URL HTTPS pública de la Mini App"""
    url = tunnel_manager.start()
    return web.json_response({
        "tunnel_url": url,
        "app_url": f"{url}/" if url else None
    })

async def handle_backtest_page(request):
    """Servir la página visual interactiva del reporte de Backtest"""
    backtest_html = WEB_APP_DIR / "alpaca_backtest.html"
    if backtest_html.exists():
        return web.FileResponse(backtest_html)
    return web.Response(text="Página de reporte no encontrada", status=404)

async def handle_api_backtest(request):
    """Retornar el reporte JSON completo de Backtest"""
    report_file = PROJECT_DIR / "alpaca_strict_backtest_report.json"
    if report_file.exists():
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
            return web.json_response(data)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    return web.json_response([], status=200)

# =============================================================================
# CONTROL REMOTO DE LA PC VÍA MQTT -> RASPBERRY PI PICO
# =============================================================================
MQTT_BROKER_HOST = "broker.hivemq.com"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC_COMMAND = "guille_pibot_913843638/pc/command"

def _mqtt_publish_raw(topic: str, message: str, timeout: float = 3.0) -> bool:
    """
    Publica un mensaje MQTT al broker HiveMQ usando un socket TCP raw.
    No requiere paho-mqtt ni ninguna dependencia externa.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((MQTT_BROKER_HOST, MQTT_BROKER_PORT))
        
        # 1. CONNECT packet
        client_id = f"pibot_web_{os.getpid()}".encode('utf-8')
        var_header = b'\x00\x04MQTT\x04\x02\x00\x3c'
        payload = struct.pack("!H", len(client_id)) + client_id
        rem_len = len(var_header) + len(payload)
        connect_pkt = bytes([0x10, rem_len]) + var_header + payload
        s.sendall(connect_pkt)
        
        # Esperar CONNACK
        connack = s.recv(4)
        if len(connack) < 4 or connack[0] != 0x20:
            s.close()
            return False
        
        # 2. PUBLISH packet
        topic_bytes = topic.encode('utf-8')
        msg_bytes = message.encode('utf-8')
        pub_rem_len = 2 + len(topic_bytes) + len(msg_bytes)
        publish_pkt = bytes([0x30, pub_rem_len]) + struct.pack("!H", len(topic_bytes)) + topic_bytes + msg_bytes
        s.sendall(publish_pkt)
        
        # 3. DISCONNECT
        s.sendall(b'\xe0\x00')
        s.close()
        print(f"[WebServer] ✅ MQTT publicado: {topic} -> {message}")
        return True
    except Exception as e:
        print(f"[WebServer] ❌ Error publicando MQTT: {e}")
        return False

async def handle_api_pc_power(request):
    """Endpoint para controlar el encendido/apagado de la PC vía MQTT -> Pico -> Relé."""
    try:
        payload = await request.json()
        action = payload.get("action", "WAKE").upper()
        
        valid_actions = {
            "WAKE": "Encendido completo (Relé + USB + WOL)",
            "POWER_PRESS": "Pulsación corta del botón Power (Relé)",
            "FORCE_OFF": "Apagado forzado 6 segundos (Relé)"
        }
        
        if action not in valid_actions:
            return web.json_response({"error": f"Acción inválida. Válidas: {list(valid_actions.keys())}"}, status=400)
        
        # Publicar comando al broker MQTT (la Pico lo recibe en <50ms)
        success = await asyncio.get_event_loop().run_in_executor(
            None, _mqtt_publish_raw, MQTT_TOPIC_COMMAND, action
        )
        
        if success:
            return web.json_response({
                "status": "ok",
                "action": action,
                "description": valid_actions[action],
                "message": f"✅ Comando {action} enviado a la Pico"
            })
        else:
            return web.json_response({
                "status": "error",
                "message": "No se pudo conectar al broker MQTT"
            }, status=503)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def handle_api_chart(request):
    try:
        broker = request.match_info.get('broker', 'both')
        import io
        import matplotlib.pyplot as plt
        from gui_bridge import GUIBridge
        bridge = GUIBridge()
        
        # Generar figura usando el mismo motor que la GUI
        fig = bridge.generate_today_pnl_chart_figure(broker=broker, figsize=(5.0, 3.5))
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none', dpi=100)
        plt.close(fig)
        buf.seek(0)
        
        return web.Response(body=buf.read(), content_type='image/png')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.Response(text=f"Error generating chart: {e}", status=500)

async def handle_api_chart_hist(request):
    try:
        broker = request.match_info.get('broker', 'both')
        import io
        import matplotlib.pyplot as plt
        from gui_bridge import GUIBridge
        bridge = GUIBridge()
        
        # Gráfico histórico continuo
        fig = bridge.generate_linear_chart_figure(broker=broker, figsize=(5.0, 3.5))
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none', dpi=100)
        plt.close(fig)
        buf.seek(0)
        
        return web.Response(body=buf.read(), content_type='image/png')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.Response(text=f"Error generating chart_hist: {e}", status=500)

async def handle_videos_page(request):
    """Servir la página de videos del primo"""
    videos_html = WEB_APP_DIR / "videos.html"
    if videos_html.exists():
        return web.FileResponse(videos_html)
    return web.Response(text="Página de videos no encontrada", status=404)

async def handle_api_emails(request):
    try:
        from email_handler import get_emails_with_videos
        emails, err = await asyncio.get_event_loop().run_in_executor(None, get_emails_with_videos)
        if err:
            return web.json_response({"error": err}, status=400)
        return web.json_response({"emails": emails})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_download_video(request):
    try:
        data = await request.json()
        email_id = data.get("email_id")
        filename = data.get("filename")
        drive_url = data.get("drive_url")
        if not email_id or not filename:
            return web.json_response({"error": "Faltan parámetros"}, status=400)
        
        from email_handler import download_video
        success, res = await asyncio.get_event_loop().run_in_executor(None, download_video, email_id, filename, drive_url)
        if success:
            return web.json_response({"status": "success", "filepath": res})
        else:
            return web.json_response({"error": res}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

def create_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/pibot", handle_pibot)
    app.router.add_get("/biometric", handle_biometric)
    app.router.add_get("/api/face_status", handle_face_status)
    app.router.add_post("/api/enroll_face", handle_enroll_face)
    app.router.add_post("/api/verify_face", handle_verify_face)
    app.router.add_get("/backtest", handle_backtest_page)
    app.router.add_get("/api/stats", handle_api_stats)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_get("/api/trades", handle_api_trades)
    app.router.add_get("/api/config", handle_api_config_get)
    app.router.add_post("/api/config", handle_api_config_post)
    app.router.add_get("/api/tunnel_url", handle_api_tunnel_url)
    app.router.add_get("/api/backtest", handle_api_backtest)
    app.router.add_post("/api/pc/power", handle_api_pc_power)
    app.router.add_get("/api/chart/{broker}", handle_api_chart)
    app.router.add_get("/api/chart_hist/{broker}", handle_api_chart_hist)
    app.router.add_get("/videos", handle_videos_page)
    app.router.add_get("/api/emails", handle_api_emails)
    app.router.add_post("/api/download_video", handle_api_download_video)
    
    if WEB_APP_DIR.exists():
        app.router.add_static("/static/", WEB_APP_DIR)
        
    return app

async def start_server_async(port=8085):
    """Iniciar servidor aiohttp y túnel Cloudflare en segundo plano"""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[WebServer] Servidor Web corriendo en http://127.0.0.1:{port}")
    
    tunnel_url = tunnel_manager.start()
    if tunnel_url:
        print(f"[WebServer] 🚀 Telegram Mini App URL activa: {tunnel_url}/")
    return runner, tunnel_url

async def main():
    runner, tunnel_url = await start_server_async()
    print("[WebServer] Servidor activo. Presiona Ctrl+C para salir.")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[WebServer] Deteniendo servidor...")
