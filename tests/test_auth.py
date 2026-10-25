from datetime import datetime, timedelta, timezone

from fastapi import status
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from tests.conftest import create_test_user, login_user, auth_header
from app.models import User
from app.core import security
from sqlalchemy import select
from freezegun import freeze_time



# ========= LOGIN =============
@pytest.mark.anyio
async def test_user_wrong_password_login(client: AsyncClient):

    username: str = "user@example.com"
    user = await create_test_user(client, username = username)

    login_data = {
        "username": username,
        "password": "Wrong password"
    }

    response = await client.post(
        "/api/v1/auth/login",
        data = login_data
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"login with wrong password didn't return 401"
    assert response.json()['detail'] == 'Wrong Username or Password'


@pytest.mark.anyio
async def test_empty_login_felds(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "", "password": ""}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post(
        "/api/v1/auth/login",
        data={}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT



# test login with 'username + trailing space( )' combo
@pytest.mark.anyio
async def test_login_username_trailing_space(client: AsyncClient):
    username = "user@example.com"
    await create_test_user(client, username=username)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": username + " ", "password": "Pass@123456"}
    )
    assert response.status_code != status.HTTP_200_OK


# test if username is case sensitive in login and registration
@pytest.mark.anyio
async def test_login_username_case_sensitivity(client: AsyncClient):
    username = "User@Example.com"
    await create_test_user(client, username=username)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": username.lower(), "password": "Pass@123456"}
    )
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED)


# test /api/v1/auth/me with unauthenticated user
@pytest.mark.anyio
async def test_unauthenticated_get_current_user_info(client: AsyncClient):

    response = await client.get(
        "/api/v1/auth/me"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()['detail'] == 'Not authenticated'


# ======= AFTER LOGIN ==========

# test /api/v1/auth/me
@pytest.mark.anyio
async def test_get_current_user_info(client: AsyncClient):

    username = "user@example.com"
    user = await create_test_user(client, username=username)
    token = await login_user(client)
    header = auth_header(token)


    response = await client.get(
        "/api/v1/auth/me",
        headers=header
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['username'] == username

    

# test login endpoint when user is logged in
@pytest.mark.anyio
async def test_login_while_already_authenticated(client: AsyncClient):
    username = "user@example.com"
    await create_test_user(client, username=username)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "Pass@123456"},
        headers=header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ======= REGISTRATION =========

# normal registration flow
@pytest.mark.anyio
async def test_normal_registration(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "newuser@example.com",
            "name": "New User",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        }
    )
    assert response.status_code == status.HTTP_201_CREATED


# register two users with same username
@pytest.mark.anyio
async def test_register_duplicate_username(client: AsyncClient):
    username = "dup@example.com"
    await create_test_user(client, username=username)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "name": "Second",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        }
    )
    assert response.status_code != status.HTTP_201_CREATED


# registration with missing fields
@pytest.mark.anyio
async def test_registration_missing_fields(client: AsyncClient):
    base = {
        "username": "miss@example.com",
        "name": "Name",
        "password": "Pass@123456",
        "password_repeat": "Pass@123456"
    }
    for key in list(base.keys()):
        payload = {k: v for k, v in base.items() if k != key}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# registration with mismatched type fields
@pytest.mark.anyio
async def test_registration_mismatched_types(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": 123,
            "name": True,
            "password": 12345678,
            "password_repeat": 12345678
        }
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# registter 

# test registration endpoint when user is logged in
@pytest.mark.anyio
async def test_registration_while_authenticated(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "another@example.com",
            "name": "Another",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        },
        headers=header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

