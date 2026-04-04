from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Arcadians Score API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@arcadians-postgresql:5432/arcadians"
)

pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id        SERIAL PRIMARY KEY,
                initials  VARCHAR(3)  NOT NULL,
                score     INTEGER     NOT NULL,
                wave      INTEGER     NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
    logger.info("Database ready")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

class ScoreIn(BaseModel):
    initials: str = Field(..., min_length=1, max_length=3)
    score:    int  = Field(..., ge=0)
    wave:     int  = Field(1, ge=1)

class ScoreOut(BaseModel):
    id:       int
    initials: str
    score:    int
    wave:     int

@app.get("/api/scores", response_model=list[ScoreOut])
async def get_scores():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, initials, score, wave FROM scores ORDER BY score DESC LIMIT 10"
        )
    return [dict(r) for r in rows]

@app.post("/api/scores", response_model=ScoreOut, status_code=201)
async def post_score(body: ScoreIn):
    initials = body.initials.upper().strip()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO scores (initials, score, wave) VALUES ($1, $2, $3) RETURNING id, initials, score, wave",
            initials, body.score, body.wave
        )
    return dict(row)

@app.get("/healthz")
async def health():
    return {"status": "ok"}
