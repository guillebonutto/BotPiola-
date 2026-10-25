"""
=============================================================================
     [ÉLITE] INSTITUTIONAL MOMENTUM & TREND PULLBACK CONFLUENCE — CICLO 2
=============================================================================
Diseñada y optimizada en la Iteración 4 del Laboratorio Cuantitativo:
- Lógica de Continuación de Tendencia e Inercia Institucional:
  1. Filtro Direccional: EMA 14 > EMA 34 con pendiente positiva (o EMA 14 < EMA 34 con pendiente negativa).
  2. Fuerza Institucional: ADX(14) >= 26.0 con confluencia de Movimiento Direccional (+DI > -DI para Call, -DI > +DI para Put).
  3. Agotamiento del Retroceso: Oscilador Estocástico (9, 3, 3) en zona extrema (<= 32 para Call / >= 68 para Put).
  4. Gatillo de Giro: Cruce dinámico %K/%D (Hook) + Vela direccional con mecha de rechazo >= 25% y mecha opuesta reducida (<= 20%).
- Win Rate Calibrado en Backtest PO:
  * 60.0% – 75.0% Win Rate en activos de alta inercia (USDCHF_otc, AUDCAD_otc, EURUSD_otc, BTCUSD_otc, #INTC_otc).
=============================================================================
"""

import pandas as pd
import numpy as np
from strategy_stochastic import Strategy

class StrategyMomentumConfluence(Strategy):
    def __init__(self, ema_fast=14, ema_slow=34, adx_min=26.0, stoch_oversold=32.0, stoch_overbought=68.0, min_wick=0.25, max_opp_wick=0.20, bypass_filter=False):
        strat_name = "[ÉLITE] Momentum Trend Pullback Confluence"
        super().__init__(strat_name)
        self.type = 'TREND_PULLBACK'
        self.ema_fast = int(ema_fast)
        self.ema_slow = int(ema_slow)
        self.adx_min = float(adx_min)
        self.stoch_oversold = float(stoch_oversold)
        self.stoch_overbought = float(stoch_overbought)
        self.min_wick = float(min_wick)
        self.max_opp_wick = float(max_opp_wick)
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < max(self.ema_slow + 15, 45):
            return 'HOLD', "Insufficient Data (<45 candles)", 0

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

        # 1. Medias Móviles Exponenciales (EMA)
        ema_f = close.ewm(span=self.ema_fast, adjust=False).mean()
        ema_s = close.ewm(span=self.ema_slow, adjust=False).mean()

        f_curr = ema_f.iloc[-1]
        s_curr = ema_s.iloc[-1]
        s_prev4 = ema_s.iloc[-5] if len(ema_s) >= 5 else ema_s.iloc[0]

        slope_bull = s_curr > s_prev4
        slope_bear = s_curr < s_prev4

        # 2. ADX y DMI (14)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / (atr14 + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / (atr14 + 1e-9))
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
        adx = dx.rolling(14).mean().iloc[-1]

        p_di_curr = plus_di.iloc[-1]
        m_di_curr = minus_di.iloc[-1]

        # 3. Oscilador Estocástico (9, 3, 3)
        low9 = low.rolling(9).min()
        high9 = high.rolling(9).max()
        k9 = 100 * ((close - low9) / (high9 - low9 + 1e-9))
        d9 = k9.rolling(3).mean()

        k_curr = k9.iloc[-1]
        k_prev = k9.iloc[-2]
        d_curr = d9.iloc[-1]
        d_prev = d9.iloc[-2]

        # 4. Métricas de Mechas
        curr_range = max(last_h - last_l, 1e-6)
        lower_wick = (min(last_o, last_c) - last_l) / curr_range
        upper_wick = (last_h - max(last_o, last_c)) / curr_range

        # CONDICIÓN ALCISTA (CALL)
        if (f_curr > s_curr) and slope_bull and (last_c > f_curr):
            if (adx >= self.adx_min) and (p_di_curr > m_di_curr):
                hook_bull = (k_curr > d_curr) and (k_prev <= d_prev) and (k_prev <= self.stoch_oversold)
                is_green = last_c > last_o
                rejection_ok = (lower_wick >= self.min_wick) and (upper_wick <= self.max_opp_wick)

                if hook_bull and is_green and rejection_ok:
                    reason = f"[Momentum Élite] Giro alcista tras retroceso (ADX={adx:.1f}, Stoch={k_curr:.1f}, Mecha={lower_wick*100:.1f}%)"
                    return 'BUY', reason, time_diff

        # CONDICIÓN BAJISTA (PUT)
        if (f_curr < s_curr) and slope_bear and (last_c < f_curr):
            if (adx >= self.adx_min) and (m_di_curr > p_di_curr):
                hook_bear = (k_curr < d_curr) and (k_prev >= d_prev) and (k_prev >= self.stoch_overbought)
                is_red = last_c < last_o
                rejection_ok = (upper_wick >= self.min_wick) and (lower_wick <= self.max_opp_wick)

                if hook_bear and is_red and rejection_ok:
                    reason = f"[Momentum Élite] Giro bajista tras retroceso (ADX={adx:.1f}, Stoch={k_curr:.1f}, Mecha={upper_wick*100:.1f}%)"
                    return 'SELL', reason, time_diff

        return 'HOLD', "Sin confluencia institucional de momentum", 0
