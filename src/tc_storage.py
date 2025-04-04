from pytonconnect.storage import IStorage
import logging
import json
from src import db_bot
import psycopg2
from psycopg2.extras import RealDictCursor

# Получение логгера
logger = logging.getLogger(__name__)

class TcStorage(IStorage):
    """Реализация хранилища TonConnect через PostgreSQL базу данных"""

    def __init__(self, chat_id: int):
        """
        Инициализация хранилища
        :param chat_id: ID пользователя в Telegram
        """
        self.chat_id = chat_id
        self._ensure_connection_table()

    def _ensure_connection_table(self):
        """Создаем таблицу для хранения данных подключения, если ее нет"""
        try:
            conn = db_bot.get_connection()
            cursor = conn.cursor()
            
            # Создаем таблицу tonconnect_storage
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tonconnect_storage (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL UNIQUE,
                connection_data JSONB NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            ''')
            
            # Создаем индекс для быстрого поиска
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tonconnect_user_id ON tonconnect_storage(user_id)')
            
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating tonconnect_storage table: {e}")
        finally:
            if 'conn' in locals() and conn:
                cursor.close()
                conn.close()

    async def set_item(self, key: str, value: str):
        """
        Сохранение значения в базу данных
        :param key: Ключ
        :param value: Значение
        """
        try:
            import time
            current_time = int(time.time())
            
            conn = db_bot.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Проверяем, существует ли запись для пользователя
            cursor.execute("SELECT connection_data FROM tonconnect_storage WHERE user_id = %s", (self.chat_id,))
            row = cursor.fetchone()
            
            if row:
                # Обновляем существующие данные
                data = dict(row['connection_data'])
                data[key] = value
                
                cursor.execute("""
                UPDATE tonconnect_storage 
                SET connection_data = %s, updated_at = %s
                WHERE user_id = %s
                """, (json.dumps(data), current_time, self.chat_id))
            else:
                # Создаем новую запись
                data = {key: value}
                cursor.execute("""
                INSERT INTO tonconnect_storage (user_id, connection_data, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """, (self.chat_id, json.dumps(data), current_time, current_time))
                
            conn.commit()
        except Exception as e:
            logger.error(f"Error setting item in TcStorage: {e}")
        finally:
            if 'conn' in locals() and conn:
                cursor.close()
                conn.close()

    async def get_item(self, key: str, default_value: str = None):
        """
        Получение значения из базы данных
        :param key: Ключ
        :param default_value: Значение по умолчанию
        :return: Значение или default_value
        """
        try:
            conn = db_bot.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT connection_data FROM tonconnect_storage WHERE user_id = %s", (self.chat_id,))
            row = cursor.fetchone()
            
            if row:
                data = dict(row['connection_data'])
                return data.get(key, default_value)
            return default_value
        except Exception as e:
            logger.error(f"Error getting item from TcStorage: {e}")
            return default_value
        finally:
            if 'conn' in locals() and conn:
                cursor.close()
                conn.close()

    async def remove_item(self, key: str):
        """
        Удаление значения из базы данных
        :param key: Ключ
        """
        try:
            import time
            current_time = int(time.time())
            
            conn = db_bot.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT connection_data FROM tonconnect_storage WHERE user_id = %s", (self.chat_id,))
            row = cursor.fetchone()
            
            if row:
                data = dict(row['connection_data'])
                if key in data:
                    del data[key]
                    
                    if not data:  # Если данных больше нет, удаляем запись
                        cursor.execute("DELETE FROM tonconnect_storage WHERE user_id = %s", (self.chat_id,))
                    else:
                        cursor.execute("""
                        UPDATE tonconnect_storage 
                        SET connection_data = %s, updated_at = %s
                        WHERE user_id = %s
                        """, (json.dumps(data), current_time, self.chat_id))
                        
                conn.commit()
        except Exception as e:
            logger.error(f"Error removing item from TcStorage: {e}")
        finally:
            if 'conn' in locals() and conn:
                cursor.close()
                conn.close()

# Функция для восстановления всех активных подключений
async def restore_connections():
    """
    Восстановление всех активных подключений TonConnect
    """
    from connector import get_connector
    
    try:
        conn = db_bot.get_connection()
        cursor = conn.cursor()
        
        # Получаем всех пользователей с активными подключениями
        cursor.execute("SELECT user_id FROM tonconnect_storage")
        rows = cursor.fetchall()
        user_ids = [row[0] for row in rows]
        
        logger.info(f"Found {len(user_ids)} stored connections")
        
        for user_id in user_ids:
            try:
                # Создаем коннектор и пытаемся восстановить подключение
                connector = get_connector(user_id)
                connected = await connector.restore_connection()
                
                if connected:
                    logger.info(f"Successfully restored connection for user {user_id}")
                else:
                    logger.info(f"No active connection found for user {user_id}")
                    # Удаляем все данные этого пользователя если подключение не удалось восстановить
                    cursor.execute("DELETE FROM tonconnect_storage WHERE user_id = %s", (user_id,))
                    conn.commit()
            except Exception as e:
                logger.error(f"Error restoring connection for user_id {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in restore_connections: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()