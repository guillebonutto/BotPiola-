import pandas as pd
import numpy as np
from patterns import PatternRecognizer

def create_mock_data(highs, lows, atr_values=None):
    n = len(highs)
    df = pd.DataFrame({
        'High': highs,
        'Low': lows,
        'Open': (np.array(highs) + np.array(lows)) / 2, # Dummy
        'Close': (np.array(highs) + np.array(lows)) / 2 # Dummy
    })
    if atr_values is not None:
        df['ATR'] = atr_values
    else:
        df['ATR'] = 1.0 # Default dummy ATR
    return df

def test_triangle_patterns():
    pr = PatternRecognizer()
    
    print("--- Test 1: Symmetrical Triangle (Strict 3-Peak/3-Trough) ---")
    # Generamos 70 velas con fondo estrictamente monotónico para evitar picos fantasma
    highs = [80.0 + i * 0.05 for i in range(70)]
    lows = [60.0 - i * 0.05 for i in range(70)]
    
    # Pico 1 y Valle 1 en idx 15 (confirmados en idx 20)
    highs[15] = 110.0
    lows[15] = 40.0  # Rango = 70.0
    
    # Pico 2 Y Valle 2 en idx 35 (confirmados en idx 40)
    highs[35] = 105.0
    lows[35] = 45.0  # Rango = 60.0 (Decreciente)
    
    # Pico 3 y Valle 3 en idx 55 (confirmados en idx 60)
    highs[55] = 101.0
    lows[55] = 49.0  # Rango = 52.0 (Decreciente)
    
    # Generar ATR decreciente para simular compresión
    atr_values = [2.0] * 50 + [1.5 - i * 0.05 for i in range(20)]
    
    df = create_mock_data(highs, lows, atr_values)
    
    # Imprimir max_local y min_local para ver qué detecta
    df = pr.find_chart_patterns(df, lookback=60)
    
    print("--- DEBUGGING INFO ---")
    print("max_local indices:", df[df['max_local']].index.tolist())
    print("min_local indices:", df[df['min_local']].index.tolist())
    
    # Vamos a replicar el cálculo del patrón manualmente aquí para ver qué falla:
    recent = df.iloc[-60:]
    maxs = recent[recent['max_local']]
    mins = recent[recent['min_local']]
    print(f"len(maxs) = {len(maxs)}, len(mins) = {len(mins)}")
    if len(maxs) >= 3 and len(mins) >= 3:
        p1_idx = maxs.index[-3] - 5
        p2_idx = maxs.index[-2] - 5
        p3_idx = maxs.index[-1] - 5
        v1_idx = mins.index[-3] - 5
        v2_idx = mins.index[-2] - 5
        v3_idx = mins.index[-1] - 5
        print(f"Peaks: p1_idx={p1_idx} (High={df.loc[p1_idx]['High']}), p2_idx={p2_idx} (High={df.loc[p2_idx]['High']}), p3_idx={p3_idx} (High={df.loc[p3_idx]['High']})")
        print(f"Valleys: v1_idx={v1_idx} (Low={df.loc[v1_idx]['Low']}), v2_idx={v2_idx} (Low={df.loc[v2_idx]['Low']}), v3_idx={v3_idx} (Low={df.loc[v3_idx]['Low']})")
        peaks_decreasing = df.loc[p1_idx]['High'] > df.loc[p2_idx]['High'] > df.loc[p3_idx]['High']
        troughs_increasing = df.loc[v1_idx]['Low'] < df.loc[v2_idx]['Low'] < df.loc[v3_idx]['Low']
        range1 = df.loc[p1_idx]['High'] - df.loc[v1_idx]['Low']
        range2 = df.loc[p2_idx]['High'] - df.loc[v2_idx]['Low']
        range3 = df.loc[p3_idx]['High'] - df.loc[v3_idx]['Low']
        range_decreasing = range1 > range2 > range3
        atr_current = df.iloc[-1]['ATR']
        atr_avg_20 = df['ATR'].rolling(20).mean().iloc[-1]
        atr_compress = atr_current < atr_avg_20
        print(f"peaks_decreasing={peaks_decreasing}, troughs_increasing={troughs_increasing}, range_decreasing={range_decreasing}, atr_compress={atr_compress} (current={atr_current:.3f}, avg={atr_avg_20:.3f})")
    print("----------------------")
    
    result = df['Pattern_Triangle'].iloc[-1]
    print(f"Symmetrical Result: {result}")
    
    if result == 1:
        print("PASS: Symmetrical Triangle Detected")
    else:
        print("FAIL: Symmetrical Triangle NOT Detected")
        
    print("\n--- Test 2: Flat Peaks (Flat Top, Higher Lows) - Should NOT trigger ---")
    highs2 = [80.0 + i * 0.05 for i in range(70)]
    lows2 = [60.0 - i * 0.05 for i in range(70)]
    
    # Picos planos
    highs2[15] = 110.0
    lows2[15] = 40.0
    
    highs2[35] = 110.0
    lows2[35] = 45.0
    
    highs2[55] = 110.0
    lows2[55] = 49.0
    
    df2 = create_mock_data(highs2, lows2, atr_values)
    df2 = pr.find_chart_patterns(df2, lookback=60)
    
    result2 = df2['Pattern_Triangle'].iloc[-1]
    print(f"Flat Top Result: {result2}")
    if result2 == 0:
         print("PASS: Flat Top properly ignored by symmetrical criteria")
    else:
         print("FAIL: Flat Top falsely detected as Symmetrical Triangle")

    print("\n--- Test 3: Channel / Rectangle (Flat Peaks, Flat Troughs) - Should be 0 ---")
    highs3 = [80.0 + i * 0.05 for i in range(70)]
    lows3 = [60.0 - i * 0.05 for i in range(70)]
    
    highs3[15] = 110.0
    lows3[15] = 40.0
    
    highs3[35] = 110.0
    lows3[35] = 40.0
    
    highs3[55] = 110.0
    lows3[55] = 40.0
    
    df3 = create_mock_data(highs3, lows3, atr_values)
    df3 = pr.find_chart_patterns(df3, lookback=60)
    
    result3 = df3['Pattern_Triangle'].iloc[-1]
    print(f"Rectangle Result: {result3}")
    
    if result3 == 0:
         print("PASS: Rectangle Properly Ignored")
    else:
         print("FAIL: Rectangle falsely detected as Triangle")

if __name__ == "__main__":
    test_triangle_patterns()
