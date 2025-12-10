from strategy_stochastic import Strategy

class StrategyStructure(Strategy):
    def __init__(self):
        super().__init__("Cambio de Estructura (MSS)")
        
    def get_signal(self, df):
        if df.empty or len(df) < 20:
            return 'HOLD', None, 0
            
        last = df.iloc[-1]
        
        # Patrón de Doble Techo o Doble Suelo con confirmación de ruptura de NECKLINE
        
        # Como Pattern_DoubleTop se marca en la última vela analizada de una ventana deslizante,
        # puede que el patrón se detectara hace poco.
        # Buscamos si hubo un patrón en las últimas 5 velas
        recent = df.iloc[-5:]
        
        double_top_detected = recent['Pattern_DoubleTop'].max() == 1
        double_bottom_detected = recent['Pattern_DoubleBottom'].max() == 1
        
        # Cambio a Bajista (Doble Techo + Ruptura de Soporte/Neckline)
        if double_top_detected:
            # Recuperar el nivel del neckline (el último valor no nulo detectado)
            neckline_series = recent['Pattern_DoubleTop_Neck'].dropna()
            if not neckline_series.empty:
                neckline = neckline_series.iloc[-1]
                
                # Verificar ruptura: El cierre actual debe estar CLARAMENTE POR DEBAJO del neckline
                # Estrategia pide "Retesteo", una aproximación simple es que la ruptura ya ocurrió
                # y el precio actual está cerca del nivel roto pero confirmando la baja.
                if last['Close'] < neckline:
                     # Confirmación extra: MACD cruzando a la baja (momentum bajista)
                     if last['MACD'] < last['MACD_Signal']:
                         return 'SELL', f"Cambio Estructura: Doble Techo + Ruptura confirmada de {neckline:.5f}", 300
                 
        # Cambio a Alcista (Doble Suelo + Ruptura de Resistencia/Neckline)
        if double_bottom_detected:
            neckline_series = recent['Pattern_DoubleBottom_Neck'].dropna()
            if not neckline_series.empty:
                neckline = neckline_series.iloc[-1]
                
                # Verificar ruptura: El cierre actual debe estar CLARAMENTE POR ENCIMA del neckline
                if last['Close'] > neckline:
                    if last['MACD'] > last['MACD_Signal']:
                        return 'BUY', f"Cambio Estructura: Doble Suelo + Ruptura confirmada de {neckline:.5f}", 300
                
        return 'HOLD', None, 0
