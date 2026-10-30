import asyncio
from pathlib import Path
import re
from typing import AsyncIterator, Iterator
from openai import AsyncOpenAI
import pymupdf
import structlog
import pymupdf4llm
from app.core.config import settings

logger = structlog.get_logger()

CHUNK_SIZE = 900
PAGES_PER_BATCH = 10
MAX_EMBED_CHUNK_SIZE=64

def chunk_markdown(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    parts = re.split(r"(\n#+\s.*\n)", text)
    chunks, current = [], ""
    for part in parts:
        # Hard-split any single part that is bigger than chunk_size
        pieces = [part[i:i + chunk_size] for i in range(0, len(part), chunk_size)] or [""]
        for piece in pieces:
            if current and len(current) + len(piece) > chunk_size:
                chunks.append(current.strip())
                current = piece
            else:
                current += piece
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]

def iter_markdown_batches(file_path: str, pages_per_batch: int = PAGES_PER_BATCH) -> Iterator[str]:
    """ Convert PDF to markdown and chunk it"""
    with pymupdf.open(file_path) as document:
        total_pages = document.page_count
        for page_index in range(0, total_pages, pages_per_batch):
            last_batch_page_index = min(page_index + pages_per_batch, total_pages)
            pages = list(range(page_index, last_batch_page_index))
            
            yield pymupdf4llm.to_markdown(document, pages=pages)
            
            logger.debug("pdf_batch_converted", start=page_index, total=total_pages)




def iter_chunks(file_path: str):
    carry = ""
    for md in iter_markdown_batches(file_path, pages_per_batch=PAGES_PER_BATCH):
        chunks = chunk_markdown(carry + "\n" + md)

        if not chunks:
            continue

        carry = chunks.pop()
        if chunks:
            yield chunks

    if carry:
        yield [carry]


async def get_embeddings(chunks: list[str], client: AsyncOpenAI) -> list[list[float]]:
    """ Get embeddings of chunks"""
    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL_NAME,
        input=chunks,
        dimensions=1536
    )

    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]



async def iter_chunk_embedding(file_path: str, client: AsyncOpenAI) -> AsyncIterator:
    chunk_generator = iter_chunks(file_path)
    total = 0
    while True:
        batch = await asyncio.to_thread(next, chunk_generator, None)
        if batch is None:
            break

        for chunk_index in range(0, len(batch), MAX_EMBED_CHUNK_SIZE):
            sub = batch[chunk_index: chunk_index + MAX_EMBED_CHUNK_SIZE]
            embeddings = await get_embeddings(sub, client)
            yield sub, embeddings
            total += len(sub)

        logger.info("pdf_chunks_saved", total=total)