import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
import dotenv
from datetime import datetime, timedelta
# Загружаем переменные окружения из .env файла
dotenv.load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db')

# Получаем параметры подключения к базе данных
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'dex_db')
DB_USER = os.getenv('DB_USER', 'sdf')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

def get_connection():
    """Получение соединения с базой данных PostgreSQL"""
    try:
        print(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        raise

def init_db():
    """Инициализация базы данных"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу цен
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            id SERIAL PRIMARY KEY,
            pool_address TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp INTEGER NOT NULL,
            UNIQUE(pool_address, timestamp)
        )
        ''')
        
        # Создаем индекс для быстрого поиска по адресу пула и времени
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_prices_pool_address ON prices(pool_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_prices_timestamp ON prices(timestamp)')
        
        # Создаем таблицу токенов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            id SERIAL PRIMARY KEY,
            token_symbol TEXT NOT NULL,
            token_name TEXT,
            master_address TEXT NOT NULL UNIQUE,
            decimals INTEGER NOT NULL DEFAULT 9,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        ''')
        
        # Создаем индексы для таблицы токенов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(token_symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tokens_master_address ON tokens(master_address)')
        
        # Создаем таблицу пулов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS pools (
            id SERIAL PRIMARY KEY,
            token1 TEXT NOT NULL,
            token2 TEXT NOT NULL,
            pool_address TEXT NOT NULL UNIQUE,
            liquidity REAL NOT NULL DEFAULT 0,
            token1_address TEXT,
            token2_address TEXT,
            token1_reserve REAL,
            token2_reserve REAL,
            pool_type TEXT,
            created_at INTEGER NOT NULL
        )
        ''')
        
        # Создаем индекс для быстрого поиска пулов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pools_tokens ON pools(token1, token2)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pools_address ON pools(pool_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pools_type ON pools(pool_type)')
        
        # Создаем таблицу позиций ликвидности
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id SERIAL PRIMARY KEY,
            wallet_address TEXT NOT NULL,
            pool_address TEXT NOT NULL,
            token1_amount REAL NOT NULL,
            token2_amount REAL NOT NULL,
            lp_tokens REAL NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(wallet_address, pool_address)
        )
        ''')
        
        # Создаем индекс для быстрого поиска позиций
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_wallet ON positions(wallet_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_pool ON positions(pool_address)')
        
        # Создаем таблицу для хранения транзакций
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            tx_hash VARCHAR(255) UNIQUE,
            block_number BIGINT,
            from_address VARCHAR(255),
            to_address VARCHAR(255),
            token_address VARCHAR(255),
            value DECIMAL(78, 0),
            timestamp TIMESTAMP,
            gas_used BIGINT,
            gas_price BIGINT
        )
        """)
        
        # Создаем индексы для оптимизации запросов
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_token_address ON transactions(token_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)")
        
        # Создаем таблицу цен токенов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_prices (
            id SERIAL PRIMARY KEY,
            token_address TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp INTEGER NOT NULL,
            UNIQUE(token_address, timestamp)
        )
        ''')
        
        # Создаем индекс для быстрого поиска цен токенов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_token_prices_address ON token_prices(token_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_token_prices_timestamp ON token_prices(timestamp)')
        
        conn.commit()
        logger.info("База данных успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

# Функции для работы с ценами

def save_price(pool_address: str, price: float):
    """Сохранение цены токена в пуле"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        timestamp = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO prices (pool_address, price, timestamp) 
            VALUES (%s, %s, %s)
            ON CONFLICT (pool_address, timestamp) 
            DO UPDATE SET price = EXCLUDED.price
            """,
            (pool_address, price, timestamp)
        )
        
        conn.commit()
        logger.debug(f"Цена для пула {pool_address} сохранена: {price}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении цены: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_prices(pool_address: str, from_time: Optional[int] = None, to_time: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Получение исторических цен для пула"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT pool_address, price, timestamp FROM prices WHERE pool_address = %s"
        params = [pool_address]
        
        if from_time:
            query += " AND timestamp >= %s"
            params.append(from_time)
        
        if to_time:
            query += " AND timestamp <= %s"
            params.append(to_time)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        
        return list(result)
    except Exception as e:
        logger.error(f"Ошибка при получении истории цен: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_latest_price(pool_address: str) -> Optional[float]:
    """Получение последней цены для пула"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT price FROM prices WHERE pool_address = %s ORDER BY timestamp DESC LIMIT 1",
            (pool_address,)
        )
        
        row = cursor.fetchone()
        if row:
            return row["price"]
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении последней цены: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

# Функции для работы с пулами

def save_pool(token1: str, token2: str, pool_address: str, liquidity: float = 0, 
              token1_address: Optional[str] = None, token2_address: Optional[str] = None,
              token1_reserve: Optional[float] = None, token2_reserve: Optional[float] = None,
              pool_type: Optional[str] = None):
    """Сохранение информации о пуле"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO pools 
            (token1, token2, pool_address, liquidity, token1_address, token2_address, 
             token1_reserve, token2_reserve, pool_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (pool_address) 
            DO UPDATE SET 
                token1 = EXCLUDED.token1,
                token2 = EXCLUDED.token2,
                liquidity = EXCLUDED.liquidity,
                token1_address = EXCLUDED.token1_address,
                token2_address = EXCLUDED.token2_address,
                token1_reserve = EXCLUDED.token1_reserve,
                token2_reserve = EXCLUDED.token2_reserve,
                pool_type = EXCLUDED.pool_type
            """,
            (token1, token2, pool_address, liquidity, token1_address, token2_address, 
             token1_reserve, token2_reserve, pool_type, current_time)
        )
        
        conn.commit()
        logger.debug(f"Пул {token1}/{token2} с адресом {pool_address} сохранен")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пула: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def update_pool_liquidity(pool_address: str, liquidity: float, 
                         token1_reserve: Optional[float] = None, 
                         token2_reserve: Optional[float] = None):
    """Обновление ликвидности пула"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if token1_reserve is not None and token2_reserve is not None:
            cursor.execute(
                "UPDATE pools SET liquidity = %s, token1_reserve = %s, token2_reserve = %s WHERE pool_address = %s",
                (liquidity, token1_reserve, token2_reserve, pool_address)
            )
        else:
            cursor.execute(
                "UPDATE pools SET liquidity = %s WHERE pool_address = %s",
                (liquidity, pool_address)
            )
        
        conn.commit()
        logger.debug(f"Ликвидность пула {pool_address} обновлена: {liquidity}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении ликвидности пула: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_pool(pool_address: str) -> Optional[Dict[str, Any]]:
    """Получение информации о пуле по адресу"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT id, token1, token2, pool_address, liquidity, token1_address, 
                   token2_address, token1_reserve, token2_reserve, created_at
            FROM pools 
            WHERE pool_address = %s
            """,
            (pool_address,)
        )
        
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пуле: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_pool_by_tokens(token1: str, token2: str) -> Optional[Dict[str, Any]]:
    """Получение информации о пуле по паре токенов"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем в обоих направлениях (token1/token2 и token2/token1)
        cursor.execute(
            """
            SELECT id, token1, token2, pool_address, liquidity, token1_address, 
                   token2_address, token1_reserve, token2_reserve, created_at
            FROM pools 
            WHERE (token1 = %s AND token2 = %s) OR (token1 = %s AND token2 = %s)
            """,
            (token1, token2, token2, token1)
        )
        
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пуле по токенам: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_pool_by_tokens_and_type(token1: str, token2: str, pool_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Получение информации о пуле по паре токенов и типу пула"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        if pool_type:
            # Если указан тип пула, ищем конкретный пул
            cursor.execute(
                """
                SELECT id, token1, token2, pool_address, liquidity, token1_address, 
                       token2_address, token1_reserve, token2_reserve, pool_type, created_at
                FROM pools 
                WHERE ((token1 = %s AND token2 = %s) OR (token1 = %s AND token2 = %s))
                AND pool_type = %s
                """,
                (token1, token2, token2, token1, pool_type)
            )
        else:
            # Если тип не указан, ищем любой пул для этой пары токенов
            cursor.execute(
                """
                SELECT id, token1, token2, pool_address, liquidity, token1_address, 
                       token2_address, token1_reserve, token2_reserve, pool_type, created_at
                FROM pools 
                WHERE (token1 = %s AND token2 = %s) OR (token1 = %s AND token2 = %s)
                """,
                (token1, token2, token2, token1)
            )
        
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пуле по токенам и типу: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_all_pools() -> List[Dict[str, Any]]:
    """Получение списка всех пулов"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT id, token1, token2, pool_address, liquidity, token1_address, 
                   token2_address, token1_reserve, token2_reserve, created_at
            FROM pools
            ORDER BY liquidity DESC
            """
        )
        
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении списка пулов: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

# Функции для работы с позициями ликвидности

def save_position(wallet_address: str, pool_address: str, 
                  token1_amount: float, token2_amount: float, 
                  lp_tokens: float):
    """Сохранение информации о позиции ликвидности"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO positions
            (wallet_address, pool_address, token1_amount, token2_amount, lp_tokens, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (wallet_address, pool_address) 
            DO UPDATE SET 
                token1_amount = EXCLUDED.token1_amount,
                token2_amount = EXCLUDED.token2_amount,
                lp_tokens = EXCLUDED.lp_tokens
            """,
            (wallet_address, pool_address, token1_amount, token2_amount, lp_tokens, current_time)
        )
        
        conn.commit()
        logger.debug(f"Позиция ликвидности для кошелька {wallet_address} в пуле {pool_address} сохранена")
    except Exception as e:
        logger.error(f"Ошибка при сохранении позиции ликвидности: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def remove_position(wallet_address: str, pool_address: str):
    """Удаление позиции ликвидности"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM positions WHERE wallet_address = %s AND pool_address = %s",
            (wallet_address, pool_address)
        )
        
        conn.commit()
        logger.debug(f"Позиция ликвидности для кошелька {wallet_address} в пуле {pool_address} удалена")
    except Exception as e:
        logger.error(f"Ошибка при удалении позиции ликвидности: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_positions_by_wallet(wallet_address: str) -> List[Dict[str, Any]]:
    """Получение списка позиций ликвидности для кошелька"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT pos.id, pos.wallet_address, pos.pool_address, pos.token1_amount, 
                   pos.token2_amount, pos.lp_tokens, pos.created_at,
                   p.token1, p.token2, p.liquidity, p.token1_address, p.token2_address
            FROM positions pos
            LEFT JOIN pools p ON pos.pool_address = p.pool_address
            WHERE pos.wallet_address = %s
            """,
            (wallet_address,)
        )
        
        rows = cursor.fetchall()
        result = []
        
        for row in dict(rows):
            result.append({
                "id": row["id"],
                "wallet_address": row["wallet_address"],
                "pool_address": row["pool_address"],
                "token1_amount": row["token1_amount"],
                "token2_amount": row["token2_amount"],
                "lp_tokens": row["lp_tokens"],
                "created_at": row["created_at"],
                "pool_info": {
                    "token1": row["token1"],
                    "token2": row["token2"],
                    "liquidity": row["liquidity"],
                    "token1_address": row["token1_address"],
                    "token2_address": row["token2_address"]
                }
            })
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении позиций ликвидности: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_positions_by_pool(pool_address: str) -> List[Dict[str, Any]]:
    """Получение списка позиций ликвидности для пула"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT id, wallet_address, pool_address, token1_amount, 
                   token2_amount, lp_tokens, created_at
            FROM positions 
            WHERE pool_address = %s
            """,
            (pool_address,)
        )
        
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении позиций ликвидности для пула: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

# Функции для работы с токенами

def save_token(token_symbol: str, master_address: str, decimals: int = 9, token_name: str = None) -> bool:
    """
    Сохранение информации о токене в базу данных
    
    Args:
        token_symbol: Символ токена (например, TON, USDT)
        master_address: Адрес мастер-контракта токена
        decimals: Количество десятичных знаков токена (по умолчанию 9)
        token_name: Имя токена (опционально)
        
    Returns:
        bool: Успешность операции
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        # Проверяем, существует ли токен с таким адресом
        cursor.execute("SELECT id FROM tokens WHERE master_address = %s", (master_address,))
        existing_token = cursor.fetchone()
        
        if existing_token:
            # Обновляем существующий токен
            cursor.execute(
                """
                UPDATE tokens 
                SET token_symbol = %s, token_name = %s, decimals = %s, updated_at = %s
                WHERE master_address = %s
                """,
                (token_symbol, token_name, decimals, current_time, master_address)
            )
        else:
            # Добавляем новый токен
            cursor.execute(
                """
                INSERT INTO tokens 
                (token_symbol, token_name, master_address, decimals, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (token_symbol, token_name, master_address, decimals, current_time, current_time)
            )
        
        conn.commit()
        logger.debug(f"Токен {token_symbol} ({master_address}) сохранен в базе данных")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении токена: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_token(token_symbol: str) -> Optional[Dict[str, Any]]:
    """
    Получение информации о токене по его символу
    
    Args:
        token_symbol: Символ токена (например, TON, USDT)
        
    Returns:
        Dict[str, Any]: Информация о токене или None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Ищем токен по символу (case-insensitive)
        cursor.execute(
            "SELECT * FROM tokens WHERE LOWER(token_symbol) = LOWER(%s) ORDER BY updated_at DESC LIMIT 1",
            (token_symbol,)
        )
        
        token = cursor.fetchone()
        return dict(token) if token else None
    except Exception as e:
        logger.error(f"Ошибка при получении токена по символу {token_symbol}: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_token_by_address(master_address: str) -> Optional[Dict[str, Any]]:
    """
    Получение информации о токене по адресу мастер-контракта
    
    Args:
        master_address: Адрес мастер-контракта токена
        
    Returns:
        Dict[str, Any]: Информация о токене или None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM tokens WHERE master_address = %s",
            (master_address,)
        )
        
        token = cursor.fetchone()
        return dict(token) if token else None
    except Exception as e:
        logger.error(f"Ошибка при получении токена по адресу {master_address}: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_all_tokens() -> List[Dict[str, Any]]:
    """
    Получение списка всех токенов
    
    Returns:
        List[Dict[str, Any]]: Список токенов
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM tokens ORDER BY token_symbol")
        
        tokens = cursor.fetchall()
        return [dict(token) for token in tokens]
    except Exception as e:
        logger.error(f"Ошибка при получении списка токенов: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

def save_token_price(token_address: str, price: float, timestamp: Optional[int] = None):
    """Сохранение цены токена в базе данных"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if timestamp is None:
            timestamp = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO token_prices (token_address, price, timestamp) 
            VALUES (%s, %s, %s)
            ON CONFLICT (token_address, timestamp) 
            DO UPDATE SET price = EXCLUDED.price
            """,
            (token_address, price, timestamp)
        )
        
        conn.commit()
        logger.debug(f"Цена для токена {token_address} сохранена: {price}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении цены токена: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_token_price_history(token_address: str, days: int = 7) -> List[Dict[str, Any]]:
    """Получение истории цен токена за указанное количество дней"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Вычисляем временную метку для начала периода (N дней назад)
        from_time = int((datetime.now() - timedelta(days=days)).timestamp())
        
        query = """
            SELECT token_address, price, timestamp 
            FROM token_prices 
            WHERE token_address = %s AND timestamp >= %s
            ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (token_address, from_time))
        result = cursor.fetchall()
        
        return list(result)
    except Exception as e:
        logger.error(f"Ошибка при получении истории цен токена: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_latest_token_price(token_address: str) -> Optional[float]:
    """Получение последней цены токена"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT price 
            FROM token_prices 
            WHERE token_address = %s 
            ORDER BY timestamp DESC 
            LIMIT 1
            """,
            (token_address,)
        )
        
        row = cursor.fetchone()
        if row:
            return row["price"]
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении последней цены токена: {e}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

# Инициализируем базу данных при импорте модуля
try:
    init_db()
    logger.info("База данных PostgreSQL успешно инициализирована")
except Exception as e:
    logger.error(f"Ошибка при инициализации БД: {e}")

# Асинхронные версии функций для работы с индексером

async def save_pool(token1: str, token2: str, pool_address: str, liquidity: float = 0, 
              token1_address: Optional[str] = None, token2_address: Optional[str] = None,
              token1_reserve: Optional[float] = None, token2_reserve: Optional[float] = None,
              pool_type: Optional[str] = None):
    """Сохранение информации о пуле в базу данных (асинхронная версия)"""
    try:
        # Используем неасинхронную версию, так как у нас уже есть готовая логика
        # В будущем можно заменить на полностью асинхронную с asyncpg
        timestamp = int(time.time())
        
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id FROM pools WHERE pool_address = %s
            """,
            (pool_address,)
        )
        
        existing_pool = cursor.fetchone()
        
        if existing_pool:
            # Пул уже существует - обновляем
            cursor.execute(
                """
                UPDATE pools 
                SET token1 = %s, token2 = %s, liquidity = %s, 
                    token1_address = %s, token2_address = %s, 
                    token1_reserve = %s, token2_reserve = %s,
                    pool_type = %s
                WHERE pool_address = %s
                """,
                (token1, token2, liquidity, token1_address, token2_address, 
                 token1_reserve, token2_reserve, pool_type, pool_address)
            )
        else:
            # Пул не существует - создаем
            cursor.execute(
                """
                INSERT INTO pools 
                (token1, token2, pool_address, liquidity, token1_address, token2_address, 
                 token1_reserve, token2_reserve, pool_type, created_at) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (token1, token2, pool_address, liquidity, token1_address, token2_address, 
                 token1_reserve, token2_reserve, pool_type, timestamp)
            )
        
        conn.commit()
        logger.info(f"Пул {pool_address} ({token1}/{token2}) сохранен в базе данных")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении пула {pool_address}: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def save_token(token_symbol: str, master_address: str, decimals: int = 9, token_name: str = None) -> bool:
    """
    Сохранение информации о токене в базу данных (асинхронная версия)
    
    Args:
        token_symbol: Символ токена (например, TON, USDT)
        master_address: Адрес мастер-контракта токена
        decimals: Количество десятичных знаков токена (по умолчанию 9)
        token_name: Имя токена (опционально)
        
    Returns:
        bool: Успешность операции
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        # Проверяем, существует ли токен с таким адресом
        cursor.execute("SELECT id FROM tokens WHERE master_address = %s", (master_address,))
        existing_token = cursor.fetchone()
        
        if existing_token:
            # Обновляем существующий токен
            cursor.execute(
                """
                UPDATE tokens 
                SET token_symbol = %s, token_name = %s, decimals = %s, updated_at = %s
                WHERE master_address = %s
                """,
                (token_symbol, token_name, decimals, current_time, master_address)
            )
        else:
            # Добавляем новый токен
            cursor.execute(
                """
                INSERT INTO tokens 
                (token_symbol, token_name, master_address, decimals, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (token_symbol, token_name, master_address, decimals, current_time, current_time)
            )
        
        conn.commit()
        logger.debug(f"Токен {token_symbol} ({master_address}) сохранен в базе данных")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении токена: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_token(token_symbol: str) -> Optional[Dict[str, Any]]:
    """
    Получение информации о токене по его символу (асинхронная версия)
    
    Args:
        token_symbol: Символ токена (например, TON, USDT)
        
    Returns:
        Dict[str, Any]: Информация о токене или None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Ищем токен по символу (case-insensitive)
        cursor.execute(
            "SELECT * FROM tokens WHERE LOWER(token_symbol) = LOWER(%s) ORDER BY updated_at DESC LIMIT 1",
            (token_symbol,)
        )
        
        token = cursor.fetchone()
        return dict(token) if token else None
    except Exception as e:
        logger.error(f"Ошибка при получении токена по символу {token_symbol}: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_token_by_address(master_address: str) -> Optional[Dict[str, Any]]:
    """
    Получение информации о токене по адресу мастер-контракта (асинхронная версия)
    
    Args:
        master_address: Адрес мастер-контракта токена
        
    Returns:
        Dict[str, Any]: Информация о токене или None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM tokens WHERE master_address = %s",
            (master_address,)
        )
        
        token = cursor.fetchone()
        return dict(token) if token else None
    except Exception as e:
        logger.error(f"Ошибка при получении токена по адресу {master_address}: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_all_tokens() -> List[Dict[str, Any]]:
    """
    Получение списка всех токенов (асинхронная версия)
    
    Returns:
        List[Dict[str, Any]]: Список токенов
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM tokens ORDER BY token_symbol")
        
        tokens = cursor.fetchall()
        return [dict(token) for token in tokens]
    except Exception as e:
        logger.error(f"Ошибка при получении списка токенов: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def save_price(pool_address: str, price: float):
    """Сохранение цены токена в пуле (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        timestamp = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO prices (pool_address, price, timestamp) 
            VALUES (%s, %s, %s)
            ON CONFLICT (pool_address, timestamp) 
            DO UPDATE SET price = EXCLUDED.price
            """,
            (pool_address, price, timestamp)
        )
        
        conn.commit()
        logger.debug(f"Цена для пула {pool_address} сохранена: {price}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении цены: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def update_pool_liquidity(pool_address: str, liquidity: float, 
                         token1_reserve: Optional[float] = None, 
                         token2_reserve: Optional[float] = None):
    """Обновление информации о ликвидности пула (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование пула
        cursor.execute("SELECT id FROM pools WHERE pool_address = %s", (pool_address,))
        if not cursor.fetchone():
            logger.warning(f"Пул {pool_address} не найден при обновлении ликвидности")
            return False
        
        query = "UPDATE pools SET liquidity = %s"
        params = [liquidity]
        
        if token1_reserve is not None:
            query += ", token1_reserve = %s"
            params.append(token1_reserve)
            
        if token2_reserve is not None:
            query += ", token2_reserve = %s"
            params.append(token2_reserve)
            
        query += " WHERE pool_address = %s"
        params.append(pool_address)
        
        cursor.execute(query, params)
        conn.commit()
        
        logger.debug(f"Ликвидность пула {pool_address} обновлена: {liquidity}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении ликвидности пула {pool_address}: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_pool(pool_address: str) -> Optional[Dict[str, Any]]:
    """Получение информации о пуле по адресу (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT * FROM pools WHERE pool_address = %s
            """,
            (pool_address,)
        )
        
        pool = cursor.fetchone()
        return dict(pool) if pool else None
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пуле {pool_address}: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_all_pools() -> List[Dict[str, Any]]:
    """Получение списка всех пулов (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM pools")
        pools = cursor.fetchall()
        
        return [dict(pool) for pool in pools]
    except Exception as e:
        logger.error(f"Ошибка при получении списка пулов: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def save_position(wallet_address: str, pool_address: str, 
                  token1_amount: float, token2_amount: float, 
                  lp_tokens: float):
    """Сохранение позиции ликвидности (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        timestamp = int(time.time())
        
        # Проверяем, существует ли позиция
        cursor.execute(
            """
            SELECT id FROM positions 
            WHERE wallet_address = %s AND pool_address = %s
            """,
            (wallet_address, pool_address)
        )
        
        existing_position = cursor.fetchone()
        
        if existing_position:
            # Позиция уже существует - обновляем
            cursor.execute(
                """
                UPDATE positions 
                SET token1_amount = %s, token2_amount = %s, lp_tokens = %s
                WHERE wallet_address = %s AND pool_address = %s
                """,
                (token1_amount, token2_amount, lp_tokens, wallet_address, pool_address)
            )
        else:
            # Позиция не существует - создаем
            cursor.execute(
                """
                INSERT INTO positions 
                (wallet_address, pool_address, token1_amount, token2_amount, lp_tokens, created_at) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (wallet_address, pool_address, token1_amount, token2_amount, lp_tokens, timestamp)
            )
        
        conn.commit()
        logger.debug(f"Позиция для кошелька {wallet_address} в пуле {pool_address} сохранена")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении позиции: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

# Асинхронные функции

async def save_token_price_async(token_address: str, price: float, timestamp: Optional[int] = None) -> bool:
    """Сохранение цены токена в базе данных (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if timestamp is None:
            timestamp = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO token_prices (token_address, price, timestamp) 
            VALUES (%s, %s, %s)
            ON CONFLICT (token_address, timestamp) 
            DO UPDATE SET price = EXCLUDED.price
            """,
            (token_address, price, timestamp)
        )
        
        conn.commit()
        logger.debug(f"Цена для токена {token_address} сохранена: {price}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении цены токена: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_token_price_history_async(token_address: str, days: int = 7) -> List[Dict[str, Any]]:
    """Получение истории цен токена за указанное количество дней (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Вычисляем временную метку для начала периода (N дней назад)
        from_time = int((datetime.now() - timedelta(days=days)).timestamp())
        
        query = """
            SELECT token_address, price, timestamp 
            FROM token_prices 
            WHERE token_address = %s AND timestamp >= %s
            ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (token_address, from_time))
        result = cursor.fetchall()
        
        return list(result)
    except Exception as e:
        logger.error(f"Ошибка при получении истории цен токена: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_latest_token_price_async(token_address: str) -> Optional[float]:
    """Получение последней цены токена (асинхронная версия)"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT price 
            FROM token_prices 
            WHERE token_address = %s 
            ORDER BY timestamp DESC 
            LIMIT 1
            """,
            (token_address,)
        )
        
        row = cursor.fetchone()
        if row:
            return row["price"]
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении последней цены токена: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close() 