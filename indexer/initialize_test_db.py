"""
Скрипт для инициализации тестовой базы данных мок-данными
"""

import asyncio
import os
import logging
from dotenv import load_dotenv

from core.db import init_db, save_pool, save_price, save_position
from .mock_data import MOCK_POOLS, MOCK_PRICES, MOCK_POOL_LIQUIDITY, MOCK_POSITIONS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def initialize_test_db():
    """
    Инициализирует тестовую базу данных мок-данными
    """
    # Загрузка переменных окружения
    load_dotenv()
    
    # Инициализация базы данных
    init_success = init_db()
    if not init_success:
        logger.error("Ошибка инициализации базы данных")
        return
    
    logger.info("Начинаем инициализацию тестовой базы данных...")
    
    # Сохранение пулов
    logger.info("Сохранение пулов...")
    for pool in MOCK_POOLS:
        await save_pool(
            token1=pool['token1'],
            token2=pool['token2'],
            pool_address=pool['address'],
            liquidity=pool['liquidity'],
            token1_address=pool['token1_address'],
            token2_address=pool['token2_address']
        )
        logger.info(f"Сохранен пул {pool['token1']}/{pool['token2']} с адресом {pool['address']}")
    
    # Сохранение цен
    logger.info("Сохранение цен...")
    for pool_address, price in MOCK_PRICES.items():
        await save_price(pool_address=pool_address, price=price)
        logger.info(f"Сохранена цена {price} для пула {pool_address}")
    
    # Сохранение ликвидности
    logger.info("Сохранение позиций ликвидности...")
    for pool_address, positions in MOCK_POSITIONS.items():
        for position in positions:
            await save_position(
                wallet_address=position['wallet_address'],
                pool_address=pool_address,
                token1_amount=position['token1_amount'],
                token2_amount=position['token2_amount'],
                lp_tokens=position['lp_tokens']
            )
            logger.info(f"Сохранена позиция для кошелька {position['wallet_address']} в пуле {pool_address}")
    
    logger.info("Инициализация тестовой базы данных завершена!")

if __name__ == "__main__":
    asyncio.run(initialize_test_db()) 