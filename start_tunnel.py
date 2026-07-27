#!/usr/bin/env python3
"""Start server and cloudflared tunnel, print public URL."""
import subprocess
import time
import sys
import os

# Start uvicorn server
print("🌑 Starting Shadow Lands server...")
srv = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "admin.main:app", "--host", "0.0.0.0", "--port", "3000", "--lifespan", "on"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)
time.sleep(6)

# Test server
import urllib.request
try:
    with urllib.request.urlopen("http://localhost:3000/", timeout=5) as resp:
        html = resp.read().decode()
        if "Dashboard" in html:
            print("✅ Server running on http://localhost:3000")
        else:
            print("❌ Server not responding correctly")
            srv.kill()
            sys.exit(1)
except Exception as e:
    print(f"❌ Server error: {e}")
    srv.kill()
    sys.exit(1)

# Start cloudflared
print("🌐 Starting cloudflared tunnel...")
cf = subprocess.Popen(
    ["/tmp/cloudflared", "tunnel", "--url", "http://localhost:3000"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

# Read output and find URL
print("⏳ Waiting for tunnel URL...")
url = None
start = time.time()
while time.time() - start < 30:
    line = cf.stdout.readline()
    if line:
        print(line.strip())
        if "trycloudflare.com" in line:
            url = line.strip()
            break
    time.sleep(0.5)

if url:
    print(f"\n🎉 PUBLIC URL: {url}")
    print("\nOpen this URL in your browser!")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
else:
    print("\n❌ Could not get tunnel URL")

cf.kill()
srv.kill()
