This bot is designed to generate bids on various markets/pools on the prediction market Polymarket and profit from the rewards by providing liquidity.

Bids are not designed to be filled; rather, they are set so that they will adjust with the moving price of the market. There is a payout range for each pool that is fixed and helps concentrate liquidity among market participants.

The goal is to provide bids on multiple markets simultaneously. As long as they are not filled, the same capital earns yields from multiple pools at the same time. Capturing 5-10% of the rewards from each pool is enough to generate a decent 2-5% daily APR. Minimum pool rewards are $50 a day, with the peak at $1000 for large pools like the US general election. Based on these metrics we can assume that this strategy will work for capital allocation of up to $10,000, where larger sizes may lead to diminishing returns. 

There is also a market-making component for the bot, which follows a fair-price model. If the market price is currently below the fair price model, an alternative strategy will execute, purchasing the token at market price and placing market asks close to the fair price while still earning liquidity yields from that pool.

**Risk Management**

Some risk management is applied to counteract market volatility.

For example, larger liquidity pools have smaller unit increments compared to smaller pools. By design, this makes smaller pools more volatile, as an increment shift in a larger pool may result in a 0.1% loss, whereas in a smaller pool, the same shift will result in a 1% loss.

Knowing this, we split our orders in the small pool into two, placing 30% of the total size closer to the spread and the remaining 70% one increment down. In a fast-moving market where bids are quickly being filled, orders will automatically be canceled. If the first set of bids starts being filled, the second set will also automatically cancel. If both sets get filled, the net position will apply more weight to the second set of bids and average down the cost.

If bids end up getting filled, absent a market-making opportunity, we will seek to immediately cut the position. We market sell 50% of the position immediately, hoping to minimize direct impact. We create an order at the lowest ask price on the other side for the other 50%.

Alternatively, we can experiment with immediately hedging an equal-size position on the other outcome. Once positions have been hedged, we can slowly unwind the position by placing ask prices slightly above the current price for both. In reality, this may prove a little more difficult to execute in a timely fashion but will stop net losses in the case that assets are being actively repriced.


