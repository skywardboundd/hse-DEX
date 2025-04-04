import sqlite3
import datetime
import logging
import json

# Получение логгера
logger = logging.getLogger(__name__)

# Временный экземпляр базы данных
db = None

async def create_db():
    global db
    print("Создание базы данных")
    db = sqlite3.connect('dex_bot.db', check_same_thread=False)
    db.row_factory = sqlite3.Row
    
    # Создание таблиц если не существуют
    cursor = db.cursor()
    
    # Создание таблиц при первом запуске
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        wallet_address TEXT,
        ref INTEGER DEFAULT 0,
        sub_at INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorite_pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wallet_address TEXT NOT NULL,
        token1_symbol TEXT NOT NULL,
        token1_name TEXT NOT NULL,
        token1_address TEXT NOT NULL,
        token2_symbol TEXT NOT NULL,
        token2_name TEXT NOT NULL,
        token2_address TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(wallet_address, token1_address, token2_address)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS liquidity_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wallet_address TEXT NOT NULL,
        token1_symbol TEXT NOT NULL,
        token1_name TEXT NOT NULL,
        token1_address TEXT NOT NULL,
        token1_amount REAL NOT NULL,
        token2_symbol TEXT NOT NULL,
        token2_name TEXT NOT NULL,
        token2_address TEXT NOT NULL,
        token2_amount REAL NOT NULL,
        pool_address TEXT,
        lp_tokens REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица для подключений TonConnect
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tonconnect_storage (
        chat_id INTEGER PRIMARY KEY,
        connection_data TEXT,
        last_event_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    db.commit()

def check_holder_exist(telegram_id: int):
    cursor = db.cursor()
    cursor.execute('SELECT 1 FROM holders WHERE telegram_id = ?', (telegram_id,))
    row = cursor.fetchone()
    return row is not None

def check_whale_exist(telegram_id: int):
    cursor = db.cursor()
    cursor.execute('SELECT 1 FROM whales WHERE telegram_id = ?', (telegram_id,))
    row = cursor.fetchone()
    return row is not None

def add_holders_record(id: int, username: str, address: str, amount: int):
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO holders (telegram_id, username, address, amount, enter_time) VALUES (?, ?, ?, ?, ?)
    ''', (id, username, address, amount, int(datetime.datetime.now().timestamp())))
    db.commit()

def add_whales_record(id: int, username: str, address: str, amount: int):
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO whales (telegram_id, username, address, amount, enter_time) VALUES (?, ?, ?, ?, ?)
    ''', (id, username, address, amount, int(datetime.datetime.now().timestamp())))
    db.commit()

async def add_users_record(id: int, address: str, ref: int, lang: str, sub_at: int, username: str):
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE id = ?', (id,))
    result = cursor.fetchone()
    if result[0] > 0:
        return
    cursor.execute('''
    INSERT INTO users (id, address, ref, lang, sub_at, username) VALUES (?, ?, ?, ?, ?, ?)
    ''', (id, address, ref, lang, sub_at, username))
    db.commit()

async def update_user_address(id: int, new_address: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE users SET address = ? WHERE id = ?
    ''', (new_address, id))
    db.commit()

async def corrupted_address(address: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE users SET address="#" WHERE address = ?
    ''', (address,))
    db.commit()

async def update_user_sub(id: int, sub: int):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE users SET sub_at = ? WHERE id = ?
    ''', (sub, id))
    db.commit()

async def update_user_lang(id: int, lang: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE users SET lang = ? WHERE id = ?
    ''', (lang, id))
    db.commit()

async def update_user_username(id: int, username: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE users SET username = ? WHERE id = ?
    ''', (username, id))
    db.commit()

async def add_vars_record(variable_name: str, value: str):
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO vars (variable_name, value) VALUES (?, ?)
    ''', (variable_name, value))
    db.commit()

async def add_jettons_record(jetton: str, value: int, master_address: str):
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO jettons (jetton, value, master_address) VALUES (?, ?, ?)
    ''', (jetton, value, master_address))
    db.commit()

async def get_users_record(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT * FROM users WHERE id = ?
    ''', (id,))
    return cursor.fetchone()

async def is_unique_address(address: str) -> bool:
    cursor = db.cursor()
    cursor.execute('''
    SELECT COUNT(*) FROM users WHERE address = ?
    ''', (address,))
    count = cursor.fetchone()
    return count[0] == 0

async def get_users_lang(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT lang FROM users WHERE id = ?
    ''', (id,))
    res = cursor.fetchone()
    if res is None:
        res = 'ru'
    return res

async def get_users_ref(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT ref FROM users WHERE id = ?
    ''', (id,))
    return cursor.fetchone()

async def get_users_sub(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT sub_at FROM users WHERE id = ?
    ''', (id,))
    return cursor.fetchone()

async def get_users_addr(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT address FROM users WHERE id = ?
    ''', (id,))
    return cursor.fetchone()

async def get_vars_record(variable_name: str):
    cursor = db.cursor()
    cursor.execute('''
    SELECT * FROM vars WHERE variable_name = ?
    ''', (variable_name,))
    return cursor.fetchone()

async def get_jettons_record(jetton: str):
    cursor = db.cursor()
    cursor.execute('''
    SELECT * FROM jettons WHERE jetton = ?
    ''', (jetton,))
    return cursor.fetchone()

async def update_vars_record(variable_name: str, new_value: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE vars SET value = ? WHERE variable_name = ?
    ''', (new_value, variable_name))
    db.commit()

async def update_jettons_record(jetton: str, new_value: int, new_master_address: str):
    cursor = db.cursor()
    cursor.execute('''
    UPDATE jettons SET value = ?, master_address = ? WHERE jetton = ?
    ''', (new_value, new_master_address, jetton))
    db.commit()


async def get_all_holders():
    cursor = db.cursor()
    cursor.execute('SELECT * FROM holders')
    results = cursor.fetchall()
    return results


async def get_all_whales():
    cursor = db.cursor()
    cursor.execute('SELECT * FROM whales')
    results = cursor.fetchall()
    return results

async def get_all_jettons():
    cursor = db.cursor()
    cursor.execute('SELECT * FROM jettons')
    results = cursor.fetchall()
    return results

async def get_all_refs():
    cursor = db.cursor()
    cursor.execute('SELECT * FROM refs')
    results = cursor.fetchall()
    return results

async def get_ref_discount(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT discount FROM refs WHERE ref = ?
    ''', (id,))
    return cursor.fetchone()

async def get_ref_count(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT COUNT(*) FROM users WHERE ref = ?
    ''', (id,))
    return cursor.fetchone()

async def get_ref_count_with_sub(id: int):
    cursor = db.cursor()
    cursor.execute('''
    SELECT COUNT(*) 
    FROM users 
    WHERE ref = ? AND sub_at != 0
    ''', (id,))
    return cursor.fetchone()

async def add_refs_record(ref: int, name: str, discount: int):
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO refs (ref, name, discount) VALUES (?, ?, ?)
    ''', (ref, name, discount))
    db.commit()

async def add_staking_jvt_record(indx: int, address: str, owner_address: str, amount: int):
    cursor = db.cursor()
    cursor.execute('SELECT 1 FROM staking_jvt WHERE indx = ?', (indx,))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute('''
        INSERT INTO staking_jvt (indx, address, owner_address, amount)
        VALUES (?, ?, ?, ?)
        ''', (indx, address, owner_address, amount))
    else:
        cursor.execute('''
        UPDATE staking_jvt
        SET address = ?,
            owner_address = ?,
            amount = ?
        WHERE indx = ?
        ''', (address, owner_address, amount, indx))
    
    db.commit()

async def get_staking_jvt_amount(address: str):
    cursor = db.cursor()
    cursor.execute('''
    SELECT * FROM staking_jvt WHERE owner_address = ?
    ''', (address,))
    res = cursor.fetchall()
    if res is None:
        return 0
    amount = 0
    for i in res:
        amount += i[-1]
    return amount

async def add_favorite_pair(wallet_address: str, token1: dict, token2: dict):
    """Добавление пары в избранное"""
    try:
        cursor = db.cursor()
        
        # Проверяем, нет ли уже такой пары
        cursor.execute('''
        SELECT 1 FROM favorite_pairs 
        WHERE wallet_address = ? AND token1_address = ? AND token2_address = ?
        ''', (wallet_address, token1['address'], token2['address']))
        
        if cursor.fetchone():
            print(f"Пара уже существует для {wallet_address}")
            return False
                
        # Добавляем пару в базу данных
        cursor.execute('''
        INSERT INTO favorite_pairs 
        (wallet_address, token1_symbol, token1_name, token1_address, 
        token2_symbol, token2_name, token2_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            wallet_address,
            token1['symbol'], token1['name'], token1['address'],
            token2['symbol'], token2['name'], token2['address']
        ))
        
        db.commit()
        print(f"Добавлена пара для {wallet_address}: {token1['symbol']}/{token2['symbol']}")
        return True
    except Exception as e:
        print(f"Ошибка при добавлении пары: {e}")
        return False

async def remove_favorite_pair(wallet_address: str, token1_symbol: str, token2_symbol: str):
    """Удаление пары из избранного"""
    try:
        cursor = db.cursor()
        
        # Удаляем пару из базы данных
        cursor.execute('''
        DELETE FROM favorite_pairs 
        WHERE wallet_address = ? AND token1_symbol = ? AND token2_symbol = ?
        ''', (wallet_address, token1_symbol, token2_symbol))
        
        db.commit()
        
        if cursor.rowcount > 0:
            print(f"Удалена пара для {wallet_address}: {token1_symbol}/{token2_symbol}")
            return True
                
        return False
    except Exception as e:
        print(f"Ошибка при удалении пары: {e}")
        return False

async def get_favorite_pairs(wallet_address: str):
    """Получение избранных пар пользователя"""
    try:
        cursor = db.cursor()
        
        cursor.execute('''
        SELECT token1_symbol, token1_name, token1_address, 
               token2_symbol, token2_name, token2_address,
               created_at
        FROM favorite_pairs
        WHERE wallet_address = ?
        ORDER BY created_at DESC
        ''', (wallet_address,))
        
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'token1': {
                    'symbol': row[0],
                    'name': row[1],
                    'address': row[2]
                },
                'token2': {
                    'symbol': row[3],
                    'name': row[4],
                    'address': row[5]
                },
                'created_at': row[6]
            })
            
        return results
    except Exception as e:
        print(f"Ошибка при получении пар: {e}")
        return []

async def add_liquidity_position(wallet_address: str, token1: dict, token2: dict, 
                                token1_amount: float, token2_amount: float, 
                                pool_address: str = None, lp_tokens: float = 0):
    """
    Добавляет запись о позиции ликвидности пользователя
    
    Args:
        wallet_address: Адрес кошелька пользователя
        token1, token2: Информация о токенах (словари с полями symbol, name, address)
        token1_amount, token2_amount: Количество токенов
        pool_address: Адрес пула ликвидности (опционально)
        lp_tokens: Количество полученных LP токенов (опционально)
        
    Returns:
        int: ID позиции или None в случае ошибки
    """
    try:
        cursor = db.cursor()
        cursor.execute('''
        INSERT INTO liquidity_positions 
        (wallet_address, token1_symbol, token1_name, token1_address, token1_amount,
        token2_symbol, token2_name, token2_address, token2_amount, pool_address, lp_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            wallet_address,
            token1['symbol'], token1['name'], token1['address'], token1_amount,
            token2['symbol'], token2['name'], token2['address'], token2_amount,
            pool_address, lp_tokens
        ))
        db.commit()
        
        # Возвращаем ID добавленной записи
        return cursor.lastrowid
    except Exception as e:
        print(f"Error adding liquidity position: {e}")
        return None

async def remove_liquidity_position(position_id: int):
    """
    Удаляет позицию ликвидности по ID
    
    Args:
        position_id: ID позиции для удаления
        
    Returns:
        bool: True при успешном удалении
    """
    try:
        cursor = db.cursor()
        cursor.execute('''
        DELETE FROM liquidity_positions WHERE id = ?
        ''', (position_id,))
        db.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error removing liquidity position: {e}")
        return False

async def get_liquidity_positions(wallet_address: str):
    """
    Получает все позиции ликвидности пользователя
    
    Args:
        wallet_address: Адрес кошелька пользователя
        
    Returns:
        list: Список позиций ликвидности
    """
    try:
        cursor = db.cursor()
        cursor.execute('''
        SELECT id, token1_symbol, token1_name, token1_address, token1_amount,
               token2_symbol, token2_name, token2_address, token2_amount,
               pool_address, lp_tokens, created_at
        FROM liquidity_positions
        WHERE wallet_address = ?
        ORDER BY created_at DESC
        ''', (wallet_address,))
        
        rows = cursor.fetchall()
        positions = []
        
        for row in rows:
            positions.append({
                'id': row[0],
                'token1': {
                    'symbol': row[1],
                    'name': row[2],
                    'address': row[3]
                },
                'token1_amount': row[4],
                'token2': {
                    'symbol': row[5],
                    'name': row[6],
                    'address': row[7]
                },
                'token2_amount': row[8],
                'pool_address': row[9],
                'lp_tokens': row[10],
                'created_at': row[11]
            })
        
        return positions
    except Exception as e:
        print(f"Error getting liquidity positions: {e}")
        return []

# Функции для работы с TonConnect
async def save_tonconnect_data(chat_id: int, key: str, value: str):
    """Сохранение данных подключения TonConnect"""
    try:
        cursor = db.cursor()
        
        # Получаем текущие данные
        cursor.execute('SELECT connection_data FROM tonconnect_storage WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        
        if row:
            # Обновляем существующие данные
            data = json.loads(row['connection_data'])
            data[key] = value
            
            cursor.execute('''
            UPDATE tonconnect_storage 
            SET connection_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
            ''', (json.dumps(data), chat_id))
        else:
            # Создаем новую запись
            data = {key: value}
            cursor.execute('''
            INSERT INTO tonconnect_storage (chat_id, connection_data)
            VALUES (?, ?)
            ''', (chat_id, json.dumps(data)))
            
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving TonConnect data: {e}")
        return False

async def get_tonconnect_data(chat_id: int, key: str, default_value: str = None):
    """Получение данных подключения TonConnect"""
    try:
        cursor = db.cursor()
        cursor.execute('SELECT connection_data FROM tonconnect_storage WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        
        if row:
            data = json.loads(row['connection_data'])
            return data.get(key, default_value)
        return default_value
    except Exception as e:
        logger.error(f"Error getting TonConnect data: {e}")
        return default_value

async def remove_tonconnect_data(chat_id: int, key: str):
    """Удаление данных подключения TonConnect"""
    try:
        cursor = db.cursor()
        cursor.execute('SELECT connection_data FROM tonconnect_storage WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        
        if row:
            data = json.loads(row['connection_data'])
            if key in data:
                del data[key]
                
                if not data:  # Если данных больше нет, удаляем запись
                    cursor.execute('DELETE FROM tonconnect_storage WHERE chat_id = ?', (chat_id,))
                else:
                    cursor.execute('''
                    UPDATE tonconnect_storage 
                    SET connection_data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                    ''', (json.dumps(data), chat_id))
                    
            db.commit()
        return True
    except Exception as e:
        logger.error(f"Error removing TonConnect data: {e}")
        return False

async def get_all_tonconnect_chat_ids():
    """Получение всех chat_id с активными подключениями"""
    try:
        cursor = db.cursor()
        cursor.execute('SELECT chat_id FROM tonconnect_storage')
        return [row['chat_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting TonConnect chat IDs: {e}")
        return []
