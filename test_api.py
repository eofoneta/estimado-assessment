"""Quick API test — sends a text-only message (no image, minimal cost)."""
import os
from dotenv import load_dotenv
load_dotenv()

import anthropic

key = os.getenv("ANTHROPIC_API_KEY", "")
print(f"Key prefix: {key[:20]}...")

client = anthropic.Anthropic(api_key=key)
try:
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=50,
        messages=[{"role": "user", "content": "Say hello"}],
    )
    print("SUCCESS:", resp.content[0].text)
except Exception as e:
    print("ERROR:", e)
