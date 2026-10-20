from fastapi import FastAPI

app = FastAPI()

@app.get("/healthz")
async def home():
    return {"status": "ok"}