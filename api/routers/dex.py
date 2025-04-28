from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import sys
import os
from pytoniq import Address, Cell, begin_cell
from pathlib import Path
import time

# Добавляем путь к корневой директории проекта
root_path = str(Path(__file__).parent.parent.parent.absolute())
if root_path not in sys.path:
    sys.path.append(root_path)

# Импортируем из core
from core.dex import DexManager
# Импортируем функции для работы с БД напрямую из core
from core.db import (
    get_pool, get_pool_by_tokens, get_pool_by_tokens_and_type, 
    get_all_pools, get_positions_by_wallet, get_positions_by_pool,
    save_pool, update_pool_liquidity, save_position, remove_position,
    save_price, get_prices, get_latest_price, get_token, get_token_by_address,
    get_latest_token_price
)

from schemas.dex import (
    TokenInfo, PoolInfo, LiquidityPosition, SwapRoute,
    SwapTransaction, PoolChartPoint, CreatePoolRequest,
    AddLiquidityRequest, RemoveLiquidityRequest, SwapRequest,
    ErrorResponse
)

router = APIRouter(prefix="/dex", tags=["DEX"])
dex_manager = DexManager()

@router.get("/token/{token_identifier}", response_model=TokenInfo)
async def get_token_info(token_identifier: str):
    """Получение информации о токене"""
    try:
        # Сначала пытаемся получить данные из БД
        token_data = None
        
        # Проверяем, является ли идентификатор адресом или символом
        if token_identifier.startswith('0:'):
            token_data = await get_token_by_address(token_identifier)
        else:
            token_data = await get_token(token_identifier)
            
        if not token_data:
            raise HTTPException(status_code=404, detail=f"Токен {token_identifier} не найден в базе данных")
        
        # Получаем информацию о цене в USDT
        usdt_price = None
        usdt_pool = None
        
        # Пытаемся найти пул с USDT
        if token_data['token_symbol'] != 'USDT':
            usdt_pool = get_pool_by_tokens(token_data['token_symbol'], 'USDT')
            
            if usdt_pool:
                # Если такой пул есть, получаем цену
                if usdt_pool['token1'] == token_data['token_symbol']:
                    usdt_price = usdt_pool['token2_reserve'] / usdt_pool['token1_reserve']
                else:
                    usdt_price = usdt_pool['token1_reserve'] / usdt_pool['token2_reserve']
        
        # Получаем список всех пулов с этим токеном
        all_pools = get_all_pools()
        token_pools = []
        
        for pool in all_pools:
            if pool['token1'] == token_data['token_symbol'] or pool['token2'] == token_data['token_symbol']:
                token_pools.append({
                    'pool_address': pool['pool_address'],
                    'pair': f"{pool['token1']}/{pool['token2']}",
                    'liquidity': pool['liquidity'],
                    'type': pool['pool_type']
                })
        
        # Формируем ответ
        return TokenInfo(
            symbol=token_data['token_symbol'],
            name=token_data['token_name'] or token_data['token_symbol'],
            address=token_data['master_address'],
            decimals=token_data['decimals'],
            usdt_price=usdt_price,
            pools=token_pools
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/{token1}/{token2}", response_model=PoolInfo)
async def get_pool_info(token1: str, token2: str, type: Optional[str] = None):
    """Получение информации о пуле по паре токенов"""
    try:
        # Получаем данные напрямую из БД
        pool_data = get_pool_by_tokens_and_type(token1, token2, type)
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул для токенов {token1}/{token2} не найден в базе данных")
        
        # Формируем ответ из данных БД
        return PoolInfo(
            token1=token1,
            token2=token2,
            pool_address=pool_data['pool_address'],
            liquidity=pool_data['liquidity'],
            token1_reserve=pool_data['token1_reserve'],
            token2_reserve=pool_data['token2_reserve'],
            type=pool_data['pool_type']
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/address/{pool_address}", response_model=PoolInfo)
async def get_pool_info_by_address(pool_address: str):
    """Получение информации о пуле по адресу пула"""
    try:
        # Получаем данные напрямую из БД
        pool_data = get_pool(pool_address)
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул с адресом {pool_address} не найден в базе данных")
        
        # Формируем ответ из данных БД
        return PoolInfo(
            token1=pool_data['token1'],
            token2=pool_data['token2'],
            pool_address=pool_data['pool_address'],
            liquidity=pool_data['liquidity'],
            token1_reserve=pool_data['token1_reserve'],
            token2_reserve=pool_data['token2_reserve'],
            type=pool_data['pool_type']
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/{token1}/{token2}/chart", response_model=List[PoolChartPoint])
async def get_pool_chart(token1: str, token2: str, type: Optional[str] = None, timeframe: str = "1d", limit: int = 100):
    """Получение графика пула по паре токенов"""
    try:
        # Сначала получаем адрес пула из БД
        pool_data = get_pool_by_tokens_and_type(token1, token2, type)
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул для токенов {token1}/{token2} не найден в базе данных")
        
        # Получаем исторические цены из БД без ограничений по времени
        prices = get_prices(pool_data['pool_address'])
        
        if not prices:
            raise HTTPException(status_code=404, detail=f"Данные о ценах для пула {token1}/{token2} не найдены в базе данных")
        
        # Формируем данные для графика
        chart_data = []
        for price_data in prices:
            chart_data.append(PoolChartPoint(
                timestamp=price_data['timestamp'],
                price=price_data['price'],
                volume=0  # В данных цен нет объемов, поэтому ставим 0
            ))
        
        return chart_data
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/address/{pool_address}/chart", response_model=List[PoolChartPoint])
async def get_pool_chart_by_address(pool_address: str, timeframe: str = "1d", limit: int = 100):
    """Получение графика пула по адресу пула"""
    try:
        # Проверяем, существует ли пул с таким адресом
        pool_data = get_pool(pool_address)
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул с адресом {pool_address} не найден в базе данных")
        
        # Получаем исторические цены из БД без ограничений по времени
        prices = get_prices(pool_address)
        
        if not prices:
            raise HTTPException(status_code=404, detail=f"Данные о ценах для пула с адресом {pool_address} не найдены в базе данных")
        
        # Формируем данные для графика
        chart_data = []
        for price_data in prices:
            chart_data.append(PoolChartPoint(
                timestamp=price_data['timestamp'],
                price=price_data['price'],
                volume=0  # В данных цен нет объемов, поэтому ставим 0
            ))
        
        return chart_data
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/positions/{wallet_address}", response_model=List[LiquidityPosition])
async def get_liquidity_positions(wallet_address: str):
    """Получение позиций ликвидности пользователя"""
    try:
        # Получаем данные напрямую из БД
        positions = get_positions_by_wallet(wallet_address)
        
        if not positions:
            raise HTTPException(status_code=404, detail=f"Позиции ликвидности для кошелька {wallet_address} не найдены в базе данных")
        
        # Формируем ответ из данных БД
        result = []
        for pos in positions:
            # Получаем информацию о пуле для этой позиции
            pool_data = get_pool(pos['pool_address'])
            
            if pool_data:
                position = LiquidityPosition(
                    position_id=pos['id'],
                    pool_address=pos['pool_address'],
                    wallet_address=pos['wallet_address'],
                    token1=pool_data['token1'],
                    token2=pool_data['token2'],
                    token1_amount=pos['token1_amount'],
                    token2_amount=pos['token2_amount'],
                    lp_tokens=pos['lp_tokens'],
                    created_at=pos['created_at']
                )
                result.append(position)
        
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/create", response_model=SwapTransaction)
async def create_pool(
    token1: str, 
    token2: str, 
    initial_liquidity1: float, 
    initial_liquidity2: float, 
    wallet_address: str,
    type: Optional[str] = None
):
    """Создание нового пула"""
    try:
        # Проверяем, существует ли уже такой пул
        existing_pool = get_pool_by_tokens_and_type(token1, token2, type)
        if existing_pool:
            raise HTTPException(
                status_code=400, 
                detail=f"Пул для токенов {token1}/{token2} уже существует по адресу {existing_pool['pool_address']}"
            )
        
        # Создаем транзакцию через DexManager
        transaction = await dex_manager.create_pool(
            token1,
            token2,
            initial_liquidity1,
            initial_liquidity2,
            wallet_address,
            pool_type=type
        )
        
        # Создаем запись о новом пуле в БД
        # Адрес пула получаем из DexManager
        pool_address = str(dex_manager.get_amm_address(token1, token2))
        
        # Сохраняем информацию о пуле в БД
        save_pool(
            token1=token1,
            token2=token2,
            pool_address=pool_address,
            liquidity=initial_liquidity1 * initial_liquidity2,
            token1_reserve=initial_liquidity1,
            token2_reserve=initial_liquidity2,
            pool_type=type
        )
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/add-liquidity", response_model=SwapTransaction)
async def add_liquidity(
    token1: str, 
    token2: str, 
    token1_amount: float, 
    token2_amount: float, 
    wallet_address: str,
    type: Optional[str] = None
):
    """Добавление ликвидности в пул по паре токенов"""
    try:
        # Находим пул в БД
        pool_data = get_pool_by_tokens_and_type(token1, token2, type)
        if not pool_data:
            # Если пул не найден, вызываем ошибку
            raise HTTPException(
                status_code=404, 
                detail=f"Пул для токенов {token1}/{token2} не найден. Сначала создайте пул."
            )
        
        # Создаем транзакцию через DexManager
        transaction = await dex_manager.create_add_liquidity_transaction(
            token1,
            token2,
            token1_amount,
            token2_amount,
            wallet_address,
            pool_type=type
        )
        
        # Обновляем запись о пуле в БД
        pool_address = pool_data['pool_address']
        
        # Рассчитываем новые резервы и ликвидность
        new_token1_reserve = pool_data['token1_reserve'] + token1_amount
        new_token2_reserve = pool_data['token2_reserve'] + token2_amount
        new_liquidity = new_token1_reserve * new_token2_reserve  # Простой расчет ликвидности
        
        # Обновляем данные пула
        update_pool_liquidity(
            pool_address=pool_address,
            liquidity=new_liquidity,
            token1_reserve=new_token1_reserve,
            token2_reserve=new_token2_reserve
        )
        
        # Сохраняем позицию пользователя
        # Простой расчет LP токенов для примера
        lp_tokens = (token1_amount * token2_amount) ** 0.5
        
        save_position(
            wallet_address=wallet_address,
            pool_address=pool_address,
            token1_amount=token1_amount,
            token2_amount=token2_amount,
            lp_tokens=lp_tokens
        )
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/address/{pool_address}/add-liquidity", response_model=SwapTransaction)
async def add_liquidity_by_address(
    pool_address: str,
    token1_amount: float,
    token2_amount: float,
    wallet_address: str
):
    """Добавление ликвидности в пул по адресу пула"""
    try:
        # Находим пул в БД
        pool_data = get_pool(pool_address)
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул с адресом {pool_address} не найден в базе данных")
        
        # Создаем транзакцию через DexManager
        transaction = await dex_manager.create_add_liquidity_transaction_by_address(
            pool_address,
            token1_amount,
            token2_amount,
            wallet_address
        )
        
        # Рассчитываем новые резервы и ликвидность
        new_token1_reserve = pool_data['token1_reserve'] + token1_amount
        new_token2_reserve = pool_data['token2_reserve'] + token2_amount
        new_liquidity = new_token1_reserve * new_token2_reserve  # Простой расчет ликвидности
        
        # Обновляем данные пула
        update_pool_liquidity(
            pool_address=pool_address,
            liquidity=new_liquidity,
            token1_reserve=new_token1_reserve,
            token2_reserve=new_token2_reserve
        )
        
        # Сохраняем позицию пользователя
        # Простой расчет LP токенов для примера
        lp_tokens = (token1_amount * token2_amount) ** 0.5
        
        save_position(
            wallet_address=wallet_address,
            pool_address=pool_address,
            token1_amount=token1_amount,
            token2_amount=token2_amount,
            lp_tokens=lp_tokens
        )
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/remove-liquidity", response_model=SwapTransaction)
async def remove_liquidity(
    position_id: int, 
    wallet_address: str,
    type: Optional[str] = None
):
    """Удаление ликвидности из пула по ID позиции"""
    try:
        # Находим позицию в БД по ID
        positions = get_positions_by_wallet(wallet_address)
        position = next((p for p in positions if p['id'] == position_id), None)
        
        if not position:
            raise HTTPException(status_code=404, detail=f"Позиция #{position_id} не найдена для кошелька {wallet_address}")
        
        # Проверяем, что позиция принадлежит указанному кошельку
        if position['wallet_address'] != wallet_address:
            raise HTTPException(
                status_code=403, 
                detail=f"Позиция #{position_id} не принадлежит указанному кошельку"
            )
        
        # Получаем данные пула
        pool_address = position['pool_address']
        pool_data = get_pool(pool_address)
        
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул с адресом {pool_address} не найден в базе данных")
        
        # Создаем транзакцию через DexManager
        transaction = await dex_manager.create_remove_liquidity_transaction(
            position_id,
            wallet_address,
            pool_type=type
        )
        
        # Рассчитываем новые резервы и ликвидность
        new_token1_reserve = pool_data['token1_reserve'] - position['token1_amount']
        new_token2_reserve = pool_data['token2_reserve'] - position['token2_amount']
        new_liquidity = new_token1_reserve * new_token2_reserve if new_token1_reserve > 0 and new_token2_reserve > 0 else 0
        
        # Обновляем данные пула
        update_pool_liquidity(
            pool_address=pool_address,
            liquidity=new_liquidity,
            token1_reserve=new_token1_reserve,
            token2_reserve=new_token2_reserve
        )
        
        # Удаляем позицию пользователя
        remove_position(wallet_address, pool_address)
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pool/address/{pool_address}/remove-liquidity", response_model=SwapTransaction)
async def remove_liquidity_by_address(
    pool_address: str,
    position_id: int,
    wallet_address: str
):
    """Удаление ликвидности из пула по адресу пула и ID позиции"""
    try:
        # Находим позицию в БД
        positions = get_positions_by_wallet(wallet_address)
        position = next((p for p in positions if p['id'] == position_id and p['pool_address'] == pool_address), None)
        
        if not position:
            raise HTTPException(status_code=404, detail=f"Позиция #{position_id} не найдена для кошелька {wallet_address} в пуле {pool_address}")
        
        # Проверяем, что позиция принадлежит указанному кошельку
        if position['wallet_address'] != wallet_address:
            raise HTTPException(
                status_code=403, 
                detail=f"Позиция #{position_id} не принадлежит указанному кошельку"
            )
        
        # Получаем данные пула
        pool_data = get_pool(pool_address)
        
        if not pool_data:
            raise HTTPException(status_code=404, detail=f"Пул с адресом {pool_address} не найден в базе данных")
        
        # Создаем транзакцию через DexManager
        transaction = await dex_manager.create_remove_liquidity_transaction_by_address(
            pool_address,
            position_id,
            wallet_address
        )
        
        # Рассчитываем новые резервы и ликвидность
        new_token1_reserve = pool_data['token1_reserve'] - position['token1_amount']
        new_token2_reserve = pool_data['token2_reserve'] - position['token2_amount']
        new_liquidity = new_token1_reserve * new_token2_reserve if new_token1_reserve > 0 and new_token2_reserve > 0 else 0
        
        # Обновляем данные пула
        update_pool_liquidity(
            pool_address=pool_address,
            liquidity=new_liquidity,
            token1_reserve=new_token1_reserve,
            token2_reserve=new_token2_reserve
        )
        
        # Удаляем позицию пользователя
        remove_position(wallet_address, pool_address)
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/swap", response_model=SwapTransaction)
async def create_swap(
    token_in: str, 
    token_out: str, 
    amount: float, 
    wallet_address: str,
    path: Optional[str] = None
):
    """Создание транзакции свопа"""
    try:
        # Проверяем, существуют ли указанные токены и пулы
        if path:
            # Если указан путь, проверяем все пулы в пути
            path_list = path.split(',')
            
            # Проверяем первый пул (token_in и первый в пути)
            first_pool = get_pool_by_tokens(token_in, path_list[0])
            if not first_pool:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Пул для токенов {token_in}/{path_list[0]} не найден"
                )
            
            # Проверяем промежуточные пулы
            for i in range(len(path_list) - 1):
                intermediate_pool = get_pool_by_tokens(path_list[i], path_list[i+1])
                if not intermediate_pool:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Пул для токенов {path_list[i]}/{path_list[i+1]} не найден"
                    )
            
            # Проверяем последний пул (последний в пути и token_out)
            last_pool = get_pool_by_tokens(path_list[-1], token_out)
            if not last_pool:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Пул для токенов {path_list[-1]}/{token_out} не найден"
                )
                
            # Если все пулы найдены, создаем транзакцию кросс-свопа
            path_list_for_dex = path_list  # Используем путь из запроса
            transaction = await dex_manager.create_cross_swap_transaction(
                token_in,
                token_out,
                amount,
                wallet_address,
                path_list_for_dex
            )
        else:
            # Если путь не указан, проверяем прямой пул
            direct_pool = get_pool_by_tokens(token_in, token_out)
            if not direct_pool:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Прямой пул для токенов {token_in}/{token_out} не найден. Укажите путь для свопа."
                )
            
            # Если прямой пул найден, создаем прямую транзакцию свопа
            transaction = await dex_manager.create_swap_transaction(
                token_in,
                token_out,
                amount,
                wallet_address
            )
        
        # Сохраняем цену в момент совершения свопа
        # Предполагаем, что у нас есть функция расчета цены
        # в данном случае просто записываем соотношение резервов для прямого пула
        if not path:
            direct_pool = get_pool_by_tokens(token_in, token_out)
            if direct_pool:
                # Примерная цена на основе резервов пула
                if direct_pool['token1'] == token_in:
                    price = direct_pool['token2_reserve'] / direct_pool['token1_reserve']
                else:
                    price = direct_pool['token1_reserve'] / direct_pool['token2_reserve']
                
                # Сохраняем цену в БД
                save_price(direct_pool['pool_address'], price)
        
        return transaction
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка создания транзакции свопа: {str(e)}")

@router.get("/swap/route", response_model=SwapTransaction)
async def get_swap_route(token_in: str, token_out: str, amount: float, wallet_address: str):
    """Получение оптимального маршрута для свопа и создание транзакции"""
    try:
        # Проверяем сначала прямой пул
        direct_pool = get_pool_by_tokens(token_in, token_out)
        if direct_pool:
            # Если прямой пул найден, используем его
            return await dex_manager.create_swap_transaction(
                token_in,
                token_out,
                amount,
                wallet_address
            )
        
        # Если прямого пула нет, ищем все доступные пулы для построения маршрута
        all_pools = get_all_pools()
        
        if not all_pools:
            raise HTTPException(status_code=404, detail="Пулы не найдены в базе данных")
        
        # Сначала получаем маршрут обмена через DexManager
        try:
            route = await dex_manager.get_swap_route(token_in, token_out, int(amount * 10**9))
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Не удалось найти маршрут для свопа {token_in} -> {token_out}: {str(e)}")
        
        # Затем создаем транзакцию по этому маршруту
        return await dex_manager.create_cross_swap_transaction(
            token_in,
            token_out,
            amount,
            wallet_address,
            route.path
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 