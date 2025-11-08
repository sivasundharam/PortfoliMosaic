"""
Migration: Add brokerage firm tracking to holdings table

This migration adds three new columns to the holdings table:
- brokerage_firm: Name of the brokerage firm (e.g., "Fidelity", "Charles Schwab")
- account_number: Account number where the holding is held
- account_type: Type of account (e.g., "Individual", "IRA", "401k")

Run this migration to enable multi-account and multi-brokerage tracking.
"""

from sqlalchemy import create_engine, text
import os

# Database URL - points to backend/portfolio.db
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'portfolio.db'))
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

def upgrade():
    """Add brokerage tracking columns to holdings table"""
    print(f"Using database: {DB_PATH}")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    with engine.connect() as conn:
        # Add brokerage_firm column
        try:
            conn.execute(text("""
                ALTER TABLE holdings 
                ADD COLUMN brokerage_firm VARCHAR
            """))
            conn.commit()
            print("✓ Added brokerage_firm column")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⚠️  brokerage_firm column already exists")
            else:
                raise
        
        # Add account_number column
        try:
            conn.execute(text("""
                ALTER TABLE holdings 
                ADD COLUMN account_number VARCHAR
            """))
            conn.commit()
            print("✓ Added account_number column")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⚠️  account_number column already exists")
            else:
                raise
        
        # Add account_type column
        try:
            conn.execute(text("""
                ALTER TABLE holdings 
                ADD COLUMN account_type VARCHAR
            """))
            conn.commit()
            print("✓ Added account_type column")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⚠️  account_type column already exists")
            else:
                raise
        
        # Create index on brokerage_firm for faster queries
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_holdings_brokerage_firm 
                ON holdings(brokerage_firm)
            """))
            conn.commit()
            print("✓ Created index on brokerage_firm")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
    
    print("\n✅ Migration completed successfully!")
    print("   Holdings table now supports multi-account and multi-brokerage tracking")

def downgrade():
    """Remove brokerage tracking columns from holdings table"""
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    with engine.connect() as conn:
        # Drop index
        try:
            conn.execute(text("DROP INDEX IF EXISTS ix_holdings_brokerage_firm"))
            conn.commit()
            print("✓ Dropped index on brokerage_firm")
        except Exception as e:
            print(f"⚠️  Index drop: {e}")
        
        # Drop columns
        try:
            conn.execute(text("ALTER TABLE holdings DROP COLUMN brokerage_firm"))
            conn.commit()
            print("✓ Dropped brokerage_firm column")
        except Exception as e:
            print(f"⚠️  {e}")
        
        try:
            conn.execute(text("ALTER TABLE holdings DROP COLUMN account_number"))
            conn.commit()
            print("✓ Dropped account_number column")
        except Exception as e:
            print(f"⚠️  {e}")
        
        try:
            conn.execute(text("ALTER TABLE holdings DROP COLUMN account_type"))
            conn.commit()
            print("✓ Dropped account_type column")
        except Exception as e:
            print(f"⚠️  {e}")
    
    print("\n✅ Downgrade completed!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("Running downgrade migration...")
        downgrade()
    else:
        print("Running upgrade migration...")
        upgrade()

