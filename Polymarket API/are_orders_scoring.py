from logger_config import main_logger as logger
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderScoringParams, OrdersScoringParams
from dotenv import load_dotenv

def is_order_scoring(client, order_id):
    logger.info(f"Checking scoring for order ID: {order_id}")
    try:
        scoring = client.is_order_scoring(
            OrderScoringParams(orderId=order_id)
        )
        return scoring.scoring if scoring else False
    except Exception as e:
        logger.error(f"Error in is_order_scoring: {str(e)}")
        return False

def are_orders_scoring(client, order_ids):
    logger.info(f"Checking scoring for order IDs: {order_ids}")
    try:
        scoring = client.are_orders_scoring(
            OrdersScoringParams(orderIds=order_ids)
        )
        # Assuming scoring is already a dictionary of boolean values
        return scoring
    except Exception as e:
        logger.error(f"Error in are_orders_scoring: {str(e)}")
        return {order_id: False for order_id in order_ids}

# This function will be called from order_manager.py
def run_order_scoring(client, order_ids):
    if isinstance(order_ids, str):
        return is_order_scoring(client, order_ids)
    elif isinstance(order_ids, list):
        return are_orders_scoring(client, order_ids)
    else:
        logger.error(f"Invalid input type for order_ids: {type(order_ids)}")
        return False
