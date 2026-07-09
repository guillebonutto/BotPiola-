from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategyAlphaConvergence(Strategy):
    def __init__(self, bypass_filter=False):
        super().__init__("Alpha Convergence (Bollinger + Fibo + Stoch)")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 200:
            return 'HOLD', "Insufficient Data (<200 candles)", 0
            
        # 0. Identificar par y temporalidad
        last = df.iloc[-1]
        prev = df.iloc[-2]
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            time_diff = 60 # Default a 1m
            
        allowed_combinations = {
            ("AUDCAD_otc", 60),    # WR: 63.64% (22 trades)
            ("AUDCAD_otc", 300),   # WR: 62.50% (16 trades)
            ("GBPUSD_otc", 300),   # WR: 62.07% (29 trades)
            ("#BA_otc", 900),      # WR: 61.90% (21 trades)
            ("#INTC_otc", 300),    # WR: 59.09% (44 trades)
            ("#MSFT_otc", 900),    # WR: 58.82% (17 trades)
        }
        
        pair_tf = (pair, time_diff)
        if not self.bypass_filter and pair_tf not in allowed_combinations:
            return 'HOLD', f"Alpha Convergence deshabilitada para {pair} en {time_diff}s (Bajo Win Rate historico)", 0
            
        # 1. Parámetros optimizados
        fib_levels = [0.618, 0.786]
        tolerance = 0.03
        stoch_limit = 30
        
        # 2. Obtener Swings High y Low
        recent = df.iloc[-100:]
        swing_highs = recent[recent['max_local'] == True]
        swing_lows = recent[recent['min_local'] == True]
        
        if not swing_highs.empty:
            confirm_idx = swing_highs.index[-1]
            peak_idx = confirm_idx - 5
            high_price = df.loc[peak_idx]['High'] if peak_idx in df.index else swing_highs.iloc[-1]['High']
        else:
            high_price = recent['High'].max()
            
        if not swing_lows.empty:
            confirm_idx = swing_lows.index[-1]
            trough_idx = confirm_idx - 5
            low_price = df.loc[trough_idx]['Low'] if trough_idx in df.index else swing_lows.iloc[-1]['Low']
        else:
            low_price = recent['Low'].min()
            
        price_range = high_price - low_price
        if price_range <= 0:
            return 'HOLD', "Zero swing price range", 0
            
        close = last['Close']
        high = last['High']
        low = last['Low']
        open_p = last['Open']
        
        bb_upper = last['BB_Upper']
        bb_lower = last['BB_Lower']
        stoch_k = last['Stoch_K']
        
        # --- CONDICIONES DE COMPRA (BUY) ---
        bb_buy = low <= bb_lower
        
        fibo_buy = False
        hit_lvl = None
        for lvl in fib_levels:
            fib_val = high_price - (price_range * lvl)
            if abs(close - fib_val) < (price_range * tolerance):
                fibo_buy = True
                hit_lvl = lvl
                break
                
        stoch_buy = stoch_k < stoch_limit
        confirm_buy = close > open_p
        
        if bb_buy and fibo_buy and stoch_buy and confirm_buy:
            return 'BUY', f"Alpha Reversion: BB Lower Tocado + Fibo {hit_lvl*100:.1f}% Respetado + Stoch K={stoch_k:.1f} (Sobreventa)", 300
            
        # --- CONDICIONES DE VENTA (SELL) ---
        bb_sell = high >= bb_upper
        
        fibo_sell = False
        for lvl in fib_levels:
            fib_val = low_price + (price_range * lvl)
            if abs(close - fib_val) < (price_range * tolerance):
                fibo_sell = True
                hit_lvl = lvl
                break
                
        stoch_sell = stoch_k > (100 - stoch_limit)
        confirm_sell = close < open_p
        
        if bb_sell and fibo_sell and stoch_sell and confirm_sell:
            return 'SELL', f"Alpha Reversion: BB Upper Tocado + Fibo {hit_lvl*100:.1f}% Respetado + Stoch K={stoch_k:.1f} (Sobrecompra)", 300
            
        return 'HOLD', f"No Alpha convergence on {pair}", 0
