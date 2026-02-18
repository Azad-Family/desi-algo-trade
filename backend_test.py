#!/usr/bin/env python3
import requests
import sys
import time
import json
from datetime import datetime

class AITradingBackendTester:
    def __init__(self, base_url="https://desi-algo-trade.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.errors = []
        self.test_results = []

    def log_result(self, test_name, success, message, response_data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}: {message}")
        else:
            print(f"❌ {test_name}: {message}")
            self.errors.append(f"{test_name}: {message}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "response_data": response_data
        })

    def make_request(self, method, endpoint, data=None, timeout=30):
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=timeout)
            else:
                return False, f"Unsupported method: {method}", None
            
            return True, response.status_code, response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        except requests.exceptions.Timeout:
            return False, "Request timeout", None
        except requests.exceptions.ConnectionError:
            return False, "Connection error", None
        except Exception as e:
            return False, f"Request error: {str(e)}", None

    def test_api_health(self):
        """Test basic API health"""
        success, status, data = self.make_request('GET', '/')
        if success and status == 200:
            self.log_result("API Health", True, f"API is responding (Status: {status})", data)
            return True
        else:
            self.log_result("API Health", False, f"API not responding - Status: {status if success else 'Connection failed'}")
            return False

    def test_stock_universe(self):
        """Test stock universe endpoints"""
        print("\n🔍 Testing Stock Universe...")
        
        # Initialize stock universe first
        success, status, data = self.make_request('POST', '/stocks/initialize')
        if success and status == 200:
            stock_count = data.get('count', 0)
            self.log_result("Stock Initialization", True, f"Initialized {stock_count} stocks")
        else:
            self.log_result("Stock Initialization", False, f"Failed to initialize stocks - Status: {status}")

        # Get all stocks
        success, status, data = self.make_request('GET', '/stocks')
        if success and status == 200:
            if isinstance(data, list) and len(data) >= 50:
                self.log_result("Stock Universe", True, f"Found {len(data)} stocks (>= 50 required)")
                self.stocks_data = data
            else:
                self.log_result("Stock Universe", False, f"Expected >= 50 stocks, got {len(data) if isinstance(data, list) else 0}")
        else:
            self.log_result("Stock Universe", False, f"Failed to fetch stocks - Status: {status}")

        # Test sectors endpoint
        success, status, data = self.make_request('GET', '/stocks/sectors')
        if success and status == 200:
            if isinstance(data, list) and len(data) > 5:
                sectors = [s['sector'] for s in data if 'sector' in s]
                self.log_result("Sector List", True, f"Found {len(sectors)} sectors: {', '.join(sectors[:5])}")
                self.sectors_data = sectors
            else:
                self.log_result("Sector List", False, f"Expected multiple sectors, got {len(data) if isinstance(data, list) else 0}")
        else:
            self.log_result("Sector List", False, f"Failed to fetch sectors - Status: {status}")

        # Test sector filtering
        if hasattr(self, 'sectors_data') and self.sectors_data:
            test_sector = self.sectors_data[0]
            success, status, data = self.make_request('GET', f'/stocks/sector/{test_sector}')
            if success and status == 200:
                if isinstance(data, list) and len(data) > 0:
                    self.log_result("Sector Filtering", True, f"Found {len(data)} stocks in {test_sector} sector")
                else:
                    self.log_result("Sector Filtering", False, f"No stocks found for sector: {test_sector}")
            else:
                self.log_result("Sector Filtering", False, f"Failed to filter by sector - Status: {status}")

    def test_ai_analysis(self):
        """Test AI analysis functionality"""
        print("\n🧠 Testing AI Analysis...")
        
        if not hasattr(self, 'stocks_data') or not self.stocks_data:
            self.log_result("AI Analysis", False, "No stocks available for testing")
            return

        # Test stock for analysis
        test_stock = self.stocks_data[0]
        test_symbol = test_stock.get('symbol')
        
        if not test_symbol:
            self.log_result("AI Analysis", False, "No valid stock symbol found")
            return

        # Test AI analysis endpoint
        analysis_request = {
            "stock_symbol": test_symbol,
            "analysis_type": "hybrid"
        }
        
        success, status, data = self.make_request('POST', '/ai/analyze', analysis_request, timeout=60)
        if success and status == 200:
            if data.get('analysis') and data.get('confidence_score') is not None:
                confidence = data.get('confidence_score', 0)
                self.log_result("AI Analysis", True, f"Analysis completed for {test_symbol} (Confidence: {confidence}%)")
            else:
                self.log_result("AI Analysis", False, f"Invalid analysis response format")
        else:
            self.log_result("AI Analysis", False, f"AI analysis failed - Status: {status}")

        # Test trade recommendation generation
        success, status, data = self.make_request('POST', f'/ai/generate-recommendation/{test_symbol}', timeout=60)
        if success and status == 200:
            if data.get('action') and data.get('confidence_score') is not None:
                action = data.get('action')
                confidence = data.get('confidence_score', 0)
                self.log_result("Trade Recommendation", True, f"Generated {action} recommendation for {test_symbol} (Confidence: {confidence}%)")
                self.test_recommendation_id = data.get('id')
            else:
                self.log_result("Trade Recommendation", False, "Invalid recommendation response format")
        else:
            self.log_result("Trade Recommendation", False, f"Failed to generate recommendation - Status: {status}")

    def test_trade_queue(self):
        """Test trade queue functionality"""
        print("\n📋 Testing Trade Queue...")
        
        # Get all recommendations
        success, status, data = self.make_request('GET', '/recommendations')
        if success and status == 200:
            if isinstance(data, list):
                self.log_result("Trade Queue", True, f"Found {len(data)} total recommendations")
                self.recommendations_data = data
            else:
                self.log_result("Trade Queue", False, "Invalid recommendations response format")
        else:
            self.log_result("Trade Queue", False, f"Failed to fetch recommendations - Status: {status}")

        # Get pending recommendations
        success, status, data = self.make_request('GET', '/recommendations/pending')
        if success and status == 200:
            if isinstance(data, list):
                self.log_result("Pending Recommendations", True, f"Found {len(data)} pending recommendations")
                
                # Test approval workflow if we have pending recommendations
                if len(data) > 0 and hasattr(self, 'test_recommendation_id'):
                    rec_id = self.test_recommendation_id
                    approval_data = {"approved": True}
                    
                    success, status, response = self.make_request('POST', f'/recommendations/{rec_id}/approve', approval_data)
                    if success and status == 200:
                        self.log_result("Trade Approval", True, f"Successfully approved recommendation {rec_id}")
                    else:
                        self.log_result("Trade Approval", False, f"Failed to approve recommendation - Status: {status}")
            else:
                self.log_result("Pending Recommendations", False, "Invalid pending recommendations response")
        else:
            self.log_result("Pending Recommendations", False, f"Failed to fetch pending recommendations - Status: {status}")

    def test_portfolio(self):
        """Test portfolio endpoints"""
        print("\n💼 Testing Portfolio...")
        
        # Get portfolio
        success, status, data = self.make_request('GET', '/portfolio')
        if success and status == 200:
            if data.get('holdings') is not None and data.get('summary') is not None:
                holdings_count = len(data.get('holdings', []))
                total_value = data.get('summary', {}).get('total_current', 0)
                self.log_result("Portfolio", True, f"Portfolio loaded: {holdings_count} holdings, ₹{total_value:,.2f} value")
            else:
                self.log_result("Portfolio", False, "Invalid portfolio response format")
        else:
            self.log_result("Portfolio", False, f"Failed to fetch portfolio - Status: {status}")

        # Get sector breakdown
        success, status, data = self.make_request('GET', '/portfolio/sector-breakdown')
        if success and status == 200:
            if isinstance(data, list):
                self.log_result("Sector Breakdown", True, f"Portfolio sectors: {len(data)} sectors")
            else:
                self.log_result("Sector Breakdown", False, "Invalid sector breakdown format")
        else:
            self.log_result("Sector Breakdown", False, f"Failed to fetch sector breakdown - Status: {status}")

    def test_trade_history(self):
        """Test trade history endpoints"""
        print("\n📊 Testing Trade History...")
        
        # Get trade history
        success, status, data = self.make_request('GET', '/trades/history')
        if success and status == 200:
            if isinstance(data, list):
                self.log_result("Trade History", True, f"Found {len(data)} historical trades")
            else:
                self.log_result("Trade History", False, "Invalid trade history format")
        else:
            self.log_result("Trade History", False, f"Failed to fetch trade history - Status: {status}")

        # Get trade stats
        success, status, data = self.make_request('GET', '/trades/stats')
        if success and status == 200:
            if data.get('total_trades') is not None:
                total_trades = data.get('total_trades', 0)
                total_value = data.get('total_traded_value', 0)
                self.log_result("Trade Statistics", True, f"Stats: {total_trades} trades, ₹{total_value:,.2f} total value")
            else:
                self.log_result("Trade Statistics", False, "Invalid trade stats format")
        else:
            self.log_result("Trade Statistics", False, f"Failed to fetch trade stats - Status: {status}")

    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        print("\n📈 Testing Dashboard...")
        
        success, status, data = self.make_request('GET', '/dashboard/stats')
        if success and status == 200:
            required_fields = ['portfolio_value', 'total_invested', 'pending_recommendations', 'today_trades', 'total_stocks']
            missing_fields = [field for field in required_fields if field not in data]
            
            if not missing_fields:
                portfolio_value = data.get('portfolio_value', 0)
                stock_count = data.get('total_stocks', 0)
                pending = data.get('pending_recommendations', 0)
                self.log_result("Dashboard Stats", True, f"Dashboard loaded: ₹{portfolio_value:,.2f} portfolio, {stock_count} stocks, {pending} pending")
            else:
                self.log_result("Dashboard Stats", False, f"Missing fields: {missing_fields}")
        else:
            self.log_result("Dashboard Stats", False, f"Failed to fetch dashboard stats - Status: {status}")

    def test_settings(self):
        """Test settings endpoints"""
        print("\n⚙️ Testing Settings...")
        
        # Get settings
        success, status, data = self.make_request('GET', '/settings')
        if success and status == 200:
            expected_fields = ['max_trade_value', 'max_position_size', 'risk_per_trade_percent', 'auto_analysis_enabled']
            missing_fields = [field for field in expected_fields if field not in data]
            
            if not missing_fields:
                self.log_result("Settings Retrieval", True, f"Settings loaded successfully")
                
                # Test settings update
                test_settings = {
                    "id": "main_settings",
                    "max_trade_value": 150000.0,
                    "max_position_size": 150,
                    "risk_per_trade_percent": 2.5,
                    "auto_analysis_enabled": True
                }
                
                success, status, response = self.make_request('POST', '/settings', test_settings)
                if success and status == 200:
                    self.log_result("Settings Update", True, "Settings updated successfully")
                else:
                    self.log_result("Settings Update", False, f"Failed to update settings - Status: {status}")
            else:
                self.log_result("Settings Retrieval", False, f"Missing settings fields: {missing_fields}")
        else:
            self.log_result("Settings Retrieval", False, f"Failed to fetch settings - Status: {status}")

    def test_ai_scan_all(self):
        """Test AI scan all stocks functionality"""
        print("\n🤖 Testing AI Scan All...")
        
        success, status, data = self.make_request('POST', '/ai/scan-all')
        if success and status == 200:
            if data.get('message') and 'initiated' in data.get('message', '').lower():
                self.log_result("AI Scan All", True, "AI scan initiated successfully")
                # Wait a moment for background processing
                time.sleep(3)
            else:
                self.log_result("AI Scan All", False, "Invalid scan response")
        else:
            self.log_result("AI Scan All", False, f"Failed to start AI scan - Status: {status}")

    def run_all_tests(self):
        """Run comprehensive backend tests"""
        print("🚀 Starting AI Trading Backend Tests...")
        print("=" * 60)
        
        # Test basic connectivity first
        if not self.test_api_health():
            print("\n💥 API is not responding. Cannot continue tests.")
            return self.generate_summary()
        
        # Run all test suites
        self.test_stock_universe()
        self.test_ai_analysis()
        self.test_trade_queue()
        self.test_portfolio()
        self.test_trade_history()
        self.test_dashboard_stats()
        self.test_settings()
        self.test_ai_scan_all()
        
        return self.generate_summary()

    def generate_summary(self):
        """Generate test summary"""
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.errors:
            print(f"\n❌ Failed Tests:")
            for error in self.errors:
                print(f"  - {error}")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0,
            "errors": self.errors,
            "test_results": self.test_results
        }

def main():
    """Main test execution"""
    tester = AITradingBackendTester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    if results["success_rate"] >= 80:
        print(f"\n🎉 Backend tests mostly successful!")
        return 0
    elif results["success_rate"] >= 50:
        print(f"\n⚠️ Backend tests partially successful.")
        return 1
    else:
        print(f"\n💥 Backend tests mostly failed.")
        return 2

if __name__ == "__main__":
    sys.exit(main())