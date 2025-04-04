from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TokenInfo(BaseModel):
    name: str
    symbol: str
    address: str
    decimals: int
    price: float
    chart: List[List[Any]]

class PoolInfo(BaseModel):
    token1: TokenInfo
    token2: TokenInfo
    reserve1: float
    reserve2: float
    fee: str
    tvl: float
    address: str
    type: Optional[str] = None

class LiquidityPosition(BaseModel):
    id: int
    wallet_address: str
    token1: TokenInfo
    token2: TokenInfo
    token1_amount: float
    token2_amount: float
    lp_tokens: float
    pool_type: Optional[str] = None

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
    liquidity: float

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