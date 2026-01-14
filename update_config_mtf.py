import json
from pathlib import Path

config_path = Path('config.json')
if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if 'trading' in config:
        config['trading']['mtf_settings'] = {
            "enabled": True,
            "strict_mode": True,
            "macro_interval": 3600,
            "meso_interval": 900
        }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)
    print("✅ config.json actualizado con MTF settings.")
else:
    print("❌ No se encontró config.json")
