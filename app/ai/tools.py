from app.services.retrieval_service import retrieval_service


class Tools:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_relevant_information",
                "description": (
                    "Search the user's uploaded PDF documents for passages relevant "
                    "to a question. Call this before answering any question about "
                    "the documents' content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A standalone search query, rewritten from the user's question.",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]
