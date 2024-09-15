import asyncio
from typing import List, Dict, Any, Callable
from gql import gql, Client
from gql.transport.websockets import WebsocketsTransport
import logging
import requests
import certifi
import ssl

class SubgraphClient:
    def __init__(self, url: str):
        """
        Initializes the SubgraphClient with the provided GraphQL endpoint.

        :param url: The WebSocket URL of the subgraph.
        """
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        transport = WebsocketsTransport(url=url, ssl=ssl_context)
        self.client = Client(transport=transport, fetch_schema_from_transport=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    async def get_historical_trades(self, market_id: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict]:
        """
        Fetches historical trades for a specific market within a given time frame.

        :param market_id: The identifier of the market.
        :param start_time: The UNIX timestamp marking the start of the period.
        :param end_time: The UNIX timestamp marking the end of the period.
        :param limit: The maximum number of trades to fetch.
        :return: A list of trade dictionaries.
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
            outcome
            amount
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
            result = await self.client.execute_async(query, variable_values=variables)
            return result.get('trades', [])
        except Exception as e:
            self.logger.error(f"Error fetching historical trades for market {market_id}: {e}", exc_info=True)
            return []

    async def subscribe_to_events(self, subscription_query, variables=None):
        """
        Generic method to subscribe to events.

        :param subscription_query: The GraphQL subscription query.
        :param variables: The variables for the subscription.
        """
        async with self.client as session:
            subscription = gql(subscription_query)
            async for result in session.subscribe(subscription, variable_values=variables):
                yield result

    def get_markets(self) -> List[Dict]:
        """
        Fetches all active markets.

        :return: A list of market dictionaries.
        """
        import requests  # Imported here to avoid blocking the async event loop
        query = '''
        query {
          markets(where: { isActive: true }) {
            token_id
            name
            # Add other relevant fields if necessary
          }
        }
        '''
        url = self.client.transport.url.replace('wss://', 'https://')  # Assuming REST endpoint is similar
        try:
            response = requests.post(url, json={'query': query})
            data = response.json()
            return data.get('data', {}).get('markets', [])
        except Exception as e:
            self.logger.error(f"Error fetching markets: {e}", exc_info=True)
            return []

