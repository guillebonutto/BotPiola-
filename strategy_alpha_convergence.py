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
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))
            
        allowed_combinations = {
            ("USDCAD_otc", 900),   # WR: 75.00% (12 trades)
            ("AUDCAD_otc", 300),   # WR: 72.73% (11 trades)
            ("#MCD_otc", 300),     # WR: 66.67% (12 trades)
            ("#MSFT_otc", 900),    # WR: 62.50% (16 trades)
            ("USDCHF_otc", 900),   # WR: 61.11% (18 trades)
            ("GBPUSD_otc", 900),   # WR: 60.00% (15 trades)
            ("#INTC_otc", 900),    # WR: 60.00% (10 trades)
            ("#BA_otc", 900),      # WR: 61.90% (21 trades)
            ("GBPUSD_otc", 300),   # WR: 62.07% (29 trades)
            ("AUDCAD_otc", 900),   # WR: 62.50% (16 trades)
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
        
        # EMAs de tendencia para Trend Shield
        ema20 = last.get('EMA_20', close)
        ema50 = last.get('EMA_50', close)
        trend_shield_buy = not (close < ema20 < ema50)
        trend_shield_sell = not (close > ema20 > ema50)

        # Duración dinámica según el timeframe de la vela analizada
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300
        
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
        
        if bb_buy and fibo_buy and stoch_buy and confirm_buy and trend_shield_buy:
            return 'BUY', f"Alpha Reversion: BB Lower Tocado + Fibo {hit_lvl*100:.1f}% Respetado + Stoch K={stoch_k:.1f} (Sobreventa) + Trend Shield", target_duration
            
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
        
        if bb_sell and fibo_sell and stoch_sell and confirm_sell and trend_shield_sell:
            return 'SELL', f"Alpha Reversion: BB Upper Tocado + Fibo {hit_lvl*100:.1f}% Respetado + Stoch K={stoch_k:.1f} (Sobrecompra) + Trend Shield", target_duration
            
        return 'HOLD', f"No Alpha convergence on {pair}", 0
