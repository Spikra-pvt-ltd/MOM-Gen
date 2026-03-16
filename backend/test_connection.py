"""
Run this script to test your OpenAI API key and diagnose the issue.
Usage: python3 test_connection.py
"""
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ python-dotenv loaded")
except ImportError:
    print("✗ python-dotenv not installed")

# Check API key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("✗ OPENAI_API_KEY is NOT set")
    print("  → Create backend/.env with: OPENAI_API_KEY=sk-...")
    sys.exit(1)
elif api_key == "your_openai_api_key_here":
    print("✗ OPENAI_API_KEY is still the placeholder value")
    print("  → Replace it with your real key in backend/.env")
    sys.exit(1)
else:
    print(f"✓ OPENAI_API_KEY found: {api_key[:8]}...{api_key[-4:]}")

# Test OpenAI connection
try:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    print("✓ OpenAI client created")
except Exception as e:
    print(f"✗ Failed to create OpenAI client: {e}")
    sys.exit(1)

# Test a tiny API call (models list — no cost)
try:
    models = client.models.list()
    whisper_available = any("whisper" in m.id for m in models.data)
    print(f"✓ API key is VALID — connected to OpenAI")
    print(f"✓ Whisper API available: {whisper_available}")
except Exception as e:
    print(f"✗ API call failed: {e}")
    sys.exit(1)

print("\n✅ Everything looks good! The API key and OpenAI connection work.")
print("   If you're still getting 500 errors, check the backend terminal for the full traceback.")
