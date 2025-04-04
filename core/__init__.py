from .dex import DexManager
from .db import init_db

__all__ = [
    'DexManager',
    'init_db'
]

# Инициализируем базу данных при импорте
import asyncio
loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(init_db())
except Exception as e:
    print(f"Ошибка инициализации базы данных: {e}")
