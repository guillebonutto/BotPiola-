import asyncio
import aiohttp
import logging
import json
import time
from datetime import datetime, timezone

logger = logging.getLogger("AlpacaAdapter")

def map_symbol_to_yfinance(symbol):
    """Mapea un símbolo del bot al ticker correspondiente en Yahoo Finance."""
    # Eliminar prefijos y sufijos comunes del bot
    clean = symbol.replace("_otc", "").replace("#", "")
    # Si tiene 6 letras y es todo mayúsculas, es un par Forex (ej: EURUSD)
    if len(clean) == 6 and clean.isupper() and clean.isalpha():
        return f"{clean}=X"
    # Acciones o ETFs directos
    return clean

def map_symbol_to_alpaca(symbol):
    """Mapea un símbolo del bot al ticker correspondiente en Alpaca."""
    clean = symbol.replace("_otc", "").replace("#", "")
    # Para Alpaca, los pares Forex se escriben con barra (ej: EUR/USD)
    if len(clean) == 6 and clean.isupper() and clean.isalpha():
        return f"{clean[:3]}/{clean[3:]}"
    return clean

async def download_yahoo_candles(symbol, interval_seconds, lookback):
    """Descarga velas de Yahoo Finance usando aiohttp de manera asíncrona."""
    ticker = map_symbol_to_yfinance(symbol)
    
    # Calcular días necesarios estimando fines de semana y cierres
    days_needed = (lookback * interval_seconds) / 86400.0
    days_needed_padded = days_needed * 1.8 # Factor de seguridad
    
    # Mapear intervalos de segundos a formatos de Yahoo Finance
    # y determinar el rango de tiempo a descargar dinámicamente
    if interval_seconds <= 60:
        interval_str = "1m"
        # El historial de 1m en Yahoo Finance tiene un límite máximo de 7 días
        if days_needed_padded <= 1.0:
            range_str = "1d"
        elif days_needed_padded <= 2.0:
            range_str = "2d"
        elif days_needed_padded <= 5.0:
            range_str = "5d"
        else:
            range_str = "7d"
    elif interval_seconds <= 300:
        interval_str = "5m"
        # El historial de 5m en Yahoo Finance tiene un límite máximo de 60 días
        if days_needed_padded <= 1.0:
            range_str = "1d"
        elif days_needed_padded <= 5.0:
            range_str = "5d"
        elif days_needed_padded <= 7.0:
            range_str = "7d"
        elif days_needed_padded <= 30.0:
            range_str = "30d"
        else:
            range_str = "60d"
    elif interval_seconds <= 900:
        interval_str = "15m"
        # El historial de 15m en Yahoo Finance tiene un límite máximo de 60 días
        if days_needed_padded <= 1.0:
            range_str = "1d"
        elif days_needed_padded <= 5.0:
            range_str = "5d"
        elif days_needed_padded <= 7.0:
            range_str = "7d"
        elif days_needed_padded <= 30.0:
            range_str = "30d"
        else:
            range_str = "60d"
    elif interval_seconds <= 3600:
        interval_str = "1h"
        # El historial de 1h en Yahoo Finance tiene un límite máximo de 730 días (2 años)
        if days_needed_padded <= 30.0:
            range_str = "30d"
        elif days_needed_padded <= 60.0:
            range_str = "60d"
        elif days_needed_padded <= 365.0:
            range_str = "1y"
        else:
            range_str = "2y"
    else:
        interval_str = "1d"
        # El historial de 1d en Yahoo Finance no tiene límites estrictos recientes
        if days_needed_padded <= 365.0:
            range_str = "1y"
        elif days_needed_padded <= 730.0:
            range_str = "2y"
        elif days_needed_padded <= 1825.0:
            range_str = "5y"
        else:
            range_str = "max"
        
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval_str}&range={range_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as r:
                if r.status != 200:
                    logger.warning(f"Error descargando datos de Yahoo Finance para {ticker}: HTTP {r.status}")
                    return []
                
                data = await r.json()
                
                if not data or 'chart' not in data or not data['chart']['result']:
                    logger.warning(f"Formato inválido de Yahoo Finance para {ticker}")
                    return []
                
                result = data['chart']['result'][0]
                if 'timestamp' not in result or 'indicators' not in result:
                    logger.warning(f"Datos incompletos de Yahoo Finance para {ticker}")
                    return []
                    
                timestamps = result['timestamp']
                quote = result['indicators']['quote'][0]
                
                opens = quote.get('open', [])
                highs = quote.get('high', [])
                lows = quote.get('low', [])
                closes = quote.get('close', [])
                
                candles = []
                for i in range(len(timestamps)):
                    # Saltar velas con datos vacíos (común en mercado cerrado)
                    if (opens[i] is None or highs[i] is None or 
                        lows[i] is None or closes[i] is None):
                        continue
                    
                    candles.append({
                        'time': int(timestamps[i]),
                        'open': float(opens[i]),
                        'high': float(highs[i]),
                        'low': float(lows[i]),
                        'close': float(closes[i])
                    })
                
                # Devolver las últimas velas según el lookback
                return candles[-lookback:]
                
    except Exception as e:
        logger.error(f"Error descargando velas de Yahoo para {symbol}: {e}")
        return []

class AlpacaAdapter:
    def __init__(self, key_id, secret_key, paper=True, config=None):
        self.key_id = key_id
        self.secret_key = secret_key
        self.paper = paper
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json"
        }
        self.config = config or {}
        
        # Almacenamiento en memoria de operaciones activas para el ciclo del bot
        # { order_id: { symbol, pair, qty, side, entry_price, stop_loss, take_profit, start_time, duration, amount, status } }
        self.active_trades = {}
        # Historial de trades cerrados en esta sesión para responder a closed_deals()
        self.closed_trades_cache = []

    async def balance(self):
        """Obtiene el saldo disponible (cash) en la cuenta de Alpaca."""
        url = f"{self.base_url}/v2/account"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        # 'cash' representa el dinero en efectivo disponible para operar
                        return float(data.get('cash', 0.0))
                    elif r.status == 401:
                        logger.error(f"Error de autenticación en Alpaca (HTTP 401): Llaves no válidas.")
                        return -1.0
                    else:
                        logger.warning(f"Error temporal obteniendo balance de Alpaca: HTTP {r.status}")
                        return "Network Error"
        except Exception as e:
            logger.warning(f"Excepción temporal obteniendo balance de Alpaca: {e}")
            return "Network Error"

    async def get_candles(self, asset: str, period: int, offset: int) -> list[dict]:
        """Obtiene velas históricas utilizando el descargador de Yahoo Finance."""
        return await download_yahoo_candles(asset, period, offset)

    async def get_candles_advanced(self, asset: str, period: int, offset: int, time: int) -> list[dict]:
        """Obtiene velas avanzadas (reutiliza la misma descarga con Yahoo Finance)."""
        return await download_yahoo_candles(asset, period, offset)

    async def buy(self, asset: str, amount: float, time: int, check_win: bool = False, latest_candle: dict = None) -> tuple[str, dict]:
        """Ejecuta una orden de compra (BUY) en Alpaca con orden bracket SL/TP."""
        return await self._place_order(asset, amount, "buy", time, latest_candle)

    async def sell(self, asset: str, amount: float, time: int, check_win: bool = False, latest_candle: dict = None) -> tuple[str, dict]:
        """Ejecuta una orden de venta en corto (SELL) en Alpaca con orden bracket SL/TP."""
        return await self._place_order(asset, amount, "sell", time, latest_candle)

    async def _place_order(self, asset: str, amount: float, side: str, duration: int, latest_candle: dict = None) -> tuple[str, dict]:
        ticker = map_symbol_to_alpaca(asset)
        
        # 1. Obtener precio actual
        price = 0.0
        if latest_candle and 'Close' in latest_candle:
            price = float(latest_candle['Close'])
        else:
            # Fallback si no hay vela: consultar último precio en Alpaca
            price = await self._get_latest_price(ticker)
            
        if price <= 0:
            raise ValueError(f"No se pudo determinar el precio actual para {ticker}")

        # 2. Calcular Stop Loss y Take Profit por ATR o fallback
        atr = float(latest_candle.get('ATR', 0.0)) if latest_candle else 0.0
        tp_mult = float(self.config.get('take_profit_atr_multiplier', 2.0))
        sl_mult = float(self.config.get('stop_loss_atr_multiplier', 1.5))
        
        is_forex = "/" in ticker
        decimals = 5 if is_forex else 2
        
        if atr > 0:
            distancia_sl = sl_mult * atr
            distancia_tp = tp_mult * atr
        else:
            # Fallback a porcentajes si no hay ATR (1.5% SL, 3% TP)
            distancia_sl = price * 0.015
            distancia_tp = price * 0.03
            
        if side == "buy":
            take_profit = price + distancia_tp
            stop_loss = price - distancia_sl
        else:
            take_profit = price - distancia_tp
            stop_loss = price + distancia_sl

        # Redondear precios
        take_profit = round(take_profit, decimals)
        stop_loss = round(stop_loss, decimals)

        # 3. Calcular tamaño de la posición (cantidad de acciones/lotes)
        risk_per_trade = float(self.config.get('risk_per_trade_usd', 0.0))
        
        if risk_per_trade > 0:
            # Risk-Based Sizing: arriesgar una cantidad fija de dólares por operación
            qty = risk_per_trade / distancia_sl
        else:
            # Fixed Sizing: usar el monto nominal fijo definido
            qty = amount / price
            
        allow_fractional = self.config.get('allow_fractional', False)
        if allow_fractional:
            qty = round(qty, 4)
        else:
            qty = int(qty)
            if qty == 0:
                qty = 1

        # 4. Construir payload de Orden adaptado a Alpaca
        is_fractional = (qty != int(qty))
        
        if is_fractional:
            # Alpaca requiere time_in_force='day' para órdenes fraccionadas y no permite bracket en fracciones
            payload = {
                "symbol": ticker,
                "qty": str(qty),
                "side": side,
                "type": "market",
                "time_in_force": "day"
            }
        else:
            # Para acciones enteras, soporta bracket order completo con Take Profit y Stop Loss
            payload = {
                "symbol": ticker,
                "qty": str(int(qty)),
                "side": side,
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "take_profit": {
                    "limit_price": str(take_profit)
                },
                "stop_loss": {
                    "stop_price": str(stop_loss)
                }
            }
        
        url = f"{self.base_url}/v2/orders"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(url, json=payload, timeout=15) as r:
                    res_body = await r.read()
                    if r.status == 200 or r.status == 201:
                        order_data = json.loads(res_body)
                        order_id = order_data['id']
                        
                        # Guardar orden activa en memoria
                        self.active_trades[order_id] = {
                            "symbol": ticker,
                            "pair": asset,
                            "qty": qty,
                            "side": side,
                            "entry_price": price,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "start_time": time.time(),
                            "duration": duration,
                            "amount": amount,
                            "status": "active"
                        }
                        
                        logger.info(f"[Alpaca] Orden Bracket enviada para {ticker}. ID: {order_id} | Qty: {qty} | SL: {stop_loss} | TP: {take_profit}")
                        
                        # Formatear retorno para mantener compatibilidad
                        compat_trade = {
                            "asset": asset,
                            "amount": amount,
                            "direction": side,
                            "expiry": int(time.time() + duration),
                            "result": "pending",
                            "profit": 0.0
                        }
                        return order_id, compat_trade
                    else:
                        error_msg = res_body.decode('utf-8')
                        logger.error(f"Error colocando orden en Alpaca: HTTP {r.status} - {error_msg}")
                        raise ConnectionError(f"Error en Alpaca: {error_msg}")
        except Exception as e:
            logger.error(f"Excepción colocando orden en Alpaca: {e}")
            raise

    async def _get_latest_price(self, ticker: str) -> float:
        """Obtiene el último precio de un ticker en Alpaca."""
        # Si es forex, usamos el endpoint de bars de forex o consultamos la posición actual.
        # Para simplificar y hacerlo independiente del plan de datos, descargamos las últimas velas
        # de Yahoo Finance y tomamos el último cierre como el precio más reciente.
        candles = await download_yahoo_candles(ticker, 60, 2)
        if candles:
            return float(candles[-1]['close'])
        return 0.0

    async def opened_deals(self) -> list[dict]:
        """Devuelve una lista de las posiciones y órdenes actualmente abiertas en Alpaca."""
        url_pos = f"{self.base_url}/v2/positions"
        deals = []
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_pos, timeout=10) as r:
                    if r.status == 200:
                        positions = await r.json()
                        for p in positions:
                            deals.append({
                                "symbol": p.get("symbol"),
                                "qty": float(p.get("qty", 0.0)),
                                "side": p.get("side", "long"),
                                "entry_price": float(p.get("avg_entry_price", 0.0)),
                                "current_price": float(p.get("current_price", 0.0)),
                                "unrealized_pl": float(p.get("unrealized_pl", 0.0))
                            })
        except Exception as e:
            logger.error(f"Error consultando opened_deals en Alpaca: {e}")
        return deals

    async def closed_deals(self) -> list[dict]:
        """Escanea trades activos, cierra por tiempo si expiran, y devuelve los cerrados."""
        current_time = time.time()
        newly_closed = []
        
        # 1. Obtener posiciones abiertas reales en Alpaca para ver qué sigue abierto
        open_positions = {}
        url_pos = f"{self.base_url}/v2/positions"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_pos, timeout=10) as r:
                    if r.status == 200:
                        positions_list = await r.json()
                        open_positions = {pos['symbol']: pos for pos in positions_list}
                    else:
                        logger.warning(f"Error consultando posiciones en Alpaca: HTTP {r.status}")
        except Exception as pos_err:
            logger.error(f"Excepción obteniendo posiciones de Alpaca: {pos_err}")

        # 1.5. Sincronizar posiciones existentes en Alpaca que no estén en memoria (ej: tras reinicio)
        for sym, pos in open_positions.items():
            already_tracked = any(t.get('symbol') == sym for t in self.active_trades.values())
            if not already_tracked:
                fake_id = f"alpaca_sync_{sym}_{int(current_time)}"
                entry_p = float(pos.get('avg_entry_price', 0.0))
                qty_val = float(pos.get('qty', 0.0))
                side_val = "buy" if pos.get('side', 'long') == 'long' else "sell"
                
                tp_p = round(entry_p * (1.02 if side_val == "buy" else 0.98), 2)
                sl_p = round(entry_p * (0.985 if side_val == "buy" else 1.015), 2)
                
                self.active_trades[fake_id] = {
                    "symbol": sym,
                    "pair": sym,
                    "qty": qty_val,
                    "side": side_val,
                    "entry_price": entry_p,
                    "stop_loss": sl_p,
                    "take_profit": tp_p,
                    "start_time": current_time,
                    "duration": int(self.config.get('holding_period_seconds', 14400))
                }
                logger.info(f"[Alpaca] Posición abierta previa de {sym} ({qty_val} acciones) sincronizada y bajo seguimiento del bot.")

        # 2. Iterar sobre nuestros trades en memoria
        active_ids = list(self.active_trades.keys())
        for order_id in active_ids:
            trade = self.active_trades[order_id]
            symbol = trade['symbol']
            pair = trade['pair']
            
            is_position_open = symbol in open_positions
            time_elapsed = current_time - trade['start_time']
            should_force_close = (trade.get('duration', 0) > 0) and (time_elapsed >= trade['duration'])
            
            # Caso A: El TP o el SL se activaron solos en la nube (la posición ya se cerró en Alpaca)
            if not is_position_open:
                # Recuperar detalles del cierre y calcular PnL
                pnl, close_price = await self._get_closed_trade_details(symbol, trade['side'], trade['entry_price'], trade['qty'])
                
                closed_item = {
                    "id": order_id,
                    "asset": pair,
                    "profit": pnl,
                    "result": "win" if pnl > 0 else "loss",
                    "close_time": int(current_time)
                }
                newly_closed.append(closed_item)
                self.closed_trades_cache.append(closed_item)
                del self.active_trades[order_id]
                logger.info(f"[Alpaca] Trade {order_id} de {symbol} CERRADO por SL/TP. PnL: ${pnl:.2f} | Precio Cierre: {close_price}")
                
            # Caso B: La posición sigue abierta en Alpaca -> Monitorear TP, SL y Trailing Stop Dinámico
            elif is_position_open:
                pos_info = open_positions[symbol]
                curr_price = float(pos_info.get('current_price', 0.0))
                entry_price = trade['entry_price']
                side = trade['side']
                tp_price = trade.get('take_profit', 0.0)
                sl_price = trade.get('stop_loss', 0.0)
                
                # --- ACTUALIZACIÓN DINÁMICA DE TRAILING STOP (CHANDELIER TRAIL) ---
                if curr_price > 0:
                    atr_est = trade.get('atr', entry_price * 0.005)
                    
                    if side == "buy":
                        peak_p = max(trade.get('peak_price', entry_price), curr_price)
                        trade['peak_price'] = peak_p
                        
                        # Si el precio sube a favor, el trailing sube protegiendo la ganancia
                        if curr_price > entry_price:
                            trail_floor = peak_p - (1.2 * atr_est)
                            if trail_floor > sl_price:
                                trade['stop_loss'] = round(trail_floor, 2)
                                logger.info(f"[Alpaca] 🛡️ TRAILING STOP ELEVADO para {symbol}: Nuevo SL garantizado @ ${trade['stop_loss']} (Precio actual: ${curr_price:.2f})")

                    elif side == "sell":
                        trough_p = min(trade.get('trough_price', entry_price), curr_price)
                        trade['trough_price'] = trough_p
                        
                        # Si el precio baja a favor, el trailing baja protegiendo la ganancia
                        if curr_price < entry_price:
                            trail_ceil = trough_p + (1.2 * atr_est)
                            if trail_ceil < sl_price:
                                trade['stop_loss'] = round(trail_ceil, 2)
                                logger.info(f"[Alpaca] 🛡️ TRAILING STOP REDUCIDO para {symbol}: Nuevo SL garantizado @ ${trade['stop_loss']} (Precio actual: ${curr_price:.2f})")

                # --- VERIFICAR SI TOCÓ TAKE PROFIT, STOP LOSS O TRAILING ---
                hit_tp = (side == "buy" and tp_price > 0 and curr_price >= tp_price) or (side == "sell" and tp_price > 0 and curr_price <= tp_price)
                hit_sl = (side == "buy" and sl_price > 0 and curr_price <= trade['stop_loss']) or (side == "sell" and sl_price > 0 and curr_price >= trade['stop_loss'])
                
                if hit_tp or hit_sl or should_force_close:
                    exit_reason = "TAKE PROFIT (WIN)" if hit_tp else ("TRAILING STOP / SL" if hit_sl else "EXPIRACIÓN DE TIEMPO")
                    logger.info(f"[Alpaca] 🎯 Cerrando posición de {symbol} por {exit_reason} (Precio: ${curr_price:.2f} | Entrada: ${entry_price:.2f})...")
                    
                    # Liquidar en Alpaca
                    close_url = f"{self.base_url}/v2/positions/{symbol}"
                    try:
                        async with aiohttp.ClientSession(headers=self.headers) as session:
                            async with session.delete(close_url, timeout=15) as r:
                                if r.status in [200, 201]:
                                    logger.info(f"[Alpaca] Posición de {symbol} liquidada exitosamente en el broker.")
                    except Exception as e:
                        logger.error(f"Error liquidando {symbol}: {e}")
                        
                    await asyncio.sleep(1)
                    pnl, close_p = await self._get_closed_trade_details(symbol, side, entry_price, trade['qty'])
                    if pnl == 0.0 and curr_price > 0:
                        pnl = (curr_price - entry_price) * trade['qty'] if side == "buy" else (entry_price - curr_price) * trade['qty']
                        close_p = curr_price
                        
                    closed_item = {
                        "id": order_id,
                        "asset": pair,
                        "profit": pnl,
                        "result": "win" if pnl > 0 else "loss",
                        "close_time": int(current_time)
                    }
                    newly_closed.append(closed_item)
                    self.closed_trades_cache.append(closed_item)
                    del self.active_trades[order_id]
                    logger.info(f"[Alpaca] Trade {order_id} de {symbol} FINALIZADO por {exit_reason}. PnL: ${pnl:+.2f} USD")

        # Retornar los cerrados en este escaneo
        return newly_closed

    async def _get_closed_trade_details(self, symbol: str, side: str, entry_price: float, qty: float) -> tuple[float, float]:
        """Consulta los detalles de las órdenes completadas para determinar el precio de cierre y PnL."""
        url_orders = f"{self.base_url}/v2/orders?status=closed&symbols={symbol}&limit=5"
        close_price = 0.0
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_orders, timeout=10) as r:
                    if r.status == 200:
                        orders = await r.json()
                        # Buscar la orden de salida (debe tener el side opuesto al de entrada)
                        target_side = "sell" if side == "buy" else "buy"
                        exit_orders = [o for o in orders if o['side'] == target_side and o.get('filled_avg_price')]
                        
                        if exit_orders:
                            # Tomar la más reciente
                            close_price = float(exit_orders[0]['filled_avg_price'])
        except Exception as e:
            logger.error(f"Error recuperando detalles de cierre de orden para {symbol}: {e}")
            
        # Si falló la API, usamos el último precio de Yahoo como fallback para calcular PnL estimado
        if close_price <= 0:
            close_price = await self._get_latest_price(symbol)
            logger.warning(f"No se obtuvo precio de cierre de Alpaca. Usando precio estimado de mercado: {close_price}")

        # Calcular P&L
        if side == "buy":
            pnl = (close_price - entry_price) * qty
        else:
            pnl = (entry_price - close_price) * qty
            
        return round(pnl, 2), close_price

    async def check_win(self, id: str) -> dict:
        """Verifica el resultado de un trade específico ya cerrado consultando el cache."""
        for trade in self.closed_trades_cache:
            if str(trade['id']) == str(id):
                return {
                    "result": trade['result'],
                    "profit": trade['profit'],
                    "timestamp": trade['close_time']
                }
        # Si no está en cache, devolver un estado por defecto
        return {
            "result": "loss",
            "profit": 0.0,
            "timestamp": int(time.time())
        }

    async def clear_closed_deals(self) -> None:
        """Limpia el cache de trades cerrados en memoria."""
        self.closed_trades_cache.clear()
