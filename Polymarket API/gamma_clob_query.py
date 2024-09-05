from gamma_market_api import get_high_liquidity_markets
from int import clob_client
from tqdm import tqdm
import logging

# Configure logging to show only the message
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    if not clob_client:
        raise ValueError("clob_client is not initialized. Please run int.py first.")

    logger.info("Fetching high rewards markets from Gamma API")
    gamma_markets = get_high_liquidity_markets()

    logger.info("Now querying CLOB Markets API to match markets.")

    # Get all markets from CLOB API
    all_clob_markets = []
    next_cursor = ""
    with tqdm(total=100, desc="Fetching CLOB markets") as pbar:
        while True:
            resp = clob_client.get_markets(next_cursor=next_cursor)
            all_clob_markets.extend(resp['data'])
            next_cursor = resp['next_cursor']
            pbar.update(10)  # Update progress bar
            if next_cursor == "LTE=":
                pbar.update(100 - pbar.n)  # Ensure progress bar reaches 100%
                break

    logger.info(f"Number of Gamma markets: {len(gamma_markets)}")
    logger.info(f"Number of CLOB markets: {len(all_clob_markets)}")

    # Match and print market information
    matched_markets = []
    processed_markets = 0
    all_orders = []
    for gamma_market in gamma_markets:
        if processed_markets >= 5:
            break

        gamma_question_id = gamma_market.get('questionID')
        
        if not gamma_question_id:
            logger.warning("Gamma market missing questionID")
            continue
        
        matching_clob_market = next((market for market in all_clob_markets if market['question_id'] == gamma_question_id), None)
        
        if matching_clob_market:
            processed_markets += 1
            logger.info(f"Matched market for question_id: {gamma_question_id}")
            
            # Log market information
            logger.info(f"Gamma Market Question: {gamma_market.get('question', 'N/A')}")
            logger.info(f"CLOB Market Description: {matching_clob_market.get('description', 'N/A')}")
            logger.info(f"Category: {matching_clob_market.get('category', 'N/A')}")
            logger.info(f"End Date: {matching_clob_market.get('end_date_iso', 'N/A')}")
            logger.info(f"Minimum Order Size: {matching_clob_market.get('minimum_order_size', 'N/A')}")
            logger.info(f"Minimum Tick Size: {matching_clob_market.get('minimum_tick_size', 'N/A')}")
            logger.info(f"Min Incentive Size: {matching_clob_market.get('min_incentive_size', 'N/A')}")
            logger.info(f"Max Incentive Spread: {matching_clob_market.get('max_incentive_spread', 'N/A')}")
            logger.info(f"Active: {matching_clob_market.get('active', 'N/A')}")
            logger.info(f"Closed: {matching_clob_market.get('closed', 'N/A')}")
            logger.info(f"Seconds Delay: {matching_clob_market.get('seconds_delay', 'N/A')}")
            logger.info(f"FPMM Address: {matching_clob_market.get('fpmm', 'N/A')}")
            
            logger.info("Tokens:")
            for token in matching_clob_market.get('tokens', []):
                logger.info(f"  Outcome: {token.get('outcome', 'N/A')}")
                logger.info(f"  Token ID: {token.get('token_id', 'N/A')}")

            # Extract token IDs
            token_ids = [token['token_id'] for token in matching_clob_market.get('tokens', [])]
            
            # Add to matched_markets list
            matched_markets.append({
                'question': gamma_market.get('question'),
                'questionID': gamma_question_id,
                'token_ids': token_ids,
                'gamma_market': gamma_market,
                'clob_market': matching_clob_market
            })
            
            
            logger.info("-" * 50)
        else:
            logger.warning(f"No matching CLOB market found for question_id: {gamma_question_id}")
            logger.warning(f"Gamma Market Question: {gamma_market.get('question', 'N/A')[:100]}...")
            logger.info("-" * 50)

    logger.info(f"Processed {processed_markets} markets.")
    logger.info(f"Total Gamma markets: {len(gamma_markets)}")
    logger.info(f"Total CLOB markets: {len(all_clob_markets)}")
    logger.info(f"Total orders built: {len(all_orders)}")

    return matched_markets

if __name__ == "__main__":
    main()
