from pathlib import Path

from openai import AsyncOpenAI
import structlog

from app.helpers.pdf_processing import iter_chunk_embedding
from app.core.database import AsyncSessionLocal, AsyncSession
from app.models import DocumentState, DocumentEmbedding, Documents
from sqlalchemy import delete as SQDelete, select, update

logger = structlog.get_logger()


async def _update_state(session: AsyncSession, doc_id: int, state: DocumentState):
    await session.execute(
        update(Documents).where(Documents.id == doc_id).values(status=state)
    )

    await session.commit()




async def ingest_document(
    project_id: int,
    doc_id: int,
    client: AsyncOpenAI,
    file_path: str
):
    """ 
        Ingest PDF document. 
        Covert it into chunks and save with it's embeddings in database.
    """

    async with AsyncSessionLocal() as db:

        
        total = 0
        
        try:
            await _update_state(db , doc_id, DocumentState.PROCESSING)
            async for (chunks, embeddings) in iter_chunk_embedding(file_path, client):
                doc_embed = [
                    DocumentEmbedding(
                        document_id = doc_id,
                        project_id = project_id,
                        chunk_metadata = {},
                        content = chunk,
                        embedding = embedding
                    ) for chunk, embedding in zip(chunks, embeddings)
                ]
    
                db.add_all(doc_embed)
                await db.commit()
    
                total += len(chunks)
                logger.info("document_ingested", document_id=doc_id, chunks=total)
    
            if total == 0:
                raise ValueError("No text extracted from PDF")
    
            await _update_state(db , doc_id, DocumentState.READY)

        except Exception as err:
            logger.exception("document_ingest_failed", document_id=doc_id)
            await db.rollback()

            await db.execute(
                SQDelete(DocumentEmbedding).where(DocumentEmbedding.document_id == doc_id)
            )

            await db.commit()
            await _update_state(db, doc_id, DocumentState.FAILED)

        finally:
            Path(file_path).unlink(missing_ok=True)
"""

"""