import json
from typing import AsyncGenerator
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

    async def run_tool(self, name: str, arguments: str, project_id: int, client: AsyncOpenAI) -> str:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "Error: invalid tool arguments."

        if name == "get_relevant_information":
            chunks = await retrieval_service.get_relevant_chunks_from_user_query(
                user_query=args.get("query", ""),
                project_id=project_id,
                client=client,
            )
            if not chunks:
                return "No relevant information found in the documents."
            return "\n\n---\n\n".join(chunks)

        return f"Unknown tool: {name}"

    

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
            results = req.scalars().all()

        history = list()
        for chat_message in results:
            history.append({"role": chat_message.role, "content": chat_message.text})


        return history


    async def ask_stream(self, session_id: UUID, project_id: int, user_query: str, client: AsyncOpenAI) -> AsyncGenerator:
        history = await self.get_recent_messages(session_id)
        messages = self.build_input(history, user_query)

        final_parts = []

        for _ in range(MAX_TOOL_ROUNDS):

            round_text: list[str] = list()
            calls: dict[int, dict] = {}

            response = await client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                tools=Tools.tools,
                stream=True
            )

            async for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    round_text.append(delta.content)
                    yield {"type": "token", "content": delta.content}


                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        idx = tool_call.index if tool_call.index is not None else 0
                        entry = calls.setdefault(idx, {"id": "", "name": "","arguments": ""})
                        if tool_call.id:
                            entry['id'] = tool_call.id

                        if tool_call.function:
                            if tool_call.function.name:
                                entry['name'] += tool_call.function.name

                            if tool_call.function.arguments:
                                entry['arguments'] += tool_call.function.arguments

            # the round is done here
            if not calls:
                final_parts = round_text
                break

            all_calls = [calls[i] for i in sorted(calls)]

            messages.append({
                "role": "assistant",
                "content": "".join(round_text) or None,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": c["arguments"]},
                    }
                    for c in all_calls
                ],
            })

            yield {"type": "status", "content": "searching_documents"}


            for c in all_calls:
                result = await self.run_tool(c["name"], c["arguments"], project_id, client)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})

        answer = "".join(final_parts).strip()
        if not answer:
            answer = "Sorry, I couldn't find an answer. Please try rephrasing your question."
            yield {"type": "token", "content": answer}

        await self.save_exchange(session_id, user_query, answer)
        yield {"type": "done"}

            
                    


chat_service = ChatService()