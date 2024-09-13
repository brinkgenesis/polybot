import logging
from typing import List, Dict, Any, AsyncGenerator
from gql import gql, Client
from gql.transport.websockets import WebsocketsTransport
from datetime import datetime, timedelta

class SubgraphClient:
    def __init__(self, url: str):
        transport = WebsocketsTransport(url=url)
        self.client = Client(transport=transport, fetch_schema_from_transport=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    async def subscribe_to_trades(self, market_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        subscription = gql('''
        subscription onTrade($market: String!) {
          trades(
            where: { market: $market }
            orderBy: timestamp
            orderDirection: asc
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        try:
            async for result in self.client.subscribe(subscription, variable_values={"market": market_id}):
                yield result['trades']
        except Exception as e:
            self.logger.error(f"Error in trade subscription for market {market_id}: {e}")

    async def get_recent_trades(self, market_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        query = gql('''
        query getRecentTrades($market: String!, $limit: Int!) {
          trades(
            where: { market: $market }
            orderBy: timestamp
            orderDirection: desc
            first: $limit
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        try:
            result = await self.client.execute_async(query, variable_values={"market": market_id, "limit": limit})
            return result['trades']
        except Exception as e:
            self.logger.error(f"Error fetching recent trades for market {market_id}: {e}")
            return []

    async def get_market_info(self, market_id: str) -> Dict[str, Any]:
        query = gql('''
        query getMarketInfo($market: String!) {
          market(id: $market) {
            id
            question
            description
            creationTime
            closeTime
            resolutionTime
            outcomes
            liquidity
            volume
            openInterest
          }
        }
        ''')
        try:
            result = await self.client.execute_async(query, variable_values={"market": market_id})
            return result['market']
        except Exception as e:
            self.logger.error(f"Error fetching market info for {market_id}: {e}")
            return {}

    async def get_user_activities(self, user_address: str, start_time: int, end_time: int) -> Dict[str, List[Dict[str, Any]]]:
        query = gql('''
        query getUserActivities($user: String!, $startTime: Int!, $endTime: Int!) {
          orderPlacements(
            where: { user: $user, timestamp_gte: $startTime, timestamp_lte: $endTime }
          ) {
            id
            timestamp
            market
            size
            price
          }
          orderCancellations(
            where: { user: $user, timestamp_gte: $startTime, timestamp_lte: $endTime }
          ) {
            id
            timestamp
            market
          }
        }
        ''')
        try:
            result = await self.client.execute_async(query, variable_values={
                "user": user_address,
                "startTime": start_time,
                "endTime": end_time
            })
            return result
        except Exception as e:
            self.logger.error(f"Error fetching user activities for {user_address}: {e}")
            return {"orderPlacements": [], "orderCancellations": []}

    async def get_aggregated_metrics(self, market_id: str) -> Dict[str, Any]:
        query = gql('''
        query getAggregatedMetrics($market: String!) {
          market(id: $market) {
            id
            totalVolume
            openInterest
            liquidity
          }
        }
        ''')
        try:
            result = await self.client.execute_async(query, variable_values={"market": market_id})
            return result['market']
        except Exception as e:
            self.logger.error(f"Error fetching aggregated metrics for market {market_id}: {e}")
            return {}

    async def get_historical_trades(self, market_id: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        query = gql('''
        query getHistoricalTrades($market: String!, $startTime: Int!, $endTime: Int!) {
          trades(
            where: { market: $market, timestamp_gte: $startTime, timestamp_lte: $endTime }
            orderBy: timestamp
            orderDirection: asc
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        try:
            result = await self.client.execute_async(query, variable_values={
                "market": market_id,
                "startTime": start_time,
                "endTime": end_time
            })
            return result['trades']
        except Exception as e:
            self.logger.error(f"Error fetching historical trades for market {market_id}: {e}")
            return []

    async def subscribe_to_events(self, event_type: str, callback: callable, filters: Dict[str, Any] = None):
        if event_type == "liquidityChange":
            subscription = gql('''
            subscription onLiquidityChange($market: String!) {
              liquidityChanges(where: { market: $market }) {
                id
                timestamp
                market
                newLiquidity
              }
            }
            ''')
        elif event_type == "largeTrade":
            subscription = gql('''
            subscription onLargeTrade($market: String!, $minAmount: Float!) {
              trades(where: { market: $market, amount_gt: $minAmount }) {
                id
                timestamp
                market
                type
                outcomeIndex
                amount
                price
              }
            }
            ''')
        elif event_type == "protocolUpgrade":
            subscription = gql('''
            subscription onProtocolUpgrade {
              protocolUpgrades {
                id
                timestamp
                description
              }
            }
            ''')
        else:
            self.logger.error(f"Unsupported event type: {event_type}")
            return

        try:
            async for result in self.client.subscribe(subscription, variable_values=filters or {}):
                callback(result)
        except Exception as e:
            self.logger.error(f"Error in event subscription for {event_type}: {e}")

    async def analyze_user_metrics(self, user_address: str) -> Dict[str, Any]:
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        activities = await self.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return {}

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        total_orders = len(placements)
        total_cancellations = len(cancellations)
        total_volume = sum(float(order['size']) for order in placements)
        avg_order_size = total_volume / total_orders if total_orders > 0 else 0

        return {
            "total_orders": total_orders,
            "total_cancellations": total_cancellations,
            "total_volume": total_volume,
            "avg_order_size": avg_order_size
        }

    async def analyze_historical_trends(self, market_id: str) -> Dict[str, Any]:
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        trades = await self.get_historical_trades(market_id, start_time, end_time)
        if not trades:
            self.logger.warning(f"No historical trades found for market {market_id}.")
            return {}

        total_volume = sum(float(trade['amount']) for trade in trades)
        average_price = sum(float(trade['price']) for trade in trades) / len(trades)

        return {
            "total_volume": total_volume,
            "average_price": average_price
        }

    async def monitor_user_activities(self, user_address: str) -> Dict[str, int]:
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 24 * 3600  # Past 24 hours

        activities = await self.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return {}

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        return {
            "orders_placed": len(placements),
            "orders_canceled": len(cancellations)
        }

# Example usage
async def main():
    from config import SUBGRAPH_URL
    subgraph_client = SubgraphClient(SUBGRAPH_URL)
    
    # Example: Fetch recent trades for a market
    market_id = "0xYourMarketIdHere"
    recent_trades = await subgraph_client.get_recent_trades(market_id)
    print(f"Recent trades for market {market_id}:", recent_trades)

    # Add more example usage as needed

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

