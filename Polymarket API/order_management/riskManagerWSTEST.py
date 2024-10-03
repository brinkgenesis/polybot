import unittest
from unittest.mock import MagicMock, patch
from order_management.riskManagerWS import RiskManagerWS
from datetime import datetime

class TestHandleBookEvent(unittest.TestCase):
    def setUp(self):
        client = MagicMock()
        self.risk_manager = RiskManagerWS(client)
        self.risk_manager.logger = MagicMock()

    def test_handle_book_event_with_data(self):
        data = {
            "event_type": "book",
            "asset_id": "1234567890",
            "market": "0xabcdef123456",
            "buys": [
                {"price": ".48", "size": "30"},
                {"price": ".49", "size": "20"},
                {"price": ".50", "size": "15"}
            ],
            "sells": [
                {"price": ".52", "size": "25"},
                {"price": ".53", "size": "60"},
                {"price": ".54", "size": "10"}
            ],
            "timestamp": "1701600127000",
            "hash": "0xhashvalue"
        }

        # Patch the shorten_id function to return a predictable output
        with patch('order_management.riskManagerWS.shorten_id', return_value='1234567...'):
            self.risk_manager.handle_book_event(data)

        # Assertions to verify logging
        self.risk_manager.logger.info.assert_called_with(
            "Book Event - Asset ID: 1234567..., Market: 0xabcdef123456, "
            "Buys: [{'price': '.48', 'size': '30'}, "
            "{'price': '.49', 'size': '20'}, "
            "{'price': '.50', 'size': '15'}], "
            "Sells: [{'price': '.52', 'size': '25'}, "
            "{'price': '.53', 'size': '60'}, "
            "{'price': '.54', 'size': '10'}], "
            "Timestamp: 1701600127000, Hash: 0xhashvalue"
        )

if __name__ == '__main__':
    unittest.main()
