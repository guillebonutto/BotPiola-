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
        # Como no tenemos lineas de tendencia trazadas, usamos la EMA como filtro de tendencia mayor
        if trend_up:
            return 'BUY', "Patrón Triángulo/Banderín de Continuación Alcista (Trend Filter OK)", 300
        else:
            return 'SELL', "Patrón Triángulo/Banderín de Continuación Bajista (Trend Filter OK)", 300
