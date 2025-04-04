from pytonconnect import TonConnect

import config
from tc_storage import TcStorage
import logging
from src import db_bot
import time
import os 

# Кэш коннекторов для каждого пользователя
_connectors = {}

logger = logging.getLogger(__name__)

def get_connector(chat_id: int):
    """
    Получение экземпляра TonConnect для пользователя
    :param chat_id: ID пользователя в Telegram
    :return: Экземпляр TonConnect
    """
    if chat_id not in _connectors:
        # Создаем новый экземпляр коннектора
        storage = TcStorage(chat_id)
        connector = TonConnect(config.MANIFEST_URL, storage=storage, api_tokens={'tonapi': os.getenv('TONCONNECTOR_TOKEN')})
        _connectors[chat_id] = connector
        
        # Добавляем обработчики событий
        def on_status_change(wallet_info):
            save_connection_status(chat_id, wallet_info)
        
        def on_status_error(error):
            logger.error(f"Connection status error for user {chat_id}: {error}")
        
        connector.on_status_change(on_status_change, on_status_error)
    
    return _connectors[chat_id]

def save_connection_status(chat_id: int, wallet_info):
    """
    Сохранение информации о состоянии подключения кошелька
    :param chat_id: ID пользователя
    :param wallet_info: Информация о подключенном кошельке
    """
    try:
        # Если кошелек успешно подключен
        if wallet_info:
            # Получаем адрес кошелька безопасным способом
            wallet_address = None
            if hasattr(wallet_info, 'address'):
                wallet_address = wallet_info.address
            elif hasattr(wallet_info, 'account') and hasattr(wallet_info.account, 'address'):
                wallet_address = wallet_info.account.address
            
            # Логируем информацию о подключении
            address_info = f" с адресом {wallet_address}" if wallet_address else ""
            logger.info(f"User {chat_id} connected wallet{address_info}")
            
            # Сохраняем информацию о пользователе в БД
            db_bot.save_user(
                user_id=chat_id,
                username=str(chat_id),  # Используем chat_id как имя пользователя
                first_name="TON Wallet User",  # Заглушка
                last_name=""
            )
            
            # Обновляем время последней активности
            db_bot.update_user_activity(chat_id)
        else:
            # Пользователь отключил кошелек
            logger.info(f"User {chat_id} disconnected wallet")
    except Exception as e:
        logger.error(f"Error saving connection status: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def get_wallet_address(user_id: int) -> str:
    """
    Получение адреса подключенного кошелька пользователя
    :param user_id: ID пользователя в Telegram
    :return: Адрес кошелька или None
    """
    try:
        connector = get_connector(user_id)
        if not connector.connected:
            return None
            
        # Безопасно получаем информацию о кошельке
        wallet_info = connector.account
        if not wallet_info:
            return None
            
        # Получаем адрес кошелька безопасным способом
        wallet_address = None
        if hasattr(wallet_info, 'address'):
            wallet_address = wallet_info.address
        elif hasattr(wallet_info, 'account') and hasattr(wallet_info.account, 'address'):
            wallet_address = wallet_info.account.address
            
        if not wallet_address:
            logger.warning(f"Could not extract wallet address for user {user_id}")
            return None
            
        # Обновляем время последней активности
        db_bot.update_user_activity(user_id)
        
        return wallet_address
    except Exception as e:
        logger.error(f"Error getting wallet address: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
