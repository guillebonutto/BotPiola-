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
        if df.empty or len(df) < 200:
            return 'HOLD', "Insufficient Data (<200 candles for SMA)", 0

        # Asegurar copia independiente para evitar SettingWithCopyWarning
        df = df.copy()

        # Asegurar columna RSI
        if 'RSI_14' not in df.columns:
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 0.00001)
            df['RSI_14'] = 100 - (100 / (1 + rs))

        # Calcular SMA 200 para filtro de tendencia mayor
        if 'SMA_200' not in df.columns:
            df['SMA_200'] = df['Close'].rolling(window=200).mean()

        last = df.iloc[-1]
        sma_200 = last['SMA_200']

        time_diff = 60
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            pass

        target_duration = time_diff if time_diff in [60, 300, 900] else 60

        # Buscar Pivots (Fractales de 5 velas) en las últimas 60 velas
        # Ignoramos las últimas 2 velas porque un pivot necesita 2 velas a la derecha para confirmarse
        pivot_lows = []
        pivot_highs = []
        
        limit_idx = max(2, len(df) - 60)
        for i in range(len(df) - 3, limit_idx, -1):
            # Pivot Low (Valle)
            if (df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i-2] and 
                df['Low'].iloc[i] < df['Low'].iloc[i+1] and df['Low'].iloc[i] < df['Low'].iloc[i+2]):
                pivot_lows.append((i, df['Low'].iloc[i], df['RSI_14'].iloc[i]))
            
            # Pivot High (Pico)
            if (df['High'].iloc[i] > df['High'].iloc[i-1] and df['High'].iloc[i] > df['High'].iloc[i-2] and 
                df['High'].iloc[i] > df['High'].iloc[i+1] and df['High'].iloc[i] > df['High'].iloc[i+2]):
                pivot_highs.append((i, df['High'].iloc[i], df['RSI_14'].iloc[i]))

        # 1. Divergencia Alcista (BUY)
        # Requiere: Tendencia mayor alcista (Precio > SMA200)
        if len(pivot_lows) >= 2 and last['Close'] > sma_200:
            idx1, p_low1, rsi_low1 = pivot_lows[1] # Valle anterior
            idx2, p_low2, rsi_low2 = pivot_lows[0] # Valle reciente
            
            # El valle más reciente debe haber ocurrido hace menos de 10 velas (para no tradear señales viejas)
            if (len(df) - 1 - idx2) <= 10:
                # Divergencia clásica: Precio hace mínimo más bajo, RSI hace mínimo más alto
                if p_low2 < p_low1 and rsi_low2 > rsi_low1:
                    # Exigir que al menos uno de los valles haya tocado sobreventa (< 35)
                    if rsi_low1 < 35 or rsi_low2 < 35:
                        # Confirmación con vela verde o patrón martillo
                        if last['Close'] > last['Open'] or last.get('CDL_HAMMER', 0) == 100:
                            return 'BUY', f"Divergencia Alcista RSI ({rsi_low2:.1f} > {rsi_low1:.1f}) + SMA200", target_duration

        # 2. Divergencia Bajista (SELL)
        # Requiere: Tendencia mayor bajista (Precio < SMA200)
        if len(pivot_highs) >= 2 and last['Close'] < sma_200:
            idx1, p_high1, rsi_high1 = pivot_highs[1] # Pico anterior
            idx2, p_high2, rsi_high2 = pivot_highs[0] # Pico reciente
            
            if (len(df) - 1 - idx2) <= 10:
                # Divergencia clásica: Precio hace máximo más alto, RSI hace máximo más bajo
                if p_high2 > p_high1 and rsi_high2 < rsi_high1:
                    # Exigir que al menos uno de los picos haya tocado sobrecompra (> 65)
                    if rsi_high1 > 65 or rsi_high2 > 65:
                        # Confirmación con vela roja
                        if last['Close'] < last['Open']:
                            return 'SELL', f"Divergencia Bajista RSI ({rsi_high2:.1f} < {rsi_high1:.1f}) + SMA200", target_duration

        return 'HOLD', "No Divergence Detected", 0
