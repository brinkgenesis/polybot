import os
from dotenv import load_dotenv

load_dotenv()

# General settings
HOST = "https://clob.polymarket.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 137
GAMMA_API_URL = "https://gamma-api.polymarket.com"
TOTAL_BID_SIZE = 1000  # Adjust as needed
MAX_MARKETS = 10
YIELD_THRESHOLD = 0.02  # 2% yield threshold

# Subgraph settings
SUBGRAPH_HTTP_URL = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets"

# RiskManager parameters
RISK_VOLUME_THRESHOLD = 999  # Dollar amount threshold
RISK_VOLATILITY_COOLDOWN_PERIOD = 600  # 10 minutes in seconds
RISK_INACTIVITY_THRESHOLD = 86400  # 1 day in seconds
RISK_OPEN_INTEREST_THRESHOLD = 1000000
RISK_HIGH_ACTIVITY_THRESHOLD_PERCENT = 50  # 50%

# RiskManager intervals and delays
RISK_FETCH_RETRY_DELAY = 60
RISK_ORDER_BOOK_FETCH_DELAY = 1
RISK_MONITOR_INTERVAL = 10  # seconds between each OrderManager run
RISK_CORE_MANAGEMENT_INTERVAL = 3600

# Parameters for gamma_market_api.py
GAMMA_API_PAGE_LIMIT = 100
GAMMA_API_SORT_PARAM = '-clobRewards.rewardsDailyRate'
GAMMA_API_MIN_REWARDS_DAILY_RATE = 20
GAMMA_API_MAX_MARKETS_TO_RETURN = 10

# Maximum number of markets to process
MAX_PROCESSED_MARKETS = 5

# Polymarket API credentials
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_API_SECRET = os.getenv("POLY_API_SECRET")
POLY_PASSPHRASE = os.getenv("POLY_PASSPHRASE")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")

# Market IDs and User Addresses to monitor (replace with actual values)
MARKET_IDS = ["0xMarketId1", "0xMarketId2"]  # Example placeholder values
USER_ADDRESSES = ["0xUserAddress1", "0xUserAddress2"]  # Example placeholder values
TICK_SIZE = 0.01  # Adjust this value as needed
MAX_INCENTIVE_SPREAD = 0.02  # Adjust this value as needed
MAX_ORDER_SIZE = float(500)

# Other configuration variables can be added here
