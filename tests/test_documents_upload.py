import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# ---- adjust these imports to your project layout ---------------------------
from app.main import app
from app.models import DocumentState, Documents
from app.routers import project as documents_router
from app.core.deps import get_ai_client
from tests.conftest import create_project, create_user_and_login, make_pdf, upload
# -----------------------------------------------------------------------------

pytestmark = pytest.mark.anyio


# --------------------------------------------------------------------------- #
# Fixtures: everything that touches the outside world is replaced
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def fake_llm_client():
    """Never build a real OpenAI client in router tests."""
    app.dependency_overrides[get_ai_client] = lambda: AsyncMock()
    yield
    app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture(autouse=True)
def ingest_calls(monkeypatch) -> list[dict]:
    """
    Replace ingest_document in the *router's* namespace (where it is looked up).
    With httpx's ASGITransport the background task runs before `client.post`
    returns, so without this the real ingestion would run inside every test.
    A plain async function is used (not a Mock) so Starlette awaits it properly.
    """
    calls: list[dict] = []

    async def fake_ingest(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(documents_router, "ingest_document", fake_ingest)
    return calls


@pytest.fixture(autouse=True)
def tmp_upload_dir(tmp_path, monkeypatch) -> Path:
    """Write uploads into pytest's tmp dir so we can assert on what is left behind."""
    monkeypatch.setattr(documents_router, "TEMP_FILE_DIRECTORY", str(tmp_path))
    return tmp_path


@pytest.fixture
async def project(client):
    headers = await create_user_and_login(client)
    project_id = await create_project(client, headers=headers)
    return headers, project_id


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pdf_variant(n: int) -> bytes:
    return make_pdf(f"variant-{n}")


async def count_docs(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(Documents))


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
async def test_upload_success(client, project, db_session, tmp_upload_dir, ingest_calls):
    headers, project_id = project
    content = make_pdf()

    response = await upload(client, headers, project_id, content, filename="report.pdf")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == DocumentState.PENDING

    doc = await db_session.get(Documents, body["document_id"])
    assert doc.project_id == project_id
    assert doc.filename == "report.pdf"
    assert doc.status == DocumentState.PENDING
    assert doc.content_hash == hashlib.sha256(content).hexdigest()

    # file was kept on disk (handed off to the background task) and is intact
    saved = Path(doc.temp_path)
    assert saved.parent == tmp_upload_dir
    assert saved.read_bytes() == content

    # background task scheduled exactly once with the right arguments
    assert len(ingest_calls) == 1
    call = ingest_calls[0]
    assert call["project_id"] == project_id
    assert call["doc_id"] == doc.id
    assert call["file_path"] == str(saved)
    assert call["client"] is not None


async def test_same_pdf_allowed_in_different_projects(client, project):
    headers, first_project = project
    second_project = await create_project(client, headers=headers)
    content = make_pdf()

    r1 = await upload(client, headers, first_project, content)
    r2 = await upload(client, headers, second_project, content)

    assert r1.status_code == 202
    assert r2.status_code == 202


# --------------------------------------------------------------------------- #
# Validation failures: nothing persisted, nothing left on disk, no ingestion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "content, content_type, expected_status",
    [
        pytest.param(make_pdf(), "text/plain", 415, id="wrong-content-type"),
        pytest.param(b"definitely not a pdf", "application/pdf", 415, id="bad-magic-bytes"),
        pytest.param(b"", "application/pdf", 400, id="empty-file"),
    ],
)
async def test_rejected_uploads(
    client, project, db_session, tmp_upload_dir, ingest_calls,
    content, content_type, expected_status,
):
    headers, project_id = project

    response = await upload(client, headers, project_id, content, content_type=content_type)

    assert response.status_code == expected_status
    assert await count_docs(db_session) == 0
    assert list(tmp_upload_dir.iterdir()) == []
    assert ingest_calls == []


async def test_file_too_large(client, project, db_session, tmp_upload_dir, ingest_calls, monkeypatch):
    monkeypatch.setattr(documents_router, "MAX_DOCUMENT_SIZE", 100)
    headers, project_id = project

    response = await upload(client, headers, project_id, b"%PDF-" + b"0" * 500)

    assert response.status_code == 413
    assert await count_docs(db_session) == 0
    assert list(tmp_upload_dir.iterdir()) == []
    assert ingest_calls == []


async def test_duplicate_document_in_same_project(client, project, db_session, tmp_upload_dir):
    headers, project_id = project
    content = make_pdf()

    first = await upload(client, headers, project_id, content)
    second = await upload(client, headers, project_id, content)

    assert first.status_code == 202
    assert second.status_code == 409
    assert await count_docs(db_session) == 1
    # only the first upload's file remains
    assert len(list(tmp_upload_dir.iterdir())) == 1


async def test_document_limit_reached(client, project, db_session, monkeypatch):
    monkeypatch.setattr(documents_router, "MAX_DOCUMENTS_PER_PROJECT", 2)
    headers, project_id = project

    for i in range(2):
        assert (await upload(client, headers, project_id, pdf_variant(i))).status_code == 202

    response = await upload(client, headers, project_id, pdf_variant(99))

    assert response.status_code == 409
    assert await count_docs(db_session) == 2


# --------------------------------------------------------------------------- #
# Auth / ownership
# --------------------------------------------------------------------------- #
async def test_requires_authentication(client, project):
    _, project_id = project
    response = await upload(client, {}, project_id, make_pdf())
    assert response.status_code == 401


async def test_cannot_upload_to_someone_elses_project(client, project, db_session):
    _, project_id = project
    # adjust: a second, distinct user
    other_headers = await create_user_and_login(client, username="other@example.com")

    response = await upload(client, other_headers, project_id, make_pdf())

    assert response.status_code in (403, 404)  # whichever OwnedProject raises
    assert await count_docs(db_session) == 0


async def test_nonexistent_project(client, project):
    headers, _ = project
    response = await upload(client, headers, 999_999, make_pdf())
    assert response.status_code in (403, 404)


# --------------------------------------------------------------------------- #
# Filename handling
# --------------------------------------------------------------------------- #
async def test_filename_path_components_are_stripped(client, project, db_session, tmp_upload_dir):
    headers, project_id = project

    response = await upload(client, headers, project_id, make_pdf(), filename="../../etc/passwd.pdf")

    assert response.status_code == 202
    doc = await db_session.get(Documents, response.json()["document_id"])
    assert doc.filename == "passwd.pdf"
    assert Path(doc.temp_path).parent == tmp_upload_dir  # never escapes the temp dir


async def test_long_filename_is_truncated(client, project, db_session):
    headers, project_id = project
    long_name = "a" * 1000 + ".pdf"

    response = await upload(client, headers, project_id, make_pdf(), filename=long_name)

    assert response.status_code == 202
    doc = await db_session.get(Documents, response.json()["document_id"])
    assert len(doc.filename) == documents_router.MAX_FILENAME_LENGTH


# --------------------------------------------------------------------------- #
# Failure handling after the file has already been written to disk
# --------------------------------------------------------------------------- #
async def test_commit_race_returns_409_and_cleans_file(
    client, project, tmp_upload_dir, ingest_calls, monkeypatch
):
    """Two concurrent uploads of the same file: the unique constraint fires on commit."""
    headers, project_id = project

    async def boom(self):
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    monkeypatch.setattr(AsyncSession, "commit", boom)

    response = await upload(client, headers, project_id, make_pdf())

    assert response.status_code == 409
    assert list(tmp_upload_dir.iterdir()) == []
    assert ingest_calls == []


async def test_unexpected_error_returns_500_and_cleans_file(
    client, project, tmp_upload_dir, ingest_calls, monkeypatch
):
    headers, project_id = project

    async def boom(self):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(AsyncSession, "commit", boom)

    response = await upload(client, headers, project_id, make_pdf())

    assert response.status_code == 500
    assert response.json()["detail"] == "Something went wrong. Please try again"
    assert list(tmp_upload_dir.iterdir()) == []
    assert ingest_calls == []