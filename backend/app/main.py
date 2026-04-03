import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.database import engine, Base, run_migrations
from app.routers import analysts, statements, predictions, review, importdata, bulk_import

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables...")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    logger.info("Database tables ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Prediction Tracker API",
    description="Track and rate the accuracy of expert predictions.",
    version="1.0.0",
    lifespan=lifespan,
)

import os
_frontend_url = os.getenv("FRONTEND_URL", "")
_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if _frontend_url:
    _allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysts.router, prefix="/api")
app.include_router(statements.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(importdata.router)
app.include_router(bulk_import.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "prediction-tracker-api"}
