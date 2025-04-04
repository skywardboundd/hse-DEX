from .blockchain_indexer import BlockchainIndexer
from .run import main as run_main

__all__ = [
    'BlockchainIndexer',
    'run_main'
]

"""
Модуль индексирования блокчейна TON.

Этот модуль предоставляет функциональность для отслеживания 
данных из блокчейна TON, включая пулы ликвидности и цены токенов.

Примечание: Для работы модуля необходим файл .env с параметрами:
- TONAPI_KEY=YOUR_API_KEY
- DEX_CONTRACT_ADDRESS=EQBeHLvZ4urFg9C2z5m6TxM-JKBwYEQwl1-BJQxOjnE0wYgt
- FACTORY_CONTRACT_ADDRESS=EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUs
- PRICE_UPDATE_INTERVAL=300
- POOLS_CHECK_INTERVAL=600
""" 