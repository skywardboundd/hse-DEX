from os import environ as env

from dotenv import load_dotenv
load_dotenv()

# Конфигурация бота
TOKEN = env.get("TOKEN")  
TONAPI_KEY = env.get("TONAPI_KEY")    

MANIFEST_URL = env.get("MANIFEST_URL", "https://ton-connect.github.io/demo-dapp-with-react-ui/tonconnect-manifest.json")

# Настройки сети
NETWORK = env.get("NETWORK", "testnet")  

# Комиссии
SWAP_FEE = float(env.get("SWAP_FEE", "0.003"))  # 0.3%
GAS_FEE = float(env.get("GAS_FEE", "0.1"))  # TON