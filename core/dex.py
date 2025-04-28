from pytonapi import AsyncTonapi
from pytoniq_core import Address, StateInit
import time
import json
import os
from typing import Optional
from pytoniq import Cell, begin_cell, Contract, LiteBalancer
from .utils import *
# Импортируем модули из нашего пакета
from .config import DEFAULT_TOKENS, AMM_CODE, AMM_SYSTEM
from .db import (
    get_positions_by_wallet,
    get_all_pools, get_pool, get_pool_by_tokens, get_pool_by_tokens_and_type, 
    save_pool, save_position, remove_position, get_connection
)
from .utils import createJettonVaultSwapRequest
from psycopg2.extras import RealDictCursor


class DexManager:
    def __init__(self):
        self.vault_code = Cell.one_from_boc(AMM_SYSTEM)
        self.amm_code = Cell.one_from_boc(AMM_CODE)
        self.payloadOnSuccess = begin_cell().store_snake_string("Success").end_cell()
        self.payloadOnError = begin_cell().store_snake_string("Error").end_cell()
        
    async def start_up(self):
        await self.provider.start_up()
    
    def get_vault_address(self, jetton_master: str):
        data = begin_cell().store_uint(0, 1).store_address(jetton_master).store_bit(False).store_uint(0, 2).end_cell()
        stateInit = StateInit(code=Cell.one_from_boc(self.vault_code), data=data)
        return Address((0, stateInit.serialize().hash))

    def get_amm_address(self, token1: str, token2: str):
        token1, token2 = sorted([token1, token2])
        data = begin_cell().store_address(token1).store_address(token2).end_cell()
        stateInit = StateInit(code=Cell.one_from_boc(self.amm_code), data=data)
        return Address((0, stateInit.serialize().hash))

    
    async def get_price(self, token_in: str, token_out: str) -> float:
        """Получение цены токена через TonAPI"""
        try:
            vault = self.get_vault_address(token_in)
            amm_pool_address = self.get_amm_address(token_in, token_out)
            expected_price = await self.tonapi.blockchain.execute_get_method(amm_pool_address, 'get_expected_price', [vault])
            return expected_price

        except Exception as e:
            raise Exception(f"Ошибка получения цены: {e}")


    def create_swap_body(destinationVault: str, minAmountOut: int, timeout: int):
        return begin_cell().store_address(destinationVault).store_address(minAmountOut).store_uint(timeout, 32).end_cell()
    
    async def create_swap_transaction(self, token1: str, token2: str, amount: float, wallet_address: str, 
                                     token1_address: str = None, token2_address: str = None) -> dict:
        """
        Создание транзакции для свопа токенов
        
        Args:
            token1: Адрес или символ входящего токена
            token2: Адрес или символ исходящего токена
            amount: Количество токена для свопа
            wallet_address: Адрес кошелька пользователя
            token1_address: Прямой адрес первого токена (используется, если токен не найден по символу)
            token2_address: Прямой адрес второго токена (используется, если токен не найден по символу)
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        # Определяем адрес хранилища токена 1
        vault1_address = None
        if token1_address:
            vault1_address = self.get_vault_address(token1_address)
        else:
            try:
                vault1_address = self.get_vault_address(token1)
            except:
                # Если не удалось получить адрес по символу, используем DEFAULT_TOKENS
                if token1.upper() in DEFAULT_TOKENS:
                    vault1_address = self.get_vault_address(DEFAULT_TOKENS[token1.upper()])
                else:
                    raise Exception(f"Не удалось найти токен {token1}")
        
        # Определяем адрес хранилища токена 2
        vault2_address = None
        if token2_address:
            vault2_address = self.get_vault_address(token2_address)
        else:
            try:
                vault2_address = self.get_vault_address(token2)
            except:
                # Если не удалось получить адрес по символу, используем DEFAULT_TOKENS
                if token2.upper() in DEFAULT_TOKENS:
                    vault2_address = self.get_vault_address(DEFAULT_TOKENS[token2.upper()])
                else:
                    raise Exception(f"Не удалось найти токен {token2}")
        
        msg = {"to": vault1_address}
        msg["body"] = createJettonVaultSwapRequest(vault2_address, amount, 0, self.payloadOnSuccess, self.payloadOnError)
        msg['value'] = int(0.55 * 1e9)
        msg["valid_until"] = int(time.time()) + 60 * 10
        return {"valid_until": int(time.time()) + 60 * 10, "messages": [msg] }
    
    async def get_liquidity(self, token_pair: str) -> dict:

        try:
            token_in, token_out = token_pair.split('/')
            pool_info = await self.tonapi.get_pool_info(
                token_in=DEFAULT_TOKENS[token_in],
                token_out=DEFAULT_TOKENS[token_out]
            )
            
            return {
                "total": pool_info['total_liquidity'],
                "token1": {
                    "amount": pool_info['reserve_in'],
                    "symbol": token_in
                },
                "token2": {
                    "amount": pool_info['reserve_out'],
                    "symbol": token_out
                }
            }
        except Exception as e:
            raise Exception(f"Error getting liquidity: {e}")

    async def get_token_balance(self, wallet_address: str, token_address: str) -> int:
        """Получение баланса токена через TonAPI"""
        try:
            # Получаем балансы всех токенов
            balances = await self.tonapi.get_token_balances(wallet_address)
            
            # Ищем нужный токен
            for balance in balances:
                if balance['token_address'] == token_address:
                    return int(balance['balance'])
            
            return 0
        except Exception as e:
            raise Exception(f"Error getting token balance: {e}")

    async def get_ton_balance(self, wallet_address: str) -> int:
        """Получение баланса TON через TonAPI"""
        try:
            account = await self.tonapi.get_account(wallet_address)
            return int(account['balance'])
        except Exception as e:
            raise Exception(f"Error getting TON balance: {e}")


    async def get_pool_stats(self, token_pair: str) -> dict:
        """Получение статистики пула через TonAPI"""
        try:
            token_in, token_out = token_pair.split('/')
            stats = await self.tonapi.get_pool_stats(
                token_in=DEFAULT_TOKENS[token_in],
                token_out=DEFAULT_TOKENS[token_out]
            )
            return stats
        except Exception as e:
            raise Exception(f"Error getting pool stats: {e}")


    async def add_liquidity(self, wallet_address: str, token1: str, token2: str, 
                           token1_amount: float, token2_amount: float) -> dict:
        """
        Добавление ликвидности в пул
        
        Args:
            wallet_address: Адрес кошелька пользователя
            token1: Адрес или символ первого токена
            token2: Адрес или символ второго токена
            token1_amount: Количество первого токена
            token2_amount: Количество второго токена
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о токенах
            token1_info = await self.get_token_info(token1)
            token2_info = await self.get_token_info(token2)
            
            # Создаем транзакцию для добавления ликвидности
            transaction = await self.create_add_liquidity_transaction(
                token1, token2, token1_amount, token2_amount, wallet_address
            )
            
            # Находим соответствующий пул в БД
            pool_address = str(self.get_amm_address(token1, token2))
            pool_data = await get_pool(pool_address)
            
            if not pool_data:
                # Если пул не найден, значит он еще не проиндексирован
                raise Exception(f"Пул {token1}/{token2} не найден в базе данных. Дождитесь индексации.")
            
            # Сохраняем позицию пользователя в БД
            lp_tokens = (token1_amount * token2_amount) ** 0.5  # Простой расчет для примера
            
            await save_position(
                wallet_address=wallet_address,
                pool_address=pool_address,
                token1_amount=token1_amount,
                token2_amount=token2_amount,
                lp_tokens=lp_tokens
            )
            
            return transaction
        except Exception as e:
            raise Exception(f"Ошибка добавления ликвидности: {e}")
            
    async def create_add_liquidity_transaction(self, token1: str, token2: str, 
                                              token1_amount: float, token2_amount: float, 
                                              wallet_address: str, pool_type: str = None) -> dict:
        """
        Создание транзакции для добавления ликвидности
        
        Args:
            token1: Адрес или символ первого токена
            token2: Адрес или символ второго токена
            token1_amount: Количество первого токена
            token2_amount: Количество второго токена
            wallet_address: Адрес кошелька пользователя
            pool_type: Тип пула
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о токенах
            token1_info = await self.get_token_info(token1)
            token2_info = await self.get_token_info(token2)
            
            # Учитываем тип пула
            pool_type_param = {"pool_type": pool_type} if pool_type else {}
            
            # Заглушка для тестирования
            # Возвращаем тестовую транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            # Добавляем информацию о типе пула в транзакцию, если указан
            type_info = f" (тип: {pool_type})" if pool_type else ""
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': '1000000000',  # 1 TON
                        'payload': f'Добавление ликвидности {token1_info["symbol"]}/{token2_info["symbol"]}{type_info}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания транзакции для добавления ликвидности: {e}")

    
    async def remove_liquidity(self, position_id: int, wallet_address: str) -> dict:
        """
        Удаление ликвидности из пула
        
        Args:
            position_id: ID позиции в БД
            wallet_address: Адрес кошелька пользователя
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем позиции из БД
            positions = await get_positions_by_wallet(wallet_address)
            position = next((p for p in positions if p['id'] == position_id), None)
            
            if not position:
                raise Exception(f"Позиция с ID {position_id} не найдена")
                
            # Создаем транзакцию для удаления ликвидности
            transaction = await self.create_remove_liquidity_transaction(
                position_id, wallet_address
            )
            
            # Удаляем позицию из БД
            await remove_position(wallet_address, position['pool_address'])
            
            return transaction
        except Exception as e:
            raise Exception(f"Ошибка удаления ликвидности: {e}")
            
    async def create_remove_liquidity_transaction(self, position_id: int, wallet_address: str,
                                                pool_type: str = None) -> dict:
        """
        Создание транзакции для удаления ликвидности
        
        Args:
            position_id: ID позиции ликвидности
            wallet_address: Адрес кошелька пользователя
            pool_type: Тип пула
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о позиции
            position = await self.get_liquidity_position(position_id, wallet_address)
            if not position:
                raise Exception(f"Позиция с ID {position_id} не найдена")
            
            # Учитываем тип пула
            pool_type_param = {"pool_type": pool_type} if pool_type else {}
            
            # Заглушка для тестирования
            # Возвращаем тестовую транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            # Добавляем информацию о типе пула в транзакцию, если указан
            type_info = f" (тип: {pool_type})" if pool_type else ""
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': '1000000000',  # 1 TON
                        'payload': f'Удаление ликвидности из позиции {position_id}{type_info}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания транзакции для удаления ликвидности: {e}")

    
    async def get_user_liquidity_positions(self, wallet_address: str) -> list:
        """Получение списка позиций ликвидности пользователя из БД"""
        try:
            # Получаем позиции из БД
            positions = await get_positions_by_wallet(wallet_address)
            return positions
        except Exception as e:
            print(f"Ошибка при получении позиций ликвидности пользователя: {e}")
            return []
            
    async def get_all_pools(self) -> list:
        """
        Получение списка всех доступных пулов ликвидности из БД
        
        Returns:
            list: Список пулов ликвидности
        """
        try:
            # Получаем данные о пулах из БД
            pools = await get_all_pools()
            return pools
        except Exception as e:
            print(f"Ошибка получения списка пулов из БД: {e}")
            return []
            
    async def get_pool_info(self, token_pair: str, pool_type: str = None) -> dict:
        """
        Получение информации о пуле из БД
        
        Args:
            token_pair: Пара токенов в формате "token1/token2"
            pool_type: Тип пула (например, "stable", "volatile", и т.д.)
        
        Returns:
            dict: Информация о пуле
        """
        try:
            token1, token2 = token_pair.split('/')
            
            # Получаем информацию о пуле из БД
            pool_data = await get_pool_by_tokens(token1, token2)
            
            if not pool_data:
                # Если пул не найден в БД, возвращаем ошибку
                raise Exception(f"Пул {token1}/{token2} не найден в базе данных")
            
            return pool_data
        except Exception as e:
            raise Exception(f"Ошибка получения информации о пуле из БД: {e}")

    async def create_pool(self, token1: str, token2: str, initial_liquidity1: float, 
                         initial_liquidity2: float, wallet_address: str, pool_type: str = None) -> dict:
        """
        Создание нового пула ликвидности
        
        Args:
            token1: Адрес или символ первого токена
            token2: Адрес или символ второго токена
            initial_liquidity1: Начальная ликвидность первого токена
            initial_liquidity2: Начальная ликвидность второго токена
            wallet_address: Адрес кошелька пользователя
            pool_type: Тип пула
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о токенах
            token1_info = await self.get_token_info(token1)
            token2_info = await self.get_token_info(token2)
            
            # Учитываем тип пула
            pool_type_param = {"pool_type": pool_type} if pool_type else {}
            
            # Заглушка для тестирования
            # Возвращаем тестовую транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            # Добавляем информацию о типе пула в транзакцию, если указан
            type_info = f" (тип: {pool_type})" if pool_type else ""
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': '1000000000',  # 1 TON
                        'payload': f'Создание пула {token1_info["symbol"]}/{token2_info["symbol"]}{type_info}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания пула: {e}")

    async def create_cross_swap_transaction(self, token_in: str, token_out: str, 
                                            amount: float, wallet_address: str, 
                                            path: list = None, pool_addresses: list = None) -> dict:
        """
        Создание транзакции для кросс-свопа через несколько пулов
        
        Args:
            token_in: Адрес или символ входящего токена
            token_out: Адрес или символ исходящего токена
            amount: Количество токена для свопа
            wallet_address: Адрес кошелька пользователя
            path: Опциональный путь свопа через промежуточные токены
            pool_addresses: Адреса пулов для выполнения свопа
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            if not path:
                # Если путь не передан, получаем маршрут
                route = await self.get_swap_route(token_in, token_out, int(amount * 10**9))
                path = route['path']
                pool_addresses = route.get('pool_addresses', [])
            
            # Конвертируем количество в наноТОНы
            amount_nano = int(amount * 10**9)
            
            # Создаем описание пути свопа
            path_description = " -> ".join(path)
            pools_description = ", ".join(pool_addresses) if pool_addresses else "default pools"
            
            # Создаем транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': str(amount_nano),
                        'payload': f'Своп {path_description} через пулы: {pools_description}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания транзакции кросс-свопа: {e}")

    async def get_pool_chart(self, token_pair: str, timeframe: str = "1d", limit: int = 100, pool_type: str = None) -> list:
        """
        Получение данных графика для пула
        
        Args:
            token_pair: Пара токенов в формате "token1/token2"
            timeframe: Временной интервал
            limit: Количество точек данных
            pool_type: Тип пула
            
        Returns:
            list: Список точек данных для графика
        """
        try:
            token1, token2 = token_pair.split('/')
            
            # Учитываем тип пула
            pool_type_param = {"pool_type": pool_type} if pool_type else {}
            
            # Заглушка для тестирования
            # Генерируем тестовые данные для графика
            current_time = int(time.time())
            result = []
            
            # Различные интервалы времени в секундах
            timeframe_seconds = {
                "1h": 60 * 60,
                "1d": 24 * 60 * 60,
                "1w": 7 * 24 * 60 * 60,
                "1m": 30 * 24 * 60 * 60
            }
            
            # Интервал времени в секундах
            interval = timeframe_seconds.get(timeframe, 24 * 60 * 60)
            
            # Генерируем точки данных
            for i in range(limit):
                # Множитель для типа пула
                type_multiplier = 2 if pool_type == "stable" else 1
                
                timestamp = current_time - (i * interval)
                price = 1.5 + 0.1 * (i % 10) * type_multiplier
                volume = 100000 + 10000 * (i % 5) * type_multiplier
                liquidity = 2000000 + 100000 * (i % 3) * type_multiplier
                
                result.append({
                    'timestamp': timestamp,
                    'price': price,
                    'volume': volume,
                    'liquidity': liquidity
                })
            
            return result
        except Exception as e:
            raise Exception(f"Ошибка получения данных графика пула: {e}")

    async def get_pool_info_by_address(self, pool_address: str) -> dict:
        """
        Получение информации о пуле по его адресу из БД
        
        Args:
            pool_address: Адрес пула
            
        Returns:
            dict: Информация о пуле
        """
        try:
            # Получаем информацию о пуле из БД
            pool_data = await get_pool(pool_address)
            
            if not pool_data:
                # Если пул не найден в БД, возвращаем ошибку
                raise Exception(f"Пул с адресом {pool_address} не найден в базе данных")
            
            return pool_data
        except Exception as e:
            raise Exception(f"Ошибка получения информации о пуле по адресу из БД: {e}")

    async def get_pool_chart_by_address(self, pool_address: str, timeframe: str = "1d", limit: int = 100) -> list:
        """
        Получение данных графика для пула по его адресу
        
        Args:
            pool_address: Адрес пула
            timeframe: Временной интервал
            limit: Количество точек данных
            
        Returns:
            list: Список точек данных для графика
        """
        try:
            # Определяем тип пула на основе адреса (для тестирования)
            pool_type = None
            if "_stable" in pool_address:
                pool_type = "stable"
            elif "_volatile" in pool_address:
                pool_type = "volatile"
            
            # Заглушка для тестирования
            # Генерируем тестовые данные для графика
            current_time = int(time.time())
            result = []
            
            # Различные интервалы времени в секундах
            timeframe_seconds = {
                "1h": 60 * 60,
                "1d": 24 * 60 * 60,
                "1w": 7 * 24 * 60 * 60,
                "1m": 30 * 24 * 60 * 60
            }
            
            # Интервал времени в секундах
            interval = timeframe_seconds.get(timeframe, 24 * 60 * 60)
            
            # Генерируем точки данных
            for i in range(limit):
                # Множитель для типа пула
                type_multiplier = 2 if pool_type == "stable" else 1
                
                timestamp = current_time - (i * interval)
                price = 1.5 + 0.1 * (i % 10) * type_multiplier
                volume = 100000 + 10000 * (i % 5) * type_multiplier
                liquidity = 2000000 + 100000 * (i % 3) * type_multiplier
                
                result.append({
                    'timestamp': timestamp,
                    'price': price,
                    'volume': volume,
                    'liquidity': liquidity
                })
            
            return result
        except Exception as e:
            raise Exception(f"Ошибка получения данных графика пула по адресу: {e}")

    async def create_add_liquidity_transaction_by_address(self, pool_address: str, 
                                                         token1_amount: float, token2_amount: float, 
                                                         wallet_address: str) -> dict:
        """
        Создание транзакции для добавления ликвидности по адресу пула
        
        Args:
            pool_address: Адрес пула
            token1_amount: Количество первого токена
            token2_amount: Количество второго токена
            wallet_address: Адрес кошелька пользователя
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о пуле по адресу
            pool_info = await self.get_pool_info_by_address(pool_address)
            
            # Используем тип пула из информации о пуле
            pool_type = pool_info.get('type')
            
            # Заглушка для тестирования
            # Возвращаем тестовую транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            # Добавляем информацию о типе пула в транзакцию, если указан
            type_info = f" (тип: {pool_type})" if pool_type else ""
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': '1000000000',  # 1 TON
                        'payload': f'Добавление ликвидности в пул {pool_address}{type_info}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания транзакции для добавления ликвидности по адресу пула: {e}")

    async def create_remove_liquidity_transaction_by_address(self, pool_address: str, 
                                                            position_id: int, wallet_address: str) -> dict:
        """
        Создание транзакции для удаления ликвидности по адресу пула
        
        Args:
            pool_address: Адрес пула
            position_id: ID позиции ликвидности
            wallet_address: Адрес кошелька пользователя
            
        Returns:
            dict: Транзакция для отправки через TonConnect
        """
        try:
            # Получаем информацию о пуле по адресу
            pool_info = await self.get_pool_info_by_address(pool_address)
            
            # Используем тип пула из информации о пуле
            pool_type = pool_info.get('type')
            
            # Получаем информацию о позиции
            position = await self.get_liquidity_position(position_id, wallet_address)
            if not position:
                raise Exception(f"Позиция с ID {position_id} не найдена")
            
            # Заглушка для тестирования
            # Возвращаем тестовую транзакцию
            valid_until = int(time.time()) + 60 * 10  # 10 минут
            
            # Добавляем информацию о типе пула в транзакцию, если указан
            type_info = f" (тип: {pool_type})" if pool_type else ""
            
            return {
                'valid_until': valid_until,
                'messages': [
                    {
                        'address': str(self.dex_address),
                        'amount': '1000000000',  # 1 TON
                        'payload': f'Удаление ликвидности из пула {pool_address} позиция {position_id}{type_info}'
                    }
                ]
            }
        except Exception as e:
            raise Exception(f"Ошибка создания транзакции для удаления ликвидности по адресу пула: {e}")

    async def get_liquidity_position(self, position_id: int, wallet_address: str) -> dict:
        """
        Получение информации о позиции ликвидности из БД
        
        Args:
            position_id: ID позиции ликвидности
            wallet_address: Адрес кошелька пользователя
            
        Returns:
            dict: Информация о позиции ликвидности или None, если позиция не найдена
        """
        try:
            # Получаем все позиции пользователя
            positions = await get_positions_by_wallet(wallet_address)
            
            # Ищем нужную позицию
            position = next((p for p in positions if p['id'] == position_id), None)
            
            if not position:
                return None
                
            return position
        except Exception as e:
            raise Exception(f"Ошибка получения информации о позиции ликвидности: {e}")

    async def get_pool_info_with_type(self, token1: str, token2: str, pool_type: Optional[str] = None) -> dict:
        """
        Получение полной информации о пуле по паре токенов и типу пула
        
        Args:
            token1: Символ или адрес первого токена
            token2: Символ или адрес второго токена
            pool_type: Тип пула (например, "stable", "volatile", и т.д.)
            
        Returns:
            dict: Полная информация о пуле из БД
        """
        try:
            # Получаем информацию о пуле из БД
            pool_data = await get_pool_by_tokens_and_type(token1, token2, pool_type)
            
            if not pool_data:
                raise Exception(f"Пул для токенов {token1}/{token2} {f'с типом {pool_type}' if pool_type else ''} не найден")
            
            # Получаем дополнительную информацию о токенах
            token1_info = await self.get_token_info(pool_data['token1'])
            token2_info = await self.get_token_info(pool_data['token2'])
            
            # Дополняем информацию о пуле
            pool_data['token1_info'] = token1_info
            pool_data['token2_info'] = token2_info
            
            # Вычисляем текущую цену токенов
            if pool_data['token1_reserve'] and pool_data['token2_reserve']:
                pool_data['price1_2'] = pool_data['token2_reserve'] / pool_data['token1_reserve']
                pool_data['price2_1'] = pool_data['token1_reserve'] / pool_data['token2_reserve']
            
            return pool_data
        except Exception as e:
            raise Exception(f"Ошибка получения информации о пуле: {e}")
