import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-production")
os.environ.setdefault("GROQ_API_KEY", "")

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base
from app.services.groq_client import reset_groq_client
from app.services.rate_limiter import limiter

test_engine = create_async_engine(settings.DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session")
async def client(setup_database):
    limiter._storage = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def registered_user(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"username": "testuser", "email": "testuser@example.com", "password": "SecurePass123"},
    )
    assert response.status_code in (201, 409)
    return {"username": "testuser", "password": "SecurePass123"}


@pytest_asyncio.fixture(scope="session")
async def auth_token(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/auth/login",
        json={"username": registered_user["username"], "password": registered_user["password"]},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def auth_headers(auth_token: str):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture(scope="session")
async def registered_equipment(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/equipment",
        json={
            "equipment_id": "EQ-TEST-001",
            "equipment_type": "motor",
            "location": "Plant A",
        },
        headers=auth_headers,
    )
    assert response.status_code in (201, 409)
    if response.status_code == 409:
        eq_list = await client.get("/equipment", headers=auth_headers)
        for eq in eq_list.json():
            if eq["equipment_id"] == "EQ-TEST-001":
                return eq
    return response.json()


@pytest.fixture(autouse=True)
def reset_groq():
    reset_groq_client()
    yield
    reset_groq_client()
