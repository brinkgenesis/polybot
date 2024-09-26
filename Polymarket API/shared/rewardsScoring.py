import math
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookLevel
from gamma_client.gamma_market_api import get_gamma_market_data

def calculate_market_score(client: ClobClient, market_id: str, v: float, b: float, c: float = 3.0):
    # Fetch the order book for the market
    book = client.get_book(market_id)
    
    # Calculate the adjusted midpoint
    best_bid = float(book.bids[0].price) if book.bids else 0
    best_ask = float(book.asks[0].price) if book.asks else 1
    midpoint = (best_bid + best_ask) / 2
    
    # Calculate Qone and Qtwo
    Qone = calculate_Q(book.bids, book.asks, v, b, midpoint)
    Qtwo = calculate_Q(book.asks, book.bids, v, b, midpoint)
    
    # Calculate Qmin based on the midpoint
    if 0.10 <= midpoint <= 0.90:
        Qmin = max(min(Qone, Qtwo), max(Qone/c, Qtwo/c))
    else:
        Qmin = min(Qone, Qtwo)
    
    return Qmin

def calculate_Q(side1: list[BookLevel], side2: list[BookLevel], v: float, b: float, midpoint: float):
    Q = 0
    for level in side1:
        s = abs(float(level.price) - midpoint)
        Q += S(v, s, b) * float(level.size)
    for level in side2:
        s = abs(float(level.price) - midpoint)
        Q += S(v, s, b) * float(level.size)
    return Q

def S(v: float, s: float, b: float):
    return ((v - s) / v) ** 2 * b

if __name__ == "__main__":
    client = ClobClient("https://clob.polymarket.com")
    
    while True:
        token_id = input("Enter the token ID (or 'q' to quit): ")
        if token_id.lower() == 'q':
            break

        gamma_market = get_gamma_market_data(token_id)
        if gamma_market is None:
            print("Failed to fetch market data. Please try a different token ID.")
            continue

        print(f"Market Question: {gamma_market.get('question', 'N/A')}")
        print(f"Question ID: {gamma_market.get('questionID', 'N/A')}")
        print(f"Token ID: {gamma_market.get('tokenId', 'N/A')}")
        print(f"Outcome: {gamma_market.get('outcome', 'N/A')}")
        print(f"Best Bid: {gamma_market.get('bestBid', 'N/A')}")
        print(f"Best Ask: {gamma_market.get('bestAsk', 'N/A')}")

        v = float(input("Enter the max spread from midpoint in cents (e.g., 3 for 3 cents): ")) / 100
        b = float(input("Enter the in-game multiplier: "))
        c = float(input("Enter the scaling factor (default is 3.0): ") or "3.0")

        score = calculate_market_score(client, token_id, v, b, c)
        print(f"Market score: {score}")

        another = input("Do you want to check another token? (y/n): ")
        if another.lower() != 'y':
            break

    print("Thank you for using the rewards scoring tool!")
