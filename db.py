# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use environment variable if set; otherwise use local sqlite file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///transactions.db")

# For SQLite, set check_same_thread False to allow multiple threads
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """
    Create tables (if they don't exist).
    Call this once at app startup.
    """
    from models import Base
    Base.metadata.create_all(bind=engine)
