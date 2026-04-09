"""
database/connection.py
----------------------
Convenience re-exports so other modules can import cleanly:
 
    from database.connection import get_db, engine
"""
 
from database.models import engine, SessionLocal, get_db, create_tables
 
__all__ = ["engine", "SessionLocal", "get_db", "create_tables"]
 