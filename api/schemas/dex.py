from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TokenInfo(BaseModel):
    name: str
    symbol: str
    address: str
    decimals: int
    usdt_price: Optional[float] = None
    pools: Optional[List[Dict[str, Any]]] = []

class PoolInfo(BaseModel):
    token1: str
    token2: str
    pool_address: str
    liquidity: float
    token1_reserve: Optional[float] = None
    token2_reserve: Optional[float] = None
    type: Optional[str] = None

class LiquidityPosition(BaseModel):
    position_id: int
    pool_address: str
    wallet_address: str
    token1: str
    token2: str
    token1_amount: float
    token2_amount: float
    lp_tokens: float
    created_at: int

class SwapRoute(BaseModel):
    min_amount_out: int
    fee: float
    path: List[str]
    pool_addresses: List[str]

class SwapTransaction(BaseModel):
    valid_until: int
    messages: List[Dict[str, Any]]

class PoolChartPoint(BaseModel):
    timestamp: int
    price: float
    volume: float

class CreatePoolRequest(BaseModel):
    token1: str
    token2: str
    initial_liquidity1: float = Field(..., gt=0)
    initial_liquidity2: float = Field(..., gt=0)
    wallet_address: str
    type: Optional[str] = None

class AddLiquidityRequest(BaseModel):
    token1: str
    token2: str
    token1_amount: float = Field(..., gt=0)
    token2_amount: float = Field(..., gt=0)
    wallet_address: str
    type: Optional[str] = None

class RemoveLiquidityRequest(BaseModel):
    position_id: int
    wallet_address: str
    type: Optional[str] = None

class SwapRequest(BaseModel):
    token_in: str
    token_out: str
    amount: float = Field(..., gt=0)
    wallet_address: str
    path: Optional[List[str]] = None

class ErrorResponse(BaseModel):
    detail: str 