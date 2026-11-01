from typing import Sequence

from openai import AsyncOpenAI
from openai.types import Embedding
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import DocumentEmbedding, ChatMessage

async def get_text_embeddings(query: str, client: AsyncOpenAI) -> list[Embedding]:
    """ Return embeddings of the `query` using embedding model defined in settings """
    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL_NAME,
        input=query,
        dimensions=1536
    )

    return response.data

async def retrieve_relevant_chunks(
        query_embedding: list[Embedding], 
        project_id: int,
        similarity_threshold: float = 0.90,
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
        user_query: str, 
        project_id: int,
        client: AsyncOpenAI
) -> Sequence[str]:
    user_query_embeddings = await get_text_embeddings(user_query, client)
    relevant_chunks = await retrieve_relevant_chunks(user_query_embeddings, project_id)
    return relevant_chunks


async def get_chat_session_history(session_id: int):
    """
        Return history of chat session given `session_id`.
        You should check authorization before using this function
    """
    statement = (
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )

    results = None

    async with AsyncSessionLocal() as db:
        req = await db.execute(statement)
        results = req.all()

    return results