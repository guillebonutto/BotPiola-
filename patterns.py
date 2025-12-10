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

    def find_chart_patterns(self, df, lookback=30):
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

        window = 10
        # Rolling de Pandas
        df['max_local'] = df['High'].rolling(window, center=True).max() == df['High']
        df['min_local'] = df['Low'].rolling(window, center=True).min() == df['Low']
    
        
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
                # Marcar en la última vela (asumimos que acabamos de completar el patrón)
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
             
             # Maximos decrecientes Y mínimos crecientes
             if p_max2 < p_max1 and p_min2 > p_min1:
                 df.iloc[-1, df.columns.get_loc('Pattern_Triangle')] = 1
                 
        return df
