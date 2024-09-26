mock_open_orders = [
    {'id': '1', 'asset_id': 'asset1', 'size': '100', 'price': '0.75'},
    {'id': '2', 'asset_id': 'asset2', 'size': '200', 'price': '0.50'},
    {'id': '3', 'asset_id': 'asset3', 'size': '150', 'price': '0.60'},
]

mock_markets = {
    'asset1': {
        'description': 'Will Bitcoin reach $50,000 by end of 2023?',
        'clobRewards': [{'rewardsDailyRate': '10.5'}]
    },
    'asset2': {
        'description': 'Will Ethereum 2.0 launch successfully in 2023?',
        'clobRewards': [{'rewardsDailyRate': '8.75'}]
    },
    'asset3': {
        'description': 'Will the US Federal Reserve raise interest rates in Q3 2023?',
        'clobRewards': []
    },
}

mock_scoring_info = [
    {'orderId': '1', 'isScoring': True},
    {'orderId': '2', 'isScoring': False},
    {'orderId': '3', 'isScoring': True},
]

from py_clob_client.clob_types import OrderBookSummary, OrderSummary

class MockOrderSummary:
    def __init__(self, price, size):
        self.price = str(price)
        self.size = str(size)

class MockOrderBookSummary:
    def __init__(self, market, asset_id, bids, asks):
        self.market = market
        self.asset_id = asset_id
        self.bids = [MockOrderSummary(price, size) for price, size in bids]
        self.asks = [MockOrderSummary(price, size) for price, size in asks]
        self.hash = "mock_hash"

class MockClobClient:
    def __init__(self):
        self.mock_books = {
            "market1": MockOrderBookSummary(
                market="market1",
                asset_id="asset1",
                bids=[(0.48, 100), (0.47, 200), (0.46, 300)],
                asks=[(0.52, 100), (0.53, 200), (0.54, 300)]
            ),
            "market2": MockOrderBookSummary(
                market="market2",
                asset_id="asset2",
                bids=[(0.30, 500), (0.29, 1000)],
                asks=[(0.70, 500), (0.71, 1000)]
            ),
            "market3": MockOrderBookSummary(
                market="market3",
                asset_id="asset3",
                bids=[(0.09, 1000), (0.08, 2000)],
                asks=[(0.11, 1000), (0.12, 2000)]
            )
        }
        self.mock_markets = {
            "market1": {"minimum_tick_size": "0.01"},
            "market2": {"minimum_tick_size": "0.01"},
            "market3": {"minimum_tick_size": "0.01"}
        }

    def get_book(self, token_id):
        return self.mock_books.get(token_id, MockOrderBookSummary("unknown", "unknown", [], []))

    def get_market(self, market_id):
        return self.mock_markets.get(market_id, {"minimum_tick_size": "0.01"})

# Test function
def test_calculate_market_score():
    from rewards_dashboard.rewardsDashboard import calculate_market_score

    mock_client = MockClobClient()
    
    # Test cases
    test_cases = [
        ("market1", 0.03, 1.0, 3.0),
        ("market2", 0.05, 1.5, 3.0),
        ("market3", 0.02, 0.8, 3.0),
    ]

    for market_id, v, b, c in test_cases:
        score = calculate_market_score(mock_client, market_id, v, b, c)
        print(f"Market {market_id} score: {score}")

if __name__ == "__main__":
    test_calculate_market_score()
