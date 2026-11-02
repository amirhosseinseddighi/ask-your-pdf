import json
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select
import structlog

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, MessageRole
from app.ai.prompts import Prompts
from app.ai.tools import Tools
from app.services.retrieval_service import retrieval_service

HISTORY_LIMIT = 6
MAX_TOOL_ROUNDS = 3


logger = structlog.get_logger()


class ChatService:

    async def get_recent_messages(self, session_id: UUID, limit: int = HISTORY_LIMIT) -> list[dict]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        async with AsyncSessionLocal() as db:
            rows = (await db.scalars(statement)).all()
        return [{"role": m.role.value, "content": m.text} for m in reversed(rows)]

    async def save_exchange(self, session_id: UUID, user_text: str, assistant_text: str) -> None:
        """Persist both messages in one transaction."""
        async with AsyncSessionLocal() as db:
            db.add_all([
                ChatMessage(session_id=session_id, role=MessageRole.USER, text=user_text),
                ChatMessage(session_id=session_id, role=MessageRole.ASSISTANT, text=assistant_text),
            ])
            await db.commit()

    def build_input(self, history: list[dict], user_query: str) -> list:
        return [
            {"role": "system", "content": Prompts.SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_query},
        ]

    async def run_tool(self, tool_call, project_id: int, client: AsyncOpenAI) -> str:
        args = json.loads(tool_call.function.arguments)

        logger.info("tool_call", tool_call = tool_call, project_id = project_id)
        
        if tool_call.function.name == "get_relevant_information":
            chunks = await retrieval_service.get_relevant_chunks_from_user_query(
                user_query=args["query"],
                project_id=project_id,
                client=client,
            )
            if not chunks:
                return "No relevant information found in the documents."
            return "\n\n---\n\n".join(chunks)

        

        return f"Unknown tool: {tool_call.function.name}"


    async def get_chat_session_history(self,session_id: UUID):
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

        history = list()
        for chat_message in results:
            history.append({"role": chat_message.role, "content": chat_message.text})


        return history


    async def ask(self, session_id: UUID, project_id: int, user_query: str, client: AsyncOpenAI) -> str:
        history = await self.get_recent_messages(session_id)
        messages = self.build_input(history, user_query)

        answer = None
        for _ in range(MAX_TOOL_ROUNDS):
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                tools=Tools.tools,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                answer = msg.content
                break

            # Add the assistant's tool-call message to the context
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Run each tool and add its result
            for tc in msg.tool_calls:
                result = await self.run_tool(tc, project_id, client)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        if not answer:
            answer = "Sorry, I couldn't find an answer. Please try rephrasing your question."

        await self.save_exchange(session_id, user_query, answer)
        return answer


chat_service = ChatService()