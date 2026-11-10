import sqlite3
from pathlib import Path

# Stores jobs.db inside the 00_Data folder
DB_PATH = Path("00_Data/jobs.db")

def init_db():
    """Initializes the SQLite database with the full application schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                match_score REAL DEFAULT 0.0,
                status_id INTEGER REFERENCES application_statuses(id),
                status TEXT DEFAULT 'Analyzed',
                date_submitted TEXT DEFAULT '—',
                date_follow_up TEXT DEFAULT '—',
                salary TEXT DEFAULT 'Not specified',
                experience TEXT DEFAULT 'Not specified',
                skills TEXT DEFAULT '[]',
                missing_skills TEXT DEFAULT '[]',
                jd_file TEXT,
                resume_file TEXT,
                date_captured TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status_name TEXT UNIQUE NOT NULL,
                display_order INTEGER NOT NULL,
                is_default BOOLEAN DEFAULT 0
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO application_statuses (status_name, display_order, is_default) VALUES
                ('Analyzed', 1, 1),
                ('Tailored', 2, 0),
                ('Applied', 3, 0),
                ('Interviewing', 4, 0),
                ('Rejected', 5, 0),
                ('Ghosted', 6, 0),
                ('Withdrawn', 7, 0),
                ('Offered', 8, 0),
                ('Ignored', 9, 0)
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
                old_status_id INTEGER REFERENCES application_statuses(id),
                new_status_id INTEGER REFERENCES application_statuses(id),
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)

        cursor.execute("DROP TRIGGER IF EXISTS log_status_change")
        cursor.execute("""
            CREATE TRIGGER log_status_change
            AFTER UPDATE OF status_id ON applications
            WHEN old.status_id IS NOT new.status_id
            BEGIN
                INSERT INTO application_status_history (application_id, old_status_id, new_status_id, changed_at)
                VALUES (new.id, old.status_id, new.status_id, CURRENT_TIMESTAMP);
            END;
        """)

        conn.commit()

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized successfully at 00_Data/jobs.db")