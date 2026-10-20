from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    async_sessionmaker, 
    AsyncSession
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# 1. engine
engine = create_async_engine(str(settings.database_url))
# 2. define declarative base


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

