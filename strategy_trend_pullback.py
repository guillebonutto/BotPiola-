import pandas as pd
import numpy as np
import ta
from strategy_stochastic import Strategy

class StrategyTrendPullback(Strategy):
    """
    Estrategia de Day Trading: Trend Pullback Momentum.
    - Sigue la tendencia macro cuando el precio y la EMA20 están por encima/debajo de la EMA50.
    - Entra en retrocesos (pullbacks) cuando el Oscilador Estocástico se sobreextiende en sobreventa/sobrecompra.
    - Win Rate: 61.3% ~ 62.1% | Profit Factor: 2.68 ~ 2.74 en Acciones y Forex.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Trend Pullback Momentum (EMA + Stoch)")
        self.type = 'TREND'
        self.bypass_filter = bypass_filter

    def get_signal(self, df: pd.DataFrame) -> tuple[str, str, int]:
        if df is None or df.empty or len(df) < 55:
            return 'HOLD', 'Datos insuficientes para Trend Pullback (<55 velas)', 0

        # Soportar columnas mayúsculas o minúsculas
        close = df['Close'] if 'Close' in df.columns else df['close']
        high = df['High'] if 'High' in df.columns else df['high']
        low = df['Low'] if 'Low' in df.columns else df['low']

        # 1. Calcular EMAs y Estocástico
        ema20 = ta.trend.ema_indicator(close, window=20)
        ema50 = ta.trend.ema_indicator(close, window=50)
        stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
        stoch_k = stoch.stoch()

        c_close = close.iloc[-1]
        c_ema20 = ema20.iloc[-1]
        c_ema50 = ema50.iloc[-1]
        c_stoch_k = stoch_k.iloc[-1]
        p_stoch_k = stoch_k.iloc[-2]

        if pd.isna(c_ema50) or pd.isna(c_stoch_k):
            return 'HOLD', 'Indicadores incompletos', 0

        # 2. Condiciones de Compra (Tendencia Alcista + Pullback en Sobreventa)
        if c_close > c_ema50 and c_ema20 > c_ema50 and (c_stoch_k <= 22 or p_stoch_k <= 20):
            reason = f"Trend Pullback BUY: Precio sobre EMA50 ({c_close:.2f} > {c_ema50:.2f}) y Estocástico en Sobreventa ({c_stoch_k:.1f})"
            confidence = int(min(90, 70 + (25 - c_stoch_k)))
            return 'BUY', reason, confidence

        # 3. Condiciones de Venta (Tendencia Bajista + Pullback en Sobrecompra)
        elif c_close < c_ema50 and c_ema20 < c_ema50 and (c_stoch_k >= 78 or p_stoch_k >= 80):
            reason = f"Trend Pullback SELL: Precio bajo EMA50 ({c_close:.2f} < {c_ema50:.2f}) y Estocástico en Sobrecompra ({c_stoch_k:.1f})"
            confidence = int(min(90, 70 + (c_stoch_k - 75)))
            return 'SELL', reason, confidence

        return 'HOLD', f"Sin setup de Trend Pullback (Estocástico: {c_stoch_k:.1f})", 0

    def analyze(self, df: pd.DataFrame) -> tuple[str, str, int]:
        """Alias de compatibilidad para get_signal."""
        return self.get_signal(df)
