"""Połączenie z Supabase Postgres."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from norfingen.config import settings

if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL nie jest ustawione w środowisku")

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
