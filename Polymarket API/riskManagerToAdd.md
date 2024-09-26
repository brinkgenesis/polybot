    @lru_cache(maxsize=128)
    async def get_cached_market_info(self, market_id):
        return await self.subgraph_client.get_market_info(market_id)

    async def fetch_market_info(self, market_id):
        try:
            market_info = await self.get_cached_market_info(market_id)
            return market_info
        except Exception as e:
            self.logger.error(f"Failed to fetch market info for {market_id}: {e}")
            # Implement retry logic or fallback mechanisms here
            return None

        # Check if market has been inactive for a long time
        current_time = int(time.time())
        if current_time - int(market_info['lastActiveTimestamp']) > self.INACTIVITY_THRESHOLD:
            await self.handle_inactive_market(token_id)

        # Check open interest
        if float(market_info['openInterest']) > self.OPEN_INTEREST_THRESHOLD:
            await self.handle_high_open_interest(token_id)

    async def handle_inactive_market(self, token_id):
        # Implement logic to handle inactive markets
        # For example, you might want to cancel orders in these markets
        pass

    async def handle_high_open_interest(self, token_id):
        # Implement logic to handle markets with high open interest
        # For example, you might want to reduce exposure in these markets
        pass

        async def analyze_historical_trends(self, market_id: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        trades = await self.subgraph_client.get_historical_trades(market_id, start_time, end_time)
        if not trades:
            self.logger.warning(f"No historical trades found for market {shorten_id(market_id)}.")
            return

        # Example: Calculate total volume and average price
        total_volume = sum(float(trade['amount']) for trade in trades)
        average_price = sum(float(trade['price']) for trade in trades) / len(trades)

        self.logger.info(f"Market {shorten_id(market_id)} - Total Volume (7d): {total_volume}")
        self.logger.info(f"Market {shorten_id(market_id)} - Average Price (7d): {average_price:.4f}")

        # Further trend analysis can be implemented here

    async def monitor_user_activities(self, user_address: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 24 * 3600  # Past 24 hours

        activities = await self.subgraph_client.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        self.logger.info(f"User {shorten_id(user_address)} - Orders Placed (24h): {len(placements)}")
        self.logger.info(f"User {shorten_id(user_address)} - Orders Canceled (24h): {len(cancellations)}")

        # Example: Flag if user cancels more than a threshold number of orders
        CANCEL_THRESHOLD = 10
        if len(cancellations) > CANCEL_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded cancellation threshold with {len(cancellations)} cancellations.")
            # Implement further actions like alerting or restricting activities

    async def collect_aggregate_metrics(self, market_id: str):
        metrics = await self.subgraph_client.get_aggregated_metrics(market_id)
        if not metrics:
            self.logger.warning(f"No aggregated metrics found for market {shorten_id(market_id)}.")
            return

        self.logger.info(f"Market {shorten_id(market_id)} - Total Volume: {metrics['totalVolume']}")
        self.logger.info(f"Market {shorten_id(market_id)} - Open Interest: {metrics['openInterest']}")
        self.logger.info(f"Market {shorten_id(market_id)} - Liquidity: {metrics['liquidity']}")

        # Example: Flag markets with low liquidity
        LIQUIDITY_THRESHOLD = 5000
        if metrics['liquidity'] < LIQUIDITY_THRESHOLD:
            self.logger.warning(f"Market {shorten_id(market_id)} liquidity below threshold: {metrics['liquidity']}")
            # Implement further actions like adjusting order sizes or alerting

    def handle_protocol_upgrade(self, event: Dict):
        upgrade_id = event['id']
        description = event['description']
        timestamp = datetime.utcfromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f"Protocol Upgrade Detected: Upgrade ID {shorten_id(upgrade_id)}, Description: {description}, Timestamp: {timestamp}")

        # Example: Implement necessary adjustments post-upgrade
        # This could include refreshing connections, updating configurations, etc.


        # Subscribe to protocol upgrades
        asyncio.create_task(
            self.subgraph_client.subscribe_to_events(
                event_type="protocolUpgrade",
                callback=self.handle_protocol_upgrade
            )
        )



    async def analyze_user_metrics(self, user_address: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        activities = await self.subgraph_client.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        # Calculate metrics
        total_orders = len(placements)
        total_cancellations = len(cancellations)
        total_volume = sum(float(order['size']) for order in placements)
        avg_order_size = total_volume / total_orders if total_orders > 0 else 0

        self.logger.info(f"User {shorten_id(user_address)} Metrics (7d):")
        self.logger.info(f"  Total Orders Placed: {total_orders}")
        self.logger.info(f"  Total Cancellations: {total_cancellations}")
        self.logger.info(f"  Total Volume: {total_volume}")
        self.logger.info(f"  Average Order Size: {avg_order_size:.2f}")

        # Define risk thresholds
        ORDER_THRESHOLD = 100  # Max orders in 7 days
        CANCELLATION_THRESHOLD = 20  # Max cancellations in 7 days
        VOLUME_THRESHOLD = 50000  # Max total volume
        AVG_ORDER_SIZE_THRESHOLD = 1000  # Max average order size

        # Flag users exceeding thresholds
        if total_orders > ORDER_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded order placement threshold with {total_orders} orders.")
            # Implement actions like flagging, auditing, or restricting

        if total_cancellations > CANCELLATION_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded cancellation threshold with {total_cancellations} cancellations.")
            # Implement actions like flagging, auditing, or restricting

        if total_volume > VOLUME_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded total volume threshold with volume {total_volume}.")
            # Implement actions like flagging, auditing, or restricting

        if avg_order_size > AVG_ORDER_SIZE_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded average order size threshold with average size {avg_order_size}.")
            # Implement actions like flagging, auditing, or restricting

    async def straddle_midpoint(self, market_id: str):
        # Fetch current order book
        order_book = self.clob_client.get_order_book(market_id)
        if not order_book or not order_book.bids or not order_book.asks:
            self.logger.error(f"Order book data missing for market {shorten_id(market_id)}. Cannot straddle midpoint.")
            return

        # Determine best bid and ask
        best_bid = float(order_book.bids[0].price)
        best_ask = float(order_book.asks[0].price)
        midpoint = (best_bid + best_ask) / 2

        self.logger.info(f"Market {shorten_id(market_id)} - Best Bid: {best_bid}, Best Ask: {best_ask}, Midpoint: {midpoint}")

        # Define price offsets for straddling
        BUY_OFFSET = 0.01  # Place buy order slightly below midpoint
        SELL_OFFSET = 0.01  # Place sell order slightly above midpoint

        buy_price = midpoint - BUY_OFFSET
        sell_price = midpoint + SELL_OFFSET

        # Define order sizes based on historical volatility or aggregate metrics
        order_size = self.determine_order_size(market_id)

        # Build and place buy order
        buy_order = self.clob_client.create_order(
            OrderArgs(
                token_id=market_id,
                price=buy_price,
                size=order_size,
                side="BUY"
            )
        )
        self.clob_client.post_order(buy_order, OrderType.GTC)
        self.logger.info(f"Placed BUY order at {buy_price} with size {order_size} for market {shorten_id(market_id)}.")

        # Build and place sell order
        sell_order = self.clob_client.create_order(
            OrderArgs(
                token_id=market_id,
                price=sell_price,
                size=order_size,
                side="SELL"
            )
        )
        self.clob_client.post_order(sell_order, OrderType.GTC)
        self.logger.info(f"Placed SELL order at {sell_price} with size {order_size} for market {shorten_id(market_id)}.")


    def determine_order_size(self, market_id: str) -> float:
        """
        Determine the size of the order based on historical volatility and aggregate metrics.
        """
        # Fetch aggregate metrics
        metrics = asyncio.run(self.subgraph_client.get_aggregated_metrics(market_id))
        if not metrics:
            self.logger.warning(f"Using default order size for market {shorten_id(market_id)} due to missing metrics.")
            return 10.0  # Default size

        volatility = self.calculate_volatility(market_id)
        liquidity = metrics.get('liquidity', 0)

        # Example logic: larger order sizes for higher liquidity and lower volatility
        base_size = 10.0
        size = base_size * (liquidity / 10000) * (1 / (volatility + 1))

        self.logger.info(f"Determined order size for market {shorten_id(market_id)}: {size:.2f}")
        return size

