#!/usr/bin/env python3
"""
Test script that starts the server and tests the endpoint.
"""

import subprocess
import json
import time
import sys
import os


def run_test():
    # Start the Flask app in a subprocess
    print("Starting Flask server...")
    server_proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # Wait for server to start
    print("Waiting for server to start...")
    time.sleep(8)

    try:
        import urllib.request

        # Test health endpoint
        print("\n=== Testing health endpoint ===")
        try:
            with urllib.request.urlopen(
                "http://localhost:7860/", timeout=5
            ) as response:
                print(f"Health check: {response.read().decode()}")
        except Exception as e:
            print(f"Health check failed: {e}")

        # Test new-releases endpoint
        print("\n=== Testing /new-releases endpoint ===")
        url = "http://localhost:7860/new-releases?days=90&limit=50"
        print(f"URL: {url}")

        start = time.time()
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                data = json.loads(response.read().decode())
                elapsed = time.time() - start

                print(f"\nSuccess in {elapsed:.2f}s")
                print(f"Total found: {data.get('totalFound', 0)}")
                print(f"Days threshold: {data.get('daysThreshold', 0)}")
                print(f"Last updated: {data.get('lastUpdated', 'N/A')}")

                apps = data.get("apps", [])
                print(f"\nTop 10 New Releases:")
                print("-" * 70)
                for i, app in enumerate(apps[:10], 1):
                    title = app.get("title", "Unknown")[:35]
                    released = app.get("released", "N/A")
                    days_old = app.get("days_old", "?")
                    score = app.get("score", "N/A")
                    installs = app.get("installs", "N/A")
                    print(
                        f"{i:2}. {title:<35} | {released} ({days_old}d) | Score: {score}"
                    )

                return True
        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()
            return False
    finally:
        print("\nStopping server...")
        server_proc.terminate()
        server_proc.wait(timeout=5)


if __name__ == "__main__":
    run_test()
