
# Simulating the layout logic from main.py
pairs = ['EURUSD', 'GBPUSD']
verbose = True

print("--- PREVIEW OF TELEGRAM MESSAGE ---\n")

report_lines = []

# Mock logic for EURUSD (Signal)
pair = "EURUSD"
cycle_log = f"\n🔹 <b>{pair}</b>"
# Strategy 1: Signal
cycle_log += f"\n   🔥 <b>BUY</b>: StrategyStochastic\n      <i>Cruce Estocástico confirmado...</i>"
# Strategy 2: Hold
cycle_log += f"\n   ⏱ <i>Hold: ADX < 20</i>"
report_lines.append(cycle_log)

# Mock logic for GBPUSD (No Signal)
pair = "GBPUSD"
cycle_log = f"\n🔹 <b>{pair}</b>"
cycle_log += f"\n   ⏱ <i>Hold: Tendencia bajista fuerte</i>"
cycle_log += f"\n   ⏱ <i>Hold: No pattern</i>"
report_lines.append(cycle_log)

full_report = "📊 <b>Reporte de Ciclo</b>\n\n" + "\n".join(report_lines)

print(full_report)
print("\n-----------------------------------")
