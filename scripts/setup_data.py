import os
import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "jobs.db"

def init_empty_database():
    """Initialize a fresh empty database. Always recreates to avoid corruption issues."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # ALWAYS remove existing file to avoid corruption issues on Railway
    if DB_FILE.exists():
        print(f"Removing existing database file: {DB_FILE}")
        try:
            DB_FILE.unlink()
        except Exception as e:
            print(f"Warning: Could not remove file: {e}")
    
    # Also remove WAL files if they exist
    wal_file = DATA_DIR / "jobs.db-wal"
    shm_file = DATA_DIR / "jobs.db-shm"
    for f in [wal_file, shm_file]:
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass
    
    print("Creating fresh empty database...")
    try:
        conn = sqlite3.connect(str(DB_FILE))
        conn.execute("PRAGMA journal_mode=DELETE")  # Use DELETE mode, not WAL (simpler for containers)
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                description TEXT,
                skills TEXT,
                experience_min INTEGER,
                experience_max INTEGER,
                seniority TEXT,
                location TEXT,
                remote BOOLEAN DEFAULT FALSE,
                salary_min INTEGER,
                salary_max INTEGER,
                needs_review BOOLEAN DEFAULT FALSE,
                posted_date TIMESTAMP,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                skills TEXT,
                experience_years INTEGER,
                seniority TEXT,
                location_preference TEXT,
                remote_preferred BOOLEAN DEFAULT FALSE,
                salary_expected INTEGER,
                weights_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                preset_used TEXT,
                weights_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_seniority ON jobs(seniority);
            CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(remote);
        ''')
        conn.close()
        print(f"Created empty database: {DB_FILE}")
        
        # Verify it works
        conn = sqlite3.connect(str(DB_FILE))
        conn.execute("SELECT 1")
        conn.close()
        print("Database verification: OK")
        return True
    except Exception as e:
        print(f"ERROR creating database: {e}")
        return False

if __name__ == "__main__":
    success = init_empty_database()
    if not success:
        exit(1)
