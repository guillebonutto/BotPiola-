import json

with open("next_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

state = data.get('props', {}).get('pageProps', {}).get('state', {})
print("Llaves en state:")
print(state.keys())

# A menudo los eventos están en algo como 'ecEvents' o 'economicCalendar'
# Vamos a buscar llaves que parezcan relevantes
for key in state.keys():
    if 'event' in key.lower() or 'calendar' in key.lower() or 'ec' in key.lower():
        print(f"Llave candidata: {key}")
        # Ver una muestra si es una lista
        val = state[key]
        if isinstance(val, list) and len(val) > 0:
            print(f"Muestra de {key} (primer elemento):")
            print(json.dumps(val[0], indent=2))
        elif isinstance(val, dict):
            print(f"Muestra de {key} (llaves):")
            print(val.keys())
