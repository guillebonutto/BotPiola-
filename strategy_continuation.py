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
        
        # Obtener niveles de ruptura del patrón
        # Si no existen (por versión anterior de patterns.py), usar infinito o 0 para evitar falsos positivos
        tri_upper = last.get('Pattern_Triangle_Upper', float('inf'))
        tri_lower = last.get('Pattern_Triangle_Lower', 0)
        
        current_close = last['Close']

        # Si hay triángulo, operamos SOLO si hay ruptura confirmada
        # Miramos la tendencia de corto plazo (EMA 20 vs 50) como filtro adicional
        trend_up = last['EMA_20'] > last['EMA_50']
        
        # Confirmación de Ruptura Alcista
        # 1. Close actual > Resistencia del triángulo
        # 2. Tendencia a favor (opcional pero recomendado)
        if current_close > tri_upper and trend_up:
            return 'BUY', f"Ruptura Triángulo Alcista Confirmada (Close {current_close:.5f} > {tri_upper:.5f})", 300
            
        # Confirmación de Ruptura Bajista
        # 1. Close actual < Soporte del triángulo
        # 2. Tendencia a favor
        elif current_close < tri_lower and not trend_up:
            return 'SELL', f"Ruptura Triángulo Bajista Confirmada (Close {current_close:.5f} < {tri_lower:.5f})", 300
            
        return 'HOLD', None, 0
