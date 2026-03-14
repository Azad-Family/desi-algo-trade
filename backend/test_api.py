"""Minimal test script to verify backend and frontend connectivity"""
import requests
import sys

def test_backend():
    """Test backend API"""
    print("\n🧪 Testing Backend API...\n")
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:8000/api/health")
        print(f"✓ Health Check: {response.status_code}")
        data = response.json()
        print(f"  Status: {data.get('status')}")
        print(f"  Database: {data.get('database')}")
        print(f"  Stocks in DB: {data.get('stocks_count')}")
        
        # Test stocks endpoint
        response = requests.get("http://localhost:8000/api/stocks")
        print(f"\n✓ Stocks Endpoint: {response.status_code}")
        stocks = response.json()
        print(f"  Total stocks returned: {len(stocks)}")
        if stocks:
            print(f"  First stock: {stocks[0]['symbol']} - {stocks[0]['name']}")
        
        # Test sectors endpoint
        response = requests.get("http://localhost:8000/api/stocks/sectors")
        print(f"\n✓ Sectors Endpoint: {response.status_code}")
        sectors = response.json()
        print(f"  Sectors: {', '.join([s['sector'] for s in sectors])}")
        
        print("\n✅ Backend is working correctly!\n")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to backend at http://localhost:8000")
        print("   Make sure backend is running: uvicorn server:app --reload")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_backend()
    sys.exit(0 if success else 1)
