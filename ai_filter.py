import pandas as pd
import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder
    import warnings
    warnings.filterwarnings('ignore', category=UserWarning)
    import joblib
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    
import os


class AIFilter:
    def __init__(self):
        self.is_trained = False
        self.models = {}  # { pair: model }
        self.model_dir = "ai_models"
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
            
        if SKLEARN_AVAILABLE:
            self.le_pattern = LabelEncoder()
            self.load_models()
        else:
            pass

    def train(self, hist_df):
        """
        Entrena un modelo independiente por cada par con el historial de trades.
        """
        if not SKLEARN_AVAILABLE:
            print("[AI FILTER] ⚠️ scikit-learn no está instalado. No se puede entrenar.")
            return

        if hist_df.empty or len(hist_df) < 50:
            print("[AI FILTER] ⚠️ Historial insuficiente para entrenar la IA (mínimo 50 operaciones).")
            return

        try:
            df = hist_df.copy()
            df = df.dropna(subset=["timestamp", "pair", "pattern_detected", "result"])
            df = df[df["result"].str.upper().isin(["WIN", "LOSS"])]
            df["target"] = np.where(df["result"].str.upper() == "WIN", 1, 0)
            
            if len(df) < 30:
                 print("[AI FILTER] ⚠️ Muy pocas operaciones WIN/LOSS limpias para entrenar.")
                 return

            df["hour"] = df["timestamp"].dt.hour
            df["dayofweek"] = df["timestamp"].dt.dayofweek
            df["pattern_encoded"] = self.le_pattern.fit_transform(df["pattern_detected"].astype(str))
            
            # Entrenar un modelo por par
            pairs = df["pair"].unique()
            for pair in pairs:
                df_pair = df[df["pair"] == pair]
                if len(df_pair) < 15: # Mínimo de trades para entrenar un modelo específico
                    continue
                    
                # Llenar valores faltantes (para trades antiguos que no tenían indicadores guardados)
                df_pair = df_pair.fillna({'rsi': 50, 'stoch_k': 50, 'macd_hist': 0, 'ema_distance': 0, 'atr': 0.001})
                
                X = df_pair[["hour", "dayofweek", "pattern_encoded", "rsi", "stoch_k", "macd_hist", "ema_distance", "atr"]]
                y = df_pair["target"]
                
                model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
                model.fit(X, y)
                self.models[pair] = model
                
            self.is_trained = len(self.models) > 0
            
            print(f"[AI FILTER] 🧠 Entrenados {len(self.models)} modelos específicos por par con {len(df)} operaciones.")
            self.save_models()
            
        except Exception as e:
            print(f"[AI FILTER] ❌ Error entrenando modelo: {e}")
            self.is_trained = False

    def save_models(self):
        if not SKLEARN_AVAILABLE: return
        try:
            joblib.dump(self.models, os.path.join(self.model_dir, "models.joblib"))
            joblib.dump(self.le_pattern, os.path.join(self.model_dir, "le_pattern.joblib"))
            print(f"[AI FILTER] 💾 Modelos de IA guardados en disco exitosamente.")
        except Exception as e:
            print(f"[AI FILTER] ⚠️ Error guardando modelos en disco: {e}")

    def load_models(self):
        if not SKLEARN_AVAILABLE: return
        try:
            model_path = os.path.join(self.model_dir, "models.joblib")
            le_path = os.path.join(self.model_dir, "le_pattern.joblib")
            if os.path.exists(model_path) and os.path.exists(le_path):
                self.models = joblib.load(model_path)
                self.le_pattern = joblib.load(le_path)
                self.is_trained = True
                print(f"[AI FILTER] 🧠 Modelos IA cargados desde disco ({len(self.models)} pares).")
        except Exception as e:
            print(f"[AI FILTER] ⚠️ Error cargando modelos desde disco: {e}")

    def predict_probability(self, timestamp, pair, pattern, indicators=None):
        """
        Estima la probabilidad de que la señal sea ganadora (WIN).
        'indicators' debe ser un dict con: rsi, stoch_k, macd_hist, ema_distance, atr
        """
        if not self.is_trained or not SKLEARN_AVAILABLE:
            return None
            
        if pair not in self.models:
            return None # No hay modelo entrenado para este par
            
        try:
            hour = timestamp.hour
            dayofweek = timestamp.dayofweek
            
            if pattern in self.le_pattern.classes_:
                pattern_enc = self.le_pattern.transform([pattern])[0]
            else:
                pattern_enc = -1
                
            if indicators is None:
                indicators = {'rsi': 50, 'stoch_k': 50, 'macd_hist': 0, 'ema_distance': 0, 'atr': 0.001}
                
            X_new = pd.DataFrame([[
                hour, dayofweek, pattern_enc, 
                indicators.get('rsi', 50), 
                indicators.get('stoch_k', 50), 
                indicators.get('macd_hist', 0), 
                indicators.get('ema_distance', 0), 
                indicators.get('atr', 0.001)
            ]], columns=["hour", "dayofweek", "pattern_encoded", "rsi", "stoch_k", "macd_hist", "ema_distance", "atr"])
            
            model = self.models[pair]
            proba = model.predict_proba(X_new)[0][1]
            return float(proba)
            
        except Exception as e:
            print(f"[AI FILTER] ⚠️ Error en predicción para {pair}: {e}")
            return None
