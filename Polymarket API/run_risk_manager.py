import asyncio
from py_clob_client.client import ClobClient
from subgraph_client import SubgraphClient
from riskManager import RiskManager
import config

async def main():
    # Initialize ClobClient
    clob_client = ClobClient(
        host=config.HOST,
        chain_id=config.CHAIN_ID,
        key=config.PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=config.POLYMARKET_PROXY_ADDRESS
    )
    clob_client.set_api_creds(clob_client.create_or_derive_api_creds())

    # Initialize SubgraphClient with HTTP URL
    subgraph_client = SubgraphClient(config.SUBGRAPH_HTTP_URL)
    
    # Create RiskManager instance
    risk_manager = RiskManager(clob_client, subgraph_client)
    
    # Run the RiskManager
    await risk_manager.main()

if __name__ == "__main__":
    asyncio.run(main())
