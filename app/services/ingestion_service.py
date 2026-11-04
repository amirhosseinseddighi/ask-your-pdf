from abc import ABC, abstractmethod
from pathlib import Path

from openai import AsyncOpenAI
import structlog

from app.services.chunking_service import pdf_chunker
from app.core.database import AsyncSessionLocal, AsyncSession
from app.models import DocumentState, DocumentEmbedding, Documents
from sqlalchemy import delete as SQDelete, select, update




class IngestorBase(ABC):
    """ Ingest document """
    
    @abstractmethod
    async def ingest(self, project_id: int, doc_id: int, client: AsyncOpenAI, document_path: str):
        """ Ingest document """
        ...


class PDFIngestor(IngestorBase):
    def __init__(self) -> None:
        super().__init__()
        self.logger = structlog.get_logger()


    async def _update_state(self, session: AsyncSession, doc_id: int, state: DocumentState):
        await session.execute(
            update(Documents).where(Documents.id == doc_id).values(status=state)
        )

        await session.commit()


    async def ingest(self, project_id: int, doc_id: int, client: AsyncOpenAI, document_path: str):
        """ 
        Ingest PDF document. 
        Covert it into chunks and save with it's embeddings in database.
        """

        async with AsyncSessionLocal() as db:

            
            total = 0
            
            try:
                await self._update_state(db , doc_id, DocumentState.PROCESSING)
                async for (chunks, embeddings) in pdf_chunker.chunk(document_path, client):
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
                    self.logger.info("document_ingested", document_id=doc_id, chunks=total)
        
                if total == 0:
                    raise ValueError("No text extracted from PDF")
        
                await self._update_state(db , doc_id, DocumentState.READY)

            except Exception as err:
                self.logger.exception("document_ingest_failed", document_id=doc_id)
                await db.rollback()

                await db.execute(
                    SQDelete(DocumentEmbedding).where(DocumentEmbedding.document_id == doc_id)
                )

                await db.commit()
                await self._update_state(db, doc_id, DocumentState.FAILED)

            finally:
                Path(document_path).unlink(missing_ok=True)



pdf_ingestor = PDFIngestor()