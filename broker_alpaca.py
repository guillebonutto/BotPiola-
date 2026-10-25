import asyncio
import aiohttp
import logging
import json
import time
from datetime import datetime, timezone

logger = logging.getLogger("AlpacaAdapter")

def map_symbol_to_yfinance(symbol):
    """Mapea un símbolo del bot al ticker correspondiente en Yahoo Finance."""
    clean = symbol.replace("_otc", "").replace("#", "")
    # Forex
    if len(clean) == 6 and clean.isupper() and clean.isalpha() and not clean.endswith("USD") or clean in ["EURUSD", "GBPUSD", "USDJPY"]:
        return f"{clean}=X"
    # Crypto (terminan en USD y suelen tener 6-7 caracteres, ej: BTCUSD, ETHUSD)
    if clean.endswith("USD") and clean not in ["EURUSD", "GBPUSD"] and len(clean) >= 6:
        return f"{clean[:-3]}-USD"
    # Acciones o ETFs directos
    return clean

def map_symbol_to_alpaca(symbol):
    """Mapea un símbolo del bot al ticker correspondiente en Alpaca."""
    clean = symbol.replace("_otc", "").replace("#", "")
    # Crypto y Forex en Alpaca usan barra (ej: BTC/USD, EUR/USD)
    if (len(clean) == 6 and clean.isupper() and clean.isalpha()) or (clean.endswith("USD") and len(clean) >= 6):
        return f"{clean[:-3]}/{clean[-3:]}"
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
        # Control de enfriamiento para liquidaciones fallidas {symbol: timestamp}
        self.liquidation_cooldown = {}

    async def balance(self):
        """Obtiene el saldo disponible (cash) en la cuenta de Alpaca."""
        url = f"{self.base_url}/v2/account"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        # 'equity' representa el valor total real de la cuenta (Efectivo + Valor de Mercado de Acciones)
                        return float(data.get('equity') or data.get('portfolio_value') or data.get('cash', 0.0))
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
            price = await self._get_latest_price(asset)
            
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

        # 3. Calcular tamaño de la posición (cantidad de acciones/lotes) con Interés Compuesto
        mm_cfg = self.config.get('money_management', {})
        mm_mode = mm_cfg.get('mode', 'fixed')
        
        if mm_mode == 'compound':
            compound_pct = float(mm_cfg.get('compound_percentage', 0.025))
            try:
                curr_bal = await self.balance()
                if isinstance(curr_bal, (int, float)) and curr_bal > 0:
                    risk_per_trade = curr_bal * compound_pct
                    logger.info(f"[Alpaca] Interés compuesto activo: Saldo ${curr_bal:.2f} x {compound_pct*100:.1f}% = Riesgo ${risk_per_trade:.2f}")
                else:
                    risk_per_trade = float(self.config.get('risk_per_trade_usd', 25.0))
            except Exception as e:
                logger.warning(f"[Alpaca] Error calculando balance para interés compuesto: {e}")
                risk_per_trade = float(self.config.get('risk_per_trade_usd', 25.0))
        else:
            risk_per_trade = float(self.config.get('risk_per_trade_usd', 0.0))
        
        if risk_per_trade > 0:
            # Risk-Based Sizing: arriesgar una cantidad fija de dólares por operación
            qty = risk_per_trade / distancia_sl
        else:
            # Fixed Sizing: usar el monto nominal fijo definido
            qty = amount / price

        # --- LIMITES DE SEGURIDAD DE CAPITAL (Alpaca Exposure Protection) ---
        max_invested_capital = float(self.config.get('max_invested_capital_usd', 40000.0))
        max_trade_capital = float(self.config.get('max_trade_capital_usd', 15000.0))
        max_concurrent = int(self.config.get('max_concurrent_trades', 3))

        # 1. Comprobar operaciones concurrentes y capital ya invertido
        current_invested = await self.get_invested_capital()
        current_open_count = await self.get_open_positions_count()

        if current_open_count >= max_concurrent:
            logger.warning(f"[Alpaca] Limite de operaciones simultaneas alcanzado ({current_open_count}/{max_concurrent}). No se abre {ticker}.")
            return None, None

        if current_invested >= max_invested_capital:
            logger.warning(f"[Alpaca] Limite de capital invertido alcanzado (${current_invested:,.2f} >= ${max_invested_capital:,.2f}). No se abre {ticker}.")
            return None, None

        # 2. Limitar capital de esta operacion individual
        if (qty * price) > max_trade_capital:
            adjusted_qty = max_trade_capital / price
            logger.info(f"[Alpaca] Qty ajustada por limite de capital por operacion (${max_trade_capital:,.2f}): {qty:.4f} -> {adjusted_qty:.4f}")
            qty = adjusted_qty

        # 3. Comprobar que no sobrepase el capital total permitido
        remaining_cap = max_invested_capital - current_invested
        if (qty * price) > remaining_cap:
            adjusted_qty = remaining_cap / price
            if (adjusted_qty * price) < 50.0:
                logger.warning(f"[Alpaca] Capital disponible restante (${remaining_cap:,.2f}) insuficiente para abrir {ticker}.")
                return None, None
            logger.info(f"[Alpaca] Qty ajustada para respetar limite de capital total invertido (${max_invested_capital:,.2f}): {qty:.4f} -> {adjusted_qty:.4f}")
            qty = adjusted_qty
            
        allow_fractional = self.config.get('allow_fractional', True)
        if allow_fractional:
            qty = round(qty, 4)
        else:
            qty = int(qty)
            if qty == 0:
                qty = 1

        # 4. Construir payload de Orden adaptado a Alpaca
        is_crypto = "/" in ticker and ticker.split("/")[0] not in ["EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY"]
        
        # REGLA ALPACA & FINRA: Prohibido vender en corto acciones fraccionadas ("fractional orders cannot be sold short")
        if side.lower() == "sell" and not is_crypto:
            has_long = any(
                t.get('symbol') == ticker and t.get('side', '').lower() == 'buy' and t.get('status') == 'active'
                for t in self.active_trades.values()
            )
            if not has_long:
                # Es una venta en corto (short)
                if int(qty) < 1:
                    logger.warning(f"[Alpaca] Venta en corto (SELL) en {ticker} omitida: Alpaca prohíbe ventas en corto fraccionadas (calculado: {qty:.4f} acciones, requiere >= 1).")
                    return None, None
                qty = int(qty)

        is_fractional = (qty != int(qty))
        
        if is_fractional or is_crypto:
            # Alpaca requiere time_in_force='day' para fraccionadas y 'gtc' para crypto. No permite bracket en crypto ni fracciones.
            payload = {
                "symbol": ticker,
                "qty": str(qty),
                "side": side,
                "type": "market",
                "time_in_force": "gtc" if is_crypto else "day"
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
                        if "insufficient balance" in error_msg:
                            logger.warning(f"[Alpaca] Saldo insuficiente en la cuenta para operar {ticker}. Operación cancelada limpiamente.")
                            return None, None
                        if "cannot be sold short" in error_msg:
                            logger.warning(f"[Alpaca] Venta en corto no permitida para {ticker} por Alpaca.")
                            return None, None
                        logger.error(f"Error colocando orden en Alpaca: HTTP {r.status} - {error_msg}")
                        raise ConnectionError(f"Error en Alpaca: {error_msg}")
        except Exception as e:
            if "insufficient balance" in str(e) or "cannot be sold short" in str(e):
                return None, None
            logger.error(f"Excepción colocando orden en Alpaca: {e}")
            raise

    async def _get_latest_price(self, ticker: str) -> float:
        """Obtiene el último precio de un ticker en Alpaca directamente."""
        # ticker viene en formato Alpaca (ej: 'SOL/USD' o 'AAPL')
        is_crypto = "/" in ticker
        
        if is_crypto:
            url = f"https://data.alpaca.markets/v1beta3/crypto/us/latest/trades?symbols={ticker}"
        else:
            url = f"https://data.alpaca.markets/v2/stocks/trades/latest?symbols={ticker}"
            
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        trades = data.get("trades", {})
                        if ticker in trades:
                            return float(trades[ticker].get("p", 0.0))
        except Exception as e:
            logger.error(f"[Alpaca] Error obteniendo precio en tiempo real de {ticker}: {e}")

        # Fallback a Yahoo Finance (quitamos el / para yfinance)
        asset_for_yahoo = ticker.replace("/", "")
        candles = await download_yahoo_candles(asset_for_yahoo, 60, 2)
        if candles:
            return float(candles[-1]['close'])
        return 0.0

    async def get_invested_capital(self) -> float:
        """Devuelve el capital total actualmente invertido en posiciones abiertas en Alpaca."""
        url_pos = f"{self.base_url}/v2/positions"
        total_invested = 0.0
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_pos, timeout=10) as r:
                    if r.status == 200:
                        positions = await r.json()
                        for p in positions:
                            total_invested += abs(float(p.get("market_value", 0.0)))
                        return total_invested
        except Exception as e:
            logger.error(f"[Alpaca] Error consultando posiciones para capital invertido: {e}")
        
        # Fallback usando self.active_trades en memoria
        for t in self.active_trades.values():
            if t.get('status', 'active') == 'active':
                qty = float(t.get('qty', 0.0))
                entry_p = float(t.get('entry_price', 0.0))
                total_invested += abs(qty * entry_p)
        return total_invested

    async def get_open_positions_count(self) -> int:
        """Devuelve la cantidad de posiciones activas/abiertas en Alpaca."""
        url_pos = f"{self.base_url}/v2/positions"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_pos, timeout=10) as r:
                    if r.status == 200:
                        positions = await r.json()
                        return len(positions)
        except Exception as e:
            logger.error(f"[Alpaca] Error consultando cantidad de posiciones: {e}")
        return len([t for t in self.active_trades.values() if t.get('status', 'active') == 'active'])

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
        pos_fetch_success = False
        url_pos = f"{self.base_url}/v2/positions"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_pos, timeout=10) as r:
                    if r.status == 200:
                        positions_list = await r.json()
                        open_positions = {pos['symbol']: pos for pos in positions_list}
                        pos_fetch_success = True
                    else:
                        logger.warning(f"Error consultando posiciones en Alpaca: HTTP {r.status}")
        except Exception as pos_err:
            logger.error(f"Excepción obteniendo posiciones de Alpaca: {pos_err}")

        # Si la consulta de posiciones falló por red/API, NO evaluar cierres para evitar falsos positivos
        if not pos_fetch_success:
            return []

        # 1.5. Sincronizar posiciones existentes en Alpaca que no estén en memoria (ej: tras reinicio)
        for sym, pos in open_positions.items():
            already_tracked = any(t.get('symbol') == sym for t in self.active_trades.values())
            if not already_tracked:
                fake_id = f"alpaca_sync_{sym}"
                entry_p = float(pos.get('avg_entry_price', 0.0))
                qty_val = float(pos.get('qty', 0.0))
                side_val = "buy" if pos.get('side', 'long') == 'long' else "sell"
                
                tp_mult = float(self.config.get('take_profit_atr_multiplier', 2.0))
                sl_mult = float(self.config.get('stop_loss_atr_multiplier', 1.5))
                # Distancia porcentual razonable según configuración
                tp_p = round(entry_p * (1.0 + (tp_mult * 0.01) if side_val == "buy" else 1.0 - (tp_mult * 0.01)), 2)
                sl_p = round(entry_p * (1.0 - (sl_mult * 0.01) if side_val == "buy" else 1.0 + (sl_mult * 0.01)), 2)
                
                self.active_trades[fake_id] = {
                    "symbol": sym,
                    "pair": sym,
                    "qty": qty_val,
                    "side": side_val,
                    "entry_price": entry_p,
                    "stop_loss": sl_p,
                    "take_profit": tp_p,
                    "start_time": current_time,
                    "duration": int(self.config.get('holding_period_seconds', 14400)),
                    "amount": round(qty_val * entry_p, 2),
                    "status": "active"
                }
                logger.info(f"[Alpaca] Posición abierta previa de {sym} ({qty_val} acciones) sincronizada con ID estable {fake_id}.")

        # 2. Iterar sobre nuestros trades en memoria
        active_ids = list(self.active_trades.keys())
        for order_id in active_ids:
            trade = self.active_trades.get(order_id)
            if not trade:
                continue
            symbol = trade['symbol']
            pair = trade['pair']
            
            # 2.1 Verificar si la orden de entrada se ejecutó o fue cancelada/rechazada
            if not order_id.startswith("alpaca_sync_"):
                entry_order = await self._get_order(order_id)
                if entry_order:
                    o_status = str(entry_order.get('status', '')).lower()
                    filled_qty = float(entry_order.get('filled_qty') or 0.0)
                    if o_status in ['canceled', 'cancelled', 'rejected', 'expired'] and filled_qty == 0:
                        logger.info(f"[Alpaca] Orden {order_id} ({symbol}) fue {o_status} sin ejecución en Alpaca. Descartando de memoria.")
                        del self.active_trades[order_id]
                        continue
                    if filled_qty > 0 and entry_order.get('filled_avg_price'):
                        trade['entry_price'] = float(entry_order['filled_avg_price'])
                        trade['qty'] = filled_qty

            # Soporte de coincidencia para tickers con o sin barra (ej: ETH/USD vs ETHUSD)
            is_position_open = (symbol in open_positions) or (symbol.replace('/', '') in open_positions)
            time_elapsed = current_time - trade['start_time']
            should_force_close = (trade.get('duration', 0) > 0) and (time_elapsed >= trade['duration'])
            
            # Caso A: El TP o el SL se activaron solos en la nube (la posición ya se cerró en Alpaca)
            if not is_position_open:
                # Recuperar detalles del cierre y calcular PnL
                pnl, close_price = await self._get_closed_trade_details(symbol, trade['side'], trade['entry_price'], trade['qty'], trade.get('start_time'))
                if close_price <= 0:
                    if time_elapsed > 14400: # Más de 4 horas huérfana
                        logger.warning(f"[Alpaca] {symbol} no figura en Alpaca y excedió 4h de antigüedad. Removiendo posición fantasma de memoria.")
                        del self.active_trades[order_id]
                    else:
                        logger.warning(f"[Alpaca] {symbol} no figura en abiertas pero tampoco tiene orden de salida ejecutada. Manteniendo en memoria.")
                    continue
                
                closed_item = {
                    "id": order_id,
                    "asset": pair,
                    "profit": pnl,
                    "result": "win" if pnl > 0 else "loss",
                    "close_time": int(current_time),
                    "close_price": close_price
                }
                newly_closed.append(closed_item)
                self.closed_trades_cache.append(closed_item)
                del self.active_trades[order_id]
                logger.info(f"[Alpaca] Trade {order_id} de {symbol} CERRADO por SL/TP en broker. PnL: ${pnl:.2f} | Precio Cierre: {close_price}")
                
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
                    
                    # 1. Si ya se envió una orden de liquidación previamente, comprobar si ya se ejecutó
                    pending_liq_id = trade.get('liquidation_order_id')
                    if pending_liq_id:
                        liq_order = await self._get_order(pending_liq_id)
                        if liq_order and liq_order.get('status') == 'filled':
                            close_p = float(liq_order.get('filled_avg_price', curr_price))
                            pnl = (close_p - entry_price) * trade['qty'] if side == "buy" else (entry_price - close_p) * trade['qty']
                            closed_item = {
                                "id": order_id,
                                "asset": pair,
                                "profit": round(pnl, 2),
                                "result": "win" if pnl > 0 else "loss",
                                "close_time": int(current_time),
                                "close_price": close_p
                            }
                            newly_closed.append(closed_item)
                            self.closed_trades_cache.append(closed_item)
                            open_positions.pop(symbol, None)
                            del self.active_trades[order_id]
                            logger.info(f"[Alpaca] ✅ Orden de salida {pending_liq_id} de {symbol} COMPLETADA @ ${close_p:.2f}. PnL: ${pnl:+.2f} USD")
                            continue
                        elif liq_order and liq_order.get('status') in ['new', 'accepted', 'pending_new', 'partially_filled']:
                            # La orden sigue en cola en Alpaca (ej: esperando apertura de mercado)
                            # NO cancelar ni spamear nuevas órdenes repetidas
                            continue
                        else:
                            # Orden cancelada o fallida, limpiar id para permitir reintento
                            trade.pop('liquidation_order_id', None)

                    # Comprobar cooldown si un intento previo de liquidación falló
                    last_fail = self.liquidation_cooldown.get(symbol, 0)
                    if current_time - last_fail < 60:
                        continue  # Evitar reintentos continuos si la red o API falló

                    logger.info(f"[Alpaca] 🎯 Solicitando liquidación de {symbol} por {exit_reason} (Precio: ${curr_price:.2f} | Entrada: ${entry_price:.2f})...")
                    
                    # Liquidar en Alpaca cancelando órdenes bracket abiertas
                    close_url = f"{self.base_url}/v2/positions/{symbol}?cancel_orders=true"
                    try:
                        async with aiohttp.ClientSession(headers=self.headers) as session:
                            async with session.delete(close_url, timeout=15) as r:
                                if r.status in [200, 201]:
                                    res_data = await r.json()
                                    liq_order_id = res_data.get('id') if isinstance(res_data, dict) else None
                                    if liq_order_id:
                                        trade['liquidation_order_id'] = liq_order_id
                                    
                                    # Si se ejecutó inmediatamente (mercado abierto)
                                    if isinstance(res_data, dict) and res_data.get('status') == 'filled':
                                        close_p = float(res_data.get('filled_avg_price', curr_price))
                                        pnl = (close_p - entry_price) * trade['qty'] if side == "buy" else (entry_price - close_p) * trade['qty']
                                        closed_item = {
                                            "id": order_id,
                                            "asset": pair,
                                            "profit": round(pnl, 2),
                                            "result": "win" if pnl > 0 else "loss",
                                            "close_time": int(current_time),
                                            "close_price": close_p
                                        }
                                        newly_closed.append(closed_item)
                                        self.closed_trades_cache.append(closed_item)
                                        open_positions.pop(symbol, None)
                                        del self.active_trades[order_id]
                                        logger.info(f"[Alpaca] Posición de {symbol} liquidada inmediatamente @ ${close_p:.2f}. PnL: ${pnl:+.2f} USD")
                                    else:
                                        logger.info(f"[Alpaca] Orden de salida para {symbol} enviada (ID: {liq_order_id}, Estado: {res_data.get('status') if isinstance(res_data, dict) else 'pending'}). Esperando ejecución en mercado.")
                                    self.liquidation_cooldown.pop(symbol, None)
                                else:
                                    err_txt = await r.text()
                                    logger.error(f"[Alpaca] Error liquidando {symbol}: HTTP {r.status} - {err_txt}")
                                    self.liquidation_cooldown[symbol] = current_time
                    except Exception as e:
                        logger.error(f"Error liquidando {symbol}: {e}")
                        self.liquidation_cooldown[symbol] = current_time

        # Retornar los cerrados en este escaneo
        return newly_closed

    async def _get_order(self, order_id: str) -> dict:
        """Consulta el estado de una orden específica en Alpaca."""
        url = f"{self.base_url}/v2/orders/{order_id}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10) as r:
                    if r.status == 200:
                        return await r.json()
        except Exception as e:
            logger.error(f"Error consultando orden {order_id} en Alpaca: {e}")
        return None

    async def _get_closed_trade_details(self, symbol: str, side: str, entry_price: float, qty: float, start_time: float = None) -> tuple[float, float]:
        """Consulta los detalles de las órdenes completadas para determinar el precio de cierre y PnL."""
        sym_query = f"{symbol},{symbol.replace('/', '')}" if '/' in symbol else symbol
        url_orders = f"{self.base_url}/v2/orders?status=closed&symbols={sym_query}&limit=20&direction=desc"
        close_price = 0.0
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url_orders, timeout=10) as r:
                    if r.status == 200:
                        orders = await r.json()
                        # Buscar la orden de salida (debe tener el side opuesto al de entrada)
                        norm_side = side.lower()
                        target_side = "sell" if norm_side == "buy" else "buy"
                        exit_orders = []
                        for o in orders:
                            if o.get('side') == target_side and o.get('filled_avg_price'):
                                if start_time:
                                    f_time_str = o.get('filled_at') or o.get('submitted_at')
                                    if f_time_str:
                                        try:
                                            dt = datetime.fromisoformat(f_time_str.replace('Z', '+00:00'))
                                            if dt.timestamp() < (start_time - 60):
                                                continue
                                        except Exception:
                                            pass
                                exit_orders.append(o)
                        
                        if exit_orders:
                            # Tomar la más reciente
                            close_price = float(exit_orders[0]['filled_avg_price'])
        except Exception as e:
            logger.error(f"Error recuperando detalles de cierre de orden para {symbol}: {e}")
            
        # Si no hay orden de salida ejecutada en Alpaca, no inventar precio de cierre
        if close_price <= 0:
            logger.warning(f"[Alpaca] No se encontró orden de salida completada en Alpaca para {symbol}.")
            return 0.0, 0.0

        # Calcular P&L real de la orden de salida ejecutada
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
