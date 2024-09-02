import os
from dotenv import load_dotenv

load_dotenv()

HOST = "https://clob.polymarket.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 137
GAMMA_API_URL = "https://gamma-api.polymarket.com"
TOTAL_BID_SIZE = 1000  # Adjust as needed
MAX_MARKETS = 10
YIELD_THRESHOLD = 0.02  # 2% yield threshold

# Parameters for gamma_market_api.py
GAMMA_API_PAGE_LIMIT = 100
GAMMA_API_SORT_PARAM = '-clobRewards.rewardsDailyRate'
GAMMA_API_MIN_REWARDS_DAILY_RATE = 50
GAMMA_API_MAX_MARKETS_TO_RETURN = 10


# Maximum number of markets to process
MAX_PROCESSED_MARKETS = 5

# Other configuration variables can be added here
