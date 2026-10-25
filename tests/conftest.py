import os

from sqlalchemy import text
# ========= SET ENV VARIABLES =========

os.environ["JWT_SECRET"] = "test_secrettest_secrettest_secrettest_secrettest_secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

os.environ["APP_PORT"] = "8000"


os.environ["POSTGRES_USER"] = "app"
os.environ["POSTGRES_PASSWORD"] = "13fa426dc009d12935779579c1b9f7ad"
os.environ["POSTGRES_DB"] = "test_simeplrag"
os.environ["POSTGRES_HOST"] = "postgres"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://app:13fa426dc009d12935779579c1b9f7ad@postgres:5432/test_simeplrag"

# ========= PYTEST CONFIG =============
import os
from typing import AsyncGenerator
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.core.deps import get_db
from app.main import app
from fastapi import status


pytest_plugins = ["anyio"]

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

# ========= FIXTURES ==================

@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;"))
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(
     test_engine,
     setup_database
) -> AsyncGenerator[AsyncSession]:
     conn = await test_engine.connect()
     trans = await conn.begin()

     test_async_session = async_sessionmaker(
          conn,
          class_=AsyncSession,
          expire_on_commit=False,
          join_transaction_mode="create_savepoint"
     )



     async with test_async_session() as session:
        try:
            yield session
        finally:
             await session.close()
             await trans.rollback()
             await conn.close()



@pytest.fixture(scope="session", autouse=True)
def fast_password_hashing():
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from app.core import security

    fast_hash = PasswordHash(
        (Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),)
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(security, "password_hash", fast_hash)
        yield


# =========== DEPENDENCY OVERRIDE ===============


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db


    async with AsyncClient(
        transport=ASGITransport(app=app, client=(f"testclient-{uuid.uuid4().hex}", 12345)),
        base_url="http://test"
    ) as ac:
        yield ac


    app.dependency_overrides.clear()



# ================ AUTH HELPERS ==================
async def create_test_user(
    client: AsyncClient, 
    username: str = "user@example.com", 
    name: str = "The Test User", 
    password: str = "Pass@123456"
):

    """ Create new test user """

    new_user_json_data = {
        "username": username,
        "name": name,
        "password": password,
        "password_repeat": password
    }

    response = await client.post(
        "/api/v1/auth/register",
        json=new_user_json_data
    )


    assert response.status_code == status.HTTP_201_CREATED, f"Failed to create user: {response.text}"
    return response.json()



async def login_user(
    client: AsyncClient,
    username: str = "user@example.com",
    password: str = "Pass@123456"
):
    login_data = {
        "username": username,
        "password": password
    }

    response = await client.post(
        "/api/v1/auth/login",
        data = login_data
    )

    assert response.status_code == status.HTTP_200_OK, f"Failed to login: {response.text}"
    return response.json()['access_token']



def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}