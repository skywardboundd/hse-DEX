import asyncio
import logging
import signal
import sys
import os
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path:
    sys.path.append(root_path)

from dotenv import load_dotenv

from blockchain_indexer import BlockchainIndexer

# Загрузка переменных окружения из файла .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('indexer_runner')

async def main():
    logger.info("Запуск системы индексирования блокчейна")
    
    # Инициализация и запуск индексера
    indexer = BlockchainIndexer(
        tonapi_key=os.getenv('TONAPI_KEY', ''),
        dex_address=os.getenv('DEX_CONTRACT_ADDRESS', ''),
        factory_address=os.getenv('FACTORY_CONTRACT_ADDRESS', '')
    )
    
    # Настройка корректного завершения работы
    loop = asyncio.get_running_loop()
    
    # Обработчик сигналов для graceful shutdown
    def signal_handler():
        logger.info("Получен сигнал остановки. Завершаем работу...")
        asyncio.create_task(indexer.stop())
    
    # Регистрируем обработчики сигналов
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Запускаем индексер
        await indexer.start()
    except Exception as e:
        logger.error(f"Ошибка при запуске индексера: {e}")
    finally:
        logger.info("Завершение работы системы индексирования")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Работа индексера прервана пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        sys.exit(1) 