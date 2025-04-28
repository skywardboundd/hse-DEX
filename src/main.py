# main.py

import sys
import logging
import asyncio
import time
from datetime import datetime
import os
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path:
    sys.path.append(root_path)

import pytonconnect.exceptions
from pytoniq_core import Address
from pytonconnect import TonConnect

from nacl.utils import random

from pytonconnect.parsers import WalletInfo

from src import config
from connector import get_connector, get_wallet_address
from src import db_bot  # Импортируем модуль db_bot для работы с избранными парами

from io import BytesIO
import qrcode
from aiogram.types import BufferedInputFile


from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.deep_linking import create_start_link, decode_payload

logger = logging.getLogger(__file__)


from pytoniq import LiteBalancer, HighloadWallet
from pytoniq import WalletV4R2, Address
from pytoniq import begin_cell, Cell
import json 


from pytonapi import AsyncTonapi
# Импортируем из core вместо локального модуля src/dex.py
from core.dex import DexManager
# Импортируем функции из модуля DB для настройки соединения с PostgreSQL
from core.db import init_db, get_token, get_all_tokens, save_token
from psycopg2.extras import RealDictCursor

from pytonconnect.exceptions import UserRejectsError
from pytonconnect.storage import FileStorage

# conn.autocommit = True  # включение автокоммита
# cur = conn.cursor()

API_KEY = os.getenv("TONAPI_KEY")
client = 0

dp = Dispatcher()
bot = Bot(config.TOKEN, defaults=DefaultBotProperties(parse_mode=ParseMode.HTML))
form_router = Router()

class States(StatesGroup):
    inTransaction = State()

class DexStates(StatesGroup):
    waiting_for_token1 = State()
    waiting_for_token2 = State()
    waiting_for_amount = State()
    waiting_for_swap = State()
    waiting_for_wallet = State()
    waiting_for_liquidity_token1 = State()
    waiting_for_liquidity_token2 = State()
    waiting_for_liquidity_amount1 = State()
    waiting_for_liquidity_amount2 = State()
    # Новые состояния для добавления токенов
    waiting_for_token_master_address = State()
    waiting_for_token_decimals = State()
    waiting_for_token_name = State()

tonapi = AsyncTonapi(api_key=config.TONAPI_KEY)

dex_manager = DexManager()


connectors = {}

def generate_payload(ttl: int) -> str:
    payload = bytearray(random(8))
    ts = int(datetime.datetime.now().timestamp()) + ttl
    payload.extend(ts.to_bytes(8, 'big'))
    return payload.hex()

def check_payload(payload: str, wallet_info: WalletInfo):
    if len(payload) < 32:
        print('Payload length error')
        return False
    if not wallet_info.check_proof(payload):
        print('Check proof failed')
        return False
    ts = int(payload[16:32], 16)
    if datetime.datetime.now().timestamp() > ts:
        print('Request timeout error')
        return False
    return True

# Основные команды
@dp.message(CommandStart())
async def command_start_handler(message: Message):
    connector = get_connector(message.chat.id)
    connected = await connector.restore_connection()
    
    if connected:
        await menu(message)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="👛 Подключить кошелек", callback_data="wallets")
    builder.adjust(1)
    
    await message.answer(
        "👋 Добро пожаловать в DEX бота!\n"
        "Для начала работы необходимо подключить кошелек:",
        reply_markup=builder.as_markup()
    )

async def menu(message: Message):
    """Показывает основное меню DEX бота"""
    try:
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Цены токенов", callback_data="prices")
        builder.button(text="💧 Ликвидность", callback_data="liquidity")
        builder.button(text="🔄 Своп", callback_data="swap")
        builder.button(text="❌ Отключить кошелек", callback_data="disconnect")
        builder.adjust(2)
        
        # Всегда отправляем новое сообщение для меню, чтобы избежать проблем с редактированием
        await message.answer(
            "🔹 Главное меню DEX бота\n"
            "Выберите действие:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        print(f"Error in menu: {e}")
        # В случае ошибки просто отправляем меню ещё раз
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Цены токенов", callback_data="prices")
        builder.button(text="💧 Ликвидность", callback_data="liquidity")
        builder.button(text="🔄 Своп", callback_data="swap")
        builder.button(text="❌ Отключить кошелек", callback_data="disconnect")
        builder.adjust(2)
        
        await message.answer(
            "🔹 Главное меню DEX бота\n"
            "Выберите действие:",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(F.data == "menu")
async def callback_menu(callback: CallbackQuery):
    """Обработчик кнопки 'Меню'"""
    try:
        await menu(callback.message)
    except Exception as e:
        print(f"Error in callback_menu: {e}")
        # В случае ошибки пробуем отправить меню через answer
        await callback.message.answer(
            "Произошла ошибка при показе меню. Пожалуйста, попробуйте снова.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 В меню", callback_data="menu")
                .as_markup()
        )

async def show_wallets_page(callback: CallbackQuery, page: int = 0):
    try:
        connector = get_connector(callback.from_user.id)
        wallets_list = connector.get_wallets()
        
        # Разбиваем кошельки на страницы по 4
        wallets_per_page = 4
        total_pages = (len(wallets_list) + wallets_per_page - 1) // wallets_per_page
        
        # Проверка на случай если страница выходит за пределы
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1
        
        # Выбираем кошельки для текущей страницы
        start_idx = page * wallets_per_page
        end_idx = min(start_idx + wallets_per_page, len(wallets_list))
        current_wallets = wallets_list[start_idx:end_idx]
        
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопки кошельков
        for wallet in current_wallets:
            builder.button(text=wallet['name'], callback_data=f'connect:{wallet["name"]}')
        
        builder.adjust(1)  # По одной кнопке в ряду для кошельков
        # Добавляем кнопки навигации в одну строку
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"wallets_page:{page-1}"))
        else:
            nav_buttons.append(InlineKeyboardButton(text="⛔️", callback_data="no_action"))
            
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"wallets_page:{page+1}"))
        else:
            nav_buttons.append(InlineKeyboardButton(text="⛔️", callback_data="no_action"))
        
        builder.row(*nav_buttons)
        
        # Добавляем кнопку возврата в меню, если пользователь уже подключен
        if connector.connected:
            builder.button(text="🔙 В меню", callback_data="menu")
        
        
        # Проверяем, есть ли текст в сообщении для редактирования
        if hasattr(callback.message, 'text') and callback.message.text:
            # Если текст есть, редактируем сообщение
            await callback.message.edit_text(
                f"Выберите кошелек для подключения (страница {page+1}/{total_pages}):",
                reply_markup=builder.as_markup()
            )
        else:
            # Если текста нет, отправляем новое сообщение
            await callback.message.answer(
                f"Выберите кошелек для подключения (страница {page+1}/{total_pages}):",
                reply_markup=builder.as_markup()
            )
    except Exception as e:
        print(f"Error in show_wallets_page: {e}")
        # В случае ошибки отправляем новое сообщение
        await callback.message.answer(
            "Произошла ошибка при загрузке кошельков. Пожалуйста, попробуйте снова.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 В меню", callback_data="menu")
                .as_markup()
        )

@dp.callback_query(F.data == "wallets")
async def choose_wallets(callback: CallbackQuery):
    try:

        if hasattr(callback.message, 'text') and callback.message.text:
            # Если есть текст, редактируем сообщение
            await show_wallets_page(callback, 0)
        else:
            # Если текста нет (например, сообщение с фото), отправляем новое сообщение
            connector = get_connector(callback.from_user.id)
            wallets_list = connector.get_wallets()
            
            # Разбиваем кошельки на страницы по 4
            wallets_per_page = 4
            total_pages = (len(wallets_list) + wallets_per_page - 1) // wallets_per_page
            
            builder = InlineKeyboardBuilder()
            
            # Выбираем первые 4 кошелька для первой страницы
            current_wallets = wallets_list[:min(wallets_per_page, len(wallets_list))]
            
            # Добавляем кнопки кошельков
            for wallet in current_wallets:
                builder.button(text=wallet['name'], callback_data=f'connect:{wallet["name"]}')
            

            if len(wallets_list) > wallets_per_page:
                builder.row(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"wallets_page:1"))
            

            if connector.connected:
                builder.button(text="🔙 В меню", callback_data="menu")
            
            builder.adjust(1)  

            await callback.message.answer(
                f"Выберите кошелек для подключения (страница 1/{total_pages}):",
                reply_markup=builder.as_markup()
            )
    except Exception as e:
        print(f"Error in choose_wallets: {e}")

        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Подключить кошелек", callback_data="wallets")
        builder.button(text="🔙 В меню", callback_data="menu")
        builder.adjust(1)
        
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(F.data.startswith("wallets_page:"))
async def handle_wallets_pagination(callback: CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
        await show_wallets_page(callback, page)
    except Exception as e:
        print(f"Error in handle_wallets_pagination: {e}")

        await callback.message.answer(
            "Произошла ошибка при переключении страницы. Пожалуйста, попробуйте снова.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="Вернуться к кошелькам", callback_data="wallets")
                .button(text="🔙 В меню", callback_data="menu")
                .adjust(1)
                .as_markup()
        )

@dp.callback_query(F.data.startswith("connect:"))
async def connect_wallet(callback: CallbackQuery):
    try:
        wallet_name = callback.data.split(":")[1]
        connector = get_connector(callback.from_user.id)
        
        if connector.connected:
            await menu(callback.message)
            return
        
        # Получаем список всех кошельков через connector.get_wallets()
        wallets_list = connector.get_wallets()
        wallet = None
        
        # Ищем выбранный кошелек в списке
        for w in wallets_list:
            if w['name'] == wallet_name:
                wallet = w
                break
        
        if wallet is None:
            # Проверяем, есть ли текст в сообщении для редактирования
            if hasattr(callback.message, 'text') and callback.message.text:
                await callback.message.edit_text(
                    f"❌ Неизвестный кошелек: {wallet_name}",
                    reply_markup=InlineKeyboardBuilder().button(text="Назад", callback_data="wallets").as_markup()
                )
            else:
                await callback.message.answer(
                    f"❌ Неизвестный кошелек: {wallet_name}",
                    reply_markup=InlineKeyboardBuilder().button(text="Назад", callback_data="wallets").as_markup()
                )
            return
        
        # Отображаем информацию о подготовке QR-кода прямо в текущем сообщении
        # Проверяем, есть ли текст в сообщении для редактирования
        start_message = None
        if hasattr(callback.message, 'text') and callback.message.text:
            # Если есть текст, редактируем сообщение
            start_message = await callback.message.edit_text("⏳ Подготовка QR-кода...")
        else:
            # Если нет текста, отправляем новое сообщение
            start_message = await callback.message.answer("⏳ Подготовка QR-кода...")
        
        f = True
        def status_changed(wallet_info):
            nonlocal f
            if wallet_info is not None:
                if not check_payload(proof_payload, wallet_info):
                    f = False
            unsubscribe()
        
        def status_error(e):
            nonlocal f
            f = False
            unsubscribe()
        
        proof_payload = generate_payload(600)
        try:
            unsubscribe = connector.on_status_change(status_changed, status_error)
        except Exception as e:
            print(f"Error setting up connection status listener: {e}")
        
        # Получаем URL для подключения
        try:
            generated_url = await connector.connect(wallet, {'ton_proof': proof_payload})
        except Exception as e:
            if start_message:
                await start_message.edit_text(
                    f"❌ Ошибка при создании ссылки для подключения: {str(e)}",
                    reply_markup=InlineKeyboardBuilder().button(text="Назад", callback_data="wallets").as_markup()
                )
            return
        
        builder = InlineKeyboardBuilder()
        builder.button(text="Подключить", url=generated_url)
        builder.button(text="Назад", callback_data="wallets")
        
        # Создаем QR-код
        try:
            img = qrcode.make(generated_url)
            stream = BytesIO()
            img.save(stream)
            file = BufferedInputFile(file=stream.getvalue(), filename='qrcode')
        except Exception as e:
            if start_message:
                await start_message.edit_text(
                    f"❌ Ошибка при создании QR-кода: {str(e)}",
                    reply_markup=builder.as_markup()
                )
            return
        
        # Удаляем сообщение о подготовке и отправляем QR-код
        try:
            if start_message:
                await bot.delete_message(callback.message.chat.id, start_message.message_id)
        except Exception as e:
            print(f"Error deleting start message: {e}")
        
        # Отправляем QR-код
        qr_message = await callback.message.answer_photo(
            photo=file,
            caption=f"Отсканируйте QR-код или нажмите кнопку для подключения кошелька {wallet_name}",
            reply_markup=builder.as_markup()
        )
        
        # Ожидаем подключения
        connected = False
        for i in range(180):  # 3 минуты
            await asyncio.sleep(1)
            if connector.connected and connector.account and connector.account.address:
                connected = True
                wallet_address = connector.account.address
                wallet_address = Address(wallet_address).to_str(is_bounceable=False)
                
                # Отправляем сообщение об успешном подключении
                success_message = await callback.message.answer(
                    f"✅ Кошелек {wallet_name} успешно подключен!"
                )
                
                # Редактируем сообщение с QR-кодом
                try:
                    await bot.edit_message_caption(
                        chat_id=callback.message.chat.id,
                        message_id=qr_message.message_id,
                        caption=f"✅ Кошелек {wallet_name} успешно подключен!",
                        reply_markup=InlineKeyboardBuilder().button(text="🔙 В меню", callback_data="menu").as_markup()
                    )
                except Exception as e:
                    print(f"Error editing QR message: {e}")
                
                # Показываем главное меню в новом сообщении
                await menu(callback.message)
                
                # Через 3 секунды удаляем сообщение о успешном подключении
                await asyncio.sleep(3)
                try:
                    await bot.delete_message(callback.message.chat.id, success_message.message_id)
                except Exception as e:
                    print(f"Error deleting success message: {e}")
                
                return
        
        # Если время истекло, обновляем сообщение с QR-кодом
        if not connected:
            builder = InlineKeyboardBuilder()
            builder.button(text="Назад к выбору кошельков", callback_data="wallets")
            try:
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=qr_message.message_id,
                    caption="❌ Время подключения истекло",
                    reply_markup=builder.as_markup()
                )
                
                # Также отправляем сообщение об истечении времени
                await callback.message.answer(
                    "❌ Время подключения истекло",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                print(f"Error updating QR message: {e}")
                await callback.message.answer(
                    "❌ Время подключения истекло",
                    reply_markup=builder.as_markup()
                )
    except Exception as e:
        print(f"Error in connect_wallet: {e}")
        # В случае ошибки отправляем новое сообщение
        await callback.message.answer(
            f"Произошла ошибка при подключении кошелька: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="Вернуться к кошелькам", callback_data="wallets")
                .button(text="🔙 В меню", callback_data="menu")
                .adjust(1)
                .as_markup()
        )

@dp.callback_query(F.data == "disconnect")
async def disconnect_wallet(callback: CallbackQuery):
    try:
        connector = get_connector(callback.from_user.id)
        await connector.disconnect()
        
        # После отключения показываем стартовое меню
        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Подключить кошелек", callback_data="wallets")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "✅ Кошелек успешно отключен!\n"
            "Для продолжения работы подключите кошелек:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Error disconnecting wallet: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при отключении кошелька", 
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="menu").as_markup()
        )

# Обработка цен токенов
@dp.callback_query(F.data == "prices")
async def show_prices(callback: CallbackQuery):
    """Отображение текущих цен по популярным парам"""
    try:
        # Получаем список всех токенов из БД
        tokens = await get_all_tokens()
        
        # Получаем список всех пулов
        pools = await dex_manager.get_all_pools()
        
        # Фильтруем пулы, где вторым токеном является USDT
        usdt_pools = []
        for pool in pools:
            if pool.get('token2', '').upper() == 'USDT':
                usdt_pools.append(pool)
        
        if not usdt_pools:
            await callback.message.edit_text(
                "❌ Нет доступных токенов с ценами в USDT",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Меню", callback_data="menu")
                    .as_markup()
            )
            return
        
        # Формируем сообщение с ценами
        response = "💰 Текущие цены:\n\n"
        
        for pool in usdt_pools:
            token1 = pool.get('token1', '')
            token2 = pool.get('token2', '')
            token1_reserve = pool.get('token1_reserve', 0)
            token2_reserve = pool.get('token2_reserve', 0)
            
            if token1_reserve and token2_reserve and token1_reserve > 0:
                # Вычисляем цену на основе резервов
                price = token2_reserve / token1_reserve
                # Форматируем цену в зависимости от ее величины
                if price < 0.01:
                    price_str = f"{price:.8f}"
                elif price < 1:
                    price_str = f"{price:.4f}"
                else:
                    price_str = f"{price:.2f}"
                    
                response += f"1 {token1} = {price_str} {token2}\n"
        
        try:
            # Пытаемся отредактировать сообщение
            await callback.message.edit_text(
                response,
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔄 Обновить", callback_data="prices")
                    .button(text="🔙 Меню", callback_data="menu")
                    .as_markup()
            )
        except Exception as edit_error:
            # Проверяем, является ли ошибка "message is not modified"
            if "message is not modified" in str(edit_error):
                # Отправляем уведомление о том, что цены не изменились
                await callback.answer("Цены не изменились")
            else:
                # Для других ошибок - отправляем новое сообщение
                await callback.message.answer(
                    response,
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔄 Обновить", callback_data="prices")
                        .button(text="🔙 Меню", callback_data="menu")
                        .as_markup()
                )
    except Exception as e:
        # Пытаемся отправить новое сообщение в случае ошибки
        try:
            await callback.message.edit_text(
                f"❌ Ошибка при получении цен: {e}",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Меню", callback_data="menu")
                    .as_markup()
            )
        except Exception:
            await callback.message.answer(
                f"❌ Ошибка при получении цен. Попробуйте снова.",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Меню", callback_data="menu")
                    .as_markup()
            )

# Обработка ликвидности
@dp.callback_query(F.data == "liquidity")
async def show_liquidity(callback: CallbackQuery):
    try:
        connector = get_connector(callback.from_user.id)
        if not connector.connected:
            await callback.message.edit_text(
                "❌ Сначала подключите кошелек!",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="👛 Подключить кошелек", callback_data="wallets")
                    .as_markup()
            )
            return
        
        wallet_address = connector.account.address
        
        # Получаем текущие пулы ликвидности пользователя
        # my_pools = await dex_manager.get_user_liquidity_positions(wallet_address)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Мои пулы", callback_data="my_pools")
        builder.button(text="➕ Добавить ликвидность", callback_data="add_liquidity")
        builder.button(text="🔙 Назад", callback_data="menu")
        builder.adjust(2, 1)
        
        message_text = (
            "🌊 Управление ликвидностью\n\n"
            "Здесь вы можете:\n"
            "• Просмотреть ваши текущие пулы ликвидности\n"
            "• Добавить новую ликвидность\n"
            "• Изъять ликвидность из существующих пулов"
        )
        
        # Проверяем, можем ли мы редактировать сообщение
        if hasattr(callback.message, 'text') and callback.message.text:
            try:
                await callback.message.edit_text(
                    message_text,
                    reply_markup=builder.as_markup()
                )
            except Exception as edit_error:
                # Проверяем, является ли ошибка "message is not modified"
                if "message is not modified" in str(edit_error):
                    # Отправляем уведомление о том, что данные не изменились
                    await callback.answer("Данные актуальны")
                else:
                    # Для других ошибок - отправляем новое сообщение
                    await callback.message.answer(
                        message_text,
                        reply_markup=builder.as_markup()
                    )
        else:
            await callback.message.answer(
                message_text,
                reply_markup=builder.as_markup()
            )
    except Exception as e:
        logger.error(f"Error getting liquidity: {e}")
        try:
            await callback.message.edit_text(
                f"❌ Ошибка при получении ликвидности: {str(e)}",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="menu").as_markup()
            )
        except Exception:
            await callback.message.answer(
                f"❌ Ошибка при получении ликвидности. Попробуйте снова.",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="menu").as_markup()
            )

@dp.callback_query(F.data == "my_pools")
async def show_my_pools(callback: CallbackQuery):
    try:
        connector = get_connector(callback.from_user.id)
        wallet_address = connector.account.address
        
        # Получаем позиции пользователя из БД
        positions = await dex_manager.get_user_liquidity_positions(wallet_address)
        
        builder = InlineKeyboardBuilder()
        
        if not positions:
            no_pools_text = (
                "У вас пока нет пулов ликвидности.\n\n"
                "Добавьте ликвидность, чтобы начать зарабатывать на комиссиях."
            )
            
            no_pools_markup = InlineKeyboardBuilder()\
                .button(text="➕ Добавить ликвидность", callback_data="add_liquidity")\
                .button(text="🔙 Назад", callback_data="liquidity")\
                .adjust(1)\
                .as_markup()
            
            # Проверяем, можем ли мы редактировать сообщение
            if hasattr(callback.message, 'text') and callback.message.text:
                try:
                    await callback.message.edit_text(
                        no_pools_text,
                        reply_markup=no_pools_markup
                    )
                except Exception as edit_error:
                    # Проверяем, является ли ошибка "message is not modified"
                    if "message is not modified" in str(edit_error):
                        await callback.answer("Данные актуальны")
                    else:
                        await callback.message.answer(
                            no_pools_text,
                            reply_markup=no_pools_markup
                        )
            else:
                await callback.message.answer(
                    no_pools_text,
                    reply_markup=no_pools_markup
                )
            return
        
        text = "🌊 Ваши пулы ликвидности:\n\n"
        
        for position in positions:
            # Получаем информацию о пуле
            pool_info = position.get('pool_info', {})
            token1 = pool_info.get('token1', 'UNKNOWN')
            token2 = pool_info.get('token2', 'UNKNOWN')
            
            text += f"🔷 {token1}/{token2}\n"
            text += f"   - {position['token1_amount']:.2f} {token1}\n"
            text += f"   - {position['token2_amount']:.2f} {token2}\n"
            text += f"   - LP токены: {position['lp_tokens']:.2f}\n"
            text += f"   - Пул: {position['pool_address'][:10]}...{position['pool_address'][-6:]}\n\n"
            
            builder.button(
                text=f"Изъять {token1}/{token2}",
                callback_data=f"remove_liquidity_{position['id']}"
            )
        
        builder.button(text="🔙 Назад", callback_data="liquidity")
        builder.adjust(1)
        
        # Проверяем, можем ли мы редактировать сообщение
        if hasattr(callback.message, 'text') and callback.message.text:
            try:
                await callback.message.edit_text(text, reply_markup=builder.as_markup())
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    await callback.answer("Данные актуальны")
                else:
                    await callback.message.answer(text, reply_markup=builder.as_markup())
        else:
            await callback.message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        try:
            await callback.message.edit_text(
                f"❌ Ошибка при получении пулов: {str(e)}",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="liquidity")
                    .as_markup()
            )
        except Exception:
            await callback.message.answer(
                f"❌ Ошибка при получении пулов. Попробуйте снова.",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="liquidity")
                    .as_markup()
            )

@dp.callback_query(F.data.startswith("remove_liquidity_"))
async def remove_pool_liquidity(callback: CallbackQuery):
    try:
        position_id = int(callback.data.split("_")[2])
        connector = get_connector(callback.from_user.id)
        wallet_address = connector.account.address
        
        # Создаем транзакцию для изъятия ликвидности
        transaction = await dex_manager.remove_liquidity(position_id, wallet_address)
        
        # Отправляем транзакцию
        try:
            result = await connector.send_transaction(transaction)
            
            await callback.message.edit_text(
                "✅ Ликвидность успешно изъята!",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="my_pools")
                    .as_markup()
            )
        except UserRejectsError:
            await callback.message.edit_text(
                "❌ Транзакция отклонена пользователем",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="my_pools")
                    .as_markup()
            )
        except Exception as e:
            await callback.message.edit_text(
                f"❌ Ошибка при изъятии ликвидности: {str(e)}",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="my_pools")
                    .as_markup()
            )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при обработке запроса: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="my_pools")
                .as_markup()
        )

@dp.callback_query(F.data == "add_liquidity")
async def start_add_liquidity(callback: CallbackQuery, state: FSMContext):
    try:
        connector = get_connector(callback.from_user.id)
        if not connector.connected:
            await callback.message.edit_text(
                "❌ Сначала подключите кошелек!",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="👛 Подключить кошелек", callback_data="wallets")
                    .as_markup()
            )
            return
        
        await state.set_state(DexStates.waiting_for_liquidity_token1)
        await callback.message.edit_text(
            "Введите символ первого токена (например, TON, USDT):",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Отмена", callback_data="liquidity")
                .as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="liquidity")
                .as_markup()
        )

@dp.message(DexStates.waiting_for_liquidity_token1)
async def process_liquidity_token1(message: Message, state: FSMContext):
    """Обработка первого токена для добавления ликвидности"""
    try:
        token_symbol = message.text.upper()
        
        # Проверяем наличие токена в БД
        token_info = await get_token(token_symbol)
        
        if not token_info:
            # Если токен не найден в БД, запрашиваем дополнительную информацию
            await state.update_data(new_token_symbol=token_symbol)
            await state.set_state(DexStates.waiting_for_token_master_address)
            
            await message.answer(
                f"Токен {token_symbol} не найден в базе данных.\n\n"
                f"Пожалуйста, введите адрес мастер-контракта токена:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="add_liquidity")
                    .as_markup()
            )
            return

        # Токен найден, сохраняем и переходим к следующему шагу
        await state.update_data(token1=token_symbol)
        await state.set_state(DexStates.waiting_for_liquidity_token2)
        
        await message.answer(
            "Введите символ второго токена пары (например, TON, USDT):",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="add_liquidity")
                .as_markup()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="add_liquidity")
                .as_markup()
        )

@dp.message(DexStates.waiting_for_liquidity_token2)
async def process_liquidity_token2(message: Message, state: FSMContext):
    """Обработка второго токена для добавления ликвидности"""
    try:
        token_input = message.text.strip()
        data = await state.get_data()
        token1 = data.get('token1')
        
        # Проверяем, является ли ввод адресом
        is_address = False
        try:
            from pytoniq import Address
            Address(token_input)
            is_address = (token_input.startswith('EQ') or token_input.startswith('UQ')) and len(token_input) >= 48
        except Exception:
            is_address = False
        
        token_symbol = None
        token_info = None
        
        if is_address:
            # Проверяем наличие токена в БД по адресу
            try:
                token_info = await get_token_by_address(token_input)
                if token_info:
                    token_symbol = token_info.get('token_symbol')
                else:
                    await message.answer(
                        "❌ Токен с таким адресом не найден в базе данных.\n"
                        "Пожалуйста, введите символ существующего токена:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="add_liquidity")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token by address: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, введите символ токена:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="add_liquidity")
                        .as_markup()
                )
                return
        else:
            # Обрабатываем как символ токена
            token_symbol = token_input.upper()
            
            # Проверяем наличие токена в БД по символу
            try:
                token_info = await get_token(token_symbol)
                if not token_info:
                    await message.answer(
                        f"❌ Токен {token_symbol} не найден в базе данных.\n"
                        "Пожалуйста, введите один из доступных токенов:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="add_liquidity")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, попробуйте снова:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="add_liquidity")
                        .as_markup()
                )
                return

        # Проверяем, что токены разные
        if token1 == token_symbol:
            await message.answer(
                "❌ Токены должны быть разными. Введите другой токен:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="add_liquidity")
                    .as_markup()
            )
            return

        # Добавляем пару в избранное
        try:
            user_id = message.from_user.id
            db_bot.add_favorite_pair(user_id, token1, token_symbol)
        except Exception as e:
            print(f"Error adding favorite pair: {e}")
            
        # Получаем курс обмена
        try:
            rate = await dex_manager.get_price(token1, token_symbol)
        except Exception as e:
            print(f"Error getting price: {e}")
            rate = 0.0  # Заглушка на случай ошибки
            
        await state.update_data(token2=token_symbol, rate=rate)
        
        await message.answer(
            f"✅ Пара {token1}/{token_symbol} добавлена в избранное!"
        )
        
        await state.set_state(DexStates.waiting_for_liquidity_amount1)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="add_liquidity")
                .as_markup()
        )

@dp.message(DexStates.waiting_for_liquidity_amount1)
async def process_liquidity_amount1(message: Message, state: FSMContext):
    try:
        try:
            amount1 = float(message.text)
            if amount1 <= 0:
                raise ValueError("Сумма должна быть положительной")
        except ValueError:
            await message.answer(
                "Пожалуйста, введите корректное число:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="liquidity")
                    .as_markup()
            )
            return
        
        data = await state.get_data()
        token1 = data.get('token1')
        token2 = data.get('token2')
        
        await state.update_data(amount1=amount1)
        await state.set_state(DexStates.waiting_for_liquidity_amount2)
        await message.answer(
            f"Введите количество {token2} для добавления в пул:",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Отмена", callback_data="liquidity")
                .as_markup()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="liquidity")
                .as_markup()
        )

@dp.message(DexStates.waiting_for_liquidity_amount2)
async def process_liquidity_amount2(message: Message, state: FSMContext):
    try:
        try:
            amount2 = float(message.text)
            if amount2 <= 0:
                raise ValueError("Сумма должна быть положительной")
        except ValueError:
            await message.answer(
                "Пожалуйста, введите корректное число:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="liquidity")
                    .as_markup()
            )
            return
        
        data = await state.get_data()
        token1 = data.get('token1')
        token2 = data.get('token2')
        amount1 = data.get('amount1')
        
        connector = get_connector(message.from_user.id)
        wallet_address = connector.account.address
        
        # Создаем транзакцию для добавления ликвидности
        try:
            transaction = await dex_manager.add_liquidity(
                wallet_address=wallet_address,
                token1=token1,
                token2=token2,
                token1_amount=amount1,
                token2_amount=amount2
            )
            
            result = await connector.send_transaction(transaction)
            
            # Получаем информацию о пуле для отображения
            try:
                pool_info = await dex_manager.get_pool_info_with_type(token1, token2)
                
                await message.answer(
                    "✅ Ликвидность успешно добавлена!\n\n"
                    f"- {amount1:.2f} {token1}\n"
                    f"- {amount2:.2f} {token2}\n"
                    f"- Пул: {pool_info.get('pool_address', '')[:10]}...{pool_info.get('pool_address', '')[-6:]}",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="👀 Мои пулы", callback_data="my_pools")
                        .button(text="🔙 Меню", callback_data="menu")
                        .adjust(1)
                        .as_markup()
                )
            except Exception as e:
                # Если не удалось получить информацию о пуле, покажем упрощенное сообщение
                await message.answer(
                    "✅ Ликвидность успешно добавлена!\n\n"
                    f"- {amount1:.2f} {token1}\n"
                    f"- {amount2:.2f} {token2}",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="👀 Мои пулы", callback_data="my_pools")
                        .button(text="🔙 Меню", callback_data="menu")
                        .adjust(1)
                        .as_markup()
                )
            
        except UserRejectsError:
            await message.answer(
                "❌ Транзакция отклонена пользователем",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="liquidity")
                    .as_markup()
            )
        except Exception as e:
            await message.answer(
                f"❌ Ошибка при добавлении ликвидности: {str(e)}",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Назад", callback_data="liquidity")
                    .as_markup()
            )
        finally:
            await state.clear()
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="liquidity")
                .as_markup()
        )
        await state.clear()

# Обработка свопа
@dp.callback_query(F.data == "swap")
async def start_swap(callback: CallbackQuery, state: FSMContext):
    """Начало процесса обмена токенов"""
    try:
        # Получаем список популярных пар из БД пользователя
        user_id = callback.from_user.id
        favorite_pairs = db_bot.get_favorite_pairs(user_id)
        
        builder = InlineKeyboardBuilder()
        
        if favorite_pairs:
            # Отображаем избранные пары пользователя (не более 4)
            for pair in favorite_pairs[:4]:  # Ограничиваем количество отображаемых пар до 4
                token1 = pair.get('token1', '').upper()
                token2 = pair.get('token2', '').upper()
                pair_text = f"{token1}/{token2}"
                builder.button(text=pair_text, callback_data=f"pair:{token1}:{token2}")
            
            builder.adjust(2)  # Располагаем кнопки по 2 в ряд
        
        # Добавляем опцию создания пользовательского свопа
        builder.button(text="✏️ Выбрать другие токены", callback_data="custom_swap")
        builder.button(text="🔙 Меню", callback_data="menu")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "🔄 Обмен токенов\n\n"
            + ("Выберите пару из избранных или создайте свой своп:" if favorite_pairs else "У вас нет избранных пар. Создайте свой своп:"),
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при запуске обмена: {e}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Меню", callback_data="menu")
                .as_markup()
        )

@dp.callback_query(F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    try:
        _, token1, token2 = callback.data.split(":")
        
        # Получаем информацию о пуле с этой парой токенов из БД
        try:
            pool_info = await dex_manager.get_pool_info_with_type(token1, token2)
            
            # Вычисляем курс обмена на основе резервов в пуле
            if pool_info.get('token1_reserve') and pool_info.get('token2_reserve'):
                if token1 == pool_info['token1']:
                    rate = pool_info['token2_reserve'] / pool_info['token1_reserve']
                else:
                    rate = pool_info['token1_reserve'] / pool_info['token2_reserve']
            else:
                # Если резервы не указаны, используем заглушку
                rate = 1.0
        except Exception as e:
            # Если пул не найден, используем заглушку
            rate = 1.0
            if token1 == "TON" and token2 == "USDT":
                rate = 3.0
            elif token1 == "USDT" and token2 == "TON":
                rate = 0.33
        
        # Получаем баланс пользователя (заглушка)
        balance = 1.96

        await state.update_data(token1=token1, token2=token2, rate=rate)
        await state.set_state(DexStates.waiting_for_amount)
        
        await callback.message.edit_text(
            f"🔄 Обмен {token1} → {token2}\n\n"
            f"💰 Баланс: {balance} {token1}\n\n"
            f"Текущий курс: 1 {token1} = {rate:.4f} {token2}\n\n"
            f"Введите количество {token1} для обмена:",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )

@dp.callback_query(F.data == "custom_swap")
async def custom_swap(callback: CallbackQuery, state: FSMContext):
    # Получаем список доступных токенов из БД
    tokens = await get_all_tokens()
    
    if not tokens:
        await callback.message.edit_text(
            "❌ В базе данных нет доступных токенов.\n"
            "Пожалуйста, обратитесь к администратору.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
        return
    
    # Показываем список доступных токенов (до 10)
    available_tokens = ", ".join([token.get('token_symbol', '') for token in tokens[:10]])
    total_tokens = len(tokens)
    
    message_text = (
        f"🪙 Доступные токены ({min(10, total_tokens)} из {total_tokens}):\n"
        f"{available_tokens}"
    )
    
    if total_tokens > 10:
        message_text += "... и другие"
    
    message_text += (
        "\n\n✏️ Создание пары для обмена:\n\n"
        "1. Введите символ или адрес первого токена\n"
        "2. Затем введите символ или адрес второго токена\n"
        "3. Пара будет добавлена в избранное\n\n"
        "👛 Введите символ или адрес первого токена:"
    )
    
    await state.set_state(DexStates.waiting_for_token1)
    await callback.message.edit_text(
        message_text,
        reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Отмена", callback_data="swap")
            .as_markup()
    )

@dp.message(DexStates.waiting_for_token1)
async def process_token1(message: Message, state: FSMContext):
    """Обработка первого токена для свопа"""
    try:
        token_input = message.text.strip()
        
        # Проверяем, является ли ввод адресом
        is_address = False
        try:
            from pytoniq import Address
            Address(token_input)
            is_address = (token_input.startswith('EQ') or token_input.startswith('UQ')) and len(token_input) >= 48
        except Exception:
            is_address = False
        
        token_symbol = None
        token_info = None
        
        if is_address:
            # Проверяем наличие токена в БД по адресу
            try:
                token_info = await get_token_by_address(token_input)
                if token_info:
                    token_symbol = token_info.get('token_symbol')
                else:
                    await message.answer(
                        "❌ Токен с таким адресом не найден в базе данных.\n"
                        "Пожалуйста, введите символ существующего токена:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="swap")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token by address: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, введите символ токена:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="swap")
                        .as_markup()
                )
                return
        else:
            # Обрабатываем как символ токена
            token_symbol = token_input.upper()
            
            # Проверяем наличие токена в БД по символу
            try:
                token_info = await get_token(token_symbol)
                if not token_info:
                    await message.answer(
                        f"❌ Токен {token_symbol} не найден в базе данных.\n"
                        "Пожалуйста, введите один из доступных токенов:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="swap")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, попробуйте снова:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="swap")
                        .as_markup()
                )
                return

        # Сохраняем токен и переходим к следующему шагу
        await state.update_data(token1=token_symbol)
        await state.set_state(DexStates.waiting_for_token2)
        
        # Получаем список доступных токенов для второго выбора
        tokens = await get_all_tokens()
        available_tokens = ", ".join([token.get('token_symbol', '') for token in tokens[:10]])
        if len(tokens) > 10:
            available_tokens += "... и другие"
            
        await message.answer(
            f"✅ Выбран первый токен: {token_symbol}\n\n"
            f"Доступные токены: {available_tokens}\n\n"
            "Введите символ или адрес второго токена:",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Отмена", callback_data="swap")
                .as_markup()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
        await state.clear()

@dp.message(DexStates.waiting_for_token2)
async def process_token2(message: Message, state: FSMContext):
    """Обработка второго токена для свопа"""
    try:
        token_input = message.text.strip()
        data = await state.get_data()
        token1 = data.get('token1')
        
        # Проверяем, является ли ввод адресом
        is_address = False
        try:
            from pytoniq import Address
            Address(token_input)
            is_address = (token_input.startswith('EQ') or token_input.startswith('UQ')) and len(token_input) >= 48
        except Exception:
            is_address = False
        
        token_symbol = None
        token_info = None
        
        if is_address:
            # Проверяем наличие токена в БД по адресу
            try:
                token_info = await get_token_by_address(token_input)
                if token_info:
                    token_symbol = token_info.get('token_symbol')
                else:
                    await message.answer(
                        "❌ Токен с таким адресом не найден в базе данных.\n"
                        "Пожалуйста, введите символ существующего токена:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="swap")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token by address: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, введите символ токена:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="swap")
                        .as_markup()
                )
                return
        else:
            # Обрабатываем как символ токена
            token_symbol = token_input.upper()
            
            # Проверяем наличие токена в БД по символу
            try:
                token_info = await get_token(token_symbol)
                if not token_info:
                    await message.answer(
                        f"❌ Токен {token_symbol} не найден в базе данных.\n"
                        "Пожалуйста, введите один из доступных токенов:",
                        reply_markup=InlineKeyboardBuilder()
                            .button(text="🔙 Отмена", callback_data="swap")
                            .as_markup()
                    )
                    return
            except Exception as e:
                print(f"Error getting token: {e}")
                await message.answer(
                    "❌ Ошибка при поиске токена. Пожалуйста, попробуйте снова:",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔙 Отмена", callback_data="swap")
                        .as_markup()
                )
                return

        # Проверяем, что токены разные
        if token1 == token_symbol:
            await message.answer(
                "❌ Токены должны быть разными. Введите другой токен:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="swap")
                    .as_markup()
            )
            return

        # Добавляем пару в избранное
        try:
            user_id = message.from_user.id
            db_bot.add_favorite_pair(user_id, token1, token_symbol)
        except Exception as e:
            print(f"Error adding favorite pair: {e}")
            
        # Получаем курс обмена
        try:
            rate = await dex_manager.get_price(token1, token_symbol)
        except Exception as e:
            print(f"Error getting price: {e}")
            rate = 0.0  # Заглушка на случай ошибки
            
        await state.update_data(token2=token_symbol, rate=rate)
        
        await message.answer(
            f"✅ Пара {token1}/{token_symbol} добавлена в избранное!"
        )
        
        await state.set_state(DexStates.waiting_for_amount)
        
        await message.answer(
            f"🔄 Обмен {token1} → {token_symbol}\n\n"
            f"Примерный курс: 1 {token1} ≈ {rate} {token_symbol}\n\n"
            f"Введите количество {token1} для обмена:",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
        await state.clear()

@dp.message(DexStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    """Обработка суммы для обмена"""
    try:
        try:
            amount = float(message.text)
            if amount <= 0:
                raise ValueError("Сумма должна быть положительной")
        except ValueError:
            await message.answer(
                "Пожалуйста, введите корректное число:",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 Отмена", callback_data="swap")
                    .as_markup()
            )
            return
        
        data = await state.get_data()
        token1 = data['token1']
        token2 = data['token2']
        rate = data['rate']
        
        connector = get_connector(message.from_user.id)
        
        # Расчет итоговой суммы
        receive_amount = amount * rate
        
        # Подтверждение свопа
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить", callback_data=f"confirm_swap:{amount}")
        builder.button(text="❌ Отмена", callback_data="swap")
        builder.adjust(1)
        
        await message.answer(
            f"📊 Подтверждение обмена\n\n"
            f"Отправляете: {amount * 1.15} {token1}\n"
            f"Получаете: ~{receive_amount} {token2}\n"
            f"Курс: 1 {token1} = {rate} {token2}\n\n"
            f"Подтвердите операцию:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )

@dp.callback_query(F.data.startswith("confirm_swap:"))
async def confirm_swap(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и выполнение свопа"""
    try:
        amount = float(callback.data.split(":")[1])
        data = await state.get_data()
        token1 = data['token1']
        token2 = data['token2']
        rate = data['rate']
        
        # Расчет итоговой суммы
        receive_amount = amount * rate
        
        connector = get_connector(callback.from_user.id)
        
        try:
            # Получаем адрес кошелька пользователя
            wallet_address = connector.account.address
            
            # Создаем транзакцию через DexManager
            transaction = await dex_manager.create_swap_transaction(
                token1=token1,
                token2=token2,
                amount=amount,
                wallet_address=wallet_address
            )
            
            # Отправляем транзакцию на подписание
            result = await connector.send_transaction(transaction)
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 Меню", callback_data="menu")
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"✅ Своп ~{amount:.4f} {token1} на ~{receive_amount:.4f} {token2} выполнен успешно!\n"
                f"Итоговый курс: 1 {token1} ≈ {rate:.4f} {token2}",
                reply_markup=builder.as_markup()
            )
        except UserRejectsError:
            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 Назад", callback_data="swap")
            builder.adjust(1)
            
            await callback.message.edit_text(
                "❌ Транзакция отклонена пользователем",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 Назад", callback_data="swap")
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"❌ Ошибка при выполнении свопа: {str(e)}",
                reply_markup=builder.as_markup()
            )
            
        await state.clear()
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data="swap")
                .as_markup()
        )
        await state.clear()

@dp.callback_query(F.data.in_(["swap", "liquidity", "add_liquidity", "my_pools"]))
async def handle_cancel_buttons(callback: CallbackQuery, state: FSMContext):
    """Универсальный обработчик кнопок 'Отмена' и навигации"""
    try:
        # Очищаем любое состояние
        current_state = await state.get_state()
        if current_state is not None:
            await state.clear()
        
        # Вызываем соответствующий обработчик в зависимости от нажатой кнопки
        if callback.data == "swap":
            await start_swap(callback, state)
        elif callback.data == "liquidity":
            await show_liquidity(callback)
        elif callback.data == "add_liquidity":
            await start_add_liquidity(callback, state)
        elif callback.data == "my_pools":
            await show_my_pools(callback)
    except Exception as e:
        print(f"Error in handle_cancel_buttons: {e}")
        # В случае ошибки отправляем в главное меню
        await callback.message.answer(
            "Произошла ошибка при обработке запроса. Возвращаемся в главное меню.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 В меню", callback_data="menu")
                .as_markup()
        )

async def main() -> None:
    try:
        # Инициализация основной базы данных
        init_db() 
        print("База данных PostgreSQL успешно инициализирована")
        
        # Инициализация базы данных бота
        db_bot.init_db()
        print("База данных для бота успешно инициализирована")
        
        # Восстанавливаем подключения кошельков из БД
        from tc_storage import restore_connections
        await restore_connections()
        print("Восстановление подключений кошельков выполнено")
    except Exception as e:
        print(f"Ошибка при инициализации: {e}")


    global client 

    client = AsyncTonapi(api_key=API_KEY)

    # Инициализируем DexManager
    global dex_manager
    dex_manager = DexManager()

    print("Start Working")
    await bot.delete_webhook(drop_pending_updates=True)  # skip_updates = True
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

