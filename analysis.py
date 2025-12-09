import pandas as pd
import numpy as np
import talib
from datetime import datetime

class MarketAnalyzer:
    def __init__(self):
        pass

    def compute_indicators(self, df):
        """Calcula todos los indicadores técnicos necesarios."""
        if df.empty:
            return df
        
        # Tendencia
        df['SMA_200'] = talib.SMA(df['Close'], timeperiod=200)
        df['EMA_20'] = talib.EMA(df['Close'], timeperiod=20)
        df['EMA_50'] = talib.EMA(df['Close'], timeperiod=50)
        
        # Osciladores
        df['RSI'] = talib.RSI(df['Close'], timeperiod=14)
        
        # Estocástico (16, 3, 3)
        slowk, slowd = talib.STOCH(df['High'], df['Low'], df['Close'], 
                                   fastk_period=16, slowk_period=3, slowk_matype=0, 
                                   slowd_period=3, slowd_matype=0)
        df['Stoch_K'] = slowk
        df['Stoch_D'] = slowd
        
        # MACD (12, 26, 9)
        macd, macdsignal, macdhist = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['MACD'] = macd
        df['MACD_Signal'] = macdsignal
        df['MACD_Hist'] = macdhist
        
        # Bandas de Bollinger (20, 2)
        upper, middle, lower = talib.BBANDS(df['Close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df['BB_Upper'] = upper
        df['BB_Middle'] = middle
        df['BB_Lower'] = lower
        
        # Volatilidad
        df['ATR'] = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14)
        
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
        adx = talib.ADX(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
        
        # Lógica básica de tendencia con EMAs y ADX
        if adx > 25:
            if last['EMA_20'] > last['EMA_50'] and last['Close'] > last['EMA_50']:
                return 'TRENDING_UP'
            elif last['EMA_20'] < last['EMA_50'] and last['Close'] < last['EMA_50']:
                return 'TRENDING_DOWN'
        
        # Lógica de lateralización (Bandas de Bollinger planas o precio dentro de rango)
        # Una forma simple es ver si el ADX es bajo
        if adx < 20:
            return 'SIDEWAYS'
            
        # Detección de volatilidad alta (si ATR sube mucho respecto a su media)
        atr_avg = df['ATR'].rolling(20).mean().iloc[-1]
        if last['ATR'] > atr_avg * 1.5:
            return 'VOLATILE'
            
        return 'SIDEWAYS' # Default

    def check_news(self):
        """
        Placeholder para análisis fundamental.
        En el futuro aquí se puede conectar un scraper de Investing.com o ForexFactory.
        Por ahora retorna NEUTRAL para no bloquear operaciones.
        """
        # TODO: Implementar scraping de calendario económico
        print(f"[{datetime.now()}] [INFO] Verificando noticias... (Placeholder: Sin noticias de alto impacto)")
        return 'NEUTRAL'
