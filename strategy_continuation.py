from strategy_stochastic import Strategy
from ta.trend import ADXIndicator

class StrategyContinuation(Strategy):
    def __init__(self):
        super().__init__("Patrones de Continuación (Chartismo)")
        self.type = 'TREND'
        
    def get_signal(self, df):
        if len(df) < 50:
            return 'HOLD', None, 0
            
        last = df.iloc[-1]
        
        # 1. Chequeo de Patrón de Triángulo (Compresión)
        # NOTA: Movemos esto AL PRINCIPIO. Si hay triángulo, ignoramos el filtro de ADX bajo 
        # porque los triángulos son zonas de consolidación (baja volatilidad) por definición.
        
        has_triangle = last.get('Pattern_Triangle', 0) == 1
        
        if not has_triangle:
            return 'HOLD', "No Triangle Pattern", 0

        # 2. Análisis de Tendencia (EMAs)
        ema_20 = last['EMA_20']
        ema_50 = last['EMA_50']
        trend_up = ema_20 > ema_50
        trend_down = ema_20 < ema_50
        
        # 3. Datos informativos de Volatilidad
        # Usamos el ATR para confirmar que la ruptura sea fuerte (no solo una mecha microscópica)
        atr = last.get('ATR', 0.0002)
        min_breakout = atr * 0.25  # Exigimos al menos un 25% del ATR diario en la ruptura
        
        # 4. CONFIRMACIÓN DE RUPTURA (Breakout) - Clave según feedback
        # Buscamos los máximos/mínimos recientes para definir la zona de ruptura
        recent_high = df['High'].iloc[-10:-1].max()
        recent_low = df['Low'].iloc[-10:-1].min()
        close = last['Close']
        
        max_breakout = atr * 0.45
        
        # Señal de Compra: Tendencia Alcista + Triángulo + Ruptura de Resistencia Reciente con fuerza controlada
        if trend_up and min_breakout < (close - recent_high) <= max_breakout:
            return 'BUY', f"Ruptura Triángulo Alcista (Breakout: {(close - recent_high):.5f} | Rango: [{min_breakout:.5f}, {max_breakout:.5f}])", 300
            
        # Señal de Venta: Tendencia Bajista + Triángulo + Ruptura de Soporte Reciente con fuerza controlada
        elif trend_down and min_breakout < (recent_low - close) <= max_breakout:
            return 'SELL', f"Ruptura Triángulo Bajista (Breakout: {(recent_low - close):.5f} | Rango: [{min_breakout:.5f}, {max_breakout:.5f}])", 300
 
        # Si hay patrón pero no rompe con la fuerza adecuada, esperamos (HOLD)
        return 'HOLD', "Patrón en formación (Esperando ruptura en zona óptima)", 0
