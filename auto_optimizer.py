import sqlite3
import datetime
import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Configuración
DB_PATH = 'feedback.db'
CONFIG_FILE = 'config.json'

def install_dependencies():
    """Intenta instalar dependencias si faltan."""
    try:
        import google.generativeai as genai
    except ImportError:
        print("🔧 Instalando librería de Google AI...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "google-generativeai"],
            check=True
        )
        print("✅ Instalación completada. Reiniciando script...")
        os.execv(sys.executable, ['python'] + sys.argv)

try:
    import google.generativeai as genai
except ImportError:
    install_dependencies()

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error cargando config: {e}")
        return {}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def get_stats(days=7):
    """Obtiene estadísticas de trading de la DB."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        cursor.execute("SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff,))
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        if not trades: return None
        
        # Filtrar trades reales ejecutados vs bloqueados
        executed_trades = [t for t in trades if t['result'] in ('win', 'loss')]
        blocked_trades = [t for t in trades if t['result'] == 'blocked']
        
        wins = [t for t in executed_trades if t['result'] == 'win']
        total_profit = sum(t['profit'] for t in executed_trades)
        
        strategies = {}
        for t in executed_trades:
            s = t['strategy']
            if s not in strategies: strategies[s] = {'wins':0, 'total':0, 'profit':0}
            strategies[s]['total'] += 1
            strategies[s]['profit'] += t['profit']
            if t['result'] == 'win': strategies[s]['wins'] += 1
                
        # Estructurar bloqueos para reporte y análisis de IA
        blocked_summary = {}
        for t in blocked_trades:
            s = t['strategy']
            if s not in blocked_summary: blocked_summary[s] = []
            # Mantener los datos clave de bloqueo de forma compacta
            blocked_summary[s].append({
                'pair': t['pair'],
                'timeframe': t.get('timeframe'),
                'decision': t.get('action'),
                'reason': t.get('ai_reason', 'N/A'),
                'confidence': t.get('ai_confidence')
            })
            
        return {
            'total': len(executed_trades),
            'win_rate': (len(wins)/len(executed_trades))*100 if executed_trades else 0.0,
            'profit': total_profit,
            'strategies': strategies,
            'blocked_count': len(blocked_trades),
            'blocked_summary': blocked_summary,
            'raw_trades': executed_trades[-15:], # Últimos 15 reales para contexto
            'raw_blocked': blocked_trades[-15:]  # Últimos 15 bloqueos para contexto
        }
    except Exception as e:
        print(f"Error cargando estadísticas: {e}")
        return None

def optimize_bot(api_key):
    """Optimiza los parámetros de configuración en config.json usando Gemini sin reescribir código."""
    print("🤖 Conectando con Gemini API...")
    genai.configure(api_key=api_key)
    
    # Usar Gemini 2.5 Flash para optimizar tokens y eficiencia con mayor cuota
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=(
            "Eres un experto en trading algorítmico y gestión de riesgo. "
            "Tu única función es analizar estadísticas de rendimiento de un bot de trading "
            "y devolver un objeto JSON con la configuración óptima de parámetros de trading. "
            "Nunca devuelves código Python. Nunca explicas tu razonamiento fuera del JSON. "
            "Siempre priorizas la preservación del capital sobre las ganancias agresivas. "
            "El JSON que devuelves debe ser parseable directamente con json.loads()."
        )
    )
    
    stats = get_stats()
    if not stats or (stats['total'] < 3 and stats['blocked_count'] < 3):
        print("⚠️ Pocos datos en feedback.db (<3 operaciones). Esperando más operaciones.")
        return False
        
    config = load_config()
    
    # Prompt optimizado enfocado en parámetros de configuración, no en código
    prompt = f"""
    Actúa como un Experto Desarrollador de Trading Algorítmico y Gestión de Riesgo.
    
    Tu objetivo es analizar el rendimiento reciente y ajustar la configuración de nuestro bot en config.json para maximizar la rentabilidad, evitar riesgos técnicos y reducir el drawdown.
    
    CONFIGURACIÓN ACTUAL (parámetros de trading):
    {json.dumps(config.get('trading', {}), indent=2)}
    
    ESTADÍSTICAS RECIENTES DE TRADES REALES EJECUTADOS (Últimos 7 días):
    - Total de Operaciones Ejecutadas: {stats['total']}
    - Tasa de Éxito (Win Rate): {stats['win_rate']:.2f}%
    - Beneficio Neto de la Sesión: ${stats['profit']:.2f}
    
    DESGLOSE POR ESTRATEGIAS EJECUTADAS:
    {json.dumps(stats['strategies'], indent=2)}
    
    SEÑALES DE TRADING BLOQUEADAS POR GEMINI LIVE (Últimos 7 días):
    - Total de Señales Bloqueadas: {stats['blocked_count']}
    - Resumen de Bloqueos por Estrategia y Justificaciones:
    {json.dumps(stats['blocked_summary'], indent=2)}
    
    REGLAS DE OPTIMIZACIÓN:
    1. Si una estrategia tiene un Win Rate menor al 48% tras al menos 5 trades ejecutados, redúcela o desactívala (puedes sugerir no usarla en ciertos pares en la configuración).
    2. Analiza las justificaciones e indicadores de las señales que Gemini Live bloqueó (ej. 'Falling Knife', 'Rising Knife', 'Agotamiento Extremo', etc.). Ajusta parámetros de trading, desactiva temporalmente las estrategias en pares específicos donde Gemini bloquea repetidamente, o define configuraciones para que las estrategias filtren esos escenarios sin requerir Gemini Live en el futuro.
    3. Si los resultados generales de los trades reales son deficientes, sugiere ajustar la gestión de riesgo ("money_management" -> "mode" = "fixed" o "martingale", "fixed_amount", "martingale_max_steps").
    4. Analiza los pares más rentables y define la lista final de "pairs" y "pairs_with_timeframe".
    5. Devuelve ÚNICAMENTE un objeto JSON que represente la nueva sección "trading" para config.json.
    6. No devuelvas explicaciones ni código, solo el objeto JSON limpio dentro de un bloque ```json ... ```. Debe contener las claves exactas de la sección 'trading' que deseas actualizar.
    """
    
    print("🧠 Analizando rendimiento y generando optimizaciones en la configuración...")
    try:
        response = model.generate_content(
            prompt,
    safety_settings={
        "HARASSMENT": "BLOCK_NONE",
        "HATE_SPEECH": "BLOCK_NONE",
        "SEXUALLY_EXPLICIT": "BLOCK_NONE",
        "DANGEROUS_CONTENT": "BLOCK_NONE"
    })
        new_config_text = response.text
        
        # Limpiar formato markdown
        if "```json" in new_config_text:
            new_config_text = new_config_text.split("```json")[1].split("```")[0]
        elif "```" in new_config_text:
            new_config_text = new_config_text.split("```")[1].split("```")[0]
            
        new_config_text = new_config_text.strip()
        new_trading_data = json.loads(new_config_text)
        
        # Validación básica de la estructura
        if not isinstance(new_trading_data, dict) or "pairs" not in new_trading_data:
            print("❌ La IA generó un JSON de configuración inválido. Abortando.")
            return False
            
        # Actualizar config.json manteniendo las claves principales (como ssid, telegram, etc.)
        config['trading'] = new_trading_data
        save_config(config)
        
        print("✅ Configuración de trading optimizada y guardada en config.json exitosamente.")
        return True
        
    except Exception as e:
        print(f"❌ Error en optimizador de IA: {e}")
        return False

def main():
    print("🚀 INICIADO AUTO-OPTIMIZADOR INTELIGENTE DE CONFIGURACIÓN CON GEMINI")
    
    config = load_config()
    api_key = config.get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("\n🔑 CONFIGURACIÓN NECESARIA")
        print("Para que esto funcione automáticamente con Gemini, necesito una API Key.")
        print("Es GRATIS aquí: https://aistudio.google.com/app/apikey")
        api_key = input("\nPega tu API Key de Google AI Studio: ").strip()
        config['gemini_api_key'] = api_key
        save_config(config)
    
    while True:
        optimize_bot(api_key)
        print("💤 Durmiendo 6 horas hasta el próximo análisis...")
        time.sleep(21600) 

if __name__ == "__main__":
    main()
