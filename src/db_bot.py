import os
import time
import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import dotenv

# Загружаем переменные окружения из .env файла
dotenv.load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_bot')

# Получаем параметры подключения к базе данных
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'dex_db')
DB_USER = os.getenv('DB_USER', 'sdf')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

def get_connection():
    """Получение соединения с базой данных PostgreSQL"""
    try:
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
    """Инициализация базы данных для Telegram бота"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at INTEGER NOT NULL,
            last_activity INTEGER NOT NULL
        )
        ''')
        
        # Создаем таблицу избранных пар
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorite_pairs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            token1 TEXT NOT NULL,
            token2 TEXT NOT NULL,
            pool_address TEXT,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, token1, token2)
        )
        ''')
        
        # Индекс для быстрого поиска по пользователю
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorite_pairs_user_id ON favorite_pairs(user_id)')
        
        conn.commit()
        logger.info("База данных бота успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных бота: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

# Функции для работы с пользователями

def save_user(user_id: int, username: str = None, first_name: str = None, 
              last_name: str = None) -> bool:
    """Сохранение или обновление информации о пользователе"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        cursor.execute(
            """
            INSERT INTO bot_users 
            (user_id, username, first_name, last_name, created_at, last_activity)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_activity = EXCLUDED.last_activity
            """,
            (user_id, username, first_name, last_name, current_time, current_time)
        )
        
        conn.commit()
        logger.debug(f"Пользователь {user_id} ({username}) сохранен")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользователя: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

def update_user_activity(user_id: int) -> bool:
    """Обновление времени последней активности пользователя"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        cursor.execute(
            "UPDATE bot_users SET last_activity = %s WHERE user_id = %s",
            (current_time, user_id)
        )
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении активности пользователя {user_id}: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

# Функции для работы с избранными парами

def add_favorite_pair(user_id: int, token1: str, token2: str, pool_address: Optional[str] = None) -> bool:
    """Добавление пары токенов в избранное"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(time.time())
        
        # Всегда сохраняем токены в алфавитном порядке для консистентности
        if token1.lower() > token2.lower():
            token1, token2 = token2, token1
            
        cursor.execute(
            """
            INSERT INTO favorite_pairs 
            (user_id, token1, token2, pool_address, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, token1, token2) 
            DO UPDATE SET pool_address = EXCLUDED.pool_address
            """,
            (user_id, token1, token2, pool_address, current_time)
        )
        
        conn.commit()
        logger.debug(f"Пара {token1}/{token2} добавлена в избранное пользователем {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении пары в избранное: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

def remove_favorite_pair(user_id: int, token1: str, token2: str) -> bool:
    """Удаление пары токенов из избранного"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Всегда проверяем токены в обоих порядках
        cursor.execute(
            """
            DELETE FROM favorite_pairs 
            WHERE user_id = %s AND ((token1 = %s AND token2 = %s) OR (token1 = %s AND token2 = %s))
            """,
            (user_id, token1, token2, token2, token1)
        )
        
        conn.commit()
        logger.debug(f"Пара {token1}/{token2} удалена из избранного пользователя {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении пары из избранного: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

def get_favorite_pairs(user_id: int) -> List[Dict[str, Any]]:
    """Получение списка избранных пар пользователя"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT * FROM favorite_pairs 
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        
        pairs = cursor.fetchall()
        return [dict(pair) for pair in pairs]
    except Exception as e:
        logger.error(f"Ошибка при получении избранных пар пользователя {user_id}: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

def is_pair_favorite(user_id: int, token1: str, token2: str) -> bool:
    """Проверка, является ли пара избранной для пользователя"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id FROM favorite_pairs 
            WHERE user_id = %s AND ((token1 = %s AND token2 = %s) OR (token1 = %s AND token2 = %s))
            """,
            (user_id, token1, token2, token2, token1)
        )
        
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке избранной пары: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

# Инициализация базы данных при импорте модуля
try:
    init_db()
    logger.info("База данных для Telegram бота успешно инициализирована")
except Exception as e:
    logger.error(f"Ошибка при инициализации базы данных для Telegram бота: {e}")
