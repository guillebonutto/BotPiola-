from strategy_stochastic import Strategy
import pandas as pd
import numpy as np
import ta

class StrategyHybridSniper(Strategy):
    """
    HYBRID Ultra-Sniper Reversion:
    Combina:
      1. Trend Shield SMA 200 (Tendencia macro a favor)
      2. Bandas de Bollinger a 2.5 Desviaciones Estándar (Extremo estadístico)
      3. WaveTrend Extremo (WT1 <= -55 / >= 55)
      4. RSI 14 Extremo (RSI <= 30 / >= 70)
    Resultados Backtest: 77.3% - 100% Win Rate en activos seleccionados.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("HYBRID Ultra-Sniper (WaveTrend + BB 2.5 + RSI + SMA200)")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0
            
        # 0. Identificar par y temporalidad
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        
        try:
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))
            
        allowed_combinations = {
            ("#INTC_otc", 900),   # WR: 100.0% (PF: 99.0)
            ("NZDUSD_otc", 60),    # WR: 90.0%  (PF: 7.65)
            ("#MCD_otc", 900),    # WR: 85.7%  (PF: 5.10)
            ("#AAPL_otc", 900),   # WR: 80.0%  (PF: 3.40)
            ("AUDJPY_otc", 900),  # WR: 80.0%  (PF: 3.40)
            ("USDCOP_otc", 300),  # WR: 76.9%  (PF: 2.83)
            ("AUDJPY_otc", 300),  # WR: 75.0%  (PF: 2.55)
            ("#BA_otc", 900),     # WR: 70.0%  (PF: 1.98)
        }
        
        if not self.bypass_filter and pair != 'UNKNOWN' and (pair, time_diff) not in allowed_combinations:
            return 'HOLD', f"Asset {pair} @ {time_diff}s not in Hybrid Sniper Whitelist", 0
            
        last = df.iloc[-1]
        close = last['Close']
        high = last['High']
        low = last['Low']
        
        # 1. Trend Shield SMA 200
        if 'SMA_200' in df.columns:
            sma200 = last['SMA_200']
        else:
            sma200 = ta.trend.sma_indicator(df['Close'], window=200).iloc[-1]
            
        if pd.isna(sma200):
            sma200 = close # Fallback if not enough candles
            
        # 2. Bollinger Bands 2.5 Dev
        if 'BB_Upper_25' in df.columns and 'BB_Lower_25' in df.columns:
            bb_u25 = last['BB_Upper_25']
            bb_l25 = last['BB_Lower_25']
        else:
            bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2.5)
            bb_u25 = bb.bollinger_hband().iloc[-1]
            bb_l25 = bb.bollinger_lband().iloc[-1]
            
        # 3. WaveTrend
        if 'WT1' in df.columns:
            wt1 = last['WT1']
        else:
            ap = (df['High'] + df['Low'] + df['Close']) / 3.0
            esa = ap.ewm(span=10, adjust=False).mean()
            d = (ap - esa).abs().ewm(span=10, adjust=False).mean()
            ci = (ap - esa) / (0.015 * d.replace(0, 0.0001))
            wt1 = ci.ewm(span=21, adjust=False).mean().iloc[-1]
            
        # 4. RSI 14
        if 'RSI' in df.columns:
            rsi = last['RSI']
        elif 'RSI_14' in df.columns:
            rsi = last['RSI_14']
        else:
            rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1]
            
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300
        
        # --- SEÑAL DE COMPRA (BUY) ---
        # Precio penetra o toca banda inferior 2.5 + WaveTrend sobreventa <= -55 + RSI <= 30 + Sobre SMA200
        if (low <= bb_l25 or close <= bb_l25) and wt1 <= -55.0 and rsi <= 30.0 and close > sma200:
            reason = f"Hybrid Sniper BUY en {pair} (Low <= BB2.5 [{bb_l25:.5f}] + WT1 {wt1:.1f} <= -55 + RSI {rsi:.1f} <= 30 + Trend Shield > SMA200)"
            return 'BUY', reason, target_duration
            
        # --- SEÑAL DE VENTA (SELL) ---
        # Precio penetra o toca banda superior 2.5 + WaveTrend sobrecompra >= 55 + RSI >= 70 + Bajo SMA200
        if (high >= bb_u25 or close >= bb_u25) and wt1 >= 55.0 and rsi >= 70.0 and close < sma200:
            reason = f"Hybrid Sniper SELL en {pair} (High >= BB2.5 [{bb_u25:.5f}] + WT1 {wt1:.1f} >= 55 + RSI {rsi:.1f} >= 70 + Trend Shield < SMA200)"
            return 'SELL', reason, target_duration
            
        return 'HOLD', f"No Hybrid Sniper setup on {pair}", 0
