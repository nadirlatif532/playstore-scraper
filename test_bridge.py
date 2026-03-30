#!/usr/bin/env python3
import subprocess
import json


def test_bridge():
    print("=== Testing Node Bridge from Python ===")

    # Test app details
    print("\n1. Testing app details...")
    result = subprocess.run(
        ["node", "bridge.js", "app", json.dumps({"appId": "com.kiloo.subwaysurf"})],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    data = json.loads(result.stdout.strip())
    print("Released:", data.get("released"))

    # Test list
    print("\n2. Testing list...")
    result = subprocess.run(
        [
            "node",
            "bridge.js",
            "list",
            json.dumps({"category": "GAME", "collection": "TOP_FREE", "num": 3}),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    data = json.loads(result.stdout.strip())
    print("List length:", len(data))
    if data:
        print("First app:", data[0].get("title"))

    # Test parsing date
    print("\n3. Testing date parsing...")
    date_str = data[0].get("released") if data else None
    print("Date string:", date_str)

    # Fetch details for first app
    if data:
        app_id = data[0].get("appId")
        print(f"\n4. Fetching details for {app_id}...")
        result = subprocess.run(
            ["node", "bridge.js", "app", json.dumps({"appId": app_id})],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        details = json.loads(result.stdout.strip())
        print("Released:", details.get("released"))


if __name__ == "__main__":
    test_bridge()
