from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.dex import router as dex_router
import sys
import os
from pathlib import Path

# Получаем абсолютный путь к корневой директории проекта
root_path = str(Path(__file__).parent.parent.absolute())

# Добавляем корневую директорию в PYTHONPATH
if root_path not in sys.path:
    sys.path.append(root_path)

# Импорт базы данных из core
from core.db import init_db

# Инициализация БД при запуске API
init_db()

app = FastAPI(
    title="TON DEX API",
    description="""API для взаимодействия с TON DEX
    
    ## Основные возможности:
    
    - Получение информации о токенах
    - Получение информации о пулах ликвидности (по паре токенов или по адресу пула)
    - Получение графиков цен и объемов
    - Создание пулов ликвидности
    - Добавление и удаление ликвидности
    - Выполнение обменов токенов (свопов)
    - Расчет оптимальных маршрутов обмена
    
    Подробную документацию по всем методам API можно найти в разделе /docs
    """,
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(dex_router)

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "TON DEX API",
        "version": "1.0.0",
        "docs": "/docs"
    } 