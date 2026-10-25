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
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))
            
        # Filtro de activación por par y temporalidad según backtest maestro verificado
        allowed_combinations = {
            ("EURUSD_otc", 900),   # WR: 80.00% (PF: 3.40)
            ("#AAPL_otc", 60),     # WR: 72.73% (PF: 1.91)
            ("#PFE_otc", 300),     # WR: 71.43% (PF: 2.12)
            ("AUDCAD_otc", 900),   # WR: 70.59% (PF: 1.98)
            ("NZDUSD_otc", 900),   # WR: 70.83% (PF: 2.23)
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
        
        # EMAs de tendencia para Trend Shield
        ema20 = last.get('EMA_20', close)
        ema50 = last.get('EMA_50', close)
        
        # Trend Shield: Bloquear compras si hay una cascada bajista fuerte (Close < EMA20 < EMA50)
        trend_shield_buy = not (close < ema20 < ema50)
        # Trend Shield: Bloquear ventas si hay un rally alcista fuerte (Close > EMA20 > EMA50)
        trend_shield_sell = not (close > ema20 > ema50)
        
        # Canales de Keltner
        kc_upper = last['KC_Upper']
        kc_lower = last['KC_Lower']
        
        # WaveTrend
        wt1 = last['WT1']
        wt2 = last['WT2']
        prev_wt1 = prev['WT1']
        prev_wt2 = prev['WT2']
        
        # Parámetro optimizado para WaveTrend
        wt_limit = 45
        
        # Duración dinámica según el timeframe de la vela analizada
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300
        
        # --- CONDICIONES DE COMPRA (BUY) ---
        # 1. El precio mínimo toca o rompe el canal inferior en la vela actual o en la anterior
        kc_buy = (low <= kc_lower) or (prev['Low'] <= prev['KC_Lower'])
        
        # 2. WaveTrend está en sobreventa extrema (wt1 < -45)
        wt_oversold = wt1 < -wt_limit
        
        # 3. Cruce alcista de WaveTrend en la vela actual
        wt_cross_buy = prev_wt1 < prev_wt2 and wt1 > wt2
        
        # 4. Confirmación de vela alcista
        confirm_buy = close > open_p
        
        if kc_buy and wt_oversold and wt_cross_buy and confirm_buy and trend_shield_buy:
            return 'BUY', f"WT Reversion: Keltner Lower Tocado ({low:.5f} <= {kc_lower:.5f}) + WT Cruce Alcista {wt1:.1f} en sobreventa + Trend Shield", target_duration
            
        # --- CONDICIONES DE VENTA (SELL) ---
        # 1. El precio máximo toca o rompe el canal superior en la vela actual o en la anterior
        kc_sell = (high >= kc_upper) or (prev['High'] >= prev['KC_Upper'])
        
        # 2. WaveTrend está en sobrecompra extrema (wt1 > 45)
        wt_overbought = wt1 > wt_limit
        
        # 3. Cruce bajista de WaveTrend en la vela actual
        wt_cross_sell = prev_wt1 > prev_wt2 and wt1 < wt2
        
        # 4. Confirmación de vela bajista
        confirm_sell = close < open_p
        
        if kc_sell and wt_overbought and wt_cross_sell and confirm_sell and trend_shield_sell:
            return 'SELL', f"WT Reversion: Keltner Upper Tocado ({high:.5f} >= {kc_upper:.5f}) + WT Cruce Bajista {wt1:.1f} en sobrecompra + Trend Shield", target_duration
            
        return 'HOLD', f"No WaveTrend-Keltner signal on {pair}", 0
