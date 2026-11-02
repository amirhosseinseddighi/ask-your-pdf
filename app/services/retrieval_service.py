


from typing import Sequence

from openai import AsyncOpenAI
from openai.types import Embedding
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import DocumentEmbedding


SIMILARITY_THRESHOLD=0.5


class RetrievalService:
    def __init__(self) -> None:
        pass

        
    async def get_text_embeddings(self,query: str, client: AsyncOpenAI) -> list[float]:
        """ Return embeddings of the `query` using embedding model defined in settings """
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL_NAME,
            input=query,
            dimensions=1536
        )

        return response.data[0].embedding

    async def retrieve_relevant_chunks(
            self,
            query_embedding: list[Embedding], 
            project_id: int,
            similarity_threshold: float = SIMILARITY_THRESHOLD,
            n_top_chunks: int = 5
    ) -> Sequence[str]:
        """
            Search vector database to find most relevant 
            chunks based on input query embedding.
            Return chunks with similarity >= `similarity_threshold`
        """
        
        distance = DocumentEmbedding.embedding.cosine_distance(query_embedding)

        statement = (
            select(DocumentEmbedding.content)
            .where(DocumentEmbedding.project_id == project_id)
            .where(distance <= 1 - similarity_threshold)
            .order_by(distance)
            .limit(n_top_chunks)
        )

        async with AsyncSessionLocal() as conn:
            results = await conn.scalars(statement)
            return results.all()


    async def get_relevant_chunks_from_user_query(
            self,
            user_query: str, 
            project_id: int,
            client: AsyncOpenAI
    ) -> Sequence[str]:
        """ Retrieve relevant text chunks based on user query """
        user_query_embeddings = await self.get_text_embeddings(user_query, client)
        relevant_chunks = await self.retrieve_relevant_chunks(user_query_embeddings, project_id)
        return relevant_chunks


retrieval_service = RetrievalService()