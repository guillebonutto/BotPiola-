from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategyDivergencePivot(Strategy):
    """
    Estrategia RSI Divergence + Pivot Reversion
    -------------------------------------------
    Busca divergencias de momentum entre el precio y el RSI (14)
    confirmadas por niveles de pivote local de soporte/resistencia.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("RSI Divergence + Pivot Reversion")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        # Asegurar columna RSI
        if 'RSI_14' not in df.columns:
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 0.00001)
            df['RSI_14'] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]
        recent_df = df.iloc[-30:]

        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        target_duration = time_diff if time_diff in [60, 300, 900] else 60

        # 1. Divergencia Alcista (Precio hace un mínimo más bajo, pero RSI hace un mínimo más alto en sobreventa)
        p_min1 = recent_df.iloc[-15:-5]['Low'].min()
        p_min2 = recent_df.iloc[-5:]['Low'].min()
        rsi_min1 = recent_df.iloc[-15:-5]['RSI_14'].min()
        rsi_min2 = recent_df.iloc[-5:]['RSI_14'].min()

        if p_min2 < p_min1 and rsi_min2 > rsi_min1 and rsi_min2 < 35:
            # Confirmación con vela verde o martillo
            if last['Close'] > last['Open'] or last.get('CDL_HAMMER', 0) == 100:
                return 'BUY', f"Divergencia Alcista RSI (RSI {rsi_min2:.1f} vs {rsi_min1:.1f})", target_duration

        # 2. Divergencia Bajista (Precio hace un máximo más alto, pero RSI hace un máximo más bajo en sobrecompra)
        p_max1 = recent_df.iloc[-15:-5]['High'].max()
        p_max2 = recent_df.iloc[-5:]['High'].max()
        rsi_max1 = recent_df.iloc[-15:-5]['RSI_14'].max()
        rsi_max2 = recent_df.iloc[-5:]['RSI_14'].max()

        if p_max2 > p_max1 and rsi_max2 < rsi_max1 and rsi_max2 > 65:
            # Confirmación con vela roja
            if last['Close'] < last['Open']:
                return 'SELL', f"Divergencia Bajista RSI (RSI {rsi_max2:.1f} vs {rsi_max1:.1f})", target_duration

        return 'HOLD', "No Divergence Detected", 0
