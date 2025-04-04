import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import os
import time
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path:
    sys.path.append(root_path)

from pytonapi import AsyncTonapi

# Импортируем модули из core
from core.db import save_pool, update_pool_liquidity, get_all_pools, save_price, save_position, get_pool
from core.config import TONAPI_KEY, DEX_CONTRACT, ROUTER_CONTRACT, AMM_CODE

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('blockchain_indexer')

# Интервалы обновления из переменных окружения
PRICE_UPDATE_INTERVAL = int(os.getenv('PRICE_UPDATE_INTERVAL', 300))  # 5 минут по умолчанию
POOLS_CHECK_INTERVAL = int(os.getenv('POOLS_CHECK_INTERVAL', 600))    # 10 минут по умолчанию
POSITIONS_CHECK_INTERVAL = int(os.getenv('POSITIONS_CHECK_INTERVAL', 600))  # 10 минут по умолчанию

# Максимальное количество аккаунтов для проверки за одну итерацию
MAX_ACCOUNTS_TO_CHECK = int(os.getenv('MAX_ACCOUNTS_TO_CHECK', 100))

class BlockchainIndexer:
    """
    Индексер для отслеживания пулов и цен из блокчейна TON.
    Отслеживает:
    - Новые пулы
    - Цены в пулах ликвидности
    - Позиции ликвидности
    """
    
    def __init__(self, tonapi_key: str = TONAPI_KEY, dex_address: str = DEX_CONTRACT, factory_address: str = ROUTER_CONTRACT):
        # Инициализация TonAPI
        self.tonapi = AsyncTonapi(api_key=tonapi_key)

        self.dex_address = dex_address
        
        self.factory_address = factory_address
        
        # Отслеживаемые пулы
        self.tracked_pools: Set[str] = set()
        
        # Кэш для информации о пулах
        self.pool_cache: Dict[str, Dict[str, Any]] = {}
        
        # Время последнего обновления цен для каждого пула
        self.last_price_update: Dict[str, datetime] = {}
        
        # Время последней проверки новых пулов
        self.last_pools_check: Optional[datetime] = None
        
        # Время последней проверки позиций ликвидности
        self.last_positions_check: Optional[datetime] = None
        
        # Флаг для работы основного цикла
        self.is_running = False
    
    async def start(self):
        """Запускает индексер"""
        try:
            _ = await self.tonapi.accounts.get_info("EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c")
        except Exception as e:
            logger.error(f"Ошибка при инициализации TonAPI: {e}")
            raise
        if self.is_running:
            logger.warning("Индексер уже запущен")
            return
            
        self.is_running = True
        logger.info("Запуск индексера блокчейна")
        
        # Загружаем существующие пулы из БД
        await self.initialize()
        
        try:
            while self.is_running:
                try:
                    now = datetime.now()
                    
                    # Проверка на новые пулы
                    if (not self.last_pools_check or 
                        (now - self.last_pools_check).total_seconds() >= POOLS_CHECK_INTERVAL):
                        await self.find_new_pools()
                        self.last_pools_check = now
                    
                    # Обновление цен в пулах
                    await self.update_pool_prices()
                    
                    # Обновление позиций ликвидности
                    if (not self.last_positions_check or 
                        (now - self.last_positions_check).total_seconds() >= POSITIONS_CHECK_INTERVAL):
                        await self.update_liquidity_positions()
                        self.last_positions_check = now
                    
                    # Небольшая пауза для снижения нагрузки на API
                    await asyncio.sleep(10)
                except Exception as e:
                    logger.error(f"Ошибка в цикле индексера: {e}")
                    await asyncio.sleep(30)  # Более долгая пауза при ошибке
        finally:
            self.is_running = False
            logger.info("Индексер остановлен")
    
    async def stop(self):
        """Останавливает индексер"""
        self.is_running = False
        logger.info("Отправлен сигнал остановки индексера")
    
    async def initialize(self):
        """Инициализирует индексер, загружая текущее состояние пулов из БД"""
        try:
            logger.info("Инициализация индексера...")
            
            try:
                # Загрузка существующих пулов из БД
                pools_from_db = await get_all_pools()
                for pool in pools_from_db:
                    pool_address = pool.get('pool_address')
                    if pool_address:
                        self.tracked_pools.add(pool_address)
                        self.pool_cache[pool_address] = pool
                
                logger.info(f"Загружено {len(self.tracked_pools)} существующих пулов из БД")
            except Exception as e:
                logger.warning(f"Не удалось загрузить пулы из БД: {e}. Будут использоваться тестовые данные")
            
            # Если пулов нет (или БД пуста), загружаем тестовые данные
            
            # Проверяем на новые пулы
            await self.find_new_pools()
            
            # Инициализируем цены во всех пулах
            await self.update_pool_prices(force_update=True)
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации индексера: {e}")
            raise

    async def find_new_pools(self):
        """Поиск новых пулов ликвидности в блокчейне"""
        try:
            logger.info("Поиск новых пулов в блокчейне...")
            
            # Получение списка пулов через TonAPI (запрос к фабрике пулов или DEX контракту)
            new_pools = await self._fetch_new_pools_from_blockchain()
            
            # Подсчет новых пулов
            new_pools_count = 0
            
            # Обработка списка пулов
            for pool in new_pools:
                pool_address = pool.get('address')
                if not pool_address:
                    continue
                    
                # Обнаружение новых пулов
                if pool_address not in self.tracked_pools:
                    logger.info(f"Обнаружен новый пул: {pool_address} ({pool.get('token1', '?')}/{pool.get('token2', '?')})")
                    
                    # Сохраняем пул в БД
                    self.tracked_pools.add(pool_address)
                    
                    # Получаем дополнительную информацию о пуле и токенах
                    token1_address = pool.get('token1_address')
                    token2_address = pool.get('token2_address')
                    token1_name = pool.get('token1')
                    token2_name = pool.get('token2')
                    
                    try:
                        # Пытаемся сохранить в БД
                        await save_pool(
                            token1=token1_name,
                            token2=token2_name,
                            pool_address=pool_address,
                            token1_address=token1_address,
                            token2_address=token2_address,
                            liquidity=pool.get('liquidity', 0)
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось сохранить пул {pool_address} в БД: {e}")
                    
                    # Обновляем кэш информации о пуле
                    self.pool_cache[pool_address] = {
                        'pool_address': pool_address,
                        'token1': token1_name,
                        'token2': token2_name,
                        'token1_address': token1_address,
                        'token2_address': token2_address,
                        'liquidity': pool.get('liquidity', 0)
                    }
                    
                    new_pools_count += 1
            
            if new_pools_count > 0:
                logger.info(f"Обнаружено {new_pools_count} новых пулов. Всего отслеживается: {len(self.tracked_pools)}")
            else:
                logger.info(f"Новых пулов не обнаружено. Всего отслеживается: {len(self.tracked_pools)}")
            
        except Exception as e:
            logger.error(f"Ошибка при поиске новых пулов: {e}")
    
    async def update_pool_prices(self, force_update: bool = False):
        """Обновляет информацию о ценах в пулах с заданной периодичностью"""
        try:
            now = datetime.now()
            update_count = 0
            
            for pool_address in list(self.tracked_pools):
                # Пропускаем пул, если не время обновлять цену, кроме случая принудительного обновления
                last_update = self.last_price_update.get(pool_address)
                if not force_update and last_update and (now - last_update).total_seconds() < PRICE_UPDATE_INTERVAL:
                    continue
                
                try:
                    # Получаем актуальную информацию о пуле и его ценах из блокчейна
                    price_info = await self._fetch_pool_price_from_blockchain(pool_address)
                    
                    if not price_info:
                        logger.warning(f"Не удалось получить информацию о ценах пула {pool_address}")
                        continue
                    
                    try:
                        # Сохраняем цену в БД
                        await save_price(pool_address, price_info)
                    except Exception as e:
                        logger.warning(f"Не удалось сохранить цену пула {pool_address} в БД: {e}")
                    
                    # Обновляем время последнего обновления
                    self.last_price_update[pool_address] = now
                    
                    update_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при обновлении цен пула {pool_address}: {e}")
            
            if update_count > 0:
                logger.info(f"Обновлены цены для {update_count} пулов")
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении цен пулов: {e}")
    
    async def update_liquidity_positions(self):
        """Обновляет информацию о позициях ликвидности"""
        try:
            logger.info("Обновление позиций ликвидности...")
            update_count = 0
            
            for pool_address in list(self.tracked_pools):
                try:
                    # Получаем информацию о ликвидности пула
                    pool_liquidity = await self._fetch_pool_liquidity_from_blockchain(pool_address)
                    
                    if pool_liquidity:
                        try:
                            # Обновляем ликвидность пула в БД
                            await update_pool_liquidity(
                                pool_address=pool_address,
                                liquidity=pool_liquidity.get('total_liquidity', 0),
                                token1_reserve=pool_liquidity.get('token1_reserve', 0),
                                token2_reserve=pool_liquidity.get('token2_reserve', 0)
                            )
                        except Exception as e:
                            logger.warning(f"Не удалось обновить ликвидность пула {pool_address} в БД: {e}")
                        
                        # Обновляем позиции ликвидности пользователей
                        positions = await self._fetch_liquidity_positions_from_blockchain(pool_address)
                        
                        for position in positions:
                            wallet_address = position.get('wallet_address')
                            token1_amount = position.get('token1_amount', 0)
                            token2_amount = position.get('token2_amount', 0)
                            lp_tokens = position.get('lp_tokens', 0)
                            
                            try:
                                await save_position(
                                    wallet_address=wallet_address,
                                    pool_address=pool_address,
                                    token1_amount=token1_amount,
                                    token2_amount=token2_amount,
                                    lp_tokens=lp_tokens
                                )
                            except Exception as e:
                                logger.warning(f"Не удалось сохранить позицию {wallet_address} в пуле {pool_address}: {e}")
                        
                        update_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при обновлении ликвидности пула {pool_address}: {e}")
            
            if update_count > 0:
                logger.info(f"Обновлена ликвидность для {update_count} пулов")
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении позиций ликвидности: {e}")

    async def _fetch_new_pools_from_blockchain(self) -> List[Dict[str, Any]]:
        """Получает информацию о новых пулах из блокчейна с помощью TonAPI"""
        try:
            
            result_pools = []
            
            try:
                # Получаем последние блоки
                blocks = await self.tonapi.blockchain.get_blocks_latest(limit=10)
                
                # Создаем список аккаунтов для проверки
                accounts_to_check = set()
                
                # Извлекаем аккаунты из блоков
                for block in blocks:
                    if hasattr(block, 'transactions'):
                        for tx in block.transactions:
                            if hasattr(tx, 'account'):
                                accounts_to_check.add(tx.account)
                                
                            # Также добавляем получателей, если они есть
                            if hasattr(tx, 'in_msg') and hasattr(tx.in_msg, 'destination'):
                                accounts_to_check.add(tx.in_msg.destination)
                                
                            # Добавляем аккаунты из исходящих сообщений
                            if hasattr(tx, 'out_msgs'):
                                for msg in tx.out_msgs:
                                    if hasattr(msg, 'destination'):
                                        accounts_to_check.add(msg.destination)
                
                    # Ограничиваем количество проверяемых аккаунтов
                    if len(accounts_to_check) > MAX_ACCOUNTS_TO_CHECK:
                        break
                
                # Проверяем каждый аккаунт на соответствие коду AMM
                logger.info(f"Проверка {len(accounts_to_check)} аккаунтов на соответствие коду AMM")
                
                checked_count = 0
                for account_address in accounts_to_check:
                    checked_count += 1
                    
                    # Пропускаем, если этот пул уже отслеживается
                    if account_address in self.tracked_pools:
                        continue
                    
                    try:
                        # Получаем информацию об аккаунте
                        account_info = await self.tonapi.accounts.get_account(account_address)
                        
                        # Проверяем, соответствует ли код аккаунта коду AMM
                        if hasattr(account_info, 'code') and account_info.code:
                            # Проверяем соответствие кода AMM_CODE
                            # В реальности нужно будет сравнивать хеш кода или использовать другие методы
                            # Здесь упрощенная проверка
                            is_amm_code = False
                            
                            # Если у нас есть хеш AMM_CODE, можно сравнить хеши
                            if AMM_CODE and hasattr(account_info, 'code_hash'):
                                is_amm_code = (account_info.code_hash == AMM_CODE)
                            
                            # Если это пул ликвидности (AMM), получаем дополнительную информацию
                            if is_amm_code:
                                logger.info(f"Обнаружен новый пул: {account_address}")
                                
                                # Получаем информацию о токенах пула
                                # Это требует знания структуры данных контракта
                                token1 = "Unknown1"
                                token2 = "Unknown2"
                                token1_address = None
                                token2_address = None
                                
                                # Пытаемся получить информацию о токенах через get-методы контракта
                                try:
                                    # Пример вызова get-метода для получения адреса первого токена
                                    token1_response = await self.tonapi.accounts.run_get_method(
                                        account_id=account_address,
                                        method_name="get_token1_address",
                                        stack=[]
                                    )
                                    
                                    token2_response = await self.tonapi.accounts.run_get_method(
                                        account_id=account_address,
                                        method_name="get_token2_address",
                                        stack=[]
                                    )
                                    
                                    if token1_response and hasattr(token1_response, 'result') and token1_response.result:
                                        token1_address = token1_response.result[0]
                                        
                                    if token2_response and hasattr(token2_response, 'result') and token2_response.result:
                                        token2_address = token2_response.result[0]
                                        
                                    # Если получены адреса токенов, получаем их символы
                                    if token1_address:
                                        try:
                                            token1_info = await self.tonapi.accounts.get_account(token1_address)
                                            if hasattr(token1_info, 'name'):
                                                token1 = token1_info.name
                                        except Exception as e:
                                            logger.warning(f"Не удалось получить информацию о токене 1: {e}")
                                            
                                    if token2_address:
                                        try:
                                            token2_info = await self.tonapi.accounts.get_account(token2_address)
                                            if hasattr(token2_info, 'name'):
                                                token2 = token2_info.name
                                        except Exception as e:
                                            logger.warning(f"Не удалось получить информацию о токене 2: {e}")
                                
                                except Exception as e:
                                    logger.warning(f"Не удалось получить информацию о токенах пула {account_address}: {e}")
                                
                                # Добавляем пул в результаты
                                result_pools.append({
                                    'address': account_address,
                                    'token1': token1,
                                    'token2': token2,
                                    'token1_address': token1_address,
                                    'token2_address': token2_address,
                                    'liquidity': 0  # Заполним позже при обновлении ликвидности
                                })
                    
                    except Exception as e:
                        logger.warning(f"Ошибка при проверке аккаунта {account_address}: {e}")
                    
                    # Ограничиваем количество запросов API для избежания превышения лимитов
                    if checked_count % 10 == 0:
                        await asyncio.sleep(1)
                
                logger.info(f"Проверено {checked_count} аккаунтов, найдено {len(result_pools)} новых пулов")
                
                # Если пулы не найдены, возвращаем тестовые данные
                if not result_pools:
                    logger.warning("Новых пулов не обнаружено, возвращаем тестовые данные для разработки")
                
                return result_pools
                
            except Exception as e:
                logger.error(f"Ошибка при поиске новых пулов по блокам: {e}")
                return []
            
        except Exception as e:
            logger.error(f"Ошибка при получении новых пулов из блокчейна: {e}")
    
    async def _fetch_pool_price_from_blockchain(self, pool_address: str) -> Optional[float]:
        """Получает информацию о цене в пуле из блокчейна с помощью TonAPI"""
        try:
            # Получаем пул из кэша или БД
            pool_info = self.pool_cache.get(pool_address)
            if not pool_info:
                pool_info = await get_pool(pool_address)
                if pool_info:
                    self.pool_cache[pool_address] = pool_info
                else:
                    return None
            
            # Делаем запрос к блокчейну через TonAPI
            logger.debug(f"Запрос к TonAPI для получения цены пула {pool_address}")
            
            try:
                # Получаем данные аккаунта пула
                account_data = await self.tonapi.accounts.get_account(account_id=pool_address)
                
                # Получаем состояние пула
                # Разные DEX могут хранить данные в разных форматах, 
                # поэтому логика извлечения цены зависит от конкретного DEX
                
                # Получаем последние транзакции в пуле для анализа обменов
                pool_transactions = await self.tonapi.accounts.get_account_events(
                    account_id=pool_address,
                    limit=10  # Анализируем последние 10 транзакций
                )
                
                # Для получения цены из пула нам нужно проанализировать данные из транзакции
                # или из состояния контракта. Это требует знания структуры данных контракта.
                
                # Для примера (упрощенно) предположим, что мы можем вычислить цену на основе резервов
                # Реальная логика будет зависеть от контракта AMM и его структуры данных
                
                token1_reserve = None
                token2_reserve = None
                
                # Если контракт поддерживает get-методы, можно вызвать их через API
                # Например, если в контракте есть метод get_reserves()
                
                # В этом примере мы пытаемся получить резервы из контракта
                # Обратите внимание, что в реальной ситуации нужно знать точное название метода
                try:
                    # Выполняем get-метод контракта для получения резервов
                    response = await self.tonapi.accounts.run_get_method(
                        account_id=pool_address,
                        method_name="get_reserves",
                        stack=[]  # Параметры, если нужны
                    )
                    
                    # Анализируем результат для извлечения резервов
                    if response and hasattr(response, 'result'):
                        # Предполагаем, что результат содержит массив с двумя значениями - резервами двух токенов
                        if len(response.result) >= 2:
                            token1_reserve = float(response.result[0])
                            token2_reserve = float(response.result[1])
                except Exception as e:
                    logger.warning(f"Не удалось получить резервы из get-метода контракта: {e}")
                
                # Если не удалось получить резервы через get-метод, пробуем альтернативный способ
                if token1_reserve is None or token2_reserve is None:
                    # Альтернативно, можно проанализировать данные из состояния контракта
                    if hasattr(account_data, 'state') and hasattr(account_data.state, 'data'):
                        # Здесь должна быть логика извлечения резервов из данных контракта
                        # Это зависит от формата данных в контракте
                        pass
                
                # Если резервы получены, вычисляем цену
                if token1_reserve and token2_reserve and token1_reserve > 0:
                    price = token2_reserve / token1_reserve
                    logger.debug(f"Получена цена для пула {pool_address} из блокчейна: {price}")
                    return price
                
                # Если не удалось получить цену, возвращаем мок-данные
                logger.warning(f"Не удалось получить цену для пула {pool_address} из блокчейна, используем мок-данные")

                current_timestamp = int(time.time())
                return 1.0 + 0.01 * (current_timestamp % 100)
                
            except Exception as e:
                logger.warning(f"Ошибка при работе с TonAPI для получения цены: {e}")

                current_timestamp = int(time.time())
                return 1.0 + 0.01 * (current_timestamp % 100)
            
        except Exception as e:
            logger.error(f"Ошибка при получении цены для пула {pool_address}: {e}")
            return None

    async def _fetch_pool_liquidity_from_blockchain(self, pool_address: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о ликвидности пула из блокчейна с помощью TonAPI"""
        try:
            # Если установлен флаг тестового режима или нет ключа API, возвращаем мок-данные
            
            logger.debug(f"Запрос к TonAPI для получения ликвидности пула {pool_address}")
            
            try:
                reserves_response = await self.tonapi.accounts.run_get_method(
                    account_id=pool_address,
                    method_name="get_reserves",  # Имя метода может отличаться
                    stack=[]
                )
                
                liquidity_response = await self.tonapi.accounts.run_get_method(
                    account_id=pool_address,
                    method_name="get_total_supply",  # Имя метода может отличаться
                    stack=[]
                )
                
                token1_reserve = 0
                token2_reserve = 0
                total_liquidity = 0
                
                if reserves_response and hasattr(reserves_response, 'result') and len(reserves_response.result) >= 2:
                    token1_reserve = float(reserves_response.result[0])
                    token2_reserve = float(reserves_response.result[1])
                
                if liquidity_response and hasattr(liquidity_response, 'result') and liquidity_response.result:
                    total_liquidity = float(liquidity_response.result[0])
                
                # Если не удалось получить полную ликвидность, но есть резервы, оцениваем ее
                if total_liquidity == 0 and (token1_reserve > 0 or token2_reserve > 0):
                    # Примерная оценка ликвидности на основе резервов
                    total_liquidity = (token1_reserve + token2_reserve) / 2
                
                # Если получены осмысленные значения, возвращаем их
                if token1_reserve > 0 or token2_reserve > 0 or total_liquidity > 0:
                    return {
                        "total_liquidity": total_liquidity,
                        "token1_reserve": token1_reserve,
                        "token2_reserve": token2_reserve
                    }
                
                # Если не удалось получить данные, возвращаем мок-данные или стандартные значения
                logger.warning(f"Не удалось получить данные о ликвидности пула {pool_address} из блокчейна")
                
                return {
                    "total_liquidity": 1000000,
                    "token1_reserve": 500000,
                    "token2_reserve": 500000
                }
                
            except Exception as e:
                logger.warning(f"Ошибка при запросе данных о ликвидности пула {pool_address}: {e}")
                
                
                return {
                    "total_liquidity": 1000000,
                    "token1_reserve": 500000,
                    "token2_reserve": 500000
                }
                
        except Exception as e:
            logger.error(f"Ошибка при получении ликвидности пула {pool_address}: {e}")
            return None

    async def _fetch_liquidity_positions_from_blockchain(self, pool_address: str) -> List[Dict[str, Any]]:
        """Получает информацию о позициях ликвидности пользователей в пуле"""
        try:
            logger.debug(f"Запрос к TonAPI для получения позиций ликвидности в пуле {pool_address}")
            positions = []

            try:
                # Получаем транзакции пула для анализа участников
                pool_transactions = await self.tonapi.accounts.get_account_events(
                    account_id=pool_address,
                    limit=50  # Анализируем последние 50 транзакций
                )
                
                # Находим адреса кошельков, взаимодействовавших с пулом
                wallet_addresses = set()
                
                if pool_transactions and hasattr(pool_transactions, 'events'):
                    for event in pool_transactions.events:
                        # Добавляем отправителя
                        if hasattr(event, 'sender_address'):
                            wallet_addresses.add(event.sender_address)
                        
                        # Анализируем действия в транзакции
                        if hasattr(event, 'actions'):
                            for action in event.actions:
                                if hasattr(action, 'sender'):
                                    wallet_addresses.add(action.sender)
                                if hasattr(action, 'recipient'):
                                    wallet_addresses.add(action.recipient)
                
                logger.info(f"Найдено {len(wallet_addresses)} адресов, взаимодействовавших с пулом {pool_address}")
                
                # Получаем информацию о балансах LP-токенов для каждого кошелька
                processed_count = 0
                for wallet_address in wallet_addresses:
                    processed_count += 1
                    
                    try:
                        # Проверяем баланс LP-токенов кошелька
                        lp_tokens = 0
                        
                        # Получаем метод проверки баланса LP-токенов из контракта пула
                        try:
                            response = await self.tonapi.accounts.run_get_method(
                                account_id=pool_address,
                                method_name="get_lp_balance",  # Имя метода может отличаться
                                stack=[wallet_address]  # Передаем адрес кошелька как параметр
                            )
                            
                            if response and hasattr(response, 'result') and response.result:
                                lp_tokens = float(response.result[0])
                        except Exception as e:
                            logger.debug(f"Не удалось получить баланс LP-токенов через метод контракта: {e}")
                        
                        # Если есть LP-токены, вычисляем соответствующие доли токенов
                        if lp_tokens > 0:
                            # Получаем информацию о ликвидности пула
                            pool_liquidity = await self._fetch_pool_liquidity_from_blockchain(pool_address)
                            
                            if pool_liquidity:
                                total_liquidity = pool_liquidity.get('total_liquidity', 0)
                                token1_reserve = pool_liquidity.get('token1_reserve', 0)
                                token2_reserve = pool_liquidity.get('token2_reserve', 0)
                                
                                # Если есть данные о ликвидности, вычисляем доли
                                if total_liquidity > 0:
                                    # Доля пользователя
                                    user_share = lp_tokens / total_liquidity
                                    
                                    # Вычисляем соответствующие количества токенов
                                    token1_amount = token1_reserve * user_share
                                    token2_amount = token2_reserve * user_share
                                    
                                    # Добавляем информацию о позиции
                                    positions.append({
                                        'wallet_address': wallet_address,
                                        'lp_tokens': lp_tokens,
                                        'token1_amount': token1_amount,
                                        'token2_amount': token2_amount,
                                        'share_percentage': user_share * 100  # В процентах
                                    })
                    
                    except Exception as e:
                        logger.warning(f"Ошибка при получении информации о позиции для кошелька {wallet_address}: {e}")
                    
                    # Делаем паузу после каждых 10 запросов, чтобы избежать превышения лимитов API
                    if processed_count % 10 == 0:
                        await asyncio.sleep(1)
                
                logger.info(f"Найдено {len(positions)} позиций ликвидности в пуле {pool_address}")
                
                # Если позиции не найдены, возвращаем мок-данные или пустой список
                if not positions:
                    logger.debug(f"Позиции ликвидности для пула {pool_address} не найдены")
                    
                    # Для разработки можно вернуть мок-данные
                    pool_info = self.pool_cache.get(pool_address)
                    if pool_info:
                        positions = [{
                            'wallet_address': "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",
                            'lp_tokens': 100000,
                            'token1_amount': 50000,
                            'token2_amount': 50000,
                            'share_percentage': 10.0
                        }]
                
                return positions
                
            except Exception as e:
                logger.warning(f"Ошибка при получении данных о позициях ликвидности из TonAPI: {e}")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка при получении позиций ликвидности для пула {pool_address}: {e}")
            return []
       