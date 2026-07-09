from strategy_stochastic import Strategy

from strategy_stochastic import Strategy

class StrategyStructure(Strategy):
    def __init__(self):
        super().__init__("Cambio de Estructura (MSS)")
        self.type = 'REVERSION'
        
    def get_signal(self, df):
        if df.empty or len(df) < 30:
            return 'HOLD', "Insufficient Data (<30 candles)", 0
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        atr = last.get('ATR', 0.0002)
        
        # Buscamos si el patrón fue confirmado en las últimas 15 velas
        recent = df.iloc[-15:]
        
        double_top_detected = recent['Pattern_DoubleTop'].max() == 1
        double_bottom_detected = recent['Pattern_DoubleBottom'].max() == 1
        
        # Cambio a Bajista (Doble Techo + Ruptura de Soporte/Neckline)
        if double_top_detected:
            # Recuperar el nivel del neckline (el último valor no nulo detectado)
            neckline_series = recent['Pattern_DoubleTop_Neck'].dropna()
            if not neckline_series.empty:
                neckline = neckline_series.iloc[-1]
                
                # 1. Ruptura FRESCA: el cruce del neckline ocurrió exactamente en la vela actual
                crossover = last['Close'] < neckline and prev['Close'] >= neckline
                            
                # 2. Distancia límite: no entrar si el precio ya cayó demasiado lejos del neckline (máx 0.25 * ATR)
                not_too_far = last['Close'] >= (neckline - 0.25 * atr)
                
                if crossover and not_too_far:
                     # Confirmación extra: MACD cruzó a la baja recientemente (en las últimas 3 velas)
                     macd_cross_bear = False
                     for idx in range(-3, 0):
                          val = df.iloc[idx]
                          prev_val = df.iloc[idx-1]
                          if prev_val['MACD'] >= prev_val['MACD_Signal'] and val['MACD'] < val['MACD_Signal']:
                              macd_cross_bear = True
                              break
                      
                     if macd_cross_bear:
                          return 'SELL', f"Cambio Estructura: Doble Techo + Ruptura FRESCA de {neckline:.5f} + Cruce MACD Bajista", 300
                  
        # Cambio a Alcista (Doble Suelo + Ruptura de Resistencia/Neckline)
        if double_bottom_detected:
            neckline_series = recent['Pattern_DoubleBottom_Neck'].dropna()
            if not neckline_series.empty:
                neckline = neckline_series.iloc[-1]
                
                # 1. Ruptura FRESCA: el cruce del neckline ocurrió exactamente en la vela actual
                crossover = last['Close'] > neckline and prev['Close'] <= neckline
                            
                # 2. Distancia límite (máx 0.25 * ATR por encima de la línea)
                not_too_far = last['Close'] <= (neckline + 0.25 * atr)
                
                if crossover and not_too_far:
                    # Confirmación extra: MACD cruzó al alza recientemente (en las últimas 3 velas)
                    macd_cross_bull = False
                    for idx in range(-3, 0):
                          val = df.iloc[idx]
                          prev_val = df.iloc[idx-1]
                          if prev_val['MACD'] <= prev_val['MACD_Signal'] and val['MACD'] > val['MACD_Signal']:
                              macd_cross_bull = True
                              break
                              
                    if macd_cross_bull:
                        return 'BUY', f"Cambio Estructura: Doble Suelo + Ruptura FRESCA de {neckline:.5f} + Cruce MACD Alcista", 300
                
        return 'HOLD', f"No Confirmed Pattern (DT={double_top_detected}, DB={double_bottom_detected})", 0
