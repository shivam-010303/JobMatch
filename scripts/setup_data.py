"""
Download production data from Google Drive on Railway startup.
"""
import os
import sqlite3
import requests
from pathlib import Path

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "jobs.db"
EMBEDDINGS_FILE = DATA_DIR / "embeddings.npz"
QDRANT_DIR = DATA_DIR / "qdrant"

# Google Drive direct download URLs
# Format: https://drive.google.com/uc?export=download&id=FILE_ID
# Extract FILE_ID from sharing link: https://drive.google.com/file/d/FILE_ID/view

# TODO: Replace these with your actual Google Drive file IDs
JOBS_DB_FILE_ID = os.environ.get("GDRIVE_JOBS_DB_ID", "")
EMBEDDINGS_FILE_ID = os.environ.get("GDRIVE_EMBEDDINGS_ID", "")


def get_gdrive_download_url(file_id: str) -> str:
    """Get direct download URL for Google Drive file."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def download_large_file_from_gdrive(file_id: str, destination: Path) -> bool:
    """Download large file from Google Drive with virus scan bypass."""
    import re
    
    session = requests.Session()
    
    print(f"Downloading from Google Drive: {file_id}")
    print(f"Destination: {destination}")
    
    # First request to get cookies and check for virus scan warning
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = session.get(url, stream=True)
    
    # Check for virus scan warning page (large files > 100MB)
    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type:
        print("Large file detected, bypassing virus scan warning...")
        
        # Method 1: Check cookies for download_warning token
        token = None
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                token = value
                break
        
        # Method 2: Parse HTML for confirm token if not in cookies
        if not token:
            html_content = response.text
            # Look for confirm token in the HTML
            match = re.search(r'confirm=([0-9A-Za-z_-]+)', html_content)
            if match:
                token = match.group(1)
            else:
                # Try another pattern
                match = re.search(r'id="download-form".*?name="confirm".*?value="([^"]+)"', html_content, re.DOTALL)
                if match:
                    token = match.group(1)
        
        if token:
            print(f"Found confirmation token: {token[:10]}...")
            url = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
            response = session.get(url, stream=True)
        else:
            # Method 3: Try direct download with confirm=t (works for many files)
            print("No token found, trying confirm=t bypass...")
            url = f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
            response = session.get(url, stream=True)
        
        # Final check if still HTML
        content_type = response.headers.get('content-type', '')
        if 'text/html' in content_type:
            print("ERROR: Still getting HTML after bypass attempts.")
            print("Trying alternative download method...")
            
            # Method 4: Use drive.usercontent.google.com (newer method)
            url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
            response = session.get(url, stream=True)
            
            content_type = response.headers.get('content-type', '')
            if 'text/html' in content_type:
                print("ERROR: All download methods failed.")
                print("Please ensure the file is shared as 'Anyone with the link can view'")
                return False
    
    # Download the file
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    
    print(f"Starting download... (size: {total_size / 1024 / 1024:.1f} MB)" if total_size else "Starting download...")
    
    with open(destination, 'wb') as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (1024 * 1024) < 32768:  # Log every ~1MB
                    pct = (downloaded / total_size) * 100
                    print(f"Progress: {pct:.1f}% ({downloaded // 1024 // 1024} MB)", flush=True)
    
    print(f"Downloaded: {destination} ({downloaded / 1024 / 1024:.1f} MB)")
    return downloaded > 1000  # At least 1KB to be valid


def verify_database(db_path: Path) -> bool:
    """Verify SQLite database is valid."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"Database verified: {count} jobs found")
        return count > 0
    except Exception as e:
        print(f"Database verification failed: {e}")
        return False


def create_empty_database():
    """Create empty database as fallback."""
    print("Creating empty database as fallback...")
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("PRAGMA journal_mode=DELETE")
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
    print("Empty database created")


def init_data():
    """Initialize data directory and download files from Google Drive."""
    print("\n=== Data Initialization Starting ===")
    print(f"GDRIVE_JOBS_DB_ID: {'SET' if JOBS_DB_FILE_ID else 'NOT SET'}")
    print(f"GDRIVE_EMBEDDINGS_ID: {'SET' if EMBEDDINGS_FILE_ID else 'NOT SET'}")
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QDRANT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if database already exists and is valid
    if DB_FILE.exists():
        print(f"Found existing database: {DB_FILE}")
        if verify_database(DB_FILE):
            print("Existing database is valid, skipping download")
            return
        else:
            print("Existing database is invalid, will re-download")
    
    # Clean up any corrupted files
    for f in [DB_FILE, DATA_DIR / "jobs.db-wal", DATA_DIR / "jobs.db-shm"]:
        if f.exists():
            try:
                f.unlink()
                print(f"Removed existing: {f}")
            except Exception as e:
                print(f"Warning: Could not remove {f}: {e}")
    
    # Download jobs.db from Google Drive
    if JOBS_DB_FILE_ID:
        print(f"\n=== Downloading jobs.db from Google Drive ===")
        print(f"File ID: {JOBS_DB_FILE_ID}")
        success = download_large_file_from_gdrive(JOBS_DB_FILE_ID, DB_FILE)
        
        if success and DB_FILE.exists():
            if verify_database(DB_FILE):
                print("✓ jobs.db downloaded and verified successfully!")
            else:
                print("✗ Downloaded file is not a valid database, creating empty one")
                DB_FILE.unlink()
                create_empty_database()
        else:
            print("✗ Download failed, creating empty database")
            create_empty_database()
    else:
        print("\n*** WARNING: GDRIVE_JOBS_DB_ID environment variable is NOT SET ***")
        print("Please add GDRIVE_JOBS_DB_ID in Railway Dashboard -> Variables")
        create_empty_database()
    
    # Download embeddings.npz (optional - for vector search)
    if EMBEDDINGS_FILE_ID:
        print(f"\n=== Downloading embeddings.npz from Google Drive ===")
        print(f"File ID: {EMBEDDINGS_FILE_ID}")
        download_large_file_from_gdrive(EMBEDDINGS_FILE_ID, EMBEDDINGS_FILE)
    else:
        print("\nNo GDRIVE_EMBEDDINGS_ID set, skipping embeddings download")
    
    print("\n=== Data initialization complete ===")


if __name__ == "__main__":
    init_data()
