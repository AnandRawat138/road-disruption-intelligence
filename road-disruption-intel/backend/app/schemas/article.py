from pydantic import BaseModel
from typing import Optional

class ArticleBase(BaseModel):
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    source_name: str
    source_url: str

class ArticleCreate(ArticleBase):
    content_hash: str

class ArticleResponse(ArticleBase):
    id: str
    status: str

    class Config:
        orm_mode = True
        from_attributes = True
