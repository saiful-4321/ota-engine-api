from pydantic import BaseModel
from typing import Optional, List, Any

class BaseResponse(BaseModel):
    status: int
    message: str = 'Success'
    data: Optional[Any] = None
    errors: Optional[Any] = None

#index data {{URL}}/market-data/index-value
class IndexData(BaseModel):
    id:             int = 1
    index_name:     str = 'DSES'
    index_value:    float = 3000.52
    index_change:   float = 0.66
    index_changeper: float = 0.02

class IndexDataResponse(BaseResponse):
    data: Optional[List[IndexData]]