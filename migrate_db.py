#!/usr/bin/env python3
"""
Database migration script to add qr_code_file_id column
"""
import os
import sys
from sqlalchemy import create_engine, text
from database import SessionLocal

def migrate_database():
    """Add qr_code_file_id column to QRCodeSettings table"""
    
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')
    
    if DATABASE_URL.startswith('sqlite'):
        # SQLite migration
        engine = create_engine(DATABASE_URL)
        print("Running SQLite migration...")
        
        with engine.connect() as conn:
            try:
                # Check if column exists
                result = conn.execute(text("PRAGMA table_info(qr_code_settings)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'qr_code_file_id' not in columns:
                    print("Adding qr_code_file_id column...")
                    conn.execute(text("ALTER TABLE qr_code_settings ADD COLUMN qr_code_file_id TEXT"))
                    conn.commit()
                    print("✅ qr_code_file_id column added successfully!")
                else:
                    print("✅ qr_code_file_id column already exists!")
                    
            except Exception as e:
                print(f"❌ SQLite migration error: {e}")
                
    else:
        # PostgreSQL migration
        engine = create_engine(DATABASE_URL)
        print("Running PostgreSQL migration...")
        
        with engine.connect() as conn:
            try:
                # Check if column exists
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'qr_code_settings' 
                    AND column_name = 'qr_code_file_id'
                """))
                
                if not result.fetchone():
                    print("Adding qr_code_file_id column...")
                    conn.execute(text("ALTER TABLE qr_code_settings ADD COLUMN qr_code_file_id VARCHAR"))
                    conn.commit()
                    print("✅ qr_code_file_id column added successfully!")
                else:
                    print("✅ qr_code_file_id column already exists!")
                    
            except Exception as e:
                print(f"❌ PostgreSQL migration error: {e}")

if __name__ == "__main__":
    migrate_database()