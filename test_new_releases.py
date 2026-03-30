#!/usr/bin/env python3
"""
Test script for the new /new-releases endpoint.
"""

import subprocess
import json
import time


def test_endpoint():
    url = "http://localhost:7860/new-releases?days=14&limit=50"
    print(f"Testing: {url}")
    print("=" * 60)

    start = time.time()
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=300) as response:
            data = json.loads(response.read().decode())
            elapsed = time.time() - start

            print(f"✅ Success in {elapsed:.2f}s")
            print(f"   Total found: {data.get('totalFound', 0)}")
            print(f"   Days threshold: {data.get('daysThreshold', 0)}")
            print(f"   Last updated: {data.get('lastUpdated', 'N/A')}")

            apps = data.get("apps", [])
            print(f"\n   Top 10 New Releases:")
            for i, app in enumerate(apps[:10], 1):
                title = app.get("title", "Unknown")[:30]
                released = app.get("released", "N/A")
                days_old = app.get("days_old", "?")
                score = app.get("score", "N/A")
                print(
                    f"   {i:2}. {title:<30} | Released: {released} ({days_old} days) | Score: {score}"
                )

            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    test_endpoint()
