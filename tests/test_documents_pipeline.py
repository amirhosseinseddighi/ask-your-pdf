import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.helpers import pdf_processing
from app.helpers.pdf_processing import chunk_markdown, CHUNK_SIZE, MAX_EMBED_CHUNK_SIZE
from app.services import document_service
from app.models import DocumentEmbedding, DocumentState, Documents
from tests.conftest import create_project, create_user_and_login
# -----------------------------------------------------------------------------

pytestmark = pytest.mark.anyio


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


# =========================================================================== #
# chunk_markdown (pure function)
# =========================================================================== #
def test_chunk_markdown_empty():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n ") == []


def test_chunk_markdown_respects_chunk_size():
    text = "word " * 2000
    chunks = chunk_markdown(text, chunk_size=200)
    assert chunks
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_markdown_does_not_lose_content():
    text = "# Title\n" + ("lorem ipsum dolor sit amet " * 100) + "\n## Sub\n" + ("x" * 500)
    chunks = chunk_markdown(text, chunk_size=150)
    assert _squash("".join(chunks)) == _squash(text)


def test_chunk_markdown_hard_splits_oversized_part():
    chunks = chunk_markdown("a" * 1000, chunk_size=100)
    assert len(chunks) == 10
    assert all(len(c) == 100 for c in chunks)


def test_chunk_markdown_small_text_is_single_chunk():
    assert chunk_markdown("# Hi\nshort text") == ["# Hi\nshort text"]


# =========================================================================== #
# iter_chunks (PDF reading mocked out)
# =========================================================================== #
def test_iter_chunks_yields_everything_including_final_carry(monkeypatch):
    batches = ["a" * 500, "b" * 500, "c" * 500]
    monkeypatch.setattr(pdf_processing, "iter_markdown_batches", lambda *a, **kw: iter(batches))

    yielded = list(pdf_processing.iter_chunks("ignored.pdf"))
    flat = [c for group in yielded for c in group]

    assert _squash("".join(flat)) == "a" * 500 + "b" * 500 + "c" * 500
    assert all(len(c) <= CHUNK_SIZE for c in flat)


def test_iter_chunks_empty_document(monkeypatch):
    monkeypatch.setattr(pdf_processing, "iter_markdown_batches", lambda *a, **kw: iter(["", "  "]))
    assert list(pdf_processing.iter_chunks("ignored.pdf")) == []


# =========================================================================== #
# get_embeddings (fake OpenAI client)
# =========================================================================== #
async def test_get_embeddings_sorts_by_index_and_passes_params(monkeypatch):
    monkeypatch.setattr(pdf_processing.settings, "EMBEDDING_MODEL_NAME", "test-model", raising=False)
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[
                        SimpleNamespace(index=2, embedding=[3.0]),
                        SimpleNamespace(index=0, embedding=[1.0]),
                        SimpleNamespace(index=1, embedding=[2.0]),
                    ]
                )
            )
        )
    )

    result = await pdf_processing.get_embeddings(["a", "b", "c"], client)

    assert result == [[1.0], [2.0], [3.0]]
    client.embeddings.create.assert_awaited_once_with(
        model="test-model", input=["a", "b", "c"], dimensions=1536
    )


# =========================================================================== #
# iter_chunk_embedding (sub-batching)
# =========================================================================== #
async def test_iter_chunk_embedding_splits_into_sub_batches(monkeypatch):
    big = [f"c{i}" for i in range(MAX_EMBED_CHUNK_SIZE + 6)]  # 70 -> 64 + 6
    monkeypatch.setattr(pdf_processing, "iter_chunks", lambda path: iter([big, ["tail"]]))

    seen_inputs = []

    async def fake_get_embeddings(chunks, client):
        seen_inputs.append(list(chunks))
        return [[0.0] for _ in chunks]

    monkeypatch.setattr(pdf_processing, "get_embeddings", fake_get_embeddings)

    results = [r async for r in pdf_processing.iter_chunk_embedding("x.pdf", AsyncMock())]

    assert [len(chunks) for chunks, _ in results] == [MAX_EMBED_CHUNK_SIZE, 6, 1]
    assert all(len(chunks) == len(embs) for chunks, embs in results)
    assert [c for chunks, _ in results for c in chunks] == big + ["tail"]
    assert seen_inputs[0] == big[:MAX_EMBED_CHUNK_SIZE]


# =========================================================================== #
# ingest_document (service) - uses the test DB session
# =========================================================================== #
class _SessionCtx:
    """Mimics `async with AsyncSessionLocal() as db` but hands back the test session."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
async def pending_doc(client, db_session, tmp_path, use_test_session):
    headers = await create_user_and_login(client)
    project_id = await create_project(client, headers=headers)

    pdf_path = tmp_path / "x.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    doc = Documents(
        project_id=project_id,
        filename="x.pdf",
        temp_path=str(pdf_path),
        status=DocumentState.PENDING,
        content_hash="deadbeef",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
def use_test_session(monkeypatch, db_session):
    monkeypatch.setattr(document_service, "AsyncSessionLocal", lambda: _SessionCtx(db_session))


async def _embedding_count(db, doc_id) -> int:
    return await db.scalar(
        select(func.count()).select_from(DocumentEmbedding).where(DocumentEmbedding.document_id == doc_id)
    )


async def test_ingest_success(monkeypatch, db_session, pending_doc):
    async def fake_iter(file_path, client):
        yield ["chunk 1", "chunk 2"], [[0.1] * 1536, [0.2] * 1536]
        yield ["chunk 3"], [[0.3] * 1536]

    monkeypatch.setattr(document_service, "iter_chunk_embedding", fake_iter)

    await document_service.ingest_document(
        project_id=pending_doc.project_id,
        doc_id=pending_doc.id,
        client=AsyncMock(),
        file_path=pending_doc.temp_path,
    )

    await db_session.refresh(pending_doc)  # core UPDATE bypasses the identity map
    assert pending_doc.status == DocumentState.READY
    assert await _embedding_count(db_session, pending_doc.id) == 3


async def test_ingest_failure_midway_cleans_up_and_marks_failed(monkeypatch, db_session, pending_doc):
    async def fake_iter(file_path, client):
        yield ["chunk 1"], [[0.1] * 1536]
        raise RuntimeError("embedding API down")

    monkeypatch.setattr(document_service, "iter_chunk_embedding", fake_iter)

    await document_service.ingest_document(
        project_id=pending_doc.project_id,
        doc_id=pending_doc.id,
        client=AsyncMock(),
        file_path=pending_doc.temp_path,
    )

    await db_session.refresh(pending_doc)
    assert pending_doc.status == DocumentState.FAILED
    assert await _embedding_count(db_session, pending_doc.id) == 0  # partial chunks removed


async def test_ingest_pdf_without_text_is_failed(monkeypatch, db_session, pending_doc):
    async def fake_iter(file_path, client):
        return
        yield  # pragma: no cover  (makes this an async generator that yields nothing)

    monkeypatch.setattr(document_service, "iter_chunk_embedding", fake_iter)

    await document_service.ingest_document(
        project_id=pending_doc.project_id,
        doc_id=pending_doc.id,
        client=AsyncMock(),
        file_path=pending_doc.temp_path,
    )

    await db_session.refresh(pending_doc)
    assert pending_doc.status == DocumentState.FAILED


@pytest.mark.parametrize("succeed", [True, False], ids=["ready", "failed"])
async def test_ingest_removes_temp_file(monkeypatch, pending_doc, succeed):
    async def fake_iter(file_path, client):
        if not succeed:
            raise RuntimeError("boom")
        yield ["c"], [[0.0] * 1536]

    monkeypatch.setattr(document_service, "iter_chunk_embedding", fake_iter)

    await document_service.ingest_document(
        project_id=pending_doc.project_id,
        doc_id=pending_doc.id,
        client=AsyncMock(),
        file_path=pending_doc.temp_path,
    )

    from pathlib import Path

    assert not Path(pending_doc.temp_path).exists()