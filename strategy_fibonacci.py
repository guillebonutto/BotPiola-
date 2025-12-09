from strategy_stochastic import Strategy
import numpy as np

class StrategyFibonacci(Strategy):
    def __init__(self):
        super().__init__("Fibonacci Retracement 61.8%")
        
    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', None, 0
            
        # Detectar el último impulso grande
        # Buscamos min y max recientes (window 50)
        window = df.iloc[-50:]
        high_price = window['High'].max()
        low_price = window['Low'].min()
        
        current_price = df.iloc[-1]['Close']
        trend_sma = df.iloc[-1]['SMA_200']
        
        # Contexto Alcista (Precio > SMA200)
        # Impulso fue de Low a High. Esperamos retroceso a 61.8%
        # Nivel 61.8 desde el Low hacia el High = High - (Range * 0.618)
        price_range = high_price - low_price
        if price_range == 0: return 'HOLD', None, 0
        
        fib_618_bull = high_price - (price_range * 0.618)
        
        # Si estamos en tendencia alcista
        if current_price > trend_sma:
            # Si el precio toca la zona del 61.8% (con margen de error)
            dist = abs(current_price - fib_618_bull)
            threshold = price_range * 0.05 # 5% de tolerancia
            
            if dist < threshold:
                # Verificar señal de giro (ej. martillo o vela verde reciente)
                # Por simplicidad, entramos si la vela actual es verde (Close > Open)
                if df.iloc[-1]['Close'] > df.iloc[-1]['Open']:
                     return 'BUY', "Rebote en Fibonacci 61.8%", 300

        # Contexto Bajista
        # Impulso fue de High a Low. Retroceso sube hasta 61.8%
        # Nivel 61.8 = Low + (Range * 0.618)
        fib_618_bear = low_price + (price_range * 0.618)
        
        if current_price < trend_sma:
            dist = abs(current_price - fib_618_bear)
            threshold = price_range * 0.05
            
            if dist < threshold:
                 # Vela roja confirmatoria
                 if df.iloc[-1]['Close'] < df.iloc[-1]['Open']:
                     return 'SELL', "Rechazo en Fibonacci 61.8%", 300
                     
        return 'HOLD', None, 0
