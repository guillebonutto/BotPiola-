# 🤖 Documentación Completa del Bot de Trading de Opciones Binarias

Este documento detalla todas las lógicas, filtros, estrategias y funciones que tiene implementadas el bot de trading avanzado para la plataforma **PocketOption**.

---

## 1. Arquitectura de Escaneo y Análisis
El bot ejecuta un ciclo de análisis continuo (por defecto cada 10 segundos) realizando las siguientes tareas:
*   **Escaneo Multi-Par:** Escanea la lista de pares OTC configurados en `config.json` (ej: `EURUSD_otc`, `GBPUSD_otc`, etc.).
*   **Escaneo Multi-Temporal (MTF):** Recorre de manera secuencial la lista de temporalidades configuradas (ej: `60s` para M1, `300s` para M5, `900s` para M15).
*   **Descarga de Datos en Tiempo Real:** Descarga el historial de velas necesario para cada temporalidad y par (hasta 400 velas), eliminando duplicados y ordenándolos en DataFrames de pandas.
*   **Cálculo Técnico Interno:** Calcula indicadores sin librerías externas complejas:
    *   **Medias Móviles:** `SMA_200`, `EMA_20`, `EMA_50`.
    *   **Momentum/Osciladores:** `RSI` (14), `Stochastic` (14, 3, 3) (`Stoch_K` y `Stoch_D`), y `MACD` con su línea de señal.
    *   **Volatilidad:** `ATR` (Average True Range).
*   **Detección de Patrones de Velas:** Doji, Martillo (Hammer), Estrella Fugaz (Shooting Star), Envolvente Alcista/Bajista (Engulfing), Morning Star y Evening Star.
*   **Detección de Patrones Chartistas:** Identificación de Dobles Techos, Dobles Suelos y Triángulos de compresión usando extremos relativos (picos y valles) corregidos para evitar el desfase de confirmación de extremos.

---

## 2. Las 4 Estrategias de Trading Core

### A. Estocástico + SMA200 (`StrategyStochastic`)
*   **Tipo:** Tendencia (`TREND`).
*   **Lógica:** Busca retrocesos y giros a favor de la tendencia mayor.
    *   *Tendencia Alcista:* El precio está sobre la `SMA_200` y la `EMA_20 > EMA_50`.
    *   *Tendencia Bajista:* El precio está bajo la `SMA_200` y la `EMA_20 < EMA_50`.
*   **Filtros Incorporados:**
    *   **Crossover en Extremos:** Para comprar (BUY), el Estocástico anterior debe estar en sobreventa (`Stoch_K < 20`) y cruzarse al alza. Para vender (SELL), el Estocástico anterior debe estar en sobrecompra (`Stoch_K > 80`) y cruzarse a la baja.
    *   **Filtro de Cruce Tardío:** El Estocástico actual no debe estar lejos del extremo (máximo `30` en compras y mínimo `70` en ventas) para evitar entrar cuando el movimiento ya ocurrió.
    *   **Filtro de Vela Agotadora:** El tamaño del cuerpo de la vela actual no debe superar el `60% del ATR`. Si la vela es gigante, se bloquea la entrada para evitar comprar wicks o vender soportes que harán un pullback inmediato.
    *   **RSI Zone:** El RSI debe estar entre `40` y `70` para compras, y entre `30` y `60` para ventas (evita momentum extendido).

### B. Cambio de Estructura - MSS (`StrategyStructure`)
*   **Tipo:** Reversión (`REVERSION`).
*   **Lógica:** Detecta el agotamiento de la tendencia y entrada de volumen de reversión al romperse el Neckline (línea de cuello) de un Doble Techo o Doble Suelo.
*   **Filtros Incorporados:**
    *   **Ruptura Fresca:** El cruce del neckline por parte del precio debe ocurrir exactamente en la vela actual.
    *   **Distancia ATR Estricta:** El precio de entrada no puede estar alejado más de un `0.25 * ATR` de la línea de cuello (evita perseguir el precio tras un breakout extendido).
    *   **Confirmación MACD:** Requiere un cruce del histograma MACD (alcista para compras, bajista para ventas) en las últimas 3 velas.

### C. Patrones de Continuación (`StrategyContinuation`)
*   **Tipo:** Tendencia (`TREND`).
*   **Lógica:** Detecta zonas de compresión (Triángulos formados por máximos decrecientes y mínimos crecientes) y entra a favor del rompimiento de la compresión.
*   **Filtros Incorporados:**
    *   **Ruptura Fuerte:** Exige que el breakout rompa el último fractal de soporte/resistencia con un mínimo de fuerza de `0.25 * ATR`.
    *   **Filtro de Rompimiento Excesivo:** La vela no debe haber roto más allá de `0.45 * ATR` del fractal para evitar entrar tarde en el breakout de la compresión.

### D. Fibonacci Retracement 61.8% (`StrategyFibonacci`)
*   **Tipo:** Tendencia (`TREND`).
*   **Lógica:** Busca rebotes en el nivel del número áureo (61.8%) de Fibonacci del impulso más reciente en el gráfico.
*   **Filtros Incorporados:**
    *   **Tolerancia del 2.5%:** El precio debe estar en un rango de ±2.5% de tolerancia del nivel exacto.
    *   **Giro de Velas:** Confirmación con una vela de rechazo (Martillo o Envolvente) o una vela contraria que supere el extremo de la vela anterior.
    *   **Filtro Estocástico:** El oscilador debe estar en sobreventa (`Stoch_K < 25`) para compras o sobrecompra (`Stoch_K > 75`) para ventas.

---

## 3. Capas de Gestión de Riesgo (Risk Management)

El bot aplica múltiples capas de seguridad secuenciales antes de permitir el envío de una orden:

1.  **Límite de Operación Simultánea (Lock de Concurrencia):**
    *   Solo se permite **una operación activa a la vez** para toda la cuenta.
    *   Cuando se coloca una orden, el bot activa un bloqueo temporal hasta que la vela del trade expire (`duration + 10s`). En ese lapso, el bot sigue analizando pero bloquea cualquier otra compra/venta.
2.  **Stop Loss y Take Profit Diario:**
    *   El bot rastrea las ganancias/pérdidas totales de la sesión actual (`session_profit`).
    *   Si se pierde una cantidad igual o mayor al `daily_stop_loss` (ej: `-$15.0`), el bot se detiene por completo ese día.
    *   Si se gana una cantidad igual o mayor al `daily_take_profit` (ej: `+$10.0`), el bot se apaga para asegurar ganancias.
3.  **Bloqueo por Racha Negativa (Session Fails):**
    *   Si una estrategia individual acumula **3 pérdidas consecutivas**, esa estrategia específica se bloquea en memoria y no vuelve a tomar operaciones hasta que el bot se reinicie. Esto evita que una estrategia "queme" la cuenta si el mercado no se alinea a su lógica.
4.  **Money Management Configurable:**
    *   `fixed`: Importe fijo por operación (ej: `$1.0`).
    *   `compound`: Calcula el importe como un porcentaje (ej: `1%`) del saldo real de la cuenta para interés compuesto automático.
    *   `martingale`: Multiplica el importe (ej: `x2.0`) tras cada operación perdida, volviendo al monto base tras ganar o al alcanzar el límite de pasos (`martingale_max_steps`).
5.  **Filtro de Régimen de Mercado (Router de Estrategias):**
    *   El bot detecta la estructura actual: `TRENDING_UP`, `TRENDING_DOWN`, `SIDEWAYS` (Consolidación) o `VOLATILE` (Volatilidad Extrema).
    *   **Sideways / Volatiles:** El bot entra en un bloqueo absoluto y no opera nada para evitar el "serrucho" de las consolidaciones sin volumen y los spikes aleatorios de alta volatilidad.
    *   **Trending:** Solo permite estrategias lógicas de continuación de tendencia (`TREND`).
    *   **Neutral:** Permite tanto estrategias de tendencia como de reversión de corto plazo.
6.  **Filtro Fundamental (Noticias):**
    *   Monitorea eventos económicos de alto impacto y pausa la operativa en el par afectado durante la ventana de tiempo del evento (ej: ±15 minutos).

---

## 4. El Rol de la Inteligencia Artificial (IA Dual)

El bot cuenta con dos niveles de Inteligencia Artificial que operan de forma independiente y complementaria:

### A. Filtro IA Estático (Bucle de Auto-Aprendizaje)
*   **Función:** Identifica los mejores horarios y pares con base en la estadística histórica de trades reales guardados en la base de datos SQL local (`feedback.db`).
*   **Operativa:** Al final de cada operación cerrada, el bot ejecuta en segundo plano un script de re-cálculo (`analyze_best_times.py`) que genera o actualiza el archivo `trading_intelligence.json`.
*   **Filtro:** Define las **Zonas de Confianza** (horas y pares con efectividad histórica `> 70%`) y bloquea de manera preventiva cualquier operación que ocurra en horarios donde el rendimiento estadístico del bot sea bajo o no óptimo.

### B. Filtro IA en Tiempo Real (Gemini Live Validator)
*   **Función:** Actúa como el filtro humano/analista que toma la decisión final de presionar o no el gatillo basándose en la acción del precio visual.
*   **Operativa:** Si hay una señal válida de cualquiera de las 4 estrategias lógicas, el bot recopila un snapshot con los datos técnicos detallados (RSI, Stochastic, régimen de mercado, tendencia MTF, distancia ATR, etc.) y le envía un Prompt estricto a **Gemini Flash**.
*   **Filtro:** Gemini analiza la señal en busca de riesgos que los indicadores numéricos sencillos no ven (ej: caídas libres verticales de tipo "cuchillo cayendo", divergencias ocultas o mercados planos sin volumen).
*   **Decisión:** Gemini responde estrictamente con un JSON:
    *   `APPROVED`: Permite la orden al broker.
    *   `BLOCKED`: Bloquea la operación, guarda la razón del bloqueo y la imprime en consola/Telegram.

---

## 5. Control de Telegram y Notificaciones
*   **Mensajería:** Envía resúmenes HTML con fotos del balance, reportes de ciclo, alertas de apertura y reportes de cierre de operaciones con su resultado (WIN/LOSS) detallado.
*   **Comandos en Vivo:** Escucha activamente tus mensajes en Telegram para ejecutar acciones en la cuenta:
    *   `/balance`: Consulta el saldo actual en el broker.
    *   `/status`: Muestra el estado del bot, las rachas y si alguna estrategia está bloqueada.
    *   `/stop`: Detiene temporalmente las operaciones del bot.
    *   `/start`: Reactiva el bot.
    *   `/reload`: Recarga el archivo de configuración en caliente.
