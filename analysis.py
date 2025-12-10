import pandas as pd
import numpy as np
import ta
from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from datetime import datetime

class MarketAnalyzer:
    def __init__(self):
        pass

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
        
        # --- Volatilidad ---
        # ATR 14
        atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
        df['ATR'] = atr.average_true_range()
        
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
        
        # Lógica de lateralización
        if adx < 20:
            return 'SIDEWAYS'
            
        # Detección de volatilidad alta (si ATR sube mucho respecto a su media)
        if 'ATR' in df.columns:
            atr_avg = df['ATR'].rolling(20).mean().iloc[-1]
            if last['ATR'] > atr_avg * 1.5:
                return 'VOLATILE'
            
        return 'SIDEWAYS' # Default

    def check_news(self):
        """
        Placeholder para análisis fundamental.
        """
        # TODO: Implementar scraping de calendario económico
        # print(f"[{datetime.now()}] [INFO] Verificando noticias... (Placeholder: Sin noticias de alto impacto)")
        return 'NEUTRAL'
