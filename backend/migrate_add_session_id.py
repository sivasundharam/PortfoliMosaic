"""
Migration script to add session_id column to documents table.
Run this once if you have an existing database.
"""
import sqlite3
import os
from pathlib import Path

# Get the database path
project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "app.db"

if not db_path.exists():
    print(f"Database not found at {db_path}. No migration needed.")
    exit(0)

print(f"Migrating database at {db_path}")

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Check if session_id column already exists
    cursor.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'session_id' in columns:
        print("session_id column already exists. No migration needed.")
    else:
        print("Adding session_id column to documents table...")
        cursor.execute("ALTER TABLE documents ADD COLUMN session_id TEXT")
        conn.commit()
        print("Migration completed successfully!")
        
except Exception as e:
    print(f"Error during migration: {e}")
    conn.rollback()
finally:
    conn.close()

