import time
from typing import List, Dict
import logging
import threading
from int import clob_client  # Import the client from int.py
from concurrent.futures import ThreadPoolExecutor, as_completed  # Import ThreadPoolExecutor

# Configure logging to show only the message
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Global flag to control the scanning loop
scanning = False

def get_price(token_id: str, side: str) -> Dict:
    """Fetch the price for a given token ID and side."""
    try:
        return clob_client.get_price(token_id=token_id, side=side)
    except Exception as e:
        logger.error(f"Error fetching price for token ID {token_id}, side {side}: {str(e)}")
        return {"error": str(e)}

def get_spread(token_id: str) -> Dict:
    """Fetch the spread for a given token ID."""
    try:
        return clob_client.get_spread(token_id)
    except Exception as e:
        logger.error(f"Error fetching spread for token ID {token_id}: {str(e)}")
        return {"error": str(e)}

def get_midpoint(token_id: str) -> Dict:
    """Fetch the midpoint for a given token ID."""
    try:
        return clob_client.get_midpoint(token_id)
    except Exception as e:
        logger.error(f"Error fetching midpoint for token ID {token_id}: {str(e)}")
        return {"error": str(e)}

def fetch_data_for_token(token_id: str) -> Dict:
    """Fetch and return data for a single token ID."""
    try:
        buy_price = get_price(token_id, "buy")
        sell_price = get_price(token_id, "sell")
        midpoint = get_midpoint(token_id)
        
        return {
            "token_id": token_id,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "midpoint": midpoint
        }
    except Exception as e:
        logger.error(f"Error fetching data for token ID {token_id}: {str(e)}")
        return {"token_id": token_id, "error": str(e)}

def scan_order_markets(token_ids: List[str], duration: int = 60):
    """
    Scan order markets for the given token IDs.
    
    :param token_ids: List of token IDs to scan
    :param duration: Duration to run the scanner in seconds
    """
    global scanning
    scanning = True
    end_time = time.time() + duration
    
    with ThreadPoolExecutor(max_workers=len(token_ids)) as executor:
        while scanning and time.time() < end_time:
            futures = [executor.submit(fetch_data_for_token, token_id) for token_id in token_ids]
            results = [future.result() for future in as_completed(futures)]
            
            for result in results:
                if "error" in result:
                    logger.error(f"Error fetching data for token ID {result['token_id']}: {result['error']}")
                else:
                    logger.info(f"Token ID: {result['token_id']}")
                    logger.info(f"Best Bid: {result['buy_price']}")
                    logger.info(f"Best Ask: {result['sell_price']}")
                    logger.info(f"Midpoint: {result['midpoint']}")
                    logger.info("---")
            
            # Wait for 5 seconds before the next scan
            time.sleep(5)
    
    logger.info("Scanning completed.")

def start_order_market_scanner(token_ids: List[str]):
    """
    Start the order market scanner in a separate thread.
    
    :param token_ids: List of token IDs to scan
    """
    logger.info("Starting order market scanner...")
    scanner_thread = threading.Thread(target=scan_order_markets, args=(token_ids,))
    scanner_thread.start()
    logger.info("Order market scanner started. It will run for 60 seconds.")

def stop_order_market_scanner():
    """
    Stop the order market scanner.
    """
    global scanning
    scanning = False
    logger.info("Stopping order market scanner...")