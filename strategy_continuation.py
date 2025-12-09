from strategy_stochastic import Strategy

class StrategyContinuation(Strategy):
    def __init__(self):
        super().__init__("Patrones de Continuación (Chartismo)")
        
    def get_signal(self, df):
        if df.empty:
            return 'HOLD', None, 0
            
        last = df.iloc[-1]
        
        # Usamos los patrones detectados en analysis/patterns
        # Triángulo detectado?
        has_triangle = last.get('Pattern_Triangle', 0) == 1
        
        if not has_triangle:
             return 'HOLD', None, 0
             
        # Si hay triángulo, operamos a favor de la ruptura o tendencia previa
        # Miramos la tendencia de corto plazo (EMA 20 vs 50)
        trend_up = last['EMA_20'] > last['EMA_50']
        
        # Un triángulo es de continuación. Si es alcista y rompe resistencia...
        # Simplificación: Compramos si tendencia es alcista y hay compresión
        if trend_up:
            return 'BUY', "Triángulo de Continuación Alcista", 300
        else:
            return 'SELL', "Triángulo de Continuación Bajista", 300
