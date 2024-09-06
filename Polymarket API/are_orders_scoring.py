import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrdersScoringParams
from dotenv import load_dotenv

load_dotenv()


def order_scoring(order_id): #add order id as parameter
    host = os.getenv("POLYMARKET_HOST")
    key = os.getenv("PRIVATE_KEY")
    creds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_SECRET"),
        api_passphrase=os.getenv("POLY_PASS_PHRASE"),
    )
    chain_id = os.getenv("CHAIN_ID")
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    scoring = client.are_orders_scoring(
        OrdersScoringParams(
            orderIds=[
                "0xb816482a5187a3d3db49cbaf6fe3ddf24f53e6c712b5a4bf5e01d0ec7b11dabc" 
                #replace with order id from bid manager. bid manager should print it out and return it
            ]
        )
    )
    print(scoring)
    print("Done!")
    return scoring

order_scoring()
