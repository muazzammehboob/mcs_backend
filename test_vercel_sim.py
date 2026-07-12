import sys
import asyncio
from fastapi.testclient import TestClient

print("Simulating Vercel module load...")
try:
    import api.index
    print("Module loaded successfully.")
except Exception as e:
    print(f"Error loading module: {e}")
    sys.exit(1)

print("Simulating request to /settings/global")
client = TestClient(api.index.app)
try:
    response = client.get("/settings/global")
    print("Response status:", response.status_code)
    print("Response JSON:", response.json())
except Exception as e:
    print(f"Request failed with error: {e}")
