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
    print("Fetching high daily rewards markets from Gamma API...")
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
                        print(f"Unexpected response format. Expected a list, received: {type(markets)}")
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
                            print(f"Error processing market: {e}")
                            print(f"Market data: {market}")

                    all_markets.extend(filtered_markets)
                    print(f"Fetched page {futures[future]} with {len(markets)} markets. Found {len(all_markets)} matching markets so far.")

                    if len(all_markets) >= 50:  # We have enough markets
                        break

                except Exception as e:
                    print(f"Error fetching page {futures[future]}: {e}")

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

def get_markets_with_rewards(client):
    markets = client.get_markets()
    markets_with_rewards = []
    for market in markets:
        if market.get('clobRewards') and \
           any(float(reward.get('rewardsDailyRate', 0)) > 0 for reward in market['clobRewards']):
            markets_with_rewards.append(market)
    return markets_with_rewards

def get_top_markets():
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": GAMMA_API_PAGE_LIMIT,
        "sort": GAMMA_API_SORT_PARAM,
        "min_rewards_daily_rate": GAMMA_API_MIN_REWARDS_DAILY_RATE
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    markets = response.json().get('markets', [])
    
    filtered_markets = []
    for market in markets:
        if len(filtered_markets) >= GAMMA_API_MAX_MARKETS_TO_RETURN:
            break
        
        clob_token_ids = market.get('clob_token_ids', [])
        if clob_token_ids:
            filtered_markets.append({
                'question': market.get('question'),
                'clob_token_id': clob_token_ids[0],  # Assuming we're interested in the first token
                'best_bid': market.get('bestBid'),
                'best_ask': market.get('bestAsk'),
                'rewards_daily_rate': market.get('clobRewards', {}).get('rewardsDailyRate', 0)
            })
    
    return filtered_markets

def get_gamma_market_data(token_id: str):
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "clob_token_ids": token_id
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if isinstance(data, list):
            markets = data
        elif isinstance(data, dict):
            markets = data.get('markets', [])
        else:
            print(f"Unexpected response format for token ID: {token_id}")
            return None
        
        if markets:
            return markets[0]  # Return the first (and should be only) market
        else:
            print(f"No market found for token ID: {token_id}")
            return None
    except requests.RequestException as e:
        print(f"Error fetching data from Gamma API: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        print(f"Response content: {response.text}")
        return None

if __name__ == "__main__":
    get_high_liquidity_markets()
