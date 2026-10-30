from fastapi import status
import pytest
from httpx import AsyncClient
from app.models import DocumentState
from tests.conftest import create_project, create_user_and_login, make_pdf, upload


# ============= CREATE PROJECT =============

@pytest.mark.anyio
async def test_create_project_success(client: AsyncClient):
    """Test creating a project successfully when authenticated."""
    headers = await create_user_and_login(client)

    response = await client.post(
        "/api/v1/projects",
        json={
            "name": "AI Knowledge Base",
            "description": "RAG pipeline for internal documents."
        },
        headers=headers
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "AI Knowledge Base"
    assert data["description"] == "RAG pipeline for internal documents."
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.anyio
async def test_create_project_unauthenticated(client: AsyncClient):
    """Test creating a project without an auth token fails with 401."""
    response = await client.post(
        "/api/v1/projects",
        json={
            "name": "Unauthorized Project",
            "description": "Should fail."
        }
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.anyio
async def test_create_project_validation_error(client: AsyncClient):
    """Test creating a project with missing or invalid fields fails with 422."""
    headers = await create_user_and_login(client)

    # Missing description
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Incomplete Project"},
        headers=headers
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ============= LIST PROJECTS =============

@pytest.mark.anyio
async def test_list_projects_success(client: AsyncClient):
    """Test listing projects for the authenticated user with pagination and isolation."""
    # User A
    headers_a = await create_user_and_login(client, username="userA@example.com")

    # Create two projects for User A
    for i in range(2):
        await client.post(
            "/api/v1/projects",
            json={"name": f"Project A{i}", "description": "Desc"},
            headers=headers_a
        )

    # User B
    headers_b = await create_user_and_login(client)

    # Create one project for User B
    await client.post(
        "/api/v1/projects",
        json={"name": "Project B0", "description": "Desc"},
        headers=headers_b
    )

    # List User A projects (should only see User A's 2 projects)
    response_a = await client.get("/api/v1/projects", headers=headers_a)
    assert response_a.status_code == status.HTTP_200_OK
    projects_a = response_a.json()
    assert len(projects_a) == 2
    assert all(p["name"].startswith("Project A") for p in projects_a)

    # Test pagination parameters (skip / limit)
    response_paginated = await client.get("/api/v1/projects?skip=0&limit=1", headers=headers_a)
    assert response_paginated.status_code == status.HTTP_200_OK
    assert len(response_paginated.json()) == 1


# ============= GET PROJECT BY ID =============

@pytest.mark.anyio
async def test_get_project_success(client: AsyncClient):
    """Test retrieving a specific project by ID."""
    headers = await create_user_and_login(client)

    # Create project
    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "Target Project", "description": "Find me"},
        headers=headers
    )
    project_id = create_res.json()["id"]

    # Fetch project
    response = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == project_id
    assert response.json()["name"] == "Target Project"


@pytest.mark.anyio
async def test_get_project_not_found(client: AsyncClient):
    """Test fetching a non-existent project returns 404."""
    headers = await create_user_and_login(client)

    response = await client.get("/api/v1/projects/99999", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_get_other_user_project_forbidden(client: AsyncClient):
    """Test that a user cannot access another user's project (returns 404 due to ownership scoping)."""
    # User 1 creates a project
    headers_1 = await create_user_and_login(client)
    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "User1 Project", "description": "Private"},
        headers=headers_1
    )
    project_id = create_res.json()["id"]

    # User 2 tries to access User 1's project
    headers_2 = await create_user_and_login(client, username="user2@gmail.com")
    
    response = await client.get(f"/api/v1/projects/{project_id}", headers=headers_2)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============= UPDATE PROJECT =============

@pytest.mark.anyio
async def test_update_project_success(client: AsyncClient):
    """Test updating a project (partial update via PATCH)."""
    headers = await create_user_and_login(client)

    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "Old Name", "description": "Old Desc"},
        headers=headers
    )
    project_id = create_res.json()["id"]

    # Update only name
    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "New Name"},
        headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Old Desc"  # description remains unchanged


@pytest.mark.anyio
async def test_update_project_not_found(client: AsyncClient):
    """Test updating a non-existent project returns 404."""
    headers = await create_user_and_login(client)

    response = await client.patch(
        "/api/v1/projects/99999",
        json={"name": "Ghost Project"},
        headers=headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============= DELETE PROJECT =============

@pytest.mark.anyio
async def test_delete_project_success(client: AsyncClient):
    """Test deleting an owned project successfully."""
    headers = await create_user_and_login(client)

    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "To Delete", "description": "Will be deleted"},
        headers=headers
    )
    project_id = create_res.json()["id"]

    # Delete project
    delete_res = await client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert delete_res.status_code == status.HTTP_204_NO_CONTENT

    # Verify it's gone
    get_res = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_delete_project_not_found(client: AsyncClient):
    """Test deleting a non-existent project returns 404."""
    headers = await create_user_and_login(client)

    response = await client.delete("/api/v1/projects/99999", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND