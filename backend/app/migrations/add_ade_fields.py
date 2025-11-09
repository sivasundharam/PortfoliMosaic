"""
Migration script to add Landing AI ADE fields to Document table

Run this script to add the new columns:
    python -m backend.app.migrations.add_ade_fields
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from sqlalchemy import text
from backend.app.db import engine


def migrate():
    """Add new columns to documents table"""
    
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("PRAGMA table_info(documents)"))
        columns = [row[1] for row in result]
        
        migrations = []
        
        if 'markdown' not in columns:
            migrations.append("ALTER TABLE documents ADD COLUMN markdown TEXT")
        
        if 'extraction_json' not in columns:
            migrations.append("ALTER TABLE documents ADD COLUMN extraction_json TEXT")
        
        if 'categorized_data' not in columns:
            migrations.append("ALTER TABLE documents ADD COLUMN categorized_data TEXT")
        
        if 'ade_metadata' not in columns:
            migrations.append("ALTER TABLE documents ADD COLUMN ade_metadata TEXT")
        
        if migrations:
            print(f"Running {len(migrations)} migrations...")
            for sql in migrations:
                print(f"  - {sql}")
                conn.execute(text(sql))
            conn.commit()
            print("✅ Migration completed successfully!")
        else:
            print("✅ All columns already exist, no migration needed.")


if __name__ == "__main__":
    migrate()

