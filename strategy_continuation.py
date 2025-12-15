from strategy_stochastic import Strategy
from ta.trend import ADXIndicator

class StrategyContinuation(Strategy):
    def __init__(self):
        super().__init__("Patrones de Continuación (Chartismo)")
        
    def get_signal(self, df):
        if len(df) < 50:
            return 'HOLD', None, 0
            
        last = df.iloc[-1]
        
        # 1. Filtro de Mercado Lateral (ADX < 20 = Rango/Lateral)
        # El feedback indica fallos por "lateralización".
        adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=14).adx().iloc[-1]
        if adx < 20:
            return 'HOLD', "Mercado Lateral (ADX < 20)", 0

        # 2. Análisis de Tendencia (EMAs)
        ema_20 = last['EMA_20']
        ema_50 = last['EMA_50']
        trend_up = ema_20 > ema_50
        trend_down = ema_20 < ema_50

        # 3. Patrón de Triángulo detectado (Compresión)
        has_triangle = last.get('Pattern_Triangle', 0) == 1
        
        if not has_triangle:
            return 'HOLD', None, 0

        # 4. CONFIRMACIÓN DE RUPTURA (Breakout) - Clave según feedback
        # Buscamos los máximos/mínimos recientes para definir la zona de ruptura
        recent_high = df['High'].iloc[-10:-1].max()
        recent_low = df['Low'].iloc[-10:-1].min()
        close = last['Close']
        
        # Señal de Compra: Tendencia Alcista + Triángulo + Ruptura de Resistencia Reciente
        if trend_up and close > recent_high:
            return 'BUY', f"Ruptura Triángulo Alcista (Close > {recent_high:.5f}) + ADX {adx:.1f}", 300
            
        # Señal de Venta: Tendencia Bajista + Triángulo + Ruptura de Soporte Reciente
        elif trend_down and close < recent_low:
            return 'SELL', f"Ruptura Triángulo Bajista (Close < {recent_low:.5f}) + ADX {adx:.1f}", 300

        # Si hay patrón pero no rompe, esperamos (HOLD)
        return 'HOLD', "Patrón en formación (Esperando ruptura)", 0
