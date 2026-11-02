from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import ChatSession, Project


async def check_project_exists_and_belong_to_the_user(project_id, user_id):
    """ Return the project if it exists and `None` if it doesn't """
    statement = (
        select(Project)
    .where(Project.id == project_id)
    .where(Project.user_id == user_id)
    )
    
    async with AsyncSessionLocal() as db:
        res =await db.execute(statement)
        return res.scalar_one_or_none()


async def check_chat_exists_and_belong_to_the_user(chat_id, user_id):
    """ Return the chat session if it exists and `None` if it doesn't """
    statement = (
        select(ChatSession)
        .where(ChatSession.id == chat_id)
        .where(ChatSession.user_id == user_id)
    )
    
    async with AsyncSessionLocal() as db:
            res =await db.execute(statement)
            return res.scalar_one_or_none()

