import logging
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    GAMMA_API_URL,
    GAMMA_API_PAGE_LIMIT,
    GAMMA_API_SORT_PARAM,
    GAMMA_API_MIN_REWARDS_DAILY_RATE,
    GAMMA_API_MAX_MARKETS_TO_RETURN
)

# ============================
# Local Logging Configuration
# ============================

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more granular logs

# Create handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

file_handler = logging.FileHandler('gamma_market_api.log')  # Log to file
file_handler.setLevel(logging.INFO)

# Create formatters and add them to handlers
formatter = logging.Formatter(
     '%(message)s'
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# =========================

def fetch_page(page):
    """Fetch a single page of markets from the Gamma API."""
    params = {
        'page': page,
        'limit': GAMMA_API_PAGE_LIMIT,
        'sort': GAMMA_API_SORT_PARAM
    }
    try:
        response = requests.get(f"{GAMMA_API_URL}/markets", params=params)
        response.raise_for_status()
        logger.debug(f"Successfully fetched page {page}.")
        return response.json()
    except requests.RequestException as e:
        logger.error(f"RequestException while fetching page {page}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while fetching page {page}: {e}")
        raise

def get_high_liquidity_markets():
    """Fetch high daily rewards markets from Gamma API using threading."""
    logger.info("Fetching high daily rewards markets from Gamma API...")
    all_markets = []
    min_end_date = datetime.now(timezone.utc) + timedelta(days=4)
    logger.debug(f"Minimum end date for markets: {min_end_date.isoformat()}")
    max_pages = 50  # Increase the number of pages to fetch

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_page, page): page for page in range(1, max_pages + 1)}
            for future in as_completed(futures):
                page = futures[future]
                try:
                    markets = future.result()
                    logger.debug(f"Processing page {page} with {len(markets)} markets.")

                    if not isinstance(markets, list):
                        logger.warning(f"Unexpected response format on page {page}. Expected a list, received: {type(markets)}")
                        continue

                    # Filter markets on this page
                    filtered_markets = []
                    for market in markets:
                        try:
                            # Check for clobRewards and rewardsDailyRate
                            has_rewards = market.get('clobRewards') and \
                                          any(float(reward.get('rewardsDailyRate', 0)) > GAMMA_API_MIN_REWARDS_DAILY_RATE for reward in market['clobRewards'])
                            # Check endDate
                            valid_end_date = 'endDate' in market and parse(market['endDate']) > min_end_date

                            if has_rewards and valid_end_date:
                                filtered_markets.append(market)
                        except Exception as e:
                            logger.error(f"Error processing market on page {page}: {e}", exc_info=True)
                            logger.debug(f"Market data: {market}")

                    logger.debug(f"Page {page}: {len(filtered_markets)} markets passed the filters.")
                    all_markets.extend(filtered_markets)

                    if len(all_markets) >= GAMMA_API_MAX_MARKETS_TO_RETURN:
                        logger.info("Reached the maximum number of markets to return. Stopping fetch.")
                        break

                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}", exc_info=True)

        logger.info(f"\nTotal markets fetched: {len(all_markets)}")

        # Sort filtered markets by volumeClob
        sorted_markets = sorted(
            all_markets,
            key=lambda x: float(x.get('volumeClob', 0)),
            reverse=True
        )
        logger.debug(f"Total markets after sorting: {len(sorted_markets)}")

        # Remove duplicates while preserving order
        seen = set()
        unique_markets = []
        for market in sorted_markets:
            question_id = market.get('questionID')
            if question_id and question_id not in seen:
                seen.add(question_id)
                unique_markets.append(market)

        logger.debug(f"Total unique markets after removing duplicates: {len(unique_markets)}")

        # Take top N unique markets based on GAMMA_API_MAX_MARKETS_TO_RETURN
        top_markets = unique_markets[:GAMMA_API_MAX_MARKETS_TO_RETURN]

        logger.info(f"\nTotal unique markets fetched: {len(unique_markets)}")
        logger.info(f"\nFound {len(top_markets)} high daily rewards markets:")
        for i, market in enumerate(top_markets, 1):
            logger.info(f"\n{i}.")
            logger.info(f"question: {market.get('question', 'N/A')}")
            logger.info(f"questionID: {market.get('questionID', 'N/A')}")
            logger.info(f"liquidityClob: {market.get('liquidityClob', 'N/A')}")
            logger.info(f"volumeClob: {market.get('volumeClob', 'N/A')}")

            # Handle clobRewards
            clob_rewards = market.get('clobRewards', [])
            if clob_rewards:
                try:
                    max_reward = max(clob_rewards, key=lambda x: float(x.get('rewardsDailyRate', 0)))
                    logger.info(f"rewardsDailyRate: {max_reward.get('rewardsDailyRate', 'N/A')}")
                    logger.info(f"rewardsMinSize: {max_reward.get('rewardsMinSize', 'N/A')}")
                    logger.info(f"rewardsMaxSpread: {max_reward.get('rewardsMaxSpread', 'N/A')}")
                except ValueError as e:
                    logger.error(f"Error processing clobRewards: {e}")
                    logger.info("rewardsDailyRate: N/A")
                    logger.info("rewardsMinSize: N/A")
                    logger.info("rewardsMaxSpread: N/A")
            else:
                logger.info("rewardsDailyRate: N/A")
                logger.info("rewardsMinSize: N/A")
                logger.info("rewardsMaxSpread: N/A")

            logger.info(f"active: {market.get('active', 'N/A')}")
            logger.info(f"enableOrderBook: {market.get('enableOrderBook', 'N/A')}")
            logger.info(f"bestAsk: {market.get('bestAsk', 'N/A')}")
            logger.info(f"bestBid: {market.get('bestBid', 'N/A')}")
            logger.info(f"spread: {market.get('spread', 'N/A')}")
            logger.info(f"lastTradePrice: {market.get('lastTradePrice', 'N/A')}")
            logger.info(f"orderPriceMinTickSize: {market.get('orderPriceMinTickSize', 'N/A')}")
            logger.info(f"startDate: {market.get('startDate', 'N/A')}")
            logger.info(f"endDate: {market.get('endDate', 'N/A')}")

        return top_markets

    except requests.RequestException as e:
        logger.error(f"RequestException while fetching data from Gamma API: {e}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response content: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []

def get_markets_with_rewards(client):
    """
    Fetch markets with rewards from the client.
    """
    markets = client.get_markets()
    markets_with_rewards = []
    for market in markets:
        if (
            market.get('clobRewards') and
            any(float(reward.get('rewardsDailyRate', 0)) > 0 for reward in market['clobRewards'])
        ):
            markets_with_rewards.append(market)
    return markets_with_rewards

def get_gamma_market_data(market_id):
    """
    Retrieve specific market data by market_id.
    """
    markets = get_high_liquidity_markets()
    return next((market for market in markets if market['questionID'] == market_id), None)

# Make sure to export these functions
__all__ = ['get_high_liquidity_markets', 'get_gamma_market_data']

if __name__ == "__main__":
    # For testing purposes, fetch the high liquidity markets and print the count
    markets = get_high_liquidity_markets()
    logger.info(f"\nRetrieved {len(markets)} high liquidity markets.")