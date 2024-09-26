import asyncio
from typing import List, Dict, Callable, Any, Optional
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import logging
import certifi
import ssl
import requests

class SubgraphClient:
    def __init__(self, url: str):
        """
        Initializes the SubgraphClient with the provided GraphQL endpoint.
        """
        self.url = url  # Add this line to store the URL
        self.transport = AIOHTTPTransport(url=url)
        self.client = Client(transport=self.transport, fetch_schema_from_transport=True)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def subscribe_to_events(self, subscription_query: str, variables: Dict, callback: Callable[[Dict], Any]):
        """
        Subscribes to GraphQL events using the provided subscription query and variables.
        """
        try:
            async with self.client as session:
                async for event in session.subscribe(gql(subscription_query), variable_values=variables):
                    await callback(event)
        except Exception as e:
            self.logger.error(f"Error subscribing to events: {e}", exc_info=True)
           
    async def get_historical_trades(self, market_id: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict]:
        """
        Fetches historical trades for a specific market within a given time frame.
        """
        query = gql('''
        query getHistoricalTrades($market: String!, $startTime: Int!, $endTime: Int!, $limit: Int!) {
          trades(
            where: { 
              market: $market,
              timestamp_gte: $startTime,
              timestamp_lte: $endTime
            }
            orderBy: timestamp
            orderDirection: asc
            first: $limit
          ) {
            id
            timestamp
            market
            type
            tradeAmount
            outcomeIndex
            outcomeTokensAmount
            price
          }
        }
        ''')

        variables = {
            "market": market_id,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        try:
            async with self.client as session:
                result = await session.execute(query, variable_values=variables)
                return result.get('trades', [])
        except Exception as e:
            self.logger.error(f"Error fetching historical trades for market {market_id}: {e}", exc_info=True)
            return []

    async def get_markets(self) -> List[Dict]:
        """
        Fetches all active markets.
        """
        query = gql('''
        query {
          markets(where: { isActive: true }) {
            token_id
            name
            # Add other relevant fields if necessary
          }
        }
        ''')

        try:
            async with self.client as session:
                result = await session.execute(query)
                return result.get('markets', [])
        except Exception as e:
            self.logger.error(f"Error fetching markets: {e}", exc_info=True)
            return []

    def get_large_orders(self, volume_threshold: float) -> List[Dict]:
        """
        Fetches large orders exceeding the specified volume threshold.
        """
        query = '''
        query GetLargeOrders($value: BigDecimal!) {
            trades(where: {tradeAmount_gt: $value}) {
                id
                side
                amount
                price
                outcomeToken {
                    id
                    symbol
                }
                market {
                    id
                    question
                    resolutionTimestamp
                }
                timestamp
                tradeAmount
            }
        }
        '''

        variables = {"value": str(volume_threshold)}  # Ensure the value is a string

        try:
            response = requests.post(
                self.url,
                json={'query': query, 'variables': variables}
            )
            response.raise_for_status()
            result = response.json()
            return result.get('data', {}).get('trades', [])
        except Exception as e:
            self.logger.error(f"Error fetching large orders from Subgraph: {e}", exc_info=True)
            return []