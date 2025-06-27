from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="MHTP Chat Backend")

@app.get("/ping")
async def ping():
    return {"status": "ok"}

class MessageIn(BaseModel):
    session_id: str
    role: str  # "user" | "assistant"
    content: str

@app.post("/chat")
async def chat(msg: MessageIn):
    """Placeholder – will later call OpenAI Assistants API.
    For now, just echoes back."""
    if msg.role != "user":
        raise HTTPException(status_code=400, detail="role must be 'user'")
    return {"reply": f"echo: {msg.content}"}

