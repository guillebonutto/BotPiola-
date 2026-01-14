import json
from pathlib import Path

config_path = Path('config.json')
if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if 'trading' not in config:
        config['trading'] = {
            "pairs": ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "USDCAD_otc", "AUDCAD_otc", "USDMXN_otc", "USDCOP_otc"],
            "interval": 300,
            "lookback": 300,
            "verbose": True,
            "verbose_telegram": True,
            "amount": 1.0,
            "daily_stop_loss": -15.0,
            "daily_take_profit": 10.0,
            "news_window": 15
        }
    else:
        config['trading']['news_window'] = 15
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)
    print("✅ config.json actualizado con éxito.")
else:
    print("❌ No se encontró config.json")
