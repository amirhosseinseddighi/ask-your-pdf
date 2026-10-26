from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
import structlog
from app.middleware import ASGILoggingMiddleware
from app.core.logging_configure import setup_logging
from app.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from app.api import v1
from openai import AsyncOpenAI


logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    IS_DEV = settings.ENVIRONMENT != "PROD"
    setup_logging(is_dev=IS_DEV)
    
    # create llm client
    app.state.llm_client =  AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY.get_secret_value(),
        timeout=60.0,
        max_retries=3,
    )

    logger.info("Application setup completed! starting server...")

    
    try:
        yield
    finally:
        await app.state.llm_client.close()
        logger.info("Application shutted down successfuly! shutting down server...")


origins = [
    "http://localhost",
    "http://127.0.0.1:7000",
    "http://localhost:7000"
]



app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ASGILoggingMiddleware)

    
app.include_router(v1.router, prefix="/api")


@app.get("/healthz")
async def home():
    return {"status": "ok"}