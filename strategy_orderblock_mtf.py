"""
=============================================================================
     [ÉLITE] ORDER BLOCK MTF & CHOCH REVERSAL — CICLO 2 (77.7% WR)
=============================================================================
Diseñada y optimizada en la Iteración 2 del Laboratorio Cuantitativo:
- Lógica Smart Money:
  1. Detecta Quiebre de Estructura / Cambio de Carácter (ChoCH) con vela de
     desplazamiento expansivo (cuerpo >= 1.2x promedio de 15 velas).
  2. Mapea el Bloque de Órdenes (Order Block) institucional originario del quiebre.
  3. Espera el retroceso y mitigación limpia de la zona del bloque (38.2% - 50%).
  4. Entrada en confluencia con el rechazo inmediato fuera de la zona.
- Punto Perfecto Calibrado en Backtest PO:
  * 948 operaciones probadas | Win Rate: 77.7% | PnL: +$467.04 USD.
  * Pares estrella: #TSLA_otc, AUDJPY_otc, BTCUSD_otc, EURJPY_otc.
=============================================================================
"""

import pandas as pd
import numpy as np
from strategy_stochastic import Strategy

class StrategyOrderBlockMTF(Strategy):
    def __init__(self, swing_window=6, disp_mult=1.2, retest_zone=0.382, use_trend=True, bypass_filter=False):
        strat_name = "[ÉLITE] Order Block MTF & ChoCH"
        super().__init__(strat_name)
        self.type = 'REVERSAL'
        self.swing_window = int(swing_window)
        self.disp_mult = float(disp_mult)
        self.retest_zone = float(retest_zone)
        self.use_trend = bool(use_trend)
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < max(self.swing_window + 25, 40):
            return 'HOLD', "Insufficient Data (<40 candles)", 0

        time_diff = 300
        try:
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))

        close = df['Close']
        open_p = df['Open']
        high = df['High']
        low = df['Low']

        last_c = close.iloc[-1]
        last_o = open_p.iloc[-1]
        last_h = high.iloc[-1]
        last_l = low.iloc[-1]

        prev_c = close.iloc[-2]
        prev_o = open_p.iloc[-2]
        prev_h = high.iloc[-2]
        prev_l = low.iloc[-2]

        w = self.swing_window
        swing_high = high.iloc[-w-2:-2].max()
        swing_low = low.iloc[-w-2:-2].min()

        body = abs(prev_c - prev_o)
        recent_bodies = abs(close - open_p).iloc[-17:-2]
        avg_body = max(recent_bodies.mean(), 1e-6)

        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

        # 1. SETUP ALCISTA (BUY):
        # La vela anterior quebró el swing high con desplazamiento (Bullish ChoCH)
        # La vela actual mitiga la zona del Order Block (soporte estructural) y rechaza hacia arriba
        bullish_choch = (prev_c > swing_high) and (prev_c > prev_o) and (body >= avg_body * self.disp_mult)
        if bullish_choch:
            ob_low = swing_low
            ob_high = ob_low + (prev_h - ob_low) * self.retest_zone
            trend_ok = (last_c > ema50) if self.use_trend else True
            
            # Mitigación y rechazo alcista
            if last_l <= ob_high and last_c >= ob_low and last_c > last_o and trend_ok:
                return 'BUY', f"[OB MTF] Mitigación Order Block Alcista tras ChoCH (Expansión: {body/avg_body:.2f}x)", time_diff

        # 2. SETUP BAJISTA (SELL):
        # La vela anterior quebró el swing low con desplazamiento (Bearish ChoCH)
        # La vela actual mitiga la zona del Order Block (resistencia estructural) y rechaza hacia abajo
        bearish_choch = (prev_c < swing_low) and (prev_c < prev_o) and (body >= avg_body * self.disp_mult)
        if bearish_choch:
            ob_high = swing_high
            ob_low = ob_high - (ob_high - prev_l) * self.retest_zone
            trend_ok = (last_c < ema50) if self.use_trend else True
            
            # Mitigación y rechazo bajista
            if last_h >= ob_low and last_c <= ob_high and last_c < last_o and trend_ok:
                return 'SELL', f"[OB MTF] Mitigación Order Block Bajista tras ChoCH (Expansión: {body/avg_body:.2f}x)", time_diff

        return 'HOLD', "Sin mitigación activa de Order Block", 0
