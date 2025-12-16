
import html
import asyncio
from telegram_bot import TelegramNotifier

print("--- 1. Testing HTML Escaping ---")
raw_reason = "ADX < 20 & RSI > 50"
escaped = html.escape(raw_reason)
print(f"Original: {raw_reason}")
print(f"Escaped:  {escaped}")
assert "&lt;" in escaped, "Escaping failed"
print("✅ Escaping works")

print("\n--- 2. Testing Token Cleaning in Class ---")
# Mocking init
t1 = TelegramNotifier("bot123:ABC", "chat_id")
print(f"Input 'bot123:ABC' -> Stored '{t1.token}'")
assert t1.token == "123:ABC", "Token cleaning failed"

t2 = TelegramNotifier("  456:DEF  ", "chat_id")
print(f"Input '  456:DEF  ' -> Stored '{t2.token}'")
assert t2.token == "456:DEF", "Token stripping failed"

print("✅ Token cleaning works")

print("\n--- 3. Testing Logic is importable ---")
print("All modules imported successfully.")
