from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategySmartMoneySMC(Strategy):
    """
    Estrategia Smart Money Concepts (SMC):
    --------------------------------------
    1. Detecta Fair Value Gaps (FVG / Imbalances).
    2. Identifica Order Blocks (OB) previos a un BOS (Break of Structure).
    3. Entrada cuando el precio retorna a rebalancear el FVG y toca el Order Block en zonas de Discount/Premium.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Smart Money Concepts (FVG + Order Block)")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        # Duración objetivo según el timeframe
        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        target_duration = time_diff if time_diff in [60, 300, 900, 3600] else 300

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        recent = df.iloc[-30:]

        # --- 1. Detección de Fair Value Gap (FVG / Imbalance) ---
        # Bullish FVG: Low de la vela actual (i) > High de la vela de hace 2 periodos (i-2)
        bullish_fvg = prev['Low'] > df.iloc[-4]['High'] if len(df) >= 4 else False
        
        # Bearish FVG: High de la vela actual (i) < Low de la vela de hace 2 periodos (i-2)
        bearish_fvg = prev['High'] < df.iloc[-4]['Low'] if len(df) >= 4 else False

        # --- 2. Detección de Estructura (Swing High / Low) ---
        high_max = recent['High'].max()
        low_min = recent['Low'].min()
        eq_price = (high_max + low_min) / 2.0  # Nivel 50% Equilibrium

        # --- 3. SEÑAL DE COMPRA (BULLISH SMC ENTRY) ---
        # Condición: El precio retrocede a la zona de DISCOUNT (< 50% del rango)
        # y toca la zona de Imbalance / Order Block previa
        if last['Close'] < eq_price:
            # Detectar si la vela anterior o actual rebalanceó un FVG alcista previo
            if bullish_fvg or (last['Low'] <= df.iloc[-4]['High'] and last['Close'] > last['Open']):
                # Confirmación de rechazo alcista en el Order Block
                if last['Close'] > last['Open'] and (last['Close'] - last['Open']) > (last['High'] - last['Low']) * 0.4:
                    return 'BUY', f"SMC Bullish: Rebalanceo FVG + Retorno a OB en Zona Discount (Bajo {eq_price:.4f})", target_duration

        # --- 4. SEÑAL DE VENTA (BEARISH SMC ENTRY) ---
        # Condición: El precio retrocede a la zona PREMIUM (> 50% del rango)
        # y toca el Imbalance bajista
        if last['Close'] > eq_price:
            if bearish_fvg or (last['High'] >= df.iloc[-4]['Low'] and last['Close'] < last['Open']):
                # Confirmación de rechazo bajista en el Order Block
                if last['Close'] < last['Open'] and (last['Open'] - last['Close']) > (last['High'] - last['Low']) * 0.4:
                    return 'SELL', f"SMC Bearish: Rebalanceo FVG + Rechazo en OB en Zona Premium (Sobre {eq_price:.4f})", target_duration

        return 'HOLD', "Sin confluencia SMC (No FVG/OB active)", 0
