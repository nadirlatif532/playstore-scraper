import urllib.request
import json
import time

def test_scraper():
    url = "http://localhost:7860/charts?category=GAME_ACTION&collection=new_free"
    print(f"🔍 Testing: {url}")
    start = time.time()
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            elapsed = time.time() - start
            print(f"✅ Received {len(data)} results in {elapsed:.2f}s")
            
            if data:
                print("--- Top 3 Results ---")
                for i, app in enumerate(data[:3]):
                    print(f"{i+1}. {app.get('title')} (ID: {app.get('appId')})")
                    print(f"   Released: {app.get('released')} | Updated: {app.get('updated_str', app.get('updated'))}")
                    
                # Specifically search for Subway Surfers
                subway = next((a for a in data if a.get('appId') == 'com.kiloo.subwaysurf'), None)
                if subway:
                    print("⚠️ WARNING: Subway Surfers found in 'New Games' results!")
                    print(f"   Released: {subway.get('released')}")
                else:
                    print("✨ Success: Subway Surfers NOT found in filtered results.")
            else:
                print("⚠️ Results are empty.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_scraper()
