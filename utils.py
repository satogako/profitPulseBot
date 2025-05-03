import re

def parse_pnl_message(message: str):
    # Підтримує варіанти з двокрапкою (:) або пробілом
    pattern = r"Realized PNL.*?(\w+/\w+)(?::\w+)?\s+([+-]?\d+\.?\d*)"
    match = re.search(pattern, message)
    if match:
        pair = match.group(1)              # напр. SOL/USDT або SOL/BTC
        amount = float(match.group(2))     # напр. 1.124658
        currency = pair.split("/")[1]      # напр. USDT ← беремо валюту з пари
        return pair, amount, currency
    return None

