from backend.db import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM users")).scalar()
        print(f"SUCCESS: PostgreSQL Database Connection Active! Total Users = {count}")
except Exception as e:
    print(f"ERROR connecting to PostgreSQL: {e}")
