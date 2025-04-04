import asyncio
import logging
from indexer.blockchain_indexer import BlockchainIndexer
import os
from dotenv import load_dotenv
import sys
import signal

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_indexer')

async def test_indexer_initialization():
    """Тестирует инициализацию индексера"""
    logger.info("Тест инициализации индексера...")
    
    indexer = BlockchainIndexer(
        tonapi_key=os.getenv('TONAPI_KEY', ''),
        dex_address=os.getenv('DEX_CONTRACT_ADDRESS', ''),
        factory_address=os.getenv('FACTORY_CONTRACT_ADDRESS', '')
    )
    
    await indexer.initialize()
    
    logger.info(f"Индексер инициализирован. Отслеживаемых пулов: {len(indexer.tracked_pools)}")
    return indexer

async def test_find_new_pools(indexer):
    """Тестирует поиск новых пулов"""
    logger.info("Тест поиска новых пулов...")
    
    # Сохраняем количество пулов до поиска
    pools_before = len(indexer.tracked_pools)
    
    # Запускаем поиск новых пулов
    await indexer.find_new_pools()
    
    # Проверяем результат
    pools_after = len(indexer.tracked_pools)
    logger.info(f"Пулов до поиска: {pools_before}, после поиска: {pools_after}")
    logger.info(f"Найдено новых пулов: {pools_after - pools_before}")
    
async def test_update_prices(indexer):
    """Тестирует обновление цен в пулах"""
    logger.info("Тест обновления цен в пулах...")
    
    # Обновляем цены
    await indexer.update_pool_prices(force_update=True)
    
    # Выводим информацию о последних обновлениях
    logger.info(f"Обновлены цены для {len(indexer.last_price_update)} пулов")
    
async def test_update_liquidity(indexer):
    """Тестирует обновление позиций ликвидности"""
    logger.info("Тест обновления позиций ликвидности...")
    
    # Обновляем позиции ликвидности
    await indexer.update_liquidity_positions()
    
    logger.info("Обновление позиций ликвидности выполнено")

async def main():
    """Основная функция тестирования"""
    try:
        logger.info("Запуск тестов индексера...")
        
        # Инициализация
        indexer = await test_indexer_initialization()
        
        # Тест поиска новых пулов
        await test_find_new_pools(indexer)
        
        # Тест обновления цен
        await test_update_prices(indexer)
        
        # Тест обновления ликвидности
        await test_update_liquidity(indexer)
        
        logger.info("Все тесты выполнены успешно")
        
    except Exception as e:
        logger.error(f"Ошибка в тестах: {e}")
        raise

if __name__ == "__main__":
    try:
        # Настраиваем корректное завершение
        loop = asyncio.get_event_loop()
        
        # Запускаем тесты
        loop.run_until_complete(main())
        
    except KeyboardInterrupt:
        logger.info("Тесты прерваны пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1) 