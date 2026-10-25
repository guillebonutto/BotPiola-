"""
=============================================================================
    SMART MONEY LIQUIDITY SWEEP & FAIR VALUE GAP (FVG) REVERSAL STRATEGY
=============================================================================
Estrategia Cuantitativa de Precisión Institucional:
1. Liquidity Sweep (Toma de Liquidez):
   - El precio barre los máximos/mínimos recientes (Swing High / Swing Low)
     donde residen los Stop Loss y órdenes pendientes del retail.
   - La vela rechaza con una mecha prominente (min_wick_ratio >= 30%) y
     cierra nuevamente dentro del rango previo.
2. Fair Value Gap (FVG / Desequilibrio Institucional):
   - Detecta desequilibrios no cubiertos de 3 velas en la dirección del rechazo.
3. Confluencia Multi-Indicador:
   - Filtro de sobreextensión RSI (sobreventa para BUY, sobrecompra para SELL).
   - Confirmación de dirección de cuerpo o momentum inmediato.
4. Parámetros Auto-Optimizables (Evolución Dinámica en Paper):
   - swing_window: 10 a 25 velas.
   - min_wick_ratio: 0.25 a 0.45 (proporción de rechazo).
   - fvg_lookback: 3 a 8 velas.
   - rsi_filter_enabled: True / False.
=============================================================================
"""

import pandas as pd
import numpy as np
from strategy_stochastic import Strategy

class StrategyLiquidityFVG(Strategy):
    def __init__(self, swing_window=15, min_wick_ratio=0.32, fvg_lookback=5, rsi_filter_enabled=True, name=None):
        self.swing_window = int(swing_window)
        self.min_wick_ratio = float(min_wick_ratio)
        self.fvg_lookback = int(fvg_lookback)
        self.rsi_filter_enabled = bool(rsi_filter_enabled)
        
        strat_name = name or f"[SMC] Liquidity Sweep & FVG (W{self.swing_window}/M{int(self.min_wick_ratio*100)})"
        super().__init__(strat_name)
        self.type = 'REVERSAL'
        self.is_dynamic = True

    def get_signal(self, df):
        if df.empty or len(df) < max(self.swing_window + 15, 45):
            return 'HOLD', "Data insuficiente para Liquidity/FVG", 0

        close = df['Close']
        high = df['High']
        low = df['Low']
        open_p = df['Open']

        # Temporalidad dinámica de expiración sugerida
        time_diff = 300
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # 1. Detección de Swing High y Swing Low institucional en la ventana previa
        w = self.swing_window
        swing_high = high.iloc[-w-1:-1].max()
        swing_low = low.iloc[-w-1:-1].min()

        last_c = close.iloc[-1]
        last_o = open_p.iloc[-1]
        last_h = high.iloc[-1]
        last_l = low.iloc[-1]
        total_range = max(last_h - last_l, 1e-6)

        # Cálculo de mechas de rechazo
        lower_wick = min(last_o, last_c) - last_l
        upper_wick = last_h - max(last_o, last_c)
        lower_wick_ratio = lower_wick / total_range
        upper_wick_ratio = upper_wick / total_range

        # 2. Detección de FVG reciente (últimas velas)
        # FVG Alcista: Low[i] > High[i-2] (hueco entre mechas)
        # FVG Bajista: High[i] < Low[i-2]
        bullish_fvg = False
        bearish_fvg = False
        max_look = min(len(df), self.fvg_lookback + 2)
        for i in range(2, max_look):
            idx = -i
            if low.iloc[idx] > high.iloc[idx - 2]:
                bullish_fvg = True
            if high.iloc[idx] < low.iloc[idx - 2]:
                bearish_fvg = True

        # 3. Confluencia RSI
        rsi_val = 50.0
        if 'RSI' in df.columns:
            rsi_val = float(df['RSI'].iloc[-1])
        else:
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / (loss + 1e-6)
            rsi_s = 100 - (100 / (1 + rs))
            rsi_val = float(rsi_s.iloc[-1]) if not rsi_s.empty and not pd.isna(rsi_s.iloc[-1]) else 50.0

        # --- SETUP ALCISTA (BUY) ---
        # El precio barrió por debajo de swing_low pero cerró ARRIBA de él con rechazo
        sweep_ssl = (last_l < swing_low) and (last_c >= swing_low) and (lower_wick_ratio >= self.min_wick_ratio)
        rsi_bull_ok = (rsi_val <= 45.0) if self.rsi_filter_enabled else True

        if sweep_ssl and rsi_bull_ok and (bullish_fvg or last_c > last_o):
            return 'BUY', f"Barrido SSL ({lower_wick_ratio*100:.0f}% mecha) + FVG Alcista", time_diff

        # --- SETUP BAJISTA (SELL) ---
        # El precio barrió por encima de swing_high pero cerró ABAJO de él con rechazo
        sweep_bsl = (last_h > swing_high) and (last_c <= swing_high) and (upper_wick_ratio >= self.min_wick_ratio)
        rsi_bear_ok = (rsi_val >= 55.0) if self.rsi_filter_enabled else True

        if sweep_bsl and rsi_bear_ok and (bearish_fvg or last_c < last_o):
            return 'SELL', f"Barrido BSL ({upper_wick_ratio*100:.0f}% mecha) + FVG Bajista", time_diff

        return 'HOLD', "Sin setup de liquidez/FVG", 0
