import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, OrdersScoringParams
from py_clob_client.exceptions import PolyApiException
import math
import random
from typing import List, Dict
from gamma_market_api import get_gamma_market_data
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize ClobClient
host = os.getenv("POLYMARKET_HOST")
key = os.getenv("PRIVATE_KEY")
chain_id = int(os.getenv("CHAIN_ID"))
api_key = os.getenv("POLY_API_KEY")
api_secret = os.getenv("POLY_API_SECRET")
api_passphrase = os.getenv("POLY_PASSPHRASE")

api_creds = ApiCreds(api_key, api_secret, api_passphrase)
client = ClobClient(host, key=key, chain_id=chain_id, creds=api_creds)

def get_order_book(token_id: str):
    """
    Fetch and return the order book for the given token_id using the ClobClient.
    """
    try:
        return client.get_order_book(token_id)
    except Exception as e:
        logger.error(f"Error fetching order book for token_id {token_id}: {str(e)}")
        return None

def get_gamma_market(token_id: str):
    return get_gamma_market_data(token_id)

def generate_mock_trades(best_bid: float, best_ask: float, total_value: float, v: float):
    try:
        logger.info(f"Best Bid: {best_bid}, Best Ask: {best_ask}")

        tick_size = 0.01
        v_ticks = int(v / tick_size)

        bids = []
        asks = []
        remaining_bid_value = total_value / 2
        remaining_ask_value = total_value / 2

        def generate_random_sizes(remaining_value, num_levels):
            if num_levels == 0:
                return []
            sizes = [random.uniform(0, remaining_value) for _ in range(num_levels - 1)]
            sizes.append(remaining_value - sum(sizes))
            return [abs(size) for size in sizes]  # Ensure all sizes are positive

        # Generate bids
        bid_prices = np.arange(best_bid, best_bid - v - tick_size, -tick_size)[:v_ticks]
        logger.info(f"Bid prices: {bid_prices}")
        bid_sizes = generate_random_sizes(remaining_bid_value, len(bid_prices))
        logger.info(f"Bid sizes: {bid_sizes}")
        
        for price, size_value in zip(bid_prices, bid_sizes):
            size = size_value / price
            bids.append({"side": "bid", "price": str(price), "size": str(size)})

        # Generate asks
        ask_prices = np.arange(best_ask, best_ask + v + tick_size, tick_size)[:v_ticks]
        logger.info(f"Ask prices: {ask_prices}")
        ask_sizes = generate_random_sizes(remaining_ask_value, len(ask_prices))
        logger.info(f"Ask sizes: {ask_sizes}")
        
        for price, size_value in zip(ask_prices, ask_sizes):
            size = size_value / price
            asks.append({"side": "ask", "price": str(price), "size": str(size)})

        result = asks + bids
        logger.info(f"Generated mock trades: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in generate_mock_trades: {str(e)}")
        return None

def print_order_summary(orders: List[Dict], total_input_value: float):
    total_bid_amount = 0
    total_ask_amount = 0
    print("Generated Orders:")
    print("=================")
    
    # Sort asks in descending order (highest first)
    asks = sorted([order for order in orders if order['side'] == 'ask'], key=lambda x: float(x['price']), reverse=True)
    
    # Sort bids in descending order (highest first)
    bids = sorted([order for order in orders if order['side'] == 'bid'], key=lambda x: float(x['price']), reverse=True)
    
    # Print asks first, then bids
    for order in asks + bids:
        price = float(order['price'])
        size = float(order['size'])
        amount = price * size
        print(f"{order['side'].capitalize()}: Price: ${price:.2f}, Size: {size:.2f}, Amount: ${amount:.2f}")
        if order['side'] == 'bid':
            total_bid_amount += amount
        else:
            total_ask_amount += amount
    
    print(f"\nTotal Bid Amount: ${total_bid_amount:.2f}")
    print(f"Total Ask Amount: ${total_ask_amount:.2f}")
    total_amount = total_bid_amount + total_ask_amount
    print(f"Total Amount: ${total_amount:.2f}")
    print(f"Input Value: ${total_input_value:.2f}")
    
    if abs(total_amount - total_input_value) > 0.01:  # Allow for small rounding errors
        print("Warning: Total amount does not match input value. Adjusting...")
        adjustment = total_input_value - total_amount
        if total_bid_amount > total_ask_amount:
            bids[0]['size'] = str(float(bids[0]['size']) + adjustment / float(bids[0]['price']))
        else:
            asks[0]['size'] = str(float(asks[0]['size']) + adjustment / float(asks[0]['price']))
        print("Adjusted orders:")
        print_order_summary(asks + bids, total_input_value)

def calculate_pool_ownership(order_book, traders: List[Dict], v: float, b: float, c: float, best_bid: float, best_ask: float):
    midpoint = (best_bid + best_ask) / 2
    tick_size = 0.01  # Assuming a default tick size of 0.01

    # Calculate Qmin for the entire order book, but only for orders within 'v' of midpoint
    order_book_Qmin = calculate_order_book_Qmin(order_book, v, b, c, midpoint, tick_size)

    # Calculate Qmin for each trader, again only for orders within 'v' of midpoint
    for trader in traders:
        trader_Qmin = calculate_trader_score(order_book, trader['orders'], v, b, c, midpoint, tick_size)
        trader['Qmin'] = trader_Qmin
        trader['pool_percentage'] = (trader_Qmin / order_book_Qmin) * 100 if order_book_Qmin > 0 else 0

    return traders

def calculate_trader_score(order_book, trader_orders: List[Dict], v: float, b: float, c: float, midpoint: float, tick_size: float):
    Qone = calculate_Q_for_trader(trader_orders, 'bid', v, b, midpoint, tick_size)
    Qtwo = calculate_Q_for_trader(trader_orders, 'ask', v, b, midpoint, tick_size)

    if 0.10 <= midpoint <= 0.90:
        Qmin = max(min(Qone, Qtwo), max(Qone/c, Qtwo/c))
    else:
        Qmin = min(Qone, Qtwo)

    return Qmin

def calculate_Q_for_trader(orders: List[Dict], side: str, v: float, b: float, midpoint: float, tick_size: float):
    Q = 0
    for order in orders:
        if order['side'] == side:
            price = float(order['price'])
            s = abs(price - midpoint)
            if s <= v:  # Only consider orders within v of midpoint
                Q += S(v, s, b) * float(order['size'])
    return Q

def S(v: float, s: float, b: float):
    return ((v - s) / v) ** 2 * b

def calculate_order_book_Qmin(order_book, v: float, b: float, c: float, midpoint: float, tick_size: float):
    Qone = calculate_Q_for_side(order_book.bids, 'bid', v, b, midpoint, tick_size)
    Qtwo = calculate_Q_for_side(order_book.asks, 'ask', v, b, midpoint, tick_size)

    if 0.10 <= midpoint <= 0.90:
        Qmin = max(min(Qone, Qtwo), max(Qone/c, Qtwo/c))
    else:
        Qmin = min(Qone, Qtwo)

    return Qmin

def calculate_Q_for_side(levels, side: str, v: float, b: float, midpoint: float, tick_size: float):
    Q = 0
    for level in levels:
        price = float(level.price)
        s = abs(price - midpoint)
        if s <= v:  # Only consider orders within v of midpoint
            Q += S(v, s, b) * float(level.size)
    return Q

def estimate_daily_reward(order_book, trader: Dict, v: float, b: float, c: float, daily_reward_pool: float, best_bid: float, best_ask: float):
    # Trader's share is directly their pool percentage
    estimated_reward = (trader['pool_percentage'] / 100) * daily_reward_pool
    return estimated_reward

def calculate_apr(daily_reward: float, total_amount: float):
    if total_amount == 0:
        return 0, 0
    daily_apr = (daily_reward / total_amount) * 100
    annual_apr = daily_apr * 365
    return daily_apr, annual_apr

def print_pool_ownership_and_rewards(traders: List[Dict], order_book, v: float, b: float, c: float, daily_reward_pool: float, best_bid: float, best_ask: float):
    print("Pool Ownership Percentages and Estimated Daily Rewards:")
    print("======================================================")
    total_trader_percentage = sum(trader['pool_percentage'] for trader in traders)
    total_bid_amount = 0
    total_ask_amount = 0
    total_bid_reward = 0
    total_ask_reward = 0

    midpoint = (best_bid + best_ask) / 2

    for trader in traders:
        estimated_reward = estimate_daily_reward(order_book, trader, v, b, c, daily_reward_pool, best_bid, best_ask)
        print(f"{trader['name']}:")
        print(f"  Qmin: {trader['Qmin']:.4f}")
        print(f"  Pool Ownership: {trader['pool_percentage']:.2f}%")
        print(f"  Estimated Daily Reward: ${estimated_reward:.2f}")
        
        # Calculate total amounts and rewards for bid and ask
        for order in trader['orders']:
            amount = float(order['price']) * float(order['size'])
            if order['side'] == 'bid':
                total_bid_amount += amount
                total_bid_reward += estimated_reward * (amount / sum(float(o['price']) * float(o['size']) for o in trader['orders'] if o['side'] == 'bid'))
            else:
                total_ask_amount += amount
                total_ask_reward += estimated_reward * (amount / sum(float(o['price']) * float(o['size']) for o in trader['orders'] if o['side'] == 'ask'))
        
        print()
    
    print(f"Total pool ownership of mock traders: {total_trader_percentage:.2f}%")
    print(f"Remaining pool ownership: {100 - total_trader_percentage:.2f}%")

    # Calculate and print APR for bid side
    bid_daily_apr, bid_annual_apr = calculate_apr(total_bid_reward, total_bid_amount)
    print(f"\nBid side:")
    print(f"  Total Amount: ${total_bid_amount:.2f}")
    print(f"  Daily Reward: ${total_bid_reward:.2f}")
    print(f"  Daily APR: {bid_daily_apr:.2f}%")
    print(f"  Annual APR: {bid_annual_apr:.2f}%")

    # Calculate and print APR for ask side
    ask_daily_apr, ask_annual_apr = calculate_apr(total_ask_reward, total_ask_amount)
    print(f"\nAsk side:")
    print(f"  Total Amount: ${total_ask_amount:.2f}")
    print(f"  Daily Reward: ${total_ask_reward:.2f}")
    print(f"  Daily APR: {ask_daily_apr:.2f}%")
    print(f"  Annual APR: {ask_annual_apr:.2f}%")

    # Calculate and print total APR
    total_amount = total_bid_amount + total_ask_amount
    total_daily_reward = total_bid_reward + total_ask_reward
    total_daily_apr, total_annual_apr = calculate_apr(total_daily_reward, total_amount)
    print(f"\nTotal (Bid + Ask):")
    print(f"  Total Amount: ${total_amount:.2f}")
    print(f"  Total Daily Reward: ${total_daily_reward:.2f}")
    print(f"  Total Daily APR: {total_daily_apr:.2f}%")
    print(f"  Total Annual APR: {total_annual_apr:.2f}%")

def calculate_total_liquidity(order_book):
    total_bid_liquidity = sum(float(level.price) * float(level.size) for level in order_book.bids)
    total_ask_liquidity = sum(float(level.price) * float(level.size) for level in order_book.asks)
    total_liquidity = total_bid_liquidity + total_ask_liquidity
    return total_liquidity, total_bid_liquidity, total_ask_liquidity

def print_order_book_summary(order_book):
    total_liquidity, total_bid_liquidity, total_ask_liquidity = calculate_total_liquidity(order_book)
    print("\nOrder Book Summary:")
    print("===================")
    print(f"Total Liquidity: ${total_liquidity:.2f}")
    print(f"Total Bid Liquidity: ${total_bid_liquidity:.2f}")
    print(f"Total Ask Liquidity: ${total_ask_liquidity:.2f}")

if __name__ == "__main__":
    while True:
        token_id = input("Enter the token ID (or 'q' to quit): ")
        if token_id.lower() == 'q':
            break

        gamma_market = get_gamma_market_data(token_id)
        if gamma_market is None:
            print("Failed to fetch market data. Please try a different token ID.")
            continue

        print(f"Market Question: {gamma_market.get('question', 'N/A')}")
        print(f"Question ID: {gamma_market.get('questionID', 'N/A')}")
        print(f"Token ID: {gamma_market.get('tokenId', 'N/A')}")
        print(f"Outcome: {gamma_market.get('outcome', 'N/A')}")
        
        best_bid = float(gamma_market.get('bestBid', '0'))
        best_ask = float(gamma_market.get('bestAsk', '0'))
        
        if best_bid == 0 or best_ask == 0 or best_bid >= best_ask:
            print("Invalid best bid or best ask. Please check the market data.")
            continue
        
        print(f"Best Bid: {best_bid}, Best Ask: {best_ask}")
        
        daily_reward_pool = float(input("Enter the daily reward rate for this market: $"))
        total_mock_value = float(input("Enter the total value for generating mock trades: $"))

        v = 0.03  # max spread from best bid/ask in price units (e.g., 0.03 for 3 cents)
        b = 1.0   # in-game multiplier
        c = 3.0   # scaling factor

        # Generate mock trades using best_bid and best_ask from gamma_market
        mock_trades = generate_mock_trades(best_bid, best_ask, total_mock_value, v)
        
        if mock_trades is None or len(mock_trades) == 0:
            print("Failed to generate mock trades. Please check the market data.")
            continue

        # Print order summary
        print_order_summary(mock_trades, total_mock_value)

        # Now fetch the order book for other calculations
        order_book = get_order_book(token_id)
        if order_book is None:
            print("Failed to fetch order book. Please try a different token ID.")
            continue

        # Calculate pool ownership and rewards using order_book
        traders = [
            {"name": "Trader1", "orders": mock_trades[:len(mock_trades)//2]},
            {"name": "Trader2", "orders": mock_trades[len(mock_trades)//2:]}
        ]

        traders_with_ownership = calculate_pool_ownership(order_book, traders, v, b, c, best_bid, best_ask)
        print_pool_ownership_and_rewards(traders_with_ownership, order_book, v, b, c, daily_reward_pool, best_bid, best_ask)

        print(f"\nDaily Reward Pool for this market: ${daily_reward_pool:.2f}")

        # Print order book summary
        print_order_book_summary(order_book)

        another = input("Do you want to check another token? (y/n): ")
        if another.lower() != 'y':
            break

    print("Thank you for using the rewards dashboard!")
