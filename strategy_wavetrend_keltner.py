from strategy_stochastic import Strategy
import pandas as pd
import numpy as np

class StrategyWaveTrendKeltner(Strategy):
    def __init__(self, bypass_filter=False):
        super().__init__("WaveTrend + Keltner Channel Reversion")
        self.type = 'REVERSION'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 50:
            return 'HOLD', "Insufficient Data (<50 candles)", 0
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 0. Identificar par y temporalidad
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        
        # Calcular intervalo de tiempo en segundos
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            time_diff = 60 # Default a 1m
            
        # Filtro de activación por par y temporalidad según backtest maestro (Restricción estricta >=60% WR)
        allowed_combinations = {
            ("AUDCAD_otc", 300),   # WR: 63.86% (83 trades)
            ("NZDUSD_otc", 900),   # WR: 65.71% (35 trades)
            ("USDCAD_otc", 60),    # WR: 64.71% (17 trades)
            ("EURUSD_otc", 900),   # WR: 61.29% (31 trades)
        }
        
        if not self.bypass_filter:
            pair_tf = (pair, time_diff)
            if pair_tf not in allowed_combinations:
                return 'HOLD', f"WaveTrendKeltner deshabilitada para {pair} en {time_diff}s (Bajo Win Rate historico)", 0
                
        # 1. Obtener valores de indicadores
        close = last['Close']
        open_p = last['Open']
        high = last['High']
        low = last['Low']
        
        # Canales de Keltner
        kc_upper = last['KC_Upper']
        kc_lower = last['KC_Lower']
        
        # WaveTrend
        wt1 = last['WT1']
        wt2 = last['WT2']
        prev_wt1 = prev['WT1']
        prev_wt2 = prev['WT2']
        
        # Parámetro optimizado para WaveTrend
        wt_limit = 50
        
        # --- CONDICIONES DE COMPRA (BUY) ---
        # 1. El precio mínimo toca o rompe el canal inferior en la vela actual o en la anterior
        kc_buy = (low <= kc_lower) or (prev['Low'] <= prev['KC_Lower'])
        
        # 2. WaveTrend está en sobreventa extrema (wt1 < -50)
        wt_oversold = wt1 < -wt_limit
        
        # 3. Cruce alcista de WaveTrend en la vela actual
        wt_cross_buy = prev_wt1 < prev_wt2 and wt1 > wt2
        
        # 4. Confirmación de vela alcista
        confirm_buy = close > open_p
        
        if kc_buy and wt_oversold and wt_cross_buy and confirm_buy:
            return 'BUY', f"WT Reversion: Keltner Lower Tocado ({low:.5f} <= {kc_lower:.5f}) + WT Cruce Alcista {wt1:.1f} en sobreventa", 300
            
        # --- CONDICIONES DE VENTA (SELL) ---
        # 1. El precio máximo toca o rompe el canal superior en la vela actual o en la anterior
        kc_sell = (high >= kc_upper) or (prev['High'] >= prev['KC_Upper'])
        
        # 2. WaveTrend está en sobrecompra extrema (wt1 > 50)
        wt_overbought = wt1 > wt_limit
        
        # 3. Cruce bajista de WaveTrend en la vela actual
        wt_cross_sell = prev_wt1 > prev_wt2 and wt1 < wt2
        
        # 4. Confirmación de vela bajista
        confirm_sell = close < open_p
        
        if kc_sell and wt_overbought and wt_cross_sell and confirm_sell:
            return 'SELL', f"WT Reversion: Keltner Upper Tocado ({high:.5f} >= {kc_upper:.5f}) + WT Cruce Bajista {wt1:.1f} en sobrecompra", 300
            
        return 'HOLD', f"No WaveTrend-Keltner signal on {pair}", 0
