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
    def __init__(self):
        super().__init__("Estocástico + SMA200")
        
    def get_signal(self, df):
        if df.empty or len(df) < 200:
            return 'HOLD', None, 0
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Definir Tendencia Mayor con SMA 200
        trend = 'BULL' if last['Close'] > last['SMA_200'] else 'BEAR'
        
        # 2. Señal de Compra (Tendencia Alcista)
        # Estocástico estaba en sobreventa (<20) y cruza hacia arriba su media (%D)
        if trend == 'BULL':
            if prev['Stoch_K'] < 20 and last['Stoch_K'] > last['Stoch_D'] and last['Stoch_K'] > prev['Stoch_K']:
                 return 'BUY', "Cruce Estocástico en Sobreventa + Tendencia Alcista", 300 # 5 min
                 
        # 3. Señal de Venta (Tendencia Bajista)
        # Estocástico estaba en sobrecompra (>80) y cruza hacia abajo su media
        if trend == 'BEAR':
            if prev['Stoch_K'] > 80 and last['Stoch_K'] < last['Stoch_D'] and last['Stoch_K'] < prev['Stoch_K']:
                return 'SELL', "Cruce Estocástico en Sobrecompra + Tendencia Bajista", 300
                
        return 'HOLD', None, 0
