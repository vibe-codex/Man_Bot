import os
import json
from typing import List, Optional, Dict, Any

import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import google.generativeai as genai

# ====== Конфиг ======
DB_DSN = os.getenv("DB_DSN", "postgresql://man_admin:man_password_2026@localhost:5433/man_vector_db")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
EMBED_MODEL = "models/embedding-001"
LLM_MODEL = "gemini-pro"

# Настройка Google AI
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI(title="Pickup RAG Server")


# ====== Модели запросов/ответов ======

class ChatFilters(BaseModel):
    level: Optional[str] = None
    stage: Optional[List[str]] = None
    channel: Optional[List[str]] = None
    goal: Optional[List[str]] = None


class ChatRequest(BaseModel):
    user_message: str
    convo_history: List[Dict[str, str]] = []
    filters: Optional[ChatFilters] = None


class ChatResponse(BaseModel):
    answer: str
    used_ku_ids: List[str]


class StoryRequest(BaseModel):
    telegram_user_id: Optional[int] = None
    level: Optional[str] = None
    stage: Optional[List[str]] = None
    channel: Optional[List[str]] = None
    goal: Optional[List[str]] = None
    text: str
    outcome: str


# ====== DB utils ======

async def get_db():
    return await asyncpg.connect(dsn=DB_DSN)


# ====== Embeddings & LLM ======

async def embed_text(text: str) -> List[float]:
    """Генерация эмбеддинга через Google API"""
    try:
        if not GOOGLE_API_KEY:
            # Fallback если нет ключа
            import hashlib
            import random
            random.seed(int(hashlib.md5(text.encode()).hexdigest(), 16) % 10**8)
            return [random.random() for _ in range(768)]
        
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"⚠️ Ошибка эмбеддинга: {e}")
        # Fallback
        import hashlib
        import random
        random.seed(int(hashlib.md5(text.encode()).hexdigest(), 16) % 10**8)
        return [random.random() for _ in range(768)]


async def call_llm(prompt: str, model_name: str = LLM_MODEL) -> str:
    """Вызов LLM через Google Gemini"""
    try:
        if not GOOGLE_API_KEY:
            return "⚠️ GOOGLE_API_KEY не настроен. Добавьте ключ в .env файл"
        
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Ошибка LLM: {str(e)}"


# ====== RAG-поиск ======

async def search_knowledge_units(
    query_embedding: List[float],
    filters: Optional[ChatFilters],
    top_k: int = 8,
) -> List[asyncpg.Record]:
    db = await get_db()
    conditions = []
    params: Dict[str, Any] = {"q": query_embedding}

    if filters:
        if filters.stage:
            conditions.append("stage && $2::text[]")
            params["stage"] = filters.stage
        if filters.channel:
            conditions.append("channel && $3::text[]")
            params["channel"] = filters.channel
        if filters.goal:
            conditions.append("goal && $4::text[]")
            params["goal"] = filters.goal
        if filters.level:
            conditions.append("$5 = ANY(user_level_fit)")
            params["ulf"] = filters.level

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql_params = [params["q"]]
    for key in ("stage", "channel", "goal", "ulf"):
        if key in params:
            sql_params.append(params[key])

    query = f"""
        SELECT id, ku_id, title, content, yaml,
        1 - (embedding <=> $1::vector) AS similarity
        FROM knowledge_units
        {where_clause}
        ORDER BY embedding <=> $1::vector
        LIMIT {top_k};
    """

    rows = await db.fetch(query, *sql_params)
    await db.close()
    return rows


def build_llm_prompt(user_message: str, history: List[Dict[str, str]], ku_rows: List[asyncpg.Record]) -> tuple[str, List[str]]:
    knowledge_blocks = []
    used_ids = []
    for row in ku_rows:
        yaml = row["yaml"]
        content = row["content"]
        used_ids.append(row["ku_id"])
        block = f"### Техника: {row['title']}\n\n{content[:500]}..."
        knowledge_blocks.append(block)

    history_text = ""
    for msg in history[-5:]:
        role = msg.get("role", "user")
        history_text += f"{role.upper()}: {msg.get('content','')}\n"

    knowledge_text = "\n\n".join(knowledge_blocks)
    
    prompt = f"""Ты — профессиональный наставник по социальным взаимодействиям и соблазнению.

История диалога:
{history_text}

Вопрос пользователя:
{user_message}

Релевантные техники из базы знаний:
{knowledge_text}

Дай практичный совет на основе этих техник. Будь конкретным, дай 1-3 варианта действий."""
    
    return prompt, used_ids


# ====== Эндпоинты ======

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    q_emb = await embed_text(req.user_message)
    rows = await search_knowledge_units(q_emb, req.filters)
    prompt, used_ids = build_llm_prompt(req.user_message, req.convo_history, rows)
    answer = await call_llm(prompt)
    return ChatResponse(answer=answer, used_ku_ids=used_ids)


@app.post("/student_story")
async def student_story_endpoint(req: StoryRequest):
    db = await get_db()
    await db.execute(
        """
        INSERT INTO student_stories (telegram_user_id, level, stage, channel, goal, text, outcome, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
        """,
        req.telegram_user_id,
        req.level,
        req.stage,
        req.channel,
        req.goal,
        req.text,
        req.outcome,
        json.dumps({})
    )
    await db.close()
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Pickup RAG Server работает!", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "google_api": bool(GOOGLE_API_KEY)}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)