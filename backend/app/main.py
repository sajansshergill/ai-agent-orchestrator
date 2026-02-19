from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Enterprise AI Agent Orchestrator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import router as api_router
from app.core.config import settings
from app.db.base import Base
from app.db import models  # noqa: F401 - Import models to register them with Base

# Create database tables on startup
@app.on_event("startup")
def startup_event():
    from sqlalchemy import create_engine
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)

app.include_router(api_router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok"}
