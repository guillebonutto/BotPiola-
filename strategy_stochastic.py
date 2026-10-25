from abc import ABC, abstractmethod

class Strategy(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def get_signal(self, df):
        """
        Retorna:
        - 'BUY', 'SELL' o 'HOLD'
        - Razón/Detalle
        - Duración sugerida (en segundos)
        """
        pass

class StrategyStochastic(Strategy):
    def __init__(self, bypass_filter=False):
        super().__init__("Estocástico + SMA200")
        self.type = 'TREND'
        self.bypass_filter = bypass_filter
        
    def get_signal(self, df):
        if df.empty or len(df) < 200:
            return 'HOLD', "Insufficient Data (<200 candles)", 0
            
        # 0. Identificar par y temporalidad para aplicar filtro de efectividad
        pair = df['symbol'].iloc[-1] if 'symbol' in df.columns else df.attrs.get('pair', 'UNKNOWN')
        try:
            t1 = pd.to_datetime(df.iloc[-1]['Timestamp'])
            t2 = pd.to_datetime(df.iloc[-2]['Timestamp'])
            time_diff = int((t1 - t2).total_seconds())
        except Exception:
            time_diff = int(df.attrs.get('interval', 300))
            
        allowed_combinations = {
            ("#AAPL_otc", 900),    # WR: 58.33% (72 trades, +$12.30)
            ("AUDUSD_otc", 300),   # WR: 60.66% (61 trades, +$11.65)
            ("USDCHF_otc", 900),   # WR: 60.32% (63 trades, +$11.50)
            ("AUDCAD_otc", 900),   # WR: 71.43% (28 trades)
            ("#MSFT_otc", 900),    # WR: 63.41% (41 trades)
        }
        
        pair_tf = (pair, time_diff)
        if not self.bypass_filter and pair_tf not in allowed_combinations:
            return 'HOLD', f"Estocático deshabilitado para {pair} en {time_diff}s (Bajo Win Rate o muestra insuficiente)", 0
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Definir Tendencia Mayor y Alineación de EMAs
        sma_200 = last['SMA_200']
        ema_20 = last['EMA_20']
        ema_50 = last['EMA_50']
        close = last['Close']
        rsi = last['RSI']
        
        is_bull_trend = close > sma_200 and ema_20 > ema_50
        is_bear_trend = close < sma_200 and ema_20 < ema_50
        
        # Duración dinámica según el timeframe de la vela analizada
        target_duration = int(time_diff) if time_diff in [60, 300, 900] else 300

        # 2. Señal de Compra (Tendencia Alcista)
        if is_bull_trend:
            if prev['Stoch_K'] < 20 and prev['Stoch_K'] < prev['Stoch_D'] and last['Stoch_K'] > last['Stoch_D']:
                # Evitar entrar si el cruce es demasiado tardío (Stoch_K ya subió demasiado)
                if last['Stoch_K'] <= 30:
                    # Evitar entrar en velas gigantes agotadoras (body > 0.6 * ATR)
                    atr = last.get('ATR', 0.0002)
                    body = abs(close - last['Open'])
                    if body <= atr * 0.6:
                        # Evitar entrar si el RSI es extremadamente bajo (fuerte impulso de caída) o ya sobrecomprado
                        if rsi > 40 and rsi < 70:
                            if close > last['Open'] or last.get('CDL_HAMMER', 0) == 100:
                                return 'BUY', "Cruce Estocástico en Sobreventa + Tendencia Alcista Confirmada", target_duration
                  
        # 3. Señal de Venta (Tendencia Bajista)
        if is_bear_trend:
            if prev['Stoch_K'] > 80 and prev['Stoch_K'] > prev['Stoch_D'] and last['Stoch_K'] < last['Stoch_D']:
                # Evitar entrar si el cruce es demasiado tardío (Stoch_K ya bajó demasiado)
                if last['Stoch_K'] >= 70:
                    # Evitar entrar en velas gigantes agotadoras (body > 0.6 * ATR)
                    atr = last.get('ATR', 0.0002)
                    body = abs(close - last['Open'])
                    if body <= atr * 0.6:
                        # Evitar entrar si el RSI es extremadamente alto (fuerte impulso de subida) o ya sobrevendido
                        if rsi < 60 and rsi > 30:
                            if close < last['Open'] or last.get('CDL_SHOOTINGSTAR', 0) == -100:
                                return 'SELL', "Cruce Estocástico en Sobrecompra + Tendencia Bajista Confirmada", target_duration
                
        return 'HOLD', f"Trend {'BULL' if is_bull_trend else 'BEAR' if is_bear_trend else 'NEUTRAL'} | Stoch K={last['Stoch_K']:.1f}", 0
