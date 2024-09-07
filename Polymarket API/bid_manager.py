from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY, SELL
import logging
from balance_allowance import get_balance_allowances, update_balance_allowance
from pprint import pprint

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def build_and_print_order(market, gamma_market, client):
    # Print market information
    print("\nOrder Built for:")
    print(f"Question: {gamma_market.get('question', 'N/A')}")
    print(f"Question ID: {market.get('question_id', 'N/A')}")
    print(f"Token ID for YES: {market['token_ids'][0]}")
    print(f"Token ID for NO: {market['token_ids'][1]}")
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

    # Calculate maker amount
    best_bid = float(gamma_market.get('bestBid', '0'))
    order_price_min_tick_size = float(market.get('minimum_tick_size', '0.01'))
    max_incentive_spread = float(market.get('max_incentive_spread', '0.03'))

    # Initial calculation
    maker_amount = round(best_bid - (2 * order_price_min_tick_size), 3)

    # Check if order exceeds the maximum allowed difference from best bid
    min_allowed_price = round(best_bid - max_incentive_spread, 3)

    if maker_amount <= min_allowed_price:
        print("Order exceeds maximum allowed difference from best bid. Adjusting price.")
        maker_amount = round(best_bid - (2 * order_price_min_tick_size), 3)

    print(f"Best Bid: {best_bid}")
    print(f"Maker Amount: {maker_amount}")

    # Build order using OrderArgs
    order_args = OrderArgs(
        price=maker_amount,
        size=total_order_size,
        side=BUY,
        token_id=market['token_ids'][0],  # YES token
        fee_rate_bps=0,  # Assuming no fee, adjust if needed
        nonce=0,
        expiration='0' # Set expiration to '0' for GTC orders
    )

    print("\nOrder arguments built:")
    print(f"Order Args: {order_args}")

    return {"order_args": order_args}

    # Original code for 2 orders (commented out)
    """
    # Calculate order sizes
    order_size_30 = total_order_size * 0.3
    order_size_70 = total_order_size * 0.7

    # Calculate maker amounts
    maker_amount_30 = round(best_bid - (2 * order_price_min_tick_size), 3)
    maker_amount_70 = round(best_bid - (3 * order_price_min_tick_size), 3)

    # Check if orders exceed the maximum allowed difference from best bid
    if maker_amount_30 <= min_allowed_price:
        print("30% order exceeds maximum allowed difference from best bid. Adjusting price.")
        maker_amount_30 = round(best_bid - (2 * order_price_min_tick_size), 3)

    if maker_amount_70 <= min_allowed_price:
        print("70% order exceeds maximum allowed difference from best bid. Adjusting price.")
        maker_amount_70 = round(best_bid - (3 * order_price_min_tick_size), 3)

    print(f"Best Bid: {best_bid}")
    print(f"Maker Amount 30%: {maker_amount_30}")
    print(f"Maker Amount 70%: {maker_amount_70}")

    # Build orders using OrderArgs
    order_args_30 = OrderArgs(
        price=maker_amount_30,
        size=order_size_30,
        side=BUY,
        token_id=market['token_ids'][0],  # YES token
        fee_rate_bps=0,  # Assuming no fee, adjust if needed
        nonce=0,
        expiration='0' # Set expiration to '0' as required by the API
    )

    order_args_70 = OrderArgs(
        price=maker_amount_70,
        size=order_size_70,
        side=BUY,
        token_id=market['token_ids'][0],  # YES token
        fee_rate_bps=0,  # Assuming no fee, adjust if needed
        nonce=0,
        expiration='0' # Set expiration to '0' as required by the API
    )

    print("\nOrder arguments built:")
    print(f"30% Order Args: {order_args_30}")
    print(f"70% Order Args: {order_args_70}")

    return {"order_args_30": order_args_30, "order_args_70": order_args_70}
    """

def execute_orders(client, order_args, original_market):
    execution_results = []

    # Use the original market data which contains both token IDs
    get_balance_allowances(client, original_market)
    update_balance_allowance(client, original_market)

    try:
        # Create and sign the order
        signed_order = client.create_order(order_args['order_args'])
        pprint(vars(client))

        # Log order details before execution
        logger.info(f"Attempting to execute order: {signed_order}")

        # Post the order
        resp = client.post_order(signed_order, OrderType.GTC)

        if resp['success']:
            logger.info(f"✅ Order executed successfully: {resp['orderID']}")
            execution_results.append((True, resp['orderID']))
        else:
            logger.warning(f"⚠️ Order may not have been placed correctly: {resp['errorMsg']}")
            execution_results.append((False, resp['errorMsg']))

    except Exception as e:
        logger.error(f"❌ Failed to execute order: {str(e)}")
        execution_results.append((False, str(e)))

    # Print summary
    successful_orders = sum(1 for result in execution_results if result[0])
    logger.info(f"\nExecution Summary:")
    logger.info(f"Successfully executed orders: {successful_orders}/1")

    return execution_results

def cancel_orders(client, order_ids):
    for order_id in order_ids:
        print(f"\nAttempting to cancel order {order_id}:")
        response = client.cancel_order(order_id)
        print(f"Order {order_id} cancellation result:")
        print(response)
"""
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
"""
    
if __name__ == "__main__":
     pass