import uvicorn
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Получаем абсолютный путь к корневой директории проекта
root_path = str(Path(__file__).parent.parent.absolute())

# Загружаем переменные окружения
env_path = os.path.join(root_path, '.env')
load_dotenv(env_path)

# Добавляем пути в PYTHONPATH
if root_path not in sys.path:
    sys.path.append(root_path)

# Инициализация базы данных перед запуском
from core.db import init_db

if __name__ == "__main__":
    # Инициализируем базу данных
    init_db()
    
    # Запускаем сервер
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    ) 