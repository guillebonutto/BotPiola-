import pandas as pd
import numpy as np

class PatternRecognizer:
    def __init__(self):
        pass

    def find_candlestick_patterns(self, df):
        """
        Busca patrones de velas japonesas usando lógica personalizada (sin TA-Lib).
        Agrega columnas al DataFrame con las señales:
        100 = Bullish
        -100 = Bearish
        0 = No Pattern
        """
        # Calcular cuerpos y sombras para facilitar lógica
        df['Body'] = abs(df['Close'] - df['Open'])
        df['UpperShadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['LowerShadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['TotalRange'] = df['High'] - df['Low']
        
        # Evitar división por cero
        df['TotalRange'] = df['TotalRange'].replace(0, 0.00001)
        
        # --- DOJI ---
        # Cuerpo muy pequeño en relación al rango total (ej. < 10%)
        df['CDL_DOJI'] = np.where(df['Body'] <= df['TotalRange'] * 0.1, 100, 0)

        # --- HAMMER (Martillo) ---
        # Cuerpo pequeño en la parte superior, sombra inferior larga (> 2 * cuerpo), sombra superior pequeña
        is_hammer = (
            (df['Body'] <= df['TotalRange'] * 0.3) & # Cuerpo pequeño
            (df['LowerShadow'] >= df['Body'] * 2) & # Sombra inferior larga
            (df['UpperShadow'] <= df['Body'] * 0.5) # Sombra superior cortita
        )
        df['CDL_HAMMER'] = np.where(is_hammer, 100, 0)

        # --- SHOOTING STAR (Estrella Fugaz) ---
        # Inverso al martillo: Cuerpo pequeño abajo, sombra superior larga
        is_shooting_star = (
            (df['Body'] <= df['TotalRange'] * 0.3) &
            (df['UpperShadow'] >= df['Body'] * 2) &
            (df['LowerShadow'] <= df['Body'] * 0.5)
        )
        # TA-Lib a veces retorna -100 para shooting star (bearish)
        df['CDL_SHOOTINGSTAR'] = np.where(is_shooting_star, -100, 0)
        
        # --- ENGULFING (Envolvente) ---
        # Bullish: Vela previa ROJA, vela actual VERDE y cubre cuerpo previo
        # Bearish: Vela previa VERDE, vela actual ROJA y cubre cuerpo previo
        prev_open = df['Open'].shift(1)
        prev_close = df['Close'].shift(1)
        prev_body = abs(prev_close - prev_open)
        
        # Bullish Engulfing
        is_bull_engul = (
            (prev_close < prev_open) & # Previa Roja
            (df['Close'] > df['Open']) & # Actual Verde
            (df['Close'] > prev_open) & 
            (df['Open'] < prev_close)
        )
        
        # Bearish Engulfing
        is_bear_engul = (
            (prev_close > prev_open) & # Previa Verde
            (df['Close'] < df['Open']) & # Actual Roja
            (df['Close'] < prev_open) &
            (df['Open'] > prev_close)
        )
        
        df['CDL_ENGULFING'] = 0
        df.loc[is_bull_engul, 'CDL_ENGULFING'] = 100
        df.loc[is_bear_engul, 'CDL_ENGULFING'] = -100
        
        # --- MORNING STAR ---
        # 1. Larga Bajista, 2. Pequeña (cualquier color) abajo, 3. Larga Alcista
        # Simplificación vectorizada
        p2_open = df['Open'].shift(2)
        p2_close = df['Close'].shift(2)
        p2_body = abs(p2_close - p2_open)
        
        # Vela 1 (Hace 2): Larga y Roja
        c1_long_red = (p2_close < p2_open) & (p2_body > df['TotalRange'].shift(2) * 0.5)
        
        # Vela 2 (Hace 1): Cuerpo pequeño (Doji o Spinning Top) y Gap abajo (idealmente)
        c2_small = (prev_body < p2_body * 0.5)
        c2_gap = (np.maximum(prev_open, prev_close) < p2_close) # Gap down del cuerpo
        
        # Vela 3 (Actual): Larga y Verde, cierra dentro del cuerpo de la 1
        c3_long_green = (df['Close'] > df['Open']) & (df['Close'] > (p2_open + p2_close)/2)
        
        is_morning_star = c1_long_red & c2_small & c3_long_green
        df['CDL_MORNINGSTAR'] = np.where(is_morning_star, 100, 0)

        # --- EVENING STAR ---
        # 1. Larga Verde, 2. Pequeña arriba, 3. Larga Roja
        c1_long_green = (p2_close > p2_open) & (p2_body > df['TotalRange'].shift(2) * 0.5)
        
        c2_gap_up = (np.minimum(prev_open, prev_close) > p2_close) # Gap up
        
        c3_long_red = (df['Close'] < df['Open']) & (df['Close'] < (p2_open + p2_close)/2)
        
        is_evening_star = c1_long_green & c2_small & c3_long_red
        df['CDL_EVENINGSTAR'] = np.where(is_evening_star, -100, 0)
        
        # Limpieza de columnas temporales
        df.drop(columns=['Body', 'UpperShadow', 'LowerShadow', 'TotalRange'], inplace=True)
        
        return df

    def find_chart_patterns(self, df, lookback=60):
        """
        Intenta identificar patrones chartistas simples como Doble Techo/Suelo y Triángulos.
        Mejorado para evitar falsos positivos en consolidaciones.
        """
        # Inicializar columnas por si no existen
        df['Pattern_DoubleTop'] = 0
        df['Pattern_DoubleTop_Neck'] = np.nan
        df['Pattern_DoubleBottom'] = 0
        df['Pattern_DoubleBottom_Neck'] = np.nan
        df['Pattern_Triangle'] = 0
        # Evitamos center=True para eliminar el Lookahead Bias (Repainting).
        # Un máximo/mínimo local se confirma retrospectivamente basándonos en un desplazamiento hacia atrás (shift).
        # Para una ventana de 11 velas, confirmamos el pico de la vela en el centro (hace 5 periodos)
        # cuando la ventana de 11 velas termina de cerrarse en la vela actual.
        window = 11
        half_window = 5
        
        # El valor de hace 5 velas es el máximo/mínimo si es el mayor/menor de la ventana de 11 velas
        max_in_window = df['High'].rolling(window).max()
        min_in_window = df['Low'].rolling(window).min()
        
        # Desplazamos para comparar el High de hace 5 periodos con el valor máximo de la ventana que terminó hoy
        df['max_local'] = (df['High'].shift(half_window) == max_in_window)
        df['min_local'] = (df['Low'].shift(half_window) == min_in_window)
        
        if len(df) < lookback:
            return df
            
        recent = df.iloc[-lookback:]
        maxs = recent[recent['max_local']]
        mins = recent[recent['min_local']]
        
        # --- Doble Techo ---
        if len(maxs) >= 2:
            last_peaks = maxs.tail(2)
            p1_confirm = last_peaks.index[0]
            p2_confirm = last_peaks.index[1]
            
            # Los picos reales ocurrieron 5 velas antes de la confirmación
            p1_idx = p1_confirm - 5
            p2_idx = p2_confirm - 5
            
            p1_price = df.loc[p1_idx]['High']
            p2_price = df.loc[p2_idx]['High']
            
            # 1. Similitud de precio basada en ATR (máximo 0.25 * ATR)
            atr_current = df.loc[p2_confirm].get('ATR', 0.0002)
            price_match = abs(p1_price - p2_price) < (atr_current * 0.25)
            
            # 2. Separación temporal (mínimo 5 velas entre picos)
            pos1 = df.index.get_loc(p1_idx)
            pos2 = df.index.get_loc(p2_idx)
            separation = pos2 - pos1
            time_check = separation > 5
            
            # 3. Valle significativo entre picos (mínimo 0.25 * ATR)
            if time_check:
                valley_min = df.loc[p1_idx:p2_idx]['Low'].min()
                valley_depth = p1_price - valley_min
                valley_check = valley_depth > (atr_current * 0.25)
            else:
                valley_check = False
                valley_min = np.nan
                
            if price_match and time_check and valley_check:
                # Marcar en la vela de confirmación actual (p2_confirm)
                df.iloc[p2_confirm, df.columns.get_loc('Pattern_DoubleTop')] = 1
                df.iloc[p2_confirm, df.columns.get_loc('Pattern_DoubleTop_Neck')] = valley_min
                
        # --- Doble Suelo ---
        if len(mins) >= 2:
            last_troughs = mins.tail(2)
            p1_confirm = last_troughs.index[0]
            p2_confirm = last_troughs.index[1]
            
            # Los valles reales ocurrieron 5 velas antes de la confirmación
            p1_idx = p1_confirm - 5
            p2_idx = p2_confirm - 5
            
            p1_price = df.loc[p1_idx]['Low']
            p2_price = df.loc[p2_idx]['Low']
            
            atr_current = df.loc[p2_confirm].get('ATR', 0.0002)
            price_match = abs(p1_price - p2_price) < (atr_current * 0.25)
            
            pos1 = df.index.get_loc(p1_idx)
            pos2 = df.index.get_loc(p2_idx)
            separation = pos2 - pos1
            time_check = separation > 5
            
            if time_check:
                peak_max = df.loc[p1_idx:p2_idx]['High'].max()
                peak_height = peak_max - p1_price
                peak_check = peak_height > (atr_current * 0.25)
            else:
                peak_check = False
                peak_max = np.nan
 
            if price_match and time_check and peak_check:
                # Marcar en la vela de confirmación actual (p2_confirm)
                df.iloc[p2_confirm, df.columns.get_loc('Pattern_DoubleBottom')] = 1
                df.iloc[p2_confirm, df.columns.get_loc('Pattern_DoubleBottom_Neck')] = peak_max

        # --- Triángulo (Compresión) ---
        if len(maxs) >= 3 and len(mins) >= 3:
             # Obtener los 3 picos y 3 valles más recientes en orden cronológico
             p1_idx = maxs.index[-3] - 5
             p2_idx = maxs.index[-2] - 5
             p3_idx = maxs.index[-1] - 5
             
             v1_idx = mins.index[-3] - 5
             v2_idx = mins.index[-2] - 5
             v3_idx = mins.index[-1] - 5
             
             # Asegurarnos de que los índices sean válidos
             if p1_idx >= 0 and v1_idx >= 0:
                 p_max1 = df.loc[p1_idx]['High']
                 p_max2 = df.loc[p2_idx]['High']
                 p_max3 = df.loc[p3_idx]['High']
                 
                 p_min1 = df.loc[v1_idx]['Low']
                 p_min2 = df.loc[v2_idx]['Low']
                 p_min3 = df.loc[v3_idx]['Low']
                 
                 # 1. Máximos decrecientes Y mínimos crecientes (Compresión)
                 peaks_decreasing = p_max1 > p_max2 > p_max3
                 troughs_increasing = p_min1 < p_min2 < p_min3
                 
                 # 2. Reducción de Rango (la amplitud disminuye)
                 range1 = p_max1 - p_min1
                 range2 = p_max2 - p_min2
                 range3 = p_max3 - p_min3
                 range_decreasing = range1 > range2 > range3
                 
                 # 3. Compresión de ATR
                 # ATR actual < promedio de las últimas 20 velas
                 if 'ATR' in df.columns and len(df) >= 20:
                     atr_current = df.iloc[-1]['ATR']
                     atr_avg_20 = df['ATR'].rolling(20).mean().iloc[-1]
                     atr_compress = atr_current < atr_avg_20
                 else:
                     atr_compress = True  # Fallback si no hay ATR
                     
                 if peaks_decreasing and troughs_increasing and range_decreasing and atr_compress:
                     df.iloc[-1, df.columns.get_loc('Pattern_Triangle')] = 1
                  
        return df
