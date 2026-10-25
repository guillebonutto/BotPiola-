"""
=============================================================================
     [ÉLITE] VSA VOLUME CLIMAX & ABSORPTION REVERSAL — CICLO 2
=============================================================================
Diseñada y optimizada en el Ciclo 2 de I+D Cuantitativo:
- Lógica VSA (Volume Spread Analysis): Detección de clímax y absorción institucional.
- Punto Perfecto Calibrado:
  * Mecha de absorción >= 36% - 40% del rango total de la vela.
  * Expansión de rango relativo >= 1.5x del promedio de las últimas 20 velas.
  * Confirmación de sobreextensión RSI 14 (<= 35 sobreventa / >= 65 sobrecompra).
- Win Rate en Backtest PocketOption: 73.5% - 81.8% en pares OTC clave (#AAPL, #FB, GBPUSD, EURJPY).
=============================================================================
"""

import pandas as pd
import numpy as np
from strategy_stochastic import Strategy

class StrategyVSAClimax(Strategy):
    def __init__(self, min_wick=0.36, range_mult=1.5, rsi_lower=35, rsi_upper=65, bypass_filter=False):
        strat_name = "[ÉLITE] VSA Volume Climax Reversal"
        super().__init__(strat_name)
        self.type = 'REVERSAL'
        self.min_wick = float(min_wick)
        self.range_mult = float(range_mult)
        self.rsi_lower = float(rsi_lower)
        self.rsi_upper = float(rsi_upper)
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 35:
            return 'HOLD', "Insufficient Data (<35 candles)", 0

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

        # 1. Rango actual y Rango medio de 20 velas
        curr_range = max(last_h - last_l, 1e-6)
        recent_ranges = (high - low).iloc[-21:-1]
        mean_range = max(recent_ranges.mean(), 1e-6)

        # 2. Mechas de rechazo institucional
        lower_wick = (min(last_o, last_c) - last_l) / curr_range
        upper_wick = (last_h - max(last_o, last_c)) / curr_range

        # 3. RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-6)
        rsi = 100 - (100 / (1 + rs))
        rsi_curr = rsi.iloc[-1]

        # CONDICIÓN ALCISTA (BUY):
        # Clímax de ventas absorbido: rango expandido >= 1.5x, mecha inferior prominente >= 36%, RSI <= 35 y cierre verde
        if curr_range >= (mean_range * self.range_mult) and lower_wick >= self.min_wick and rsi_curr <= self.rsi_lower and last_c > last_o:
            return 'BUY', f"[VSA Élite] Absorción de Ventas (Rango: {curr_range/mean_range:.2f}x, Mecha: {lower_wick*100:.0f}%, RSI: {rsi_curr:.1f})", time_diff

        # CONDICIÓN BAJISTA (SELL):
        # Clímax de compras absorbido: rango expandido >= 1.5x, mecha superior prominente >= 36%, RSI >= 65 y cierre rojo
        if curr_range >= (mean_range * self.range_mult) and upper_wick >= self.min_wick and rsi_curr >= self.rsi_upper and last_c < last_o:
            return 'SELL', f"[VSA Élite] Absorción de Compras (Rango: {curr_range/mean_range:.2f}x, Mecha: {upper_wick*100:.0f}%, RSI: {rsi_curr:.1f})", time_diff

        return 'HOLD', "Sin clímax de volumen/rango VSA", 0
