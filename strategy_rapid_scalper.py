"""
=============================================================================
           RAPID SCALPER SUITE — ESTRATEGIAS DE ALTA FRECUENCIA
=============================================================================
Diseñadas para generar señales frecuentes, ágiles y con setups dinámicos:
1. Fast EMA Pullback Scalper (Micro-tendencias 9/21)
2. Stochastic Bollinger Burst (Rebotes y expansiones rápidas 5/3/3)
3. RSI Velocity Momentum (Impulsos rápidos RSI 7)
4. Micro Range Breakout (Ruptura rápida de micro-rangos de 3-5 velas)
=============================================================================
"""

import pandas as pd
import numpy as np
from strategy_stochastic import Strategy

class FastEMAPullbackScalper(Strategy):
    """
    Scalper rápido de micro-tendencia usando EMA 9 y EMA 21.
    Busca retrocesos inmediatos hacia la EMA 9 a favor de la tendencia corta.
    Frecuencia: ALTA (múltiples señales por hora).
    """
    def __init__(self, fast_period=9, slow_period=21, name=None):
        self.fast_period = fast_period
        self.slow_period = slow_period
        strat_name = name or f"Fast EMA Pullback ({fast_period}/{slow_period})"
        super().__init__(strat_name)
        self.type = 'TREND'
        self.is_dynamic = True

    def get_signal(self, df):
        if df.empty or len(df) < max(self.slow_period + 10, 35):
            return 'HOLD', "Data insuficiente", 0

        close = df['Close']
        high = df['High']
        low = df['Low']
        open_p = df['Open']

        ema_fast = close.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_period, adjust=False).mean()

        last = close.iloc[-1]
        prev = close.iloc[-2]
        last_open = open_p.iloc[-1]
        last_low = low.iloc[-1]
        last_high = high.iloc[-1]

        fast_curr = ema_fast.iloc[-1]
        slow_curr = ema_slow.iloc[-1]
        fast_prev = ema_fast.iloc[-2]

        # Determinar intervalo sugerido
        time_diff = 300
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # Condición Alcista: EMA Fast > EMA Slow, mecha o cuerpo tocó EMA Fast y rebotó cerrando verde
        if fast_curr > slow_curr:
            touched_ema = (last_low <= fast_curr * 1.0008) and (last > fast_curr)
            candle_green = last > last_open
            momentum_up = (last - last_open) > (abs(prev - open_p.iloc[-2]) * 0.7)
            if touched_ema and candle_green and momentum_up:
                return 'BUY', f"Pullback EMA {self.fast_period} alcista con rechazo", time_diff

        # Condición Bajista: EMA Fast < EMA Slow, mecha o cuerpo tocó EMA Fast y rechazó cerrando roja
        if fast_curr < slow_curr:
            touched_ema = (last_high >= fast_curr * 0.9992) and (last < fast_curr)
            candle_red = last < last_open
            momentum_down = (last_open - last) > (abs(prev - open_p.iloc[-2]) * 0.7)
            if touched_ema and candle_red and momentum_down:
                return 'SELL', f"Pullback EMA {self.fast_period} bajista con rechazo", time_diff

        return 'HOLD', "Sin pullback de micro-tendencia", 0


class StochasticBollingerBurst(Strategy):
    """
    Scalper de reversión y rebote rápido combinando Estocástico ultra-ágil (5,3,3)
    y bandas externas de Bollinger (14 periodos, 1.8 desviaciones).
    Frecuencia: ALTA.
    """
    def __init__(self, stoch_k=5, stoch_d=3, bb_window=14, bb_dev=1.8, name=None):
        self.stoch_k_period = stoch_k
        self.stoch_d_period = stoch_d
        self.bb_window = bb_window
        self.bb_dev = bb_dev
        strat_name = name or f"Stoch Burst ({stoch_k}/{stoch_d}) + BB({bb_window})"
        super().__init__(strat_name)
        self.type = 'REVERSAL'
        self.is_dynamic = True

    def get_signal(self, df):
        if df.empty or len(df) < max(self.bb_window + 10, 30):
            return 'HOLD', "Data insuficiente", 0

        close = df['Close']
        high = df['High']
        low = df['Low']
        open_p = df['Open']

        # Estocástico rápido
        low_min = low.rolling(window=self.stoch_k_period).min()
        high_max = high.rolling(window=self.stoch_k_period).max()
        denom = (high_max - low_min).replace(0, 0.00001)
        fast_k = 100 * ((close - low_min) / denom)
        k = fast_k.rolling(window=self.stoch_d_period).mean()
        d = k.rolling(window=self.stoch_d_period).mean()

        # Bandas de Bollinger rápidas
        sma_bb = close.rolling(window=self.bb_window).mean()
        std_bb = close.rolling(window=self.bb_window).std()
        upper_bb = sma_bb + (self.bb_dev * std_bb)
        lower_bb = sma_bb - (self.bb_dev * std_bb)

        k_curr, k_prev = k.iloc[-1], k.iloc[-2]
        d_curr, d_prev = d.iloc[-1], d.iloc[-2]
        c_curr, o_curr = close.iloc[-1], open_p.iloc[-1]

        time_diff = 300
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # Sobreventa extrema + cruce alcista K > D cerca o bajo banda inferior
        if (k_prev < 25 or k_curr < 25) and (k_curr > d_curr and k_prev <= d_prev):
            if low.iloc[-1] <= lower_bb.iloc[-1] or c_curr <= lower_bb.iloc[-1] * 1.001:
                return 'BUY', f"Cruce Estocástico rápido en sobreventa K={k_curr:.1f} con banda inferior", time_diff

        # Sobrecompra extrema + cruce bajista K < D cerca o sobre banda superior
        if (k_prev > 75 or k_curr > 75) and (k_curr < d_curr and k_prev >= d_prev):
            if high.iloc[-1] >= upper_bb.iloc[-1] or c_curr >= upper_bb.iloc[-1] * 0.999:
                return 'SELL', f"Cruce Estocástico rápido en sobrecompra K={k_curr:.1f} con banda superior", time_diff

        return 'HOLD', "Sin señal de oscilación extrema", 0


class RSIVelocityMomentum(Strategy):
    """
    RSI Rápido (7 o 9 periodos) con detección de aceleración de momentum.
    Entra cuando el RSI cruza con fuerza la zona neutral de 50 o rebota velozmente en 30/70.
    Frecuencia: ALTA.
    """
    def __init__(self, rsi_period=7, name=None):
        self.rsi_period = rsi_period
        strat_name = name or f"RSI Velocity ({rsi_period}p)"
        super().__init__(strat_name)
        self.type = 'MOMENTUM'
        self.is_dynamic = True

    def get_signal(self, df):
        if df.empty or len(df) < self.rsi_period + 15:
            return 'HOLD', "Data insuficiente", 0

        close = df['Close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/self.rsi_period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/self.rsi_period, adjust=False).mean()
        rs = gain / loss.replace(0, 0.00001)
        rsi = 100 - (100 / (1 + rs))

        curr_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        curr_close = close.iloc[-1]
        curr_open = df['Open'].iloc[-1]

        time_diff = 300
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # Disparo Alcista: Cruce con aceleración hacia arriba (>52 viniendo de <48) o rebote desde sobreventa (<30)
        cruce_arriba = (prev_rsi <= 50 and curr_rsi >= 53 and curr_close > curr_open)
        rebote_sobreventa = (prev_rsi < 32 and curr_rsi > 35 and curr_close > curr_open)
        if cruce_arriba or rebote_sobreventa:
            reason = "Aceleración RSI 50+" if cruce_arriba else f"Rebote sobreventa RSI ({curr_rsi:.1f})"
            return 'BUY', reason, time_diff

        # Disparo Bajista: Cruce con aceleración hacia abajo (<48 viniendo de >52) o rechazo desde sobrecompra (>70)
        cruce_abajo = (prev_rsi >= 50 and curr_rsi <= 47 and curr_close < curr_open)
        rebote_sobrecompra = (prev_rsi > 68 and curr_rsi < 65 and curr_close < curr_open)
        if cruce_abajo or rebote_sobrecompra:
            reason = "Aceleración RSI 50-" if cruce_abajo else f"Rechazo sobrecompra RSI ({curr_rsi:.1f})"
            return 'SELL', reason, time_diff

        return 'HOLD', "Sin impulso RSI suficiente", 0


class MicroRangeBreakout(Strategy):
    """
    Ruptura ágil de micro-rangos de las últimas N velas (ej. 4 a 6 velas).
    Dispara cuando una vela rompe con decisión el máximo o mínimo consolidado.
    Frecuencia: MUY ALTA.
    """
    def __init__(self, range_window=5, name=None):
        self.range_window = range_window
        strat_name = name or f"Micro Range Breakout ({range_window}v)"
        super().__init__(strat_name)
        self.type = 'BREAKOUT'
        self.is_dynamic = True

    def get_signal(self, df):
        if df.empty or len(df) < self.range_window + 10:
            return 'HOLD', "Data insuficiente", 0

        recent = df.iloc[-(self.range_window + 1):-1]
        last = df.iloc[-1]

        high_range = recent['High'].max()
        low_range = recent['Low'].min()
        body = abs(last['Close'] - last['Open'])
        avg_body = abs(recent['Close'] - recent['Open']).mean()

        time_diff = 300
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # Ruptura Alcista limpia
        if last['Close'] > high_range and last['Close'] > last['Open'] and body >= avg_body * 1.15:
            return 'BUY', f"Ruptura de micro-rango {self.range_window} velas al alza", time_diff

        # Ruptura Bajista limpia
        if last['Close'] < low_range and last['Close'] < last['Open'] and body >= avg_body * 1.15:
            return 'SELL', f"Ruptura de micro-rango {self.range_window} velas a la baja", time_diff

        return 'HOLD', "Dentro del micro-rango", 0
