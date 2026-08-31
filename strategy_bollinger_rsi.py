from strategy_stochastic import Strategy
import pandas as pd
import numpy as np
import ta

class StrategyBollingerRSI(Strategy):
    """
    PDF 16 - Bandas de Bollinger Reversion (2.5 Desviaciones) + RSI Extremo:
    Estrategia de reversión a la media basada en agotamiento estadístico del precio.
    Resultados Backtest: 75% - 83.3% Win Rate en USDCAD, USDCHF y NZDUSD.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Bollinger Extreme (2.5 Dev) + RSI Reversion")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 30:
            return 'HOLD', "Insufficient Data (<30 candles)", 0
            
        # 0. Identificar par y temporalidad
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        
        try:
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))
            
        allowed_combinations = {
            ("USDCAD_otc", 60),   # WR: 78.95% (30W / 8L | PF: 3.19)
            ("USDCHF_otc", 60),   # WR: 83.33% (PF: 4.25)
            ("NZDUSD_otc", 60),   # WR: 75.00% (PF: 2.55)
            ("NZDUSD_otc", 300),  # WR: 71.43% (PF: 2.12)
        }
        
        if not self.bypass_filter and pair != 'UNKNOWN' and (pair, time_diff) not in allowed_combinations:
            return 'HOLD', f"Asset {pair} @ {time_diff}s not in Bollinger RSI Whitelist", 0
            
        last = df.iloc[-1]
        close = last['Close']
        high = last['High']
        low = last['Low']
        
        # 1. Bollinger Bands 2.5 Dev
        if 'BB_Upper_25' in df.columns and 'BB_Lower_25' in df.columns:
            bb_u25 = last['BB_Upper_25']
            bb_l25 = last['BB_Lower_25']
        else:
            bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2.5)
            bb_u25 = bb.bollinger_hband().iloc[-1]
            bb_l25 = bb.bollinger_lband().iloc[-1]
            
        # 2. RSI 14
        if 'RSI' in df.columns:
            rsi = last['RSI']
        elif 'RSI_14' in df.columns:
            rsi = last['RSI_14']
        else:
            rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1]
            
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300
        
        # Umbrales según par
        r_buy_th = 25.0 if pair == 'USDCAD_otc' else 20.0
        r_sell_th = 75.0 if pair == 'USDCAD_otc' else 80.0
        
        # --- SEÑAL DE COMPRA (BUY) ---
        if (low <= bb_l25 or close <= bb_l25) and rsi <= r_buy_th:
            reason = f"Bollinger RSI BUY en {pair} (Low/Close <= BB2.5 [{bb_l25:.5f}] + RSI {rsi:.1f} <= {r_buy_th})"
            return 'BUY', reason, target_duration
            
        # --- SEÑAL DE VENTA (SELL) ---
        if (high >= bb_u25 or close >= bb_u25) and rsi >= r_sell_th:
            reason = f"Bollinger RSI SELL en {pair} (High/Close >= BB2.5 [{bb_u25:.5f}] + RSI {rsi:.1f} >= {r_sell_th})"
            return 'SELL', reason, target_duration
            
        return 'HOLD', f"No Bollinger RSI setup on {pair}", 0
