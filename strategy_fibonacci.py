from strategy_stochastic import Strategy
import numpy as np

class StrategyFibonacci(Strategy):
    def __init__(self, bypass_filter=False):
        super().__init__("Fibonacci Retracement 61.8%")
        self.type = 'TREND'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 200:
            return 'HOLD', "Insufficient Data (<200 candles)", 0
            
        # Filtro de activación por par y temporalidad según backtest maestro (Restricción estricta >=60% WR)
        allowed_combinations = {
            ("USDCAD_otc", 60),    # WR: 69.23% (13 trades)
        }
        
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        try:
            time_diff = int((df.iloc[-1]['Timestamp'] - df.iloc[-2]['Timestamp']).total_seconds())
        except Exception:
            time_diff = 60 # Default a 1m
            
        pair_tf = (pair, time_diff)
        if not self.bypass_filter and pair_tf not in allowed_combinations:
            return 'HOLD', f"Fibonacci deshabilitada para {pair} en {time_diff}s (Bajo Win Rate historico)", 0
            
        last = df.iloc[-1]
            
        # Detectar el último impulso real mediante Swing High / Swing Low retrospectivos
        # Usamos las marcas max_local y min_local que calculamos en patterns.py
        # Buscamos el último pico máximo y último pico mínimo dentro de las últimas 100 velas
        recent_df = df.iloc[-100:]
        
        swing_highs = recent_df[recent_df['max_local'] == True]
        swing_lows = recent_df[recent_df['min_local'] == True]
        
        # Fallback a máximos/mínimos absolutos si no hay suficientes swings confirmados
        if not swing_highs.empty:
            confirm_idx = swing_highs.index[-1]
            peak_idx = confirm_idx - 5
            if peak_idx in df.index:
                high_price = df.loc[peak_idx]['High']
            else:
                high_price = swing_highs.iloc[-1]['High']
        else:
            high_price = recent_df['High'].max()
            
        if not swing_lows.empty:
            confirm_idx = swing_lows.index[-1]
            trough_idx = confirm_idx - 5
            if trough_idx in df.index:
                low_price = df.loc[trough_idx]['Low']
            else:
                low_price = swing_lows.iloc[-1]['Low']
        else:
            low_price = recent_df['Low'].min()
            
        current_price = df.iloc[-1]['Close']
        trend_sma = df.iloc[-1]['SMA_200']
        
        # Contexto Alcista (Precio > SMA200)
        # Impulso fue de Low a High. Esperamos retroceso a 61.8%
        # Nivel 61.8 desde el Low hacia el High = High - (Range * 0.618)
        price_range = high_price - low_price
        if price_range == 0: return 'HOLD', None, 0
        
        fib_618_bull = high_price - (price_range * 0.618)
        
        # Si estamos en tendencia alcista
        if current_price > trend_sma:
            # Si el precio toca la zona del 61.8% (con margen de error más estricto: 2.5%)
            dist = abs(current_price - fib_618_bull)
            threshold = price_range * 0.025 # 2.5% de tolerancia para mayor precisión
            
            if dist < threshold:
                # Confirmación adicional: Estocástico en sobreventa (Stoch_K < 25) para asegurar fin de retroceso
                stoch_k = last.get('Stoch_K', 50)
                if stoch_k < 25:
                    # Verificar señal de giro: Martillo o Envolvente Alcista o vela de reversión
                    has_pattern = last.get('CDL_HAMMER', 0) == 100 or last.get('CDL_ENGULFING', 0) == 100
                    if has_pattern or (last['Close'] > last['Open'] and last['Close'] > df.iloc[-2]['High']):
                         return 'BUY', f"Rebote en Fibonacci 61.8% + Stoch {stoch_k:.1f} (Sobreventa) + Giro", 300

        # Contexto Bajista
        # Impulso fue de High a Low. Retroceso sube hasta 61.8%
        # Nivel 61.8 = Low + (Range * 0.618)
        fib_618_bear = low_price + (price_range * 0.618)
        
        if current_price < trend_sma:
            dist = abs(current_price - fib_618_bear)
            threshold = price_range * 0.025 # 2.5% de tolerancia
            
            if dist < threshold:
                 # Confirmación adicional: Estocástico en sobrecompra (Stoch_K > 75)
                 stoch_k = last.get('Stoch_K', 50)
                 if stoch_k > 75:
                     # Vela roja confirmatoria y Estocástico alto
                     if df.iloc[-1]['Close'] < df.iloc[-1]['Open']:
                         return 'SELL', f"Rechazo en Fibonacci 61.8% + Stoch {stoch_k:.1f} (Sobrecompra)", 300
                      
        return 'HOLD', f"Price {current_price:.4f} vs SMA {trend_sma:.4f} (No Fib signal)", 0
