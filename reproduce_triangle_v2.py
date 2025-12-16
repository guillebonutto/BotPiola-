import pandas as pd
import numpy as np
from patterns import PatternRecognizer

def create_mock_data(highs, lows):
    # Rellenar con datos dummy para crear un DF válido
    n = len(highs)
    df = pd.DataFrame({
        'High': highs,
        'Low': lows,
        'Open': (np.array(highs) + np.array(lows)) / 2, # Dummy
        'Close': (np.array(highs) + np.array(lows)) / 2 # Dummy
    })
    return df

def test_triangle_patterns():
    pr = PatternRecognizer()
    
    print("--- Test 1: Symmetrical Triangle (Standard) ---")
    # Maximos bajan: 100, 98, 96... (Detecta peaks en 100 y 90 por ejemplo)
    # Minimos suben: 50, 52, 54...
    # Necesitamos suficientes datos para el rolling window (10)
    # peaks window=10 center=True. 
    # Vamos a crear picos explícitos.
    
    # Hacemos 30 filas
    highs = [100] * 30
    lows = [50] * 30
    
    # Pico 1 (Max) en idx 5: 100
    highs[5] = 105
    # Valle 1 (Min) en idx 5: 45
    lows[5] = 45
    
    # Pico 2 (Max Lower) en idx 20: 102 (102 < 105) -> Lower High
    highs[20] = 102
    # Valle 2 (Min Higher) en idx 20: 48 (48 > 45) -> Higher Low
    lows[20] = 48
    
    df = create_mock_data(highs, lows)
    df = pr.find_chart_patterns(df)
    
    result = df['Pattern_Triangle'].iloc[-1]
    print(f"Symmetrical Result: {result}")
    
    if result == 1:
        print("PASS: Symmetrical Triangle Detected")
    else:
        print("FAIL: Symmetrical Triangle NOT Detected")
        
    print("\n--- Test 2: Ascending Triangle (Flat Top, Higher Lows) ---")
    highs = [100] * 30
    lows = [50] * 30
    
    # Pico 1: 105
    highs[5] = 105
    # Valle 1: 45
    lows[5] = 45
    
    # Pico 2: 105 (Flat Top, equal to Pico 1)
    highs[20] = 105
    # Valle 2: 48 (Higher Low)
    lows[20] = 48
    
    df = create_mock_data(highs, lows)
    df = pr.find_chart_patterns(df)
    
    result = df['Pattern_Triangle'].iloc[-1]
    print(f"Ascending Result: {result}")
    
    if result == 1:
         print("PASS: Ascending Triangle Detected")
    else:
         print("FAIL: Ascending Triangle NOT Detected")

    print("\n--- Test 3: Descending Triangle (Lower Highs, Flat Bottom) ---")
    highs = [100] * 30
    lows = [50] * 30
    
    # Pico 1: 105
    highs[5] = 105
    # Valle 1: 45
    lows[5] = 45
    
    # Pico 2: 102 (Lower High)
    highs[20] = 102
    # Valle 2: 45 (Flat Bottom)
    lows[20] = 45
    
    df = create_mock_data(highs, lows)
    df = pr.find_chart_patterns(df)
    
    result = df['Pattern_Triangle'].iloc[-1]
    print(f"Descending Result: {result}")
    
    if result == 1:
         print("PASS: Descending Triangle Detected")
    else:
         print("FAIL: Descending Triangle NOT Detected")
         
    print("\n--- Test 4: Channel / Rectangle (Both Flat) - Should be 0 ---")
    highs = [100] * 30
    lows = [50] * 30
    
    # Pico 1: 105
    highs[5] = 105
    # Valle 1: 45
    lows[5] = 45
    
    # Pico 2: 105 (Flat)
    highs[20] = 105
    # Valle 2: 45 (Flat)
    lows[20] = 45
    
    df = create_mock_data(highs, lows)
    df = pr.find_chart_patterns(df)
    
    result = df['Pattern_Triangle'].iloc[-1]
    print(f"Rectangle Result: {result}")
    
    if result == 0:
         print("PASS: Rectangle Properly Ignored")
    else:
         print("FAIL: Rectangle falsely detected as Triangle")

if __name__ == "__main__":
    test_triangle_patterns()
