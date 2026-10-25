from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategySMCElite(Strategy):
    """
    Estrategia SMC Élite (ChoCH + Multi-Timeframe 1D/4H + Confluencia MACD):
    ----------------------------------------------------------------------
    1. Filtro Macro 1D y Estructural 4H (resampleado o EMAs multi-escala).
    2. Cambio de Estructura ChoCH / Break of Structure (BoS) en 1H.
    3. Confluencia de Momentum MACD (Histograma a favor del quiebre).
    """
    def __init__(self, bypass_filter=True):
        super().__init__("SMC Élite (ChoCH + MTF + MACD)")
        self.type = 'TREND_FOLLOWING'
        self.bypass_filter = bypass_filter

    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0

        target_duration = 3600  # 1 hora por defecto

        # 1. MACD Momentum en 1H
        ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        macd_bull = macd_hist.iloc[-1] > 0
        macd_bear = macd_hist.iloc[-1] < 0

        # 2. SMC ChoCH / BoS (Ventana de 15 velas) y Tomas de Liquidez (Sweeps)
        ventana = 15
        swing_high = df["High"].rolling(ventana).max()
        swing_low = df["Low"].rolling(ventana).min()

        # BoS: El cuerpo rompe y cierra más allá del swing
        bos_bull = (df["Close"].iloc[-1] > swing_high.iloc[-3]) and (df["Close"].iloc[-2] <= swing_high.iloc[-3])
        bos_bear = (df["Close"].iloc[-1] < swing_low.iloc[-3]) and (df["Close"].iloc[-2] >= swing_low.iloc[-3])

        # Sweeps (Tomas de Liquidez): La mecha rompe el swing pero el cuerpo cierra adentro dejando rechazo
        # Sweep Alcista: Toma liquidez abajo (Low < Swing Low) pero cierra por encima del Swing Low -> BUY
        sweep_bull = (df["Low"].iloc[-1] < swing_low.iloc[-3]) and (df["Close"].iloc[-1] > swing_low.iloc[-3]) and (df["Close"].iloc[-1] > df["Open"].iloc[-1])
        # Sweep Bajista: Toma liquidez arriba (High > Swing High) pero cierra por debajo del Swing High -> SELL
        sweep_bear = (df["High"].iloc[-1] > swing_high.iloc[-3]) and (df["Close"].iloc[-1] < swing_high.iloc[-3]) and (df["Close"].iloc[-1] < df["Open"].iloc[-1])

        # 3. Filtro Multi-Timeframe (1D y 4H)
        bias_1d = 0
        bias_4h = 0
        
        if 'bias_1d' in df.columns and 'bias_4h' in df.columns:
            bias_1d = df['bias_1d'].iloc[-1]
            bias_4h = df['bias_4h'].iloc[-1]
        else:
            try:
                temp_df = df.copy()
                if 'Timestamp' in temp_df.columns:
                    temp_df.index = pd.to_datetime(temp_df['Timestamp'], unit='s' if isinstance(temp_df['Timestamp'].iloc[0], (int, float, np.integer, np.floating)) else None)
                
                # 4H EMA 20 y 50
                df_4h = temp_df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
                if len(df_4h) >= 20:
                    ema_20_4h = df_4h["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
                    ema_50_4h = df_4h["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
                    c_4h = df_4h["Close"].iloc[-1]
                    bias_4h = 1 if (c_4h > ema_20_4h and ema_20_4h > ema_50_4h) else (-1 if (c_4h < ema_20_4h and ema_20_4h < ema_50_4h) else 0)
                else:
                    ema_50_h = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
                    bias_4h = 1 if df["Close"].iloc[-1] > ema_50_h else -1

                # 1D EMA 50
                df_1d = temp_df.resample("1d").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
                if len(df_1d) >= 10:
                    ema_50_1d = df_1d["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
                    c_1d = df_1d["Close"].iloc[-1]
                    bias_1d = 1 if c_1d > ema_50_1d else -1
                else:
                    sma_200_h = df["Close"].rolling(min(len(df), 200)).mean().iloc[-1]
                    bias_1d = 1 if df["Close"].iloc[-1] > sma_200_h else -1
            except Exception:
                ema_50_h = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
                sma_200_h = df["Close"].rolling(min(len(df), 200)).mean().iloc[-1]
                bias_4h = 1 if df["Close"].iloc[-1] > ema_50_h else -1
                bias_1d = 1 if df["Close"].iloc[-1] > sma_200_h else -1

        # Gatillos Élite con confluencia total
        if (bos_bull or sweep_bull) and (bias_1d == 1) and (bias_4h == 1) and macd_bull:
            trigger_type = "ChoCH Alcista" if bos_bull else "Toma de Liquidez (Sweep) Alcista"
            return 'BUY', f"SMC Élite Long: {trigger_type} + MTF 1D/4H Alineado + MACD Momentum Positivo", target_duration

        if (bos_bear or sweep_bear) and (bias_1d == -1) and (bias_4h == -1) and macd_bear:
            trigger_type = "ChoCH Bajista" if bos_bear else "Toma de Liquidez (Sweep) Bajista"
            return 'SELL', f"SMC Élite Short: {trigger_type} + MTF 1D/4H Alineado + MACD Momentum Negativo", target_duration

        return 'HOLD', "Sin confluencia SMC Élite (Filtro MTF/ChoCH/Sweep no completado)", 0
