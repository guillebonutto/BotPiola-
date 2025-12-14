import sqlite3
import datetime
import os
import sys
import json
import time
from pathlib import Path

# Configuración
DB_PATH = 'feedback.db'
BOT_FILE = 'main.py'
RESTART_SIGNAL = 'restart.signal'
CONFIG_FILE = 'config.json'

def install_dependencies():
    """Intenta instalar dependencias si faltan."""
    try:
        import google.generativeai as genai
    except ImportError:
        print("🔧 Instalando librería de Google AI...")
        os.system(f"{sys.executable} -m pip install google-generativeai")
        print("✅ Instalación completada. Reiniciando script...")
        os.execv(sys.executable, ['python'] + sys.argv)

try:
    import google.generativeai as genai
except ImportError:
    install_dependencies()

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_stats(days=7):
    """Obtiene estadísticas de trading de la DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    cursor.execute("SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff,))
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if not trades: return None
    
    wins = [t for t in trades if t['result'] == 'win']
    total_profit = sum(t['profit'] for t in trades)
    
    strategies = {}
    for t in trades:
        s = t['strategy']
        if s not in strategies: strategies[s] = {'wins':0, 'total':0, 'profit':0}
        strategies[s]['total'] += 1
        strategies[s]['profit'] += t['profit']
        if t['result'] == 'win': strategies[s]['wins'] += 1
            
    return {
        'total': len(trades),
        'win_rate': (len(wins)/len(trades))*100,
        'profit': total_profit,
        'strategies': strategies,
        'raw_trades': trades[-10:] # Últimos 10 para contexto
    }

def get_current_code():
    with open(BOT_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def optimize_bot(api_key):
    """Ciclo principal de optimización con IA."""
    print("🤖 Conectando con Gemini API...")
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel('gemini-1.5-flash') # Modelo con mejor cuota gratuita
    
    stats = get_stats()
    if not stats or stats['total'] < 5:
        print("⚠️ Pocos datos para analizar (<5 trades). Esperando más operaciones.")
        return False
        
    code = get_current_code()
    
    prompt = f"""
    Actúa como un Desarrollador Senior de Bots de Trading en Python.
    
    ESTADÍSTICAS RECIENTES:
    - Total Operaciones: {stats['total']}
    - Win Rate: {stats['win_rate']:.2f}%
    - Beneficio Neto: ${stats['profit']:.2f}
    
    DESGLOSE ESTRATEGIAS:
    {json.dumps(stats['strategies'], indent=2)}
    
    CÓDIGO ACTUAL (main.py):
    ```python
    {code}
    ```
    
    TU TAREA:
    1. Analiza qué estrategia está fallando.
    2. Modifica el código para mejorar los parámetros o la lógica.
    3. DEVUELVE ÚNICAMENTE EL CÓDIGO PYTHON COMPLETO Y CORREGIDO.
    4. NO expliques nada, solo devuelve el bloque de código dentro de ```python ... ```.
    """
    
    print("🧠 Analizando rendimiento y generando mejoras...")
    try:
        response = model.generate_content(prompt)
        new_code = response.text
        
        # Limpiar formato markdown
        if "```python" in new_code:
            new_code = new_code.split("```python")[1].split("```")[0]
        elif "```" in new_code:
            new_code = new_code.split("```")[1].split("```")[0]
            
        new_code = new_code.strip()
        
        # Validación básica antes de guardar
        if "class TradingBot" not in new_code or "async def run" not in new_code:
            print("❌ La IA generó código inválido. Abortando.")
            return False
            
        # Backup
        backup_name = f"backups/main_backup_{int(time.time())}.py"
        os.makedirs("backups", exist_ok=True)
        with open(backup_name, 'w', encoding='utf-8') as f:
            f.write(code)
            
        # Guardar cambio
        with open(BOT_FILE, 'w', encoding='utf-8') as f:
            f.write(new_code)
            
        print(f"✅ Código optimizado y guardado. Backup en {backup_name}")
        
        # Señal de reinicio
        with open(RESTART_SIGNAL, 'w') as f:
            f.write("RESTART")
        print("♻️ Señal de reinicio enviada al supervisor.")
        return True
        
    except Exception as e:
        print(f"❌ Error en IA: {e}")
        return False

def main():
    print("🚀 INICIADO AUTO-OPTIMIZADOR CON GEMINI")
    
    config = load_config()
    api_key = config.get('gemini_api_key')
    
    if not api_key:
        print("\n🔑 CONFIGURACIÓN NECESARIA")
        print("Para que esto funcione automáticamente con 'mí mismo' (Gemini), necesito una API Key.")
        print("Es GRATIS aquí: https://aistudio.google.com/app/apikey")
        api_key = input("\nPega tu API Key de Google AI Studio: ").strip()
        config['gemini_api_key'] = api_key
        save_config(config)
    
    while True:
        print("\n⏳ Esperando próxima ventana de análisis (ejecución cada 6 horas)...")
        # En producción podrías poner time.sleep(21600)
        # Para prueba preguntamos
        
        optimize_bot(api_key)
        
        print("💤 Durmiendo 6 horas...")
        time.sleep(21600) 

if __name__ == "__main__":
    main()
