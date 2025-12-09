import talib
import numpy as np

class PatternRecognizer:
    def __init__(self):
        pass

    def find_candlestick_patterns(self, df):
        """
        Busca patrones de velas japonesas usando TA-Lib.
        Agrega columnas al DataFrame con las señales (No 0 = Patrón encontrado).
        """
        # Martillo
        df['CDL_HAMMER'] = talib.CDLHAMMER(df['Open'], df['High'], df['Low'], df['Close'])
        # Estrella Fugaz (Shooting Star)
        df['CDL_SHOOTINGSTAR'] = talib.CDLSHOOTINGSTAR(df['Open'], df['High'], df['Low'], df['Close'])
        # Envolvente (Engulfing)
        df['CDL_ENGULFING'] = talib.CDLENGULFING(df['Open'], df['High'], df['Low'], df['Close'])
        # Doji
        df['CDL_DOJI'] = talib.CDLDOJI(df['Open'], df['High'], df['Low'], df['Close'])
        # Morning Star
        df['CDL_MORNINGSTAR'] = talib.CDLMORNINGSTAR(df['Open'], df['High'], df['Low'], df['Close'])
        # Evening Star
        df['CDL_EVENINGSTAR'] = talib.CDLEVENINGSTAR(df['Open'], df['High'], df['Low'], df['Close'])
        
        return df

    def find_chart_patterns(self, df, lookback=30):
        """
        Intenta identificar patrones chartistas simples como Doble Techo/Suelo y Triángulos.
        Mejorado para evitar falsos positivos en consolidaciones.
        """
        # Aumentamos la ventana para considerar un "pico" (antes 5, ahora 10)
        # Esto filtra picos menores
        window = 10
        df['max_local'] = df['High'].rolling(window, center=True).max() == df['High']
        df['min_local'] = df['Low'].rolling(window, center=True).min() == df['Low']
        
        df['Pattern_DoubleTop'] = 0
        df['Pattern_DoubleTop_Neck'] = np.nan
        df['Pattern_DoubleBottom'] = 0
        df['Pattern_DoubleBottom_Neck'] = np.nan
        df['Pattern_Triangle'] = 0
        
        if len(df) < lookback:
            return df
            
        recent = df.iloc[-lookback:]
        maxs = recent[recent['max_local']]
        mins = recent[recent['min_local']]
        
        # --- Doble Techo ---
        if len(maxs) >= 2:
            last_peaks = maxs.tail(2)
            p1_idx = last_peaks.index[0]
            p2_idx = last_peaks.index[1]
            p1_price = last_peaks.iloc[0]['High']
            p2_price = last_peaks.iloc[1]['High']
            
            # 1. Similitud de precio (Tolerancia 0.1%)
            price_match = abs(p1_price - p2_price) / p1_price < 0.001
            
            # 2. Separación temporal (mínimo 5 velas entre picos)
            pos1 = df.index.get_loc(p1_idx)
            pos2 = df.index.get_loc(p2_idx)
            separation = pos2 - pos1
            time_check = separation > 5
            
            # 3. Valle significativo entre picos
            if time_check:
                valley_min = df.iloc[pos1:pos2]['Low'].min()
                valley_depth = (p1_price - valley_min) / p1_price
                valley_check = valley_depth > 0.002
            else:
                valley_check = False
                valley_min = np.nan
                
            if price_match and time_check and valley_check:
                # Marcar en la última vela
                df.iloc[-1, df.columns.get_loc('Pattern_DoubleTop')] = 1
                df.iloc[-1, df.columns.get_loc('Pattern_DoubleTop_Neck')] = valley_min
                
        # --- Doble Suelo ---
        if len(mins) >= 2:
            last_troughs = mins.tail(2)
            p1_idx = last_troughs.index[0]
            p2_idx = last_troughs.index[1]
            p1_price = last_troughs.iloc[0]['Low']
            p2_price = last_troughs.iloc[1]['Low']
            
            price_match = abs(p1_price - p2_price) / p1_price < 0.001
            
            pos1 = df.index.get_loc(p1_idx)
            pos2 = df.index.get_loc(p2_idx)
            separation = pos2 - pos1
            time_check = separation > 5
            
            if time_check:
                peak_max = df.iloc[pos1:pos2]['High'].max()
                peak_height = (peak_max - p1_price) / p1_price
                peak_check = peak_height > 0.002
            else:
                peak_check = False
                peak_max = np.nan

            if price_match and time_check and peak_check:
                df.iloc[-1, df.columns.get_loc('Pattern_DoubleBottom')] = 1
                df.iloc[-1, df.columns.get_loc('Pattern_DoubleBottom_Neck')] = peak_max

                
        # --- Triángulo (Compresión) ---
        if len(maxs) >= 2 and len(mins) >= 2:
             p_max1 = maxs.iloc[-2]['High']
             p_max2 = maxs.iloc[-1]['High']
             p_min1 = mins.iloc[-2]['Low']
             p_min2 = mins.iloc[-1]['Low']
             
             # Verificar que los puntos sean recientes (dentro del lookback) y alternados idealmente
             # Por simplicidad: Maximos decrecientes Y mínimos crecientes
             if p_max2 < p_max1 and p_min2 > p_min1:
                 df.iloc[-1, df.columns.get_loc('Pattern_Triangle')] = 1
                 
        return df
