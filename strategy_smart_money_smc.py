from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategySmartMoneySMC(Strategy):
    """
    Estrategia Smart Money Concepts (SMC):
    --------------------------------------
    1. Detecta Fair Value Gaps (FVG / Imbalances).
    2. Identifica Order Blocks (OB) previos a un BOS (Break of Structure).
    3. Entrada cuando el precio retorna a rebalancear el FVG y toca el Order Block en zonas de Discount/Premium.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Smart Money Concepts (FVG + Order Block)")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        # Duración objetivo según el timeframe
        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        target_duration = time_diff if time_diff in [60, 300, 900, 3600] else 300

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        recent = df.iloc[-30:]

        # --- 1. Mitigación Visual: Escaneo Histórico de FVGs ---
        lookback = min(100, len(df))
        df_recent = df.iloc[-lookback:]
        
        bullish_fvg_unmitigated = None # Tuple: (index, gap_top, gap_bottom)
        bearish_fvg_unmitigated = None # Tuple: (index, gap_top, gap_bottom)

        # Buscar de más antiguo a más nuevo
        for i in range(2, lookback - 1):
            # Bullish FVG: Low(i) > High(i-2)
            if df_recent['Low'].iloc[i] > df_recent['High'].iloc[i-2]:
                gap_top = df_recent['Low'].iloc[i]
                gap_bottom = df_recent['High'].iloc[i-2]
                
                # Chequear mitigación en velas posteriores
                mitigated = False
                for j in range(i + 1, lookback):
                    if df_recent['Low'].iloc[j] <= gap_top:
                        mitigated = True
                        break
                
                if not mitigated:
                    bullish_fvg_unmitigated = (i, gap_top, gap_bottom)
                    
            # Bearish FVG: High(i) < Low(i-2)
            if df_recent['High'].iloc[i] < df_recent['Low'].iloc[i-2]:
                gap_top = df_recent['Low'].iloc[i-2]
                gap_bottom = df_recent['High'].iloc[i]
                
                # Chequear mitigación en velas posteriores
                mitigated = False
                for j in range(i + 1, lookback):
                    if df_recent['High'].iloc[j] >= gap_bottom:
                        mitigated = True
                        break
                
                if not mitigated:
                    bearish_fvg_unmitigated = (i, gap_top, gap_bottom)

        # --- 2. Detección de Estructura (Swing High / Low) ---
        recent = df.iloc[-30:]
        high_max = recent['High'].max()
        low_min = recent['Low'].min()
        eq_price = (high_max + low_min) / 2.0  # Nivel 50% Equilibrium

        # --- 3. SEÑAL DE COMPRA (BULLISH SMC ENTRY) ---
        if last['Close'] < eq_price and bullish_fvg_unmitigated:
            gap_top = bullish_fvg_unmitigated[1]
            
            # Condición: El precio retrocede y entra en el FVG no mitigado (Low actual o previo <= gap_top)
            if last['Low'] <= gap_top or prev['Low'] <= gap_top:
                # Confirmación de rechazo alcista (Order Block válido)
                if last['Close'] > last['Open'] and (last['Close'] - last['Open']) > (last['High'] - last['Low']) * 0.4:
                    velas_atras = lookback - bullish_fvg_unmitigated[0]
                    return 'BUY', f"SMC Bullish: Rebote en FVG No Mitigado de hace {velas_atras} velas (Zona Discount)", target_duration

        # --- 4. SEÑAL DE VENTA (BEARISH SMC ENTRY) ---
        if last['Close'] > eq_price and bearish_fvg_unmitigated:
            gap_bottom = bearish_fvg_unmitigated[2]
            
            # Condición: El precio retrocede y entra en el FVG bajista no mitigado (High actual o previo >= gap_bottom)
            if last['High'] >= gap_bottom or prev['High'] >= gap_bottom:
                # Confirmación de rechazo bajista (Order Block válido)
                if last['Close'] < last['Open'] and (last['Open'] - last['Close']) > (last['High'] - last['Low']) * 0.4:
                    velas_atras = lookback - bearish_fvg_unmitigated[0]
                    return 'SELL', f"SMC Bearish: Rechazo en FVG No Mitigado de hace {velas_atras} velas (Zona Premium)", target_duration

        return 'HOLD', "Sin confluencia SMC (No FVG/OB activo o mitigado)", 0
