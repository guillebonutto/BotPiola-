from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategySqueezeVolume(Strategy):
    """
    Estrategia Squeeze Expansion + Volume Spike (Impulso Institucional)
    ------------------------------------------------------------------
    Detecta compresión extrema de volatilidad (Bollinger Bandwidth bajo)
    seguida de una vela explosiva con volumen/rango superior al promedio.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Squeeze Expansion + Volume Spike")
        self.type = 'TREND'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        # Verificar que existan columnas requeridas o calcularlas sobre la marcha
        if 'BB_Width' not in df.columns:
            bb_upper = df['Close'].rolling(20).mean() + (df['Close'].rolling(20).std() * 2.0)
            bb_lower = df['Close'].rolling(20).mean() - (df['Close'].rolling(20).std() * 2.0)
            sma20 = df['Close'].rolling(20).mean()
            df['BB_Width'] = (bb_upper - bb_lower) / sma20

        recent = df.iloc[-25:]
        min_width = recent['BB_Width'].min()
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Comprensión extrema previa (Ancho de banda en el 30% inferior de las últimas 25 velas)
        is_squeezed = prev['BB_Width'] <= min_width * 1.35

        # 2. Rango de vela explosivo (Cuerpo de la vela actual > 1.8x del promedio del cuerpo de las últimas 10 velas)
        body = abs(last['Close'] - last['Open'])
        recent_bodies = abs(df['Close'].iloc[-11:-1] - df['Open'].iloc[-11:-1])
        avg_body = recent_bodies.mean()
        
        is_explosive = body >= (avg_body * 1.8) and body > 0.00005

        if not (is_squeezed and is_explosive):
            return 'HOLD', "No Squeeze Expansion", 0

        # Determinación de dirección (CALL/BUY o PUT/SELL)
        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        target_duration = time_diff if time_diff in [60, 300, 900] else 60

        # Confirmación Alcista
        if last['Close'] > last['Open'] and last['Close'] >= last.get('BB_Upper', last['Close']):
            stoch_k = last.get('Stoch_K', 50)
            if stoch_k > 50: # Estocástico acompañando impulso
                return 'BUY', f"Explosion Alcista post-compresion (Cuerpo {body:.5f} vs Avg {avg_body:.5f})", target_duration

        # Confirmación Bajista
        if last['Close'] < last['Open'] and last['Close'] <= last.get('BB_Lower', last['Close']):
            stoch_k = last.get('Stoch_K', 50)
            if stoch_k < 50:
                return 'SELL', f"Explosion Bajista post-compresion (Cuerpo {body:.5f} vs Avg {avg_body:.5f})", target_duration

        return 'HOLD', "Signal rejected by direction/stoch filters", 0
