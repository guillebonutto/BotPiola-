from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategyChartistPatterns(Strategy):
    """
    Estrategia Experta Chartist Master (Cuñas y Triángulos):
    --------------------------------------------------------
    Especializada en rupturas y reversiones de patrones geométricos:
    1. Triángulos Ascendentes (Resistencia plana + mínimos crecientes).
    2. Triángulos Descendentes (Soporte plano + máximos decrecientes).
    3. Cuñas Ascendentes (Rising Wedge - Reversión bajista).
    4. Cuñas Descendentes (Falling Wedge - Reversión alcista).
    """
    def __init__(self, bypass_filter=True):
        super().__init__("Chartist Master (Wedges & Triangles)")
        self.type = 'BREAKOUT'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        # Matriz Aprobada de Cuñas y Triángulos con Alta Precisión (72.7% - 85.0% WR)
        allowed_combinations = {
            ("USDCHF_otc", 300),   # 72.7% WR (8 WIN / 3 LOSS)
            ("AUDCAD_otc", 3600),  # 70.0% WR (7 WIN / 3 LOSS)
            ("EURGBP_otc", 3600),  # 70.0% WR (7 WIN / 3 LOSS)
            ("#AAPL_otc", 900),    # 70.0% WR (7 WIN / 3 LOSS)
        }

        pair_tf = (pair, time_diff)
        if not self.bypass_filter and pair_tf not in allowed_combinations:
            return 'HOLD', f"Patrones Chartistas deshabilitados para {pair} en {time_diff}s", 0

        target_duration = time_diff if time_diff in [60, 300, 900, 1800, 3600] else 300
        w = 15
        
        recent = df.iloc[-w:]
        highs = recent['High'].values
        lows = recent['Low'].values
        closes = recent['Close'].values
        opens = recent['Open'].values

        last_close = closes[-1]
        last_open = opens[-1]

        high_max = highs[:-1].max()
        high_min = highs[:-1].min()
        low_max = lows[:-1].max()
        low_min = lows[:-1].min()

        res_flat = (high_max - high_min) < (last_close * 0.0025)
        sup_flat = (low_max - low_min) < (last_close * 0.0025)

        lows_rising = lows[-2] > lows[0]
        highs_falling = highs[-2] < highs[0]

        range_wide = highs[0] - lows[0]
        range_narrow = highs[-2] - lows[-2]
        wedge_compress = range_wide > range_narrow * 1.3

        # 🟢 1. TRIÁNGULO ASCENDENTE (BREAKOUT BUY)
        if res_flat and lows_rising and last_close > high_max and last_close > last_open:
            return 'BUY', f"Ascending Triangle Breakout (Resistencia: {high_max:.4f})", target_duration

        # 🔴 2. TRIÁNGULO DESCENDENTE (BREAKOUT SELL)
        if sup_flat and highs_falling and last_close < low_min and last_close < last_open:
            return 'SELL', f"Descending Triangle Breakout (Soporte: {low_min:.4f})", target_duration

        # 🟢 3. CUÑA DESCENDENTE (FALLING WEDGE - BULLISH REVERSAL)
        if wedge_compress and highs_falling and last_close > high_max and last_close > last_open:
            return 'BUY', f"Falling Wedge Bullish Reversal", target_duration

        # 🔴 4. CUÑA ASCENDENTE (RISING WEDGE - BEARISH REVERSAL)
        if wedge_compress and lows_rising and last_close < low_min and last_close < last_open:
            return 'SELL', f"Rising Wedge Bearish Reversal", target_duration

        return 'HOLD', "Sin patrón de cuña o triángulo activo", 0
