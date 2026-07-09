from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategyExpertVision(Strategy):
    def __init__(self, bypass_filter=False):
        super().__init__("Expert Vision Donchian Reversion")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0
            
        # Filtro de activación por par y temporalidad según backtest maestro (Restricción estricta >=58% WR)
        allowed_combinations = {
            ("#PFE_otc", 900),     # WR: 58.82% (17 trades)
        }
        
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            time_diff = 60 # Default a 1m
            
        pair_tf = (pair, time_diff)
        if not self.bypass_filter and pair_tf not in allowed_combinations:
            return 'HOLD', f"ExpertVision deshabilitada para {pair} en {time_diff}s (Bajo Win Rate historico)", 0
            
        last = df.iloc[-1]
        
        # 1. Calcular el canal Donchian de 20 períodos con shift 1 (para evitar lookahead bias)
        high_shift = df['High'].shift(1)
        low_shift = df['Low'].shift(1)
        
        upper_channel = high_shift.rolling(20).max().iloc[-1]
        lower_channel = low_shift.rolling(20).min().iloc[-1]
        
        # 2. Calcular filtro de volumen de rango (Price Range Ratio) para evitar volatilidad extrema (Breakouts)
        ranges = df['High'] - df['Low']
        avg_range_10 = ranges.shift(1).rolling(10).mean().iloc[-1]
        current_range = ranges.iloc[-1]
        range_ratio = current_range / avg_range_10 if avg_range_10 > 0 else 1.0
        range_spike = range_ratio > 1.5
        
        # 3. Filtro de Tendencia (EMA 50 en la temporalidad actual como "Escalera")
        ema_50 = last['EMA_50']
        low_val = last['Low']
        high_val = last['High']
        close_val = last['Close']
        
        is_uptrend = low_val >= ema_50  # Filtro Escalera alcista (compras arriba de la EMA)
        is_downtrend = high_val <= ema_50 # Filtro Escalera bajista (ventas abajo de la EMA)
        
        # Short-term trend filter (avoid counter-trend entries in high momentum)
        short_term_bullish = close_val > last.get('EMA_20', close_val) and last.get('RSI', 50) > 50
        short_term_bearish = close_val < last.get('EMA_20', close_val) and last.get('RSI', 50) < 50
        
        # Condición BUY: Toca el suelo, sin spike de rango, con filtro escalera alcista y sin micro-tendencia bajista
        if low_val <= lower_channel and not range_spike and is_uptrend and not short_term_bearish:
            return 'BUY', f"Suelo Tocado ({low_val:.5f} <= {lower_channel:.5f}) + Volatilidad Segura ({range_ratio:.2f}x) + Escalera Confirmada", 300
            
        # Condición SELL: Toca el techo, sin spike de rango, con filtro escalera bajista y sin micro-tendencia alcista
        if high_val >= upper_channel and not range_spike and is_downtrend and not short_term_bullish:
            return 'SELL', f"Techo Tocado ({high_val:.5f} >= {upper_channel:.5f}) + Volatilidad Segura ({range_ratio:.2f}x) + Escalera Confirmada", 300
            
        # Mensaje informativo de HOLD
        status_msg = f"Rango Donchian: [{lower_channel:.5f}, {upper_channel:.5f}] | Price: {close_val:.5f} | Spike Ratio: {range_ratio:.2f}x"
        return 'HOLD', status_msg, 0
