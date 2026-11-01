
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import engine


app = FastAPI(
    title="OmniAgent API",
    description="API del sistema de atención omnicanal OmniAgent",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "application": "OmniAgent",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )
