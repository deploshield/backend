"""
One-time migration: adds user_id column to projects, servers, deployments tables.
Run this once: python migrate_add_user_id.py

After running, existing rows will have user_id = 'legacy' — update them manually
or delete them if you're starting fresh.
"""
from sqlalchemy import text
from app.core.database import engine

TABLES = ["projects", "servers", "deployments"]

with engine.connect() as conn:
    for table in TABLES:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR"))
            conn.execute(text(f"UPDATE {table} SET user_id = 'user_3G7yBKBUPP23FsoJeG61mCdTBCH' WHERE user_id IS NULL"))
            conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)"))
            print(f"✓ {table}: user_id column added")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print(f"- {table}: user_id already exists, skipping")
            else:
                print(f"✗ {table}: {e}")
    conn.commit()

print("\nDone! If starting fresh, you can drop all tables and let the app recreate them.")
