from strategy_stochastic import Strategy
import pandas as pd
import numpy as np
import ta

class StrategyPriceActionEngulfing(Strategy):
    """
    PDF 12 - Price Action: Patrón de Vela Envolvente (Bullish/Bearish Engulfing)
    en Confluencia con Extremo de Banda de Bollinger a 2.5 Desviaciones.
    Resultados Backtest: 72.4% - 75% Win Rate en GBPUSD y USDCHF.
    """
    def __init__(self, bypass_filter=False):
        super().__init__("Price Action Envolvente en Extremo Bollinger 2.5")
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
            ("GBPUSD_otc", 900),  # WR: 72.41% (21W / 8L | PF: 2.23)
            ("USDCHF_otc", 60),   # WR: 75.00% (9W / 3L | PF: 2.55)
        }
        
        if not self.bypass_filter and pair != 'UNKNOWN' and (pair, time_diff) not in allowed_combinations:
            return 'HOLD', f"Asset {pair} @ {time_diff}s not in Price Action Whitelist", 0
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        c_close = last['Close']
        c_open = last['Open']
        c_low = last['Low']
        c_high = last['High']
        
        p_close = prev['Close']
        p_open = prev['Open']
        
        body_curr = c_close - c_open
        body_prev = p_close - p_open
        
        # 1. Bollinger Bands 2.5 Dev
        if 'BB_Upper_25' in df.columns and 'BB_Lower_25' in df.columns:
            bb_u25 = last['BB_Upper_25']
            bb_l25 = last['BB_Lower_25']
        else:
            bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2.5)
            bb_u25 = bb.bollinger_hband().iloc[-1]
            bb_l25 = bb.bollinger_lband().iloc[-1]
            
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300
        
        # --- SEÑAL DE COMPRA (BULLISH ENGULFING) ---
        # Vela anterior bajista, vela actual alcista envolviendo el cuerpo anterior y rebotando en banda 2.5
        if c_low <= bb_l25 and body_prev < 0 and body_curr > 0:
            if c_close > p_open and c_open <= p_close:
                reason = f"Bullish Engulfing BUY en {pair} (Low <= BB2.5 [{bb_l25:.5f}] + Vela alcista envolviendo vela previa)"
                return 'BUY', reason, target_duration
                
        # --- SEÑAL DE VENTA (BEARISH ENGULFING) ---
        # Vela anterior alcista, vela actual bajista envolviendo el cuerpo anterior y rebotando en banda 2.5
        if c_high >= bb_u25 and body_prev > 0 and body_curr < 0:
            if c_close < p_open and c_open >= p_close:
                reason = f"Bearish Engulfing SELL en {pair} (High >= BB2.5 [{bb_u25:.5f}] + Vela bajista envolviendo vela previa)"
                return 'SELL', reason, target_duration
                
        return 'HOLD', f"No Price Action Engulfing setup on {pair}", 0
