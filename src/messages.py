# messages.py
# Пустой файл для тестирования

# Словарь текстовых сообщений для бота
MESSAGES = {
    "welcome": "Добро пожаловать в DEX бота!",
    "connect_wallet": "Для начала работы необходимо подключить кошелек.",
    "wallet_connected": "Кошелек успешно подключен!",
    "wallet_disconnected": "Кошелек отключен.",
    "error": "Произошла ошибка: {error}"
}

from base64 import urlsafe_b64encode

from pytoniq_core import begin_cell

import datetime


def get_comment_message(destination_address: str, amount: int, comment: str) -> dict:

    data = {
        'address': destination_address,
        'amount': str(amount),
        'payload': urlsafe_b64encode(
            begin_cell()
            .store_uint(0, 32)  # op code for comment message
            .store_string(comment)  # store comment
            .end_cell()  # end cell
            .to_boc()  # convert it to boc
        )
        .decode()  # encode it to urlsafe base64
    }

    return data

def get_mint_message(contract_address : str, destination_address: str, TONamount: int, IDEALamount: int) -> dict:
    data = {
        'address': contract_address,
        'amount': str(TONamount),
        'payload': urlsafe_b64encode(
            begin_cell()
            .store_coins(IDEALamount)
            .store_address(destination_address)  # store address
            .end_cell()  # end cell
            .to_boc()  # convert it to boc
        )
        .decode()  # encode it to urlsafe base64
    }

    return data

def get_ton_message(destination_address: str, amount: int) -> dict:
    data = {
            'address': destination_address,
            'amount': str(amount),
            'payload': urlsafe_b64encode(
                begin_cell()
                .store_uint(0, 32)  # op code for transfer message
                .end_cell()  # end cell
                .to_boc()  # convert it to boc
            )
            .decode()  # encode it to urlsafe base64
            }

    return data


def get_transfer_ton_message(destination_address: str, amount: int, reference="no", discount=0.3) -> dict:
    msgs = []
    if reference != "no":
        msgs.append(get_ton_message(destination_address, int(amount * (1 - discount))))
        msgs.append(get_ton_message(reference, int(amount * discount)))
    else:
        msgs.append(get_ton_message(destination_address, amount))

    data = {
        'valid_until': int(datetime.datetime.now().timestamp()) + 180,\
        'network': '-239',
        'messages': msgs        
    }

    return data

def get_jetton_message(jetton_walet: str, destination_address: str, jetton: str, amount: int) -> dict:
    payload = begin_cell()\
                .store_uint(0xf8a7ea5, 32)\
                .store_uint(0, 64)\
                .store_coins(amount)\
                .store_address(address(recipient_address))\
                .store_address(my_address)\
                .store_uint(0, 1)\
                .store_coins(1)\
                .store_uint(0, 1)\
            .end_cell()

    data = {
            'address': jetton_walet,
            'amount': str(amount),
            'payload': urlsafe_b64encode(
                payload.to_boc()  # convert it to boc
            )
            .decode()  # encode it to urlsafe base64
            }

    return data
    
def get_transfer_jetton_message(jetton_wallet:str, destination_address: str, amount: int, reference="no", discount=0.3) -> dict:
    msgs = []
    if reference != "no":
        msgs.append(get_jetton_message(jetton_wallet, destination_address, int(amount * (1 - discount))))
        msgs.append(get_jetton_message(jetton_wallet, reference, int(amount * discount)))
    else:
        msgs.append(get_ton_message(jetton_wallet, destination_address, amount))

    data = {
        'valid_until': int(datetime.datetime.now().timestamp()) + 180,\
        'network': '-239',
        'messages': msgs        
    }

    return data