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

def get_high_liquidity_markets():
    """Fetch high daily rewards markets from Gamma API"""
    print("Fetching high daily rewards markets from Gamma API...")
    all_markets = []
    page = 1
    min_end_date = datetime.now(timezone.utc) + timedelta(days=4)

    try:
        while True:
            params = {
                'page': page,
                'limit': GAMMA_API_PAGE_LIMIT,
                'sort': GAMMA_API_SORT_PARAM
            }
            response = requests.get(f"{GAMMA_API_URL}/markets", params=params)
            response.raise_for_status()
            markets = response.json()
            
            if not isinstance(markets, list):
                print(f"Unexpected response format. Expected a list, received: {type(markets)}")
                break

            if not markets:  # No more markets to fetch
                break

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
                    print(f"Error processing market: {e}")
                    print(f"Market data: {market}")
            
            all_markets.extend(filtered_markets)
            print(f"Fetched page {page} with {len(markets)} markets. Found {len(all_markets)} matching markets so far.")
            
            if len(all_markets) >= 50 or len(markets) < GAMMA_API_PAGE_LIMIT:  # We have enough markets or it's the last page
                break
            
            page += 1

        print(f"\nTotal markets fetched: {len(all_markets)}")

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

        print(f"\nTotal unique markets fetched: {len(unique_markets)}")
        print(f"\nFound {len(top_markets)} high daily rewards markets:")
        for i, market in enumerate(top_markets, 1):
            print(f"\n{i}.")
            print(f"question: {market.get('question', 'N/A')}")
            print(f"questionID: {market.get('questionID', 'N/A')}")
            print(f"liquidityClob: {market.get('liquidityClob', 'N/A')}")
            print(f"volumeClob: {market.get('volumeClob', 'N/A')}")
            
            # Handle clobRewards
            clob_rewards = market.get('clobRewards', [])
            if clob_rewards:
                max_reward = max(clob_rewards, key=lambda x: float(x.get('rewardsDailyRate', 0)))
                print(f"rewardsDailyRate: {max_reward.get('rewardsDailyRate', 'N/A')}")
                print(f"rewardsMinSize: {max_reward.get('rewardsMinSize', 'N/A')}")
                print(f"rewardsMaxSpread: {max_reward.get('rewardsMaxSpread', 'N/A')}")
            else:
                print("rewardsDailyRate: N/A")
                print("rewardsMinSize: N/A")
                print("rewardsMaxSpread: N/A")
            
            print(f"active: {market.get('active', 'N/A')}")
            print(f"enableOrderBook: {market.get('enableOrderBook', 'N/A')}")
            print(f"bestAsk: {market.get('bestAsk', 'N/A')}")
            print(f"bestBid: {market.get('bestBid', 'N/A')}")
            print(f"spread: {market.get('spread', 'N/A')}")
            print(f"lastTradePrice: {market.get('lastTradePrice', 'N/A')}")
            print(f"orderPriceMinTickSize: {market.get('orderPriceMinTickSize', 'N/A')}")
            print(f"startDate: {market.get('startDate', 'N/A')}")
            print(f"endDate: {market.get('endDate', 'N/A')}")

        return top_markets

    except requests.RequestException as e:
        print(f"Error fetching data from Gamma API: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response content: {e.response.text}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []

if __name__ == "__main__":
    get_high_liquidity_markets()
