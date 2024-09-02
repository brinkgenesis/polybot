from int import clob_client
from order_market_scanner import start_order_market_scanner, stop_order_market_scanner
from gamma_clob_query import main as gamma_clob_main
import signal
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    print("Ctrl+C pressed. Stopping the scanner and exiting...")
    stop_order_market_scanner()
    sys.exit(0)

def main():
    # Set up the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Run the existing gamma_clob_query process
    matched_markets = gamma_clob_main()

    # Extract all unique token IDs from the matched markets and ensure they're strings
    token_ids = set()
    for market in matched_markets:
        token_ids.update(str(token_id) for token_id in market['token_ids'])
    token_ids = list(token_ids)

    if not token_ids:
        logger.error("No token IDs found. Exiting.")
        return

    logger.info(f"Extracted {len(token_ids)} token IDs:")
    for token_id in token_ids:
        logger.info(f"Token ID: {token_id}")

    # Start the order market scanner
    start_order_market_scanner(token_ids)

    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()