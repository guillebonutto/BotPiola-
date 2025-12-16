
import re

def validate_token(token):
    if not token:
        print("Token is empty")
        return

    original_token = token
    # Current logic
    if token and token.lower().startswith('bot'):
        token = token[3:]
    
    print(f"Original: '{original_token}' -> Parsed: '{token}'")
    
    # Regex check
    if re.match(r'^\d+:[A-Za-z0-9_-]+$', token):
        print("  -> Format VALID")
    else:
        print("  -> Format INVALID")
        
    base_url = f"https://api.telegram.org/bot{token}"
    print(f"  -> URL: {base_url}")

print("--- Scenarios ---")
validate_token("123456:ABC-DEF")  # Normal
validate_token("bot123456:ABC-DEF") # Normal with prefix
validate_token("bot 123456:ABC-DEF") # With space
validate_token("Bot123456:ABC-DEF") # Case sensitivity
validate_token("123456") # Missing secret
validate_token("https://api.telegram.org/bot123456:ABC") # Full URL paste
