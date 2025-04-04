"""
Мок-данные для тестирования индексера и базы данных
"""

# Мок-данные для пулов
MOCK_POOLS = [
    {
        'address': 'EQBeHLvZ4urFg9C2z5m6TxM-JKBwYEQwl1-BJQxOjnE0wYgt',
        'token1': 'TON',
        'token2': 'USDT',
        'liquidity': 10000000000,
        'token1_address': 'EQD7v05a3l-QEpMlQ0ZE3DuzJ6jHY14U7nGKUuErbkdUyhgY',
        'token2_address': 'EQD_s-wyz7bH8eSR7eZkzFD-xCvRKDMOCCMp-PuMvlzT_ENA'
    },
    {
        'address': 'EQA93JkCInGyoByCNCUjz-JOcYR6rramIAAHtRKdrA5wnEoA',
        'token1': 'TON',
        'token2': 'WBTC',
        'liquidity': 5000000000,
        'token1_address': 'EQD7v05a3l-QEpMlQ0ZE3DuzJ6jHY14U7nGKUuErbkdUyhgY',
        'token2_address': 'EQCjoR8e2O54D0xBGJOuChA0lzycO8eBHDDnwVwsVjkzA2k0'
    },
    {
        'address': 'EQBiGgH1iKCXzIvl4SXvMTomzWOu6wIK7TFUe-kn0H1n14tN',
        'token1': 'TON',
        'token2': 'WETH',
        'liquidity': 7500000000,
        'token1_address': 'EQD7v05a3l-QEpMlQ0ZE3DuzJ6jHY14U7nGKUuErbkdUyhgY',
        'token2_address': 'EQB-MPwrd1G6WKLaZ5jY9YKJ7Ja9Vr_I_Z6z1NwRrULEGUBi'
    },
    {
        'address': 'EQCuyvY_Jq1jLl6gXqvCOqaZphaYCjIvfM8Bld8jdJkXFvx0',
        'token1': 'USDT',
        'token2': 'WETH',
        'liquidity': 3000000000,
        'token1_address': 'EQD_s-wyz7bH8eSR7eZkzFD-xCvRKDMOCCMp-PuMvlzT_ENA',
        'token2_address': 'EQB-MPwrd1G6WKLaZ5jY9YKJ7Ja9Vr_I_Z6z1NwRrULEGUBi'
    }
]

# Мок-данные для цен в пулах
MOCK_PRICES = {
    'EQBeHLvZ4urFg9C2z5m6TxM-JKBwYEQwl1-BJQxOjnE0wYgt': 3.15,  # TON/USDT
    'EQA93JkCInGyoByCNCUjz-JOcYR6rramIAAHtRKdrA5wnEoA': 0.00012,  # TON/WBTC
    'EQBiGgH1iKCXzIvl4SXvMTomzWOu6wIK7TFUe-kn0H1n14tN': 0.0035,  # TON/WETH
    'EQCuyvY_Jq1jLl6gXqvCOqaZphaYCjIvfM8Bld8jdJkXFvx0': 0.00085  # USDT/WETH
}

# Мок-данные для ликвидности пулов
MOCK_POOL_LIQUIDITY = {
    'EQBeHLvZ4urFg9C2z5m6TxM-JKBwYEQwl1-BJQxOjnE0wYgt': {
        'token1_reserve': 1500000,  # TON
        'token2_reserve': 4725000   # USDT
    },
    'EQA93JkCInGyoByCNCUjz-JOcYR6rramIAAHtRKdrA5wnEoA': {
        'token1_reserve': 400000,   # TON
        'token2_reserve': 48        # WBTC
    },
    'EQBiGgH1iKCXzIvl4SXvMTomzWOu6wIK7TFUe-kn0H1n14tN': {
        'token1_reserve': 900000,   # TON
        'token2_reserve': 3150      # WETH
    },
    'EQCuyvY_Jq1jLl6gXqvCOqaZphaYCjIvfM8Bld8jdJkXFvx0': {
        'token1_reserve': 2000000,  # USDT
        'token2_reserve': 1700      # WETH
    }
}

# Мок-данные для позиций ликвидности
MOCK_POSITIONS = {
    'EQBeHLvZ4urFg9C2z5m6TxM-JKBwYEQwl1-BJQxOjnE0wYgt': [
        {
            'wallet_address': 'EQB7nBXbHsFt-_KFGERKvFzKMQhEgIB8c3Hz1nZ_cBzwKXYJ',
            'token1_amount': 100000,
            'token2_amount': 315000,
            'lp_tokens': 250000
        },
        {
            'wallet_address': 'EQCQxj-JalrYVmW3SoLU92XBCe7foKxBaT3ZXmtikoADdO9V',
            'token1_amount': 50000,
            'token2_amount': 157500,
            'lp_tokens': 125000
        }
    ],
    'EQA93JkCInGyoByCNCUjz-JOcYR6rramIAAHtRKdrA5wnEoA': [
        {
            'wallet_address': 'EQB7nBXbHsFt-_KFGERKvFzKMQhEgIB8c3Hz1nZ_cBzwKXYJ',
            'token1_amount': 20000,
            'token2_amount': 2.4,
            'lp_tokens': 40000
        }
    ],
    'EQBiGgH1iKCXzIvl4SXvMTomzWOu6wIK7TFUe-kn0H1n14tN': [
        {
            'wallet_address': 'EQCQxj-JalrYVmW3SoLU92XBCe7foKxBaT3ZXmtikoADdO9V',
            'token1_amount': 30000,
            'token2_amount': 105,
            'lp_tokens': 60000
        },
        {
            'wallet_address': 'EQAF0Xib-w-Mlq2LGU5Wm4FMhBEJoX3JEYm1i3phhwQXt1cI',
            'token1_amount': 15000,
            'token2_amount': 52.5,
            'lp_tokens': 30000
        }
    ],
    'EQCuyvY_Jq1jLl6gXqvCOqaZphaYCjIvfM8Bld8jdJkXFvx0': [
        {
            'wallet_address': 'EQAF0Xib-w-Mlq2LGU5Wm4FMhBEJoX3JEYm1i3phhwQXt1cI',
            'token1_amount': 100000,
            'token2_amount': 85,
            'lp_tokens': 75000
        }
    ]
} 