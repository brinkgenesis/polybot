import requests
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse
from config import (
    GAMMA_API_URL,
    GAMMA_API_PAGE_LIMIT,
    GAMMA_API_SORT_PARAM,
    GAMMA_API_MIN_REWARDS_DAILY_RATE,
    GAMMA_API_MAX_MARKETS_TO_RETURN
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger_config import main_logger as logger

def fetch_page(page):
    """Fetch a single page of markets from the Gamma API."""
    params = {
        'page': page,
        'limit': GAMMA_API_PAGE_LIMIT,
        'sort': GAMMA_API_SORT_PARAM
    }
    response = requests.get(f"{GAMMA_API_URL}/markets", params=params)
    response.raise_for_status()
    return response.json()

def get_high_liquidity_markets():
    """Fetch high daily rewards markets from Gamma API using threading."""
    logger.info("Fetching high daily rewards markets from Gamma API...")
    all_markets = []
    min_end_date = datetime.now(timezone.utc) + timedelta(days=4)
    max_pages = 50  # Increase the number of pages to fetch
    page = 1

    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_page, page): page for page in range(1, max_pages + 1)}
            for future in as_completed(futures):
                try:
                    markets = future.result()
                    if not isinstance(markets, list):
                        logger.info(f"Unexpected response format. Expected a list, received: {type(markets)}")
                        continue

                    # Filter markets on this page
                    filtered_markets = []
                    for market in markets:
                        try:
                            if market.get('clobRewards') and \
                               any(float(reward.get('rewardsDailyRate', 0)) >= GAMMA_API_MIN_REWARDS_DAILY_RATE for reward in market['clobRewards']) and \
                               'endDate' in market and \
                               parse(market['endDate']) > min_end_date:
                                filtered_markets.append(market)
                        except Exception as e:
                            logger.info(f"Error processing market: {e}")
                            logger.info(f"Market data: {market}")

                    all_markets.extend(filtered_markets)
                    logger.info(f"Fetched page {futures[future]} with {len(markets)} markets. Found {len(all_markets)} matching markets so far.")

                    if len(all_markets) >= 50:  # We have enough markets
                        break

                except Exception as e:
                    logger.info(f"Error fetching page {futures[future]}: {e}")

        logger.info(f"\nTotal markets fetched: {len(all_markets)}")

        # Sort filtered markets by volumeClob
        sorted_markets = sorted(
            all_markets, 
            key=lambda x: float(x.get('volumeClob', 0)), 
            reverse=True
        )

        # Remove duplicates while preserving order
        seen = set()
        unique_markets = []
        for market in sorted_markets:
            if market['questionID'] not in seen:
                seen.add(market['questionID'])
                unique_markets.append(market)

        # Take top 15 unique markets
        top_markets = unique_markets[:15]

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
                max_reward = max(clob_rewards, key=lambda x: float(x.get('rewardsDailyRate', 0)))
                logger.info(f"rewardsDailyRate: {max_reward.get('rewardsDailyRate', 'N/A')}")
                logger.info(f"rewardsMinSize: {max_reward.get('rewardsMinSize', 'N/A')}")
                logger.info(f"rewardsMaxSpread: {max_reward.get('rewardsMaxSpread', 'N/A')}")
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
        logger.info(f"Error fetching data from Gamma API: {e}")
        if hasattr(e.response, 'text'):
            logger.info(f"Response content: {e.response.text}")
        return []
    except Exception as e:
        logger.info(f"Unexpected error: {e}")
        return []

def get_markets_with_rewards(client):
    markets = client.get_markets()
    markets_with_rewards = []
    for market in markets:
        if market.get('clobRewards') and \
           any(float(reward.get('rewardsDailyRate', 0)) > 0 for reward in market['clobRewards']):
            markets_with_rewards.append(market)
    return markets_with_rewards

def get_gamma_market_data(market_id):
    markets = get_high_liquidity_markets()
    return next((market for market in markets if market['questionID'] == market_id), None)

# Make sure to export this function
__all__ = ['get_high_liquidity_markets', 'get_gamma_market_data']

if __name__ == "__main__":
    get_high_liquidity_markets()
