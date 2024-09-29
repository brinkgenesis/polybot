import os
from typing import List, Dict, Any
import logging
import sys
import random
from config import POLYMARKET_HOST, CHAIN_ID, PRIVATE_KEY, POLYMARKET_PROXY_ADDRESS

# Existing imports
import numpy as np
from dotenv import load_dotenv
from py_clob_client.client import ClobClient, OrderBookSummary
from py_clob_client.clob_types import ApiCreds
from py_clob_client.exceptions import PolyApiException
from gamma_client.gamma_market_api import get_gamma_market_data
from tabulate import tabulate

# Import functions and utilities from order_manager and utils
from order_management.order_manager import get_open_orders
from utils.utils import shorten_id



# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Set to DEBUG to capture all levels of logs

# Create console handler and set level to DEBUG
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.WARNING)

# Create formatter
formatter = logging.Formatter('%(message)s')

# Add formatter to console handler
ch.setFormatter(formatter)

# Add console handler to logger
if not logger.handlers:
    logger.addHandler(ch)

# Load environment variables
load_dotenv()

# Initialize ClobClient
client = ClobClient(
    host=POLYMARKET_HOST,
    chain_id=CHAIN_ID,
    key=PRIVATE_KEY,
    signature_type=2,  # POLY_GNOSIS_SAFE
    funder=POLYMARKET_PROXY_ADDRESS
)

client.set_api_creds(client.create_or_derive_api_creds())

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



def print_order_summary(orders: List[Dict], total_input_value: float):
    total_bid_amount = float("0.0")
    total_ask_amount = float("0.0")
    print("Generated Orders:")
    print("=================")
    
    # Sort asks in descending order (highest first)
    asks = sorted([order for order in orders if order['side'] == 'sell'], key=lambda x: float(x['price']), reverse=True)
    
    # Sort bids in descending order (highest first)
    bids = sorted([order for order in orders if order['side'] == 'buy'], key=lambda x: float(x['price']), reverse=True)
    
    # Print asks first, then bids
    for order in asks + bids:
        price = float(order['price'])
        size = float(order['original_size'])
        amount = price * size
        print(f"{order['side'].capitalize()}: Price: ${price:.2f}, Size: {order['original_size']:.2f}, Amount: ${amount:.2f}")
        if order['side'] == 'buy':
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

def calculate_pool_ownership(order_book, traders: List[Dict], b: float, best_bid: float, best_ask: float, tick_size: float) -> List[Dict[str, Any]]:
    midpoint = round((best_bid + best_ask) / 2, 2)  # Rounded to 2 decimal places

    logger.debug(f"Rounded Midpoint: {midpoint}")

    # Calculate Qmin for the entire order book, but only for orders within 'v' of midpoint
    order_book_Qmin = calculate_order_book_Qmin(order_book, b, midpoint, tick_size)

    # Calculate Qmin for each trader, again only for orders within 'v' of midpoint
    for trader in traders:
        trader_Qmin = calculate_trader_score(order_book, trader['orders'], b, midpoint, tick_size)
        trader['Qmin'] = trader_Qmin
        trader['pool_percentage'] = (trader_Qmin / order_book_Qmin) * float("100") if order_book_Qmin > 0 else float("0.0")
        logger.debug(f"Trader {trader['name']} - Qmin: {trader_Qmin}, Pool Percentage: {trader['pool_percentage']}%")

    return traders

def calculate_trader_score(order_book, trader_orders, b, midpoint, tick_size):
    c = 3.0  # hardcoded
    Qone = calculate_Q_for_trader(trader_orders, 'buy', b, midpoint, tick_size)
    Qtwo = calculate_Q_for_trader(trader_orders, 'sell', b, midpoint, tick_size)

    if 0.10 <= midpoint <= 0.90:
        min_Q = min(Qone, Qtwo)
        max_Q_div_c = max(Qone / c, Qtwo / c)
        Qmin = max(min_Q, max_Q_div_c)
    else:
        Qmin = min(Qone, Qtwo)

    return Qmin

def calculate_Q_for_trader(orders, side, b, midpoint, tick_size):
    v = 0.03  # hardcoded
    Q = 0.0
    side = side.lower()
    for order in orders:
        order_side = order.get('side', '').lower()
        logger.debug(f"Processing Trader Order: {order}")

        if order_side == side:
            price = float(order['price'])
            if side == 'buy':
                s = round(midpoint - price, 2)
            else:
                s = round(price - midpoint, 2)
            logger.debug(f"Order Side: {order_side}, Price: {price}, s: {s}, v: {v}")
            if 0 <= s <= v:
                scoring = S(s, b)
                logger.debug(f"Order within v: s={s}, scoring={scoring}")
                Q += scoring * float(order['original_size'])
                logger.debug(f"Updated Trader Q: {Q}")
            else:
                logger.debug(f"Order outside v: s={s}")
        else:
            logger.debug(f"Order side mismatch: order_side='{order_side}', expected_side='{side}'")
    return Q

def S(s: float, b: float) -> float:
    v = 0.03  # hardcoded
    scoring = ((v - s) / v) ** 2 * b
    return scoring

def calculate_order_book_Qmin(
    order_book: OrderBookSummary,
    b: float,
    midpoint: float,
    tick_size: float
) -> float:
    """
    Calculates the Qmin for the entire order book.
    
    Args:
        order_book (OrderBookSummary): The order book summary.
        v (float): Maximum spread from the midpoint.
        b (float): scoring factor.
        c (float): Additional scoring factor if needed.
        midpoint (float): Midpoint price.
        tick_size (float): Tick size of the market.
    
    Returns:
        float: Calculated Qmin for the order book.
    """
    c = 3.0 #hardcoded
    v = 0.03 #hardcoded
    Qone = calculate_Q_for_side(
        order_book.bids, 'buy', b, midpoint, tick_size
    )
    Qtwo = calculate_Q_for_side(
        order_book.asks, 'sell', b, midpoint, tick_size
    )
    Qmin = Qone + Qtwo
    logger.debug(f"Total order_book_Qmin: {Qmin}")
    return Qmin

def calculate_Q_for_side(levels, side, b, midpoint, tick_size):
    v = 0.03  # Hardcoded
    Q = 0.0
    side = side.lower()
    for level in levels:
        try:
            level_price = round(float(level.price), 2)
            level_size = float(level.size)
        except (AttributeError, ValueError) as e:
            logger.error(f"Invalid order book level data: {level} - {e}")
            continue

        if side == 'buy':
            s = round(midpoint - level_price, 2)
        else:
            s = round(level_price - midpoint, 2)

        if 0 <= s <= v:
            scoring = S(s, b)
            Q += scoring * level_size
    return Q

def estimate_daily_reward(trader: Dict[str, Any], daily_reward_pool: float) -> float:
    """
    Estimates the daily reward for a trader based on their pool percentage.
    
    Args:
        trader (Dict[str, Any]): Trader information containing 'pool_percentage'.
        daily_reward_pool (float): The total daily reward pool.
    
    Returns:
        float: The estimated daily reward for the trader.
    """
    try:
        pool_percentage = trader['pool_percentage']
        if not isinstance(pool_percentage, float):
            pool_percentage = float(str(pool_percentage))
        
        estimated_reward = (pool_percentage / float('100')) * daily_reward_pool
        logger.debug(f"Estimated Reward: {estimated_reward} (Pool Percentage: {pool_percentage}%)")
        return estimated_reward
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error estimating daily reward for trader: {e}")
        return float('0.0')
       
def calculate_apr(estimated_reward: float, total_amount: float):
    daily_apr = (estimated_reward / total_amount) * 100
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



    for trader in traders:
        estimated_reward = estimate_daily_reward(order_book, trader, v, b, c, daily_reward_pool, best_bid, best_ask)
        print(f"{trader['name']}:")
        print(f"  Qmin: {trader['Qmin']:.4f}")
        print(f"  Pool Ownership: {trader['pool_percentage']:.2f}%")
        print(f"  Estimated Daily Reward: ${estimated_reward:.2f}")
        
        # Calculate total amounts and rewards for bid and ask
        for order in trader['orders']:
            amount = float(order['price']) * float(order['original_size'])
            if order['side'] == 'buy':
                total_bid_amount += amount
                total_bid_reward += estimated_reward * (amount / sum(float(o['price']) * float(o['original_size']) for o in trader['orders'] if o['side'] == 'bid'))
            else:
                total_ask_amount += amount
                total_ask_reward += estimated_reward * (amount / sum(float(o['price']) * float(o['original_size']) for o in trader['orders'] if o['side'] == 'ask'))
        
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


def main():
    logger.debug("Starting rewardsDashboard.py script.")
    try:
        # Initialize the ClobClient
        client = ClobClient(
            host=POLYMARKET_HOST,
            chain_id=CHAIN_ID,
            key=PRIVATE_KEY,
            signature_type=2,  # POLY_GNOSIS_SAFE
            funder=POLYMARKET_PROXY_ADDRESS
        )
        client.set_api_creds(client.create_or_derive_api_creds())

        # Fetch open orders
        open_orders = get_open_orders(client)
        if not open_orders:
            logger.warning("No open orders found.")
            return

        # Extract unique token IDs from open orders
        unique_token_ids = set(order['asset_id'] for order in open_orders)

        # Define constants
        daily_reward_pool = 50.0  # Example value; replace with actual
        b = 1.0  # Replace with actual value
        tick_size = 0.01  # Assuming a tick size; adjust as needed

        # Create variables to store aggregate data
        total_estimated_rewards = 0.0

        # Create a list to store the results
        results = []

        for token_id in unique_token_ids:
            # Fetch order book
            order_book = client.get_order_book(token_id)

            if not order_book.bids and not order_book.asks:
                logger.warning(f"No order book data for token_id {token_id}")
                continue

            # Calculate best bid, best ask, and midpoint
            best_bid = max([float(bid.price) for bid in order_book.bids], default=0.0)
            best_ask = min([float(ask.price) for ask in order_book.asks], default=1.0)
            midpoint = round((best_bid + best_ask) / 2, 2)
            logger.debug(f"Token ID: {token_id} - Best Bid: {best_bid}, Best Ask: {best_ask}, Midpoint: {midpoint}")

            # Get trader's orders for this token
            trader_orders = [order for order in open_orders if order['asset_id'] == token_id]
            logger.debug(f"Trader Orders for token_id {token_id}: {trader_orders}")

            if not trader_orders:
                logger.warning(f"No trader orders for token_id {token_id}")
                continue

            # Prepare trader data
            traders = [{'name': 'Trader', 'orders': trader_orders}]

            # Calculate pool ownership
            traders = calculate_pool_ownership(order_book, traders, b, best_bid, best_ask, tick_size)

            # Calculate estimated rewards and APR
            for trader in traders:
                estimated_reward = estimate_daily_reward(trader, daily_reward_pool)

                # Calculate total amount for this token
                total_amount = sum(float(order['price']) * float(order['original_size']) for order in trader['orders'])

                # Store the initial total amount for later use
                trader['initial_total_amount'] = total_amount

                total_estimated_rewards += estimated_reward

                daily_apr, annual_apr = calculate_apr(estimated_reward, total_amount)

                # Add the data to the results list
                results.append({
                    'Token ID': token_id,
                    'Total Amount': total_amount,
                    'Estimated Daily Reward': estimated_reward,
                    'Pool Percentage': trader['pool_percentage'],
                    'Daily APR': daily_apr,
                    'Annual APR': annual_apr
                })

                # Log the data
                logger.debug(f"Token ID: {token_id} - Total Amount: ${total_amount:.2f}, Estimated Daily Reward: ${estimated_reward:.2f}, "
                             f"Pool Percentage: {trader['pool_percentage']}%, Daily APR: {daily_apr}, Annual APR: {annual_apr}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

    # After processing all tokens, sort and print the results in a table
    if results:
        # Sort results by Annual APR in descending order
        sorted_results = sorted(results, key=lambda x: x['Annual APR'], reverse=True)

        # Find the maximum of total amounts
        max_total_amount = max(r['Total Amount'] for r in sorted_results)

        # Format the sorted results for display
        formatted_results = [{
            'Token ID': shorten_id(str(r['Token ID'])),
            'Total Amount': f"${r['Total Amount']:.2f}",
            'Estimated Daily Reward': f"${r['Estimated Daily Reward']:.2f}",
            'Pool Percentage': f"{r['Pool Percentage']:.6f}%",
            'Daily APR': f"{r['Daily APR']:.6f}%",
            'Annual APR': f"{r['Annual APR']:.2f}%"
        } for r in sorted_results]

        print("\nLiquidity Mining Rewards Dashboard")
        print("----------------------------------")
        print(tabulate(formatted_results, headers='keys', tablefmt="pretty"))

        # Compute aggregate APR
        if max_total_amount > 0:
            total_daily_apr = (total_estimated_rewards / max_total_amount) * 100
            total_annual_apr = total_daily_apr * 365
            print(f"\nTotal Daily Rewards: ${total_estimated_rewards:.2f}")
            print(f"\nMax Liquidity Provided: ${max_total_amount:.2f}")
            print(f"Average Daily APR: {total_daily_apr:.2f}%")
            print(f"Average Annual APR: {total_annual_apr:.2f}%")
        else:
            print("Maximum liquidity provided is zero, cannot compute aggregate APR.")
    else:
        print("No rewards data available.")

    # **Simulator Functionality Starts Here**

    # Prompt the user for max_total_amount
    try:
        user_input = input("\nEnter a max total amount to simulate (or press Enter to skip simulation): ")
        if user_input.strip():
            max_total_amount_sim = float(user_input)
            if max_total_amount_sim <= 0:
                print("Max total amount must be a positive number.")
                return

            # Recalculate metrics based on new total amount
            simulated_results = []
            total_sim_estimated_rewards = 0.0

            for token_data in results:
                token_id = token_data['Token ID']
                
                # Fetch order book again (or use cached version if available)
                order_book = client.get_order_book(token_id)

                if not order_book.bids and not order_book.asks:
                    logger.warning(f"No order book data for token_id {token_id}")
                    continue

                # Calculate best bid, best ask, and midpoint
                best_bid = max([float(bid.price) for bid in order_book.bids], default=0.0)
                best_ask = min([float(ask.price) for ask in order_book.asks], default=1.0)

                # Get trader's orders for this token
                trader_orders = [order for order in open_orders if order['asset_id'] == token_id]

                # Scale up the orders to the new total amount
                scale_factor = max_total_amount_sim / token_data['Total Amount']
                scaled_orders = []
                for order in trader_orders:
                    scaled_order = order.copy()
                    scaled_order['original_size'] = str(float(order['original_size']) * scale_factor)
                    scaled_orders.append(scaled_order)

                # Prepare trader data
                traders = [{'name': 'Trader', 'orders': scaled_orders}]

                # Calculate pool ownership
                traders = calculate_pool_ownership(order_book, traders, b, best_bid, best_ask, tick_size)

                # Calculate estimated rewards and APR
                for trader in traders:
                    estimated_reward = estimate_daily_reward(trader, daily_reward_pool)
                    total_sim_estimated_rewards += estimated_reward

                    daily_apr, annual_apr = calculate_apr(estimated_reward, max_total_amount_sim)

                    simulated_results.append({
                        'Token ID': token_id,
                        'Total Amount': max_total_amount_sim,
                        'Estimated Daily Reward': estimated_reward,
                        'Pool Percentage': trader['pool_percentage'],
                        'Daily APR': daily_apr,
                        'Annual APR': annual_apr
                    })

            # Sort simulated results by Annual APR
            simulated_results = sorted(simulated_results, key=lambda x: x['Annual APR'], reverse=True)

            # Format the simulated results for display
            formatted_sim_results = [{
                'Token ID': shorten_id(str(r['Token ID'])),
                'Total Amount': f"${r['Total Amount']:.2f}",
                'Estimated Daily Reward': f"${r['Estimated Daily Reward']:.2f}",
                'Pool Percentage': f"{r['Pool Percentage']:.6f}%",
                'Daily APR': f"{r['Daily APR']:.6f}%",
                'Annual APR': f"{r['Annual APR']:.2f}%"
            } for r in simulated_results]

            # Print simulated table
            print("\nSimulated Liquidity Mining Rewards Dashboard")
            print("--------------------------------------------")
            print(tabulate(formatted_sim_results, headers='keys', tablefmt="pretty"))

            # Compute aggregate APR for simulated data
            if max_total_amount_sim > 0:
                total_daily_apr = (total_sim_estimated_rewards / max_total_amount_sim) * 100
                total_annual_apr = total_daily_apr * 365
                print(f"\nTotal Simulated Daily Rewards: ${total_sim_estimated_rewards:.2f}")
                print(f"\nSimulated Liquidity Provided: ${max_total_amount_sim:.2f}")
                print(f"Simulated Average Daily APR: {total_daily_apr:.2f}%")
                print(f"Simulated Average Annual APR: {total_annual_apr:.2f}%")
            else:
                print("Max total amount is zero, cannot compute simulated aggregate APR.")

    except ValueError:
        print("Invalid input. Please enter a numerical value for the max total amount.")

if __name__ == "__main__":
    main()


