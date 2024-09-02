from gamma_market_api import get_high_liquidity_markets
from bid_manager import place_bids, manage_bids
from position_manager import handle_filled_orders
from clob_market_api import get_market_price
from config import MAX_MARKETS
import time

def main():
    active_markets = []
    while True:
        high_liquidity_markets = get_high_liquidity_markets()
        
        for question, token_id in high_liquidity_markets:
            if token_id not in active_markets and len(active_markets) < MAX_MARKETS:
                mid_price = get_market_price(token_id)
                place_bids(token_id, mid_price)
                active_markets.append(token_id)
            
            if token_id in active_markets:
                manage_bids(token_id)
                handle_filled_orders(token_id)
        
        time.sleep(60)  # Wait for 1 minute before next iteration

if __name__ == "__main__":
    main()
