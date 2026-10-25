import pandas as pd
import numpy as np
import ta
from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from datetime import datetime
from news_fetcher import NewsFetcher

class MarketAnalyzer:
    def __init__(self):
        self.news_fetcher = NewsFetcher()

    def compute_indicators(self, df):
        """Calcula todos los indicadores técnicos necesarios."""
        if df.empty:
            return df
        
        # --- Tendencia ---
        # SMA 200
        sma_200 = SMAIndicator(close=df['Close'], window=200)
        df['SMA_200'] = sma_200.sma_indicator()
        
        # EMA 20
        ema_20 = EMAIndicator(close=df['Close'], window=20)
        df['EMA_20'] = ema_20.ema_indicator()
        
        # EMA 50
        ema_50 = EMAIndicator(close=df['Close'], window=50)
        df['EMA_50'] = ema_50.ema_indicator()
        
        # --- Osciladores ---
        # RSI 14
        rsi = RSIIndicator(close=df['Close'], window=14)
        df['RSI'] = rsi.rsi()
        
        # Estocástico (16, 3, 3) 
        # Nota: talib.STOCH usa fastk=16, slowk=3, slowd=3
        # ta.StochasticOscillator recibe window=14 (por defecto), smooth_window=3
        stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], 
                                     window=16, smooth_window=3)
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal() 
        
        # MACD (12, 26, 9)
        macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Hist'] = macd.macd_diff()
        
        # --- Bandas de Bollinger (20, 2) ---
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_Upper'] = bb.bollinger_hband()
        df['BB_Middle'] = bb.bollinger_mavg()
        df['BB_Lower'] = bb.bollinger_lband()
        
        # --- Volatilidad y Fuerza ---
        # ATR 14
        atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
        df['ATR'] = atr.average_true_range()
        
        # ADX 14
        adx = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
        df['ADX'] = adx.adx()
        
        # --- Canales de Keltner (20, 10, 1.5) ---
        kc_middle = EMAIndicator(close=df['Close'], window=20).ema_indicator()
        atr_10 = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=10).average_true_range()
        df['KC_Middle'] = kc_middle
        df['KC_Upper'] = kc_middle + (1.5 * atr_10)
        df['KC_Lower'] = kc_middle - (1.5 * atr_10)
        
        # --- WaveTrend Oscillator (10, 21) ---
        ap = (df['High'] + df['Low'] + df['Close']) / 3.0
        esa = ap.ewm(span=10, adjust=False).mean()
        d = abs(ap - esa).ewm(span=10, adjust=False).mean()
        d_clipped = d.clip(lower=1e-9)
        ci = (ap - esa) / (0.015 * d_clipped)
        df['WT1'] = ci.ewm(span=21, adjust=False).mean()
        df['WT2'] = df['WT1'].rolling(window=4).mean()
        
        return df

    def determine_market_state(self, df):
        """
        Determina si el mercado está en TENDENCIA o LATERAL/RANGO.
        Retorna: 'TRENDING_UP', 'TRENDING_DOWN', 'SIDEWAYS', 'VOLATILE'
        """
        if len(df) < 50:
            return 'UNKNOWN'
        
        last = df.iloc[-1]
        
        # Filtro ADX para fuerza de tendencia
        adx_ind = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
        # Calculamos ADX para toda la serie para obtener el último valor
        # Nota: Es eficiente hacerlo una vez, pero aquí se recalcula. 
        # Idealmente mover al compute_indicators si se usa mucho.
        adx_series = adx_ind.adx()
        adx = adx_series.iloc[-1]
        
        # Lógica básica de tendencia con EMAs y ADX
        # Asegurarse que EMA_20 y EMA_50 existen y no son NaN
        if pd.isna(last['EMA_20']) or pd.isna(last['EMA_50']):
             return 'UNKNOWN'

        if adx > 25:
            if last['EMA_20'] > last['EMA_50'] and last['Close'] > last['EMA_50']:
                return 'TRENDING_UP'
            elif last['EMA_20'] < last['EMA_50'] and last['Close'] < last['EMA_50']:
                return 'TRENDING_DOWN'
        
        # Lógica de lateralización (Relajada: ADX < 18 en lugar de 20)
        if adx < 18:
            return 'SIDEWAYS'
            
        # Detección de volatilidad alta
        if 'ATR' in df.columns:
            atr_avg = df['ATR'].rolling(20).mean().iloc[-1]
            if last['ATR'] > atr_avg * 1.8: # Más tolerante (1.8 en lugar de 1.5)
                return 'VOLATILE'
            
        # Zona de transición (Neutral)
        return 'NEUTRAL'

    def check_news(self, pair, window_minutes=15):
        """
        Verifica si hay noticias de alto impacto para las monedas del par.
        """
        if pair.endswith('_otc'):
            return 'NEUTRAL', "Sin noticias de alto impacto cercanas (Activo OTC)"
        try:
            high_impact_events = self.news_fetcher.get_upcoming_high_impact_news(pair, window_minutes)
            if high_impact_events:
                # Retornar el primer evento encontrado como razón
                event = high_impact_events[0]
                return 'HIGH_IMPACT', f"Noticia: {event['event']} ({event['currency']}) a las {event['time'].strftime('%H:%M')}"
            return 'NEUTRAL', "Sin noticias de alto impacto cercanas"
        except Exception as e:
            print(f"[WARN] Error al verificar noticias: {e}")
            return 'NEUTRAL', "Error en verificación de noticias"


    def get_trend(self, df, timeframe='meso'):
        """
        Determina la tendencia de un dataframe basado en el timeframe.
        Macro (1h): EMA 200 + MACD
        Meso (15m): EMA 50 + RSI
        """
        if df is None or df.empty or len(df) < 200:
            return 'NEUTRAL'

        close = df['Close']
        
        if timeframe == 'macro':
            ema_200 = EMAIndicator(close, window=200).ema_indicator()
            macd_obj = MACD(close)
            macd = macd_obj.macd()
            macd_signal = macd_obj.macd_signal()
            
            last_close = close.iloc[-1]
            last_ema = ema_200.iloc[-1]
            last_macd = macd.iloc[-1]
            last_signal = macd_signal.iloc[-1]
            
            if last_close > last_ema and last_macd > last_signal:
                return 'BULLISH'
            elif last_close < last_ema and last_macd < last_signal:
                return 'BEARISH'
            
        elif timeframe == 'meso':
            ema_50 = EMAIndicator(close, window=50).ema_indicator()
            rsi = RSIIndicator(close, window=14).rsi()
            
            last_close = close.iloc[-1]
            last_ema = ema_50.iloc[-1]
            last_rsi = rsi.iloc[-1]
            
            if last_close > last_ema and last_rsi > 50:
                return 'BULLISH'
            elif last_close < last_ema and last_rsi < 50:
                return 'BEARISH'
                
        return 'NEUTRAL'

    def get_market_context(self, df_5m, df_15m, df_1h):
        """
        Consenso de múltiples timeframes (Triple Screen).
        """
        macro = self.get_trend(df_1h, 'macro')
        meso = self.get_trend(df_15m, 'meso')
        
        # Lógica de Consenso
        if macro == 'BULLISH' and meso == 'BULLISH':
            return 'STRONG_BUY', f"🟢 Macro: {macro}, Meso: {meso} (Alineados)"
        elif macro == 'BEARISH' and meso == 'BEARISH':
            return 'STRONG_SELL', f"🔴 Macro: {macro}, Meso: {meso} (Alineados)"
        elif macro == 'NEUTRAL' and meso == 'NEUTRAL':
            return 'NEUTRAL', "⚪ Mercado sin tendencia clara"
        
        # Casos de conflicto o tendencia débil
        if macro != 'NEUTRAL' and meso == 'NEUTRAL':
            return f'ONLY_{macro}', f"🟡 Macro: {macro}, Meso: Neutral (Tendencia Débil)"
        
        if macro != meso and macro != 'NEUTRAL' and meso != 'NEUTRAL':
            return 'CONFLICT', f"⚠️ Macro: {macro}, Meso: {meso} (Conflicto de Tendencias)"
            
        return 'NEUTRAL', f"⚪ Macro: {macro}, Meso: {meso}"
