from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

def build_and_print_order(market, gamma_market):
    # Print market information
    print("\nOrder Builded for:")
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

    maker_amount_30 = best_bid - (2 * order_price_min_tick_size)
    maker_amount_70 = best_bid - (3 * order_price_min_tick_size)

    # Check if orders exceed the maximum allowed difference from best bid
    if maker_amount_30 < best_bid - (3 * order_price_min_tick_size) or maker_amount_70 < best_bid - (4 * order_price_min_tick_size):
        print("Orders exceed maximum allowed difference from best bid. Cancelling and creating new orders.")
        # Here you would implement the logic to cancel existing orders and create new ones
        return

    # Build orders
    order_30 = OrderArgs(
        price=maker_amount_30,
        size=order_size_30,
        side=BUY,
        token_id=market['tokens'][0]['token_id']  # YES token
    )

    order_70 = OrderArgs(
        price=maker_amount_70,
        size=order_size_70,
        side=BUY,
        token_id=market['tokens'][0]['token_id']  # YES token
    )

    print("\nOrders built:")
    print(f"30% Order: {order_30}")
    print(f"70% Order: {order_70}")

    return order_30, order_70

def execute_orders(client, orders):
    for i, order in enumerate(orders):
        signed_order = client.create_order(order)
        print(f"\nAttempting to execute order {i+1}:")
        print(signed_order)
        
        response = client.post_order(signed_order, OrderType.GTC)
        print(f"Order {i+1} execution result:")
        print(response)

def cancel_orders(client, order_ids):
    for order_id in order_ids:
        print(f"\nAttempting to cancel order {order_id}:")
        response = client.cancel_order(order_id)
        print(f"Order {order_id} cancellation result:")
        print(response)

def main(market, gamma_market, client):
    orders = build_and_print_order(market, gamma_market)
    
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

# The __main__ block is removed as we'll be calling this from gamma_clob_query.py