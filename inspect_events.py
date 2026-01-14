import json

with open("next_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

ec_store = data.get('props', {}).get('pageProps', {}).get('state', {}).get('economicCalendarStore', {})
events_by_date = ec_store.get('calendarEventsByDate', {})

print(f"Fechas encontradas: {events_by_date.keys()}")

for date, events in events_by_date.items():
    print(f"\nFecha: {date} - Total eventos: {len(events)}")
    if len(events) > 0:
        print("Muestra del primer evento:")
        print(json.dumps(events[0], indent=2))
    break # Solo ver la primera fecha
