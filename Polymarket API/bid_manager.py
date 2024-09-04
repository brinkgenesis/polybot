from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.order_builder.helpers import to_token_decimals, round_down
from py_order_utils.utils import generate_seed
import time
from py_clob_client.client import ClobClient
from dotenv import load_dotenv
import os
import logging

def build_and_print_order(market, gamma_market, client):
    # Print market information
    print("\nOrder Built for:")
    print(f"Question: {gamma_market.get('question', 'N/A')}")
    print(f"Question ID: {market.get('question_id', 'N/A')}")
    print(f"Token ID for YES: {market['tokens'][0]['token_id']}")
    print(f"Token ID for NO: {market['tokens'][1]['token_id']}")
    print(f"Condition ID: {market.get('condition_id', 'N/A')}")
    print(f"End Date: {market.get('end_date_iso', 'N/A')}")
    
    # Handle nested clobRewards
    clob_rewards = gamma_market.get('clobRewards', [])
    if clob_rewards:
        max_reward = max(clob_rewards, key=lambda x: float(x.get('rewardsDailyRate', 0)))
        print(f"Rewards Daily Rate: {max_reward.get('rewardsDailyRate', 'N/A')}")
        print(f"Rewards Max Spread: {max_reward.get('rewardsMaxSpread', 'N/A')}")
    else:
        print("Rewards Daily Rate: N/A")
        print("Rewards Max Spread: N/A")
    
    print(f"Best Ask: {gamma_market.get('bestAsk', 'N/A')}")
    print(f"Best Bid: {gamma_market.get('bestBid', 'N/A')}")
    print(f"Spread: {gamma_market.get('spread', 'N/A')}")
    print(f"Last Trade Price: {gamma_market.get('lastTradePrice', 'N/A')}")

    # Set total order size
    total_order_size = 100.0  # $100 as a float

    # Calculate order sizes
    order_size_30 = total_order_size * 0.3
    order_size_70 = total_order_size * 0.7

    # Calculate maker amounts
    best_bid = float(gamma_market.get('bestBid', '0'))
    order_price_min_tick_size = float(market.get('minimum_tick_size', '0.01'))
    max_incentive_spread = float(market.get('max_incentive_spread', '0.03'))

    # Initial calculation
    maker_amount_30 = round(best_bid - (2 * order_price_min_tick_size), 3)
    maker_amount_70 = round(best_bid - (3 * order_price_min_tick_size), 3)

    # Check if orders exceed the maximum allowed difference from best bid
    min_allowed_price = round(best_bid - max_incentive_spread, 3)

    if maker_amount_30 <= min_allowed_price:
        print("30% order exceeds maximum allowed difference from best bid. Adjusting price.")
        maker_amount_30 = round(best_bid - (2 * order_price_min_tick_size), 3)

    if maker_amount_70 <= min_allowed_price:
        print("70% order exceeds maximum allowed difference from best bid. Adjusting price.")
        maker_amount_70 = round(best_bid - (3 * order_price_min_tick_size), 3)

    print(f"Best Bid: {best_bid}")
    print(f"Maker Amount 30%: {maker_amount_30}")
    print(f"Maker Amount 70%: {maker_amount_70}")

    # Build orders
    order_30 = OrderArgs(
        price=maker_amount_30,
        size=order_size_30,
        side=BUY,
        token_id=market['tokens'][0]['token_id'],  # YES token
        fee_rate_bps=0,  # Assuming no fee, adjust if needed
        nonce=generate_seed(),
        expiration=str(int(time.time()) + 86400)  # 24 hours from now
    )

    order_70 = OrderArgs(
        price=maker_amount_70,
        size=order_size_70,
        side=BUY,
        token_id=market['tokens'][0]['token_id'],  # YES token
        fee_rate_bps=0,  # Assuming no fee, adjust if needed
        nonce=generate_seed(),
        expiration=str(int(time.time()) + 86400)  # 24 hours from now
    )

    print("\nOrders built:")
    print(f"30% Order: {order_30}")
    print(f"70% Order: {order_70}")

    return order_30, order_70

def execute_orders(clob_client, orders):
    execution_results = []
    for order in orders:
        try:
            response = clob_client.place_order(order)
            order_id = response.get('order_id')
            if order_id:
                logging.info(f"Order executed successfully. Order ID: {order_id}")
                print(f"✅ Order executed successfully. Order ID: {order_id}")
                execution_results.append((True, order_id))
            else:
                logging.warning(f"Order placement response didn't contain an order ID. Response: {response}")
                print(f"⚠️ Order may not have been placed correctly. Check the logs for details.")
                execution_results.append((False, None))
        except Exception as e:
            logging.error(f"Failed to execute order: {e}")
            print(f"❌ Failed to execute order: {str(e)}")
            execution_results.append((False, str(e)))
    
    # Summary of execution results
    total_orders = len(orders)
    successful_orders = sum(1 for result in execution_results if result[0])
    print(f"\nExecution Summary:")
    print(f"Total orders: {total_orders}")
    print(f"Successfully executed: {successful_orders}")
    print(f"Failed to execute: {total_orders - successful_orders}")
    
    # Optionally, you can add a check for open orders
    try:
        open_orders = clob_client.get_open_orders()
        logging.info(f"Current open orders: {len(open_orders)}")
        print(f"Current open orders: {len(open_orders)}")
    except Exception as e:
        logging.error(f"Failed to fetch open orders: {e}")
        print(f"Failed to fetch open orders: {str(e)}")
    
    return execution_results

def cancel_orders(client, order_ids):
    for order_id in order_ids:
        print(f"\nAttempting to cancel order {order_id}:")
        response = client.cancel_order(order_id)
        print(f"Order {order_id} cancellation result:")
        print(response)

def main(market, gamma_market, client):
    orders = build_and_print_order(market, gamma_market, client)
    
    if orders:
        action = input("Type 'execute all' to place orders or 'cancel' to cancel pending orders: ")
        
        if action.lower() == 'execute all':
            execute_orders(client, orders)
        elif action.lower() == 'cancel':
            # Assuming you have a way to get the order IDs of pending orders
            pending_order_ids = []  # You need to implement this
            cancel_orders(client, pending_order_ids)
        else:
            print("Invalid action. No orders executed or cancelled.")

    return orders

if __name__ == "__main__":
     pass