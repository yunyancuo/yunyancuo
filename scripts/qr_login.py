#!/usr/bin/env python3
"""
NetEase QR code login.
Run locally: python qr_login.py
Scans QR code with NetEase Cloud Music app, saves cookie to file.
"""

import json
import time
import urllib.request
import urllib.error
import sys
import os

API = "http://127.0.0.1:3000"


def api(path):
    req = urllib.request.Request(f"{API}{path}", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"code": -1, "message": str(e)}


def main():
    print("Starting NeteaseCloudMusicApi...")
    # Start API
    import subprocess
    subprocess.Popen(
        ["npx", "--yes", "NeteaseCloudMusicApi@4.32.0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(5)

    # Check API ready
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{API}/", timeout=2)
            break
        except:
            time.sleep(2)
    else:
        print("ERROR: API not ready")
        return

    # Step 1: Get QR key
    key_resp = api("/login/qr/key")
    unikey = key_resp.get("data", {}).get("unikey")
    if not unikey:
        print(f"Failed to get QR key: {key_resp}")
        return
    print(f"QR key: {unikey}")

    # Step 2: Create QR image URL
    qr_resp = api(f"/login/qr/create?key={unikey}&qrimg=true")
    qr_url = qr_resp.get("data", {}).get("qrimg")
    if not qr_url:
        print(f"Failed to create QR: {qr_resp}")
        return

    print(f"\nQR code URL (open in browser to scan):")
    print(f"  {qr_url}")
    print(f"\nOr use this URL with qrencode: qrencode -t ANSI '{qr_url}'")
    print(f"\nWaiting for scan (60s timeout)...")

    # Step 3: Poll for scan
    for i in range(60):
        check = api(f"/login/qr/check?key={unikey}")
        code = check.get("code", -1)
        if code == 803:
            print(f"  [{i*2}s] Waiting for authorize...")
        elif code == 800:
            print(f"  [{i*2}s] QR expired, restarting...")
            return main()  # Restart
        elif code == 802:
            print(f"  [{i*2}s] Scanned! Waiting for confirm...")
        elif code == 801:
            print(f"  [{i*2}s] Please confirm on phone...")
        elif code == 200:
            print(f"\nLogin successful!")
            cookie = check.get("cookie", "")
            if cookie:
                # Save to file
                with open("netease_cookie.txt", "w") as f:
                    f.write(cookie)
                print(f"\nCookie saved to: netease_cookie.txt")
                print(f"\nCopy this to GitHub Secrets -> NETEASE_COOKIE:")
                print(f"  {cookie[:80]}...")
            else:
                print("No cookie in response")
            return
        else:
            print(f"  [{i*2}s] Status: {code} - {check.get('message', 'unknown')}")
        time.sleep(2)

    print("Timeout. Please try again.")


if __name__ == "__main__":
    main()
