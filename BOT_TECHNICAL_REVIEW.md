# 🔍 Revisión Técnica: Detector, Router, Prompts y Estadísticas

Este documento contiene los códigos fuente exactos, plantillas de prompts y datos estadísticos reales extraídos de los archivos del bot para tu revisión detallada.

---

## 1. Código del Detector de Triángulos (Compresión)
Ubicación: `patterns.py` (Líneas 210-225)

Este fragmento de código identifica la compresión de precios (máximos decrecientes y mínimos crecientes) utilizando los extremos locales confirmados. Para evitar el *lookahead bias* (sesgo de repintado), los extremos se confirman 5 velas atrás, por lo que buscamos el precio del pico/valle real en la vela `index - 5` de la confirmación:

```python
        # --- Triángulo (Compresión) ---
        if len(maxs) >= 2 and len(mins) >= 2:
             # Los picos y valles reales ocurrieron 5 velas antes de la confirmación
             p_max1 = df.loc[maxs.index[-2] - 5]['High']
             p_max2 = df.loc[maxs.index[-1] - 5]['High']
             p_min1 = df.loc[mins.index[-2] - 5]['Low']
             p_min2 = df.loc[mins.index[-1] - 5]['Low']
             
             # Maximos decrecientes Y mínimos crecientes (Compresión clásica)
             if p_max2 < p_max1 and p_min2 > p_min1:
                 df.iloc[-1, df.columns.get_loc('Pattern_Triangle')] = 1
                  
        return df
```

### Explicación Lógica:
1.  `maxs` y `mins` contienen las velas donde se confirmó un máximo o mínimo local (utilizando una ventana de 11 velas y comparando la vela central con las 5 anteriores y 5 posteriores).
2.  `maxs.index[-1] - 5` apunta al índice exacto donde ocurrió el pico real (hace 5 periodos).
3.  Compara si el último pico es menor al anterior (`p_max2 < p_max1`) y el último valle es mayor al anterior (`p_min2 > p_min1`). Si ambas condiciones se cumplen, activa la marca `Pattern_Triangle = 1` en la vela actual.

---

## 2. Código del Router de Régimen de Mercado
Ubicación: `main.py` (Líneas 493-516)

Este bloque determina qué tipo de estrategias (`TREND` o `REVERSION`) se permiten ejecutar según el estado de la tendencia actual del gráfico de 5m (calculado mediante el ADX e inclinación de EMAs):

```python
        # --- CONFIGURACIÓN DE ACTIVACIÓN DE ESTRATEGIAS SEGÚN RÉGIMEN (Strategy Router) ---
        allowed_types = []
        if market_state in ['TRENDING_UP', 'TRENDING_DOWN']:
            allowed_types = ['TREND']
        elif market_state == 'SIDEWAYS':
            # Evitamos operar por completo en consolidaciones de bajo rango (chop market)
            allowed_types = []
        elif market_state == 'VOLATILE':
            # Protegemos el capital evitando operaciones durante volatilidad descontrolada
            allowed_types = []
        elif market_state == 'NEUTRAL':
            # En transiciones o mercados sin tendencia, permitimos tanto continuación/pullback como reversión
            allowed_types = ['TREND', 'REVERSION']
        else:
            allowed_types = []

        for strategy in self.strategies:
            strat_type = getattr(strategy, 'type', 'TREND')
            if strat_type not in allowed_types:
                if self.verbose: 
                    print(f"  [REGIME] Saltando {strategy.name} ({strat_type}) por incompatibilidad con régimen {market_state}")
                strategy_logs.append(f"   🛡️ <b>{strategy.name}</b>: Incompatible con {market_state}")
                continue
```

### Reglas de Negocio del Router:
*   `TRENDING_UP` / `TRENDING_DOWN`: Se bloquean las estrategias de reversión como Cambio de Estructura (MSS) para evitar ir contra la tendencia fuerte. Solo se permite continuar (`StrategyContinuation` o `StrategyStochastic`).
*   `SIDEWAYS` / `VOLATILE`: Se bloquean **todas** las estrategias. Es un **Hard Lock** preventivo para mercados erráticos de mechas o rangos estrechos sin volumen.
*   `NEUTRAL`: Habilita ambos mundos (`TREND` y `REVERSION`), ya que es la zona óptima donde ocurren pullbacks profundos y formaciones de doble techo/suelo.

---

## 3. Prompt Exacto Enviado a Gemini (Live Validator)
Ubicación: `main.py` (Líneas 252-268)

Este es el prompt en español estructurado que se le envía a Gemini Flash junto con un objeto JSON compacto que contiene indicadores en tiempo real (RSI, Stoch, MACD, ATR, EMA, Regime, etc.):

```text
Eres un filtro inteligente de riesgo extremo para un bot de opciones binarias (PocketOption). Analiza esta señal y responde SOLO con un objeto JSON.

SEÑAL PROPUESTA Y CONTEXTO COMPLETO:
{JSON_DE_INDICADORES}

REGLAS CRÍTICAS PARA TU ROL (FILTRO DE RIESGO Y CUIDADO DEL CAPITAL):
1. Analiza el contexto de régimen de mercado ('market_state') y la tendencia en múltiples timeframes ('multi_timeframe').
2. BLOQUEA la señal si detectas alguna de las siguientes situaciones de alto riesgo técnico:
   - "Cuchillo Cayendo" (Falling Knife): Señal de COMPRA (BUY) cuando el precio está cayendo con fuerza (ej. Close muy por debajo de la EMA 20 y RSI < 38) sin confirmación de giro o soporte.
   - "Subida Vertical" (Rising Knife): Señal de VENTA (SELL) cuando el precio está subiendo con fuerza (ej. Close muy por encima de la EMA 20 y RSI > 62) sin confirmación de resistencia.
   - Contra-Tendencia Absoluta: Ir en contra de la tendencia principal ('1h_trend') en mercados con fuerte direccionalidad (TRENDING_UP / TRENDING_DOWN).
   - Agotamiento Extremo: Señales de COMPRA con RSI > 75 o Stoch_K > 95, o señales de VENTA con RSI < 25 o Stoch_K < 5, ya que hay alta probabilidad de retroceso inmediato (mortal para opciones de 5 minutos).
   - Consolidación sin Volumen (Chop Market): Rango muy estrecho o ATR plano donde el precio oscila sin dirección clara, aumentando falsos breakouts.
3. Si el contexto técnico muestra alineación de tendencias, soporte/resistencia respetados y osciladores saliendo de zonas de sobrecompra/sobreventa de manera saludable, tu veredicto debe ser APPROVED.

Devuelve SOLO este JSON, sin explicaciones ni formato markdown fuera del bloque:
{"decision": "APPROVED" o "BLOCKED", "confidence": 1-100, "reason": "Una línea concisa en español explicando el riesgo crítico si bloqueas, o por qué se aprueba"}
```

---

## 4. Estadísticas Reales (Base de Datos: 1,979 Trades Analizados)
Ubicación: `trading_intelligence.json` (Generado el 02 de junio a las 07:31)

### A. Rendimiento por Estrategia
| Estrategia | Operaciones | Ganadas (Wins) | Win Rate (WR) |
| :--- | :---: | :---: | :---: |
| **Fibonacci Retracement 61.8%** | 301 | 158 | **52.49%** |
| **Cambio de Estructura (MSS)** | 985 | 502 | **50.96%** |
| **Estocástico + SMA200** | 611 | 307 | **50.25%** |
| **Patrones de Continuación** | 82 | 37 | **45.12%** |

---

### B. Zonas de Alta Confianza (Efectividad > 70% WR)
Estas son las combinaciones de par y hora en las que el bot tiene una tasa de éxito sobresaliente. Si el bot opera fuera de estos horarios y no tiene el validador de Gemini activo, la operación es rechazada automáticamente:

| Hora (UTC) | Hora (Local Arg GMT-3) | Par | Win Rate (WR) | Muestras |
| :---: | :---: | :--- | :---: | :---: |
| **21:00** | 18:00 (Ayer) | `USDCOP_otc` | **100.00%** | 5 trades |
| **16:00** | 13:00 | `USDCOP_otc` | **85.71%** | 7 trades |
| **01:00** | 22:00 (Ayer) | `USDMXN_otc` | **80.00%** | 5 trades |
| **20:00** | 17:00 | `AUDCAD_otc` | **80.00%** | 15 trades |
| **01:00** | 22:00 (Ayer) | `AUDCAD_otc` | **77.78%** | 9 trades |
| **18:00** | 15:00 | `USDCOP_otc` | **77.78%** | 9 trades |
| **11:00** | 08:00 | `USDCAD_otc` | **75.00%** | 4 trades |
| **17:00** | 14:00 | `AUDCAD_otc` | **73.33%** | 15 trades |
| **09:00** | 06:00 | `GBPUSD_otc` | **72.00%** | 25 trades |
| **00:00** | 21:00 (Ayer) | `USDCAD_otc` | **71.43%** | 7 trades |
| **14:00** | 11:00 | `EURUSD_otc` | **71.43%** | 28 trades |

---

### C. Zonas de Riesgo Extremo (Efectividad Muy Baja)
El bot detecta estas combinaciones como zonas de peligro y **las bloquea por completo** de forma proactiva:

| Hora (UTC) | Hora (Local) | Par | Win Rate (WR) | Muestras |
| :---: | :---: | :--- | :---: | :---: |
| **05:00** | 02:00 | `USDCOP_otc` | **0.00%** | 6 trades |
| **06:00** | 03:00 | `USDMXN_otc` | **0.00%** | 5 trades |
| **08:00** | 05:00 | `USDCAD_otc` | **0.00%** | 3 trades |
| **12:00** | 09:00 | `AUDCAD_otc` | **0.00%** | 3 trades |
| **13:00** | 10:00 | `EURUSD_otc` | **0.00%** | 5 trades |
| **13:00** | 10:00 | `GBPUSD_otc` | **0.00%** | 4 trades |
| **15:00** | 12:00 | `USDCOP_otc` | **0.00%** | 4 trades |
| **14:00** | 11:00 | `AUDCAD_otc` | **14.28%** | 7 trades |
| **12:00** | 09:00 | `EURUSD_otc` | **16.67%** | 6 trades |
| **01:00** | 22:00 | `USDCAD_otc` | **16.67%** | 6 trades |
| **03:00** | 00:00 | `USDCOP_otc` | **16.67%** | 6 trades |
| **22:00** | 19:00 | `USDCOP_otc` | **16.67%** | 6 trades |
| **02:00** | 23:00 | `USDCOP_otc` | **20.00%** | 5 trades |
