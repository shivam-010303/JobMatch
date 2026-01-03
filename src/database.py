import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.models import (
    CandidateProfile,
    ExtractedRequirements,
    FeedbackRecord,
    SeniorityLevel,
    StructuredJob,
    WeightConfig,
)

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    pass


class Database:

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.environ.get("DATABASE_PATH", "data/jobs.db")
        self.db_path = db_path
        self._local = threading.local()
        self._ensure_data_directory()
        self._init_db()

    def _ensure_data_directory(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            
            # Use DELETE journal mode (more compatible with containers than WAL)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def get_cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise DatabaseError(f"Database operation failed: {e}") from e
        finally:
            cursor.close()

    def _init_db(self) -> None:
        with self.get_cursor() as cursor:
            cursor.executescript('''
                -- Jobs table
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

                -- Candidates table
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

                -- Feedback table for analytics
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    preset_used TEXT,
                    weights_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes for fast queries
                CREATE INDEX IF NOT EXISTS idx_jobs_seniority ON jobs(seniority);
                CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(remote);
                CREATE INDEX IF NOT EXISTS idx_jobs_salary ON jobs(salary_min, salary_max);
                CREATE INDEX IF NOT EXISTS idx_jobs_experience ON jobs(experience_min, experience_max);
                CREATE INDEX IF NOT EXISTS idx_feedback_candidate ON feedback(candidate_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_preset ON feedback(preset_used);
            ''')
        logger.info(f"Database initialized: {self.db_path}")

    def close(self) -> None:
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def insert_job(self, job: StructuredJob) -> None:
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT OR REPLACE INTO jobs 
                (id, source, external_id, title, company, description, skills,
                 experience_min, experience_max, seniority, location, remote,
                 salary_min, salary_max, needs_review, posted_date, url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job.id,
                job.source,
                job.external_id,
                job.title,
                job.company,
                job.description,
                json.dumps(job.requirements.skills),
                job.requirements.experience_min,
                job.requirements.experience_max,
                job.requirements.seniority.value if job.requirements.seniority else None,
                job.requirements.location,
                job.requirements.remote,
                job.requirements.salary_min,
                job.requirements.salary_max,
                job.requirements.needs_review,
                job.posted_date.isoformat() if job.posted_date else None,
                job.url,
                job.created_at.isoformat() if job.created_at else datetime.utcnow().isoformat(),
            ))

    def insert_jobs_batch(self, jobs: List[StructuredJob]) -> int:
        with self.get_cursor() as cursor:
            data = [
                (
                    job.id,
                    job.source,
                    job.external_id,
                    job.title,
                    job.company,
                    job.description,
                    json.dumps(job.requirements.skills),
                    job.requirements.experience_min,
                    job.requirements.experience_max,
                    job.requirements.seniority.value if job.requirements.seniority else None,
                    job.requirements.location,
                    job.requirements.remote,
                    job.requirements.salary_min,
                    job.requirements.salary_max,
                    job.requirements.needs_review,
                    job.posted_date.isoformat() if job.posted_date else None,
                    job.url,
                    job.created_at.isoformat() if job.created_at else datetime.utcnow().isoformat(),
                )
                for job in jobs
            ]
            cursor.executemany('''
                INSERT OR REPLACE INTO jobs 
                (id, source, external_id, title, company, description, skills,
                 experience_min, experience_max, seniority, location, remote,
                 salary_min, salary_max, needs_review, posted_date, url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            return len(data)

    def get_job(self, job_id: str) -> Optional[StructuredJob]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def get_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        seniority: Optional[str] = None,
        remote: Optional[bool] = None,
        min_salary: Optional[int] = None,
        max_experience: Optional[int] = None,
    ) -> List[StructuredJob]:
        query = 'SELECT * FROM jobs WHERE 1=1'
        params: List = []

        if seniority:
            query += ' AND seniority = ?'
            params.append(seniority)
        if remote is not None:
            query += ' AND remote = ?'
            params.append(remote)
        if min_salary is not None:
            query += ' AND (salary_min >= ? OR salary_max >= ?)'
            params.extend([min_salary, min_salary])
        if max_experience is not None:
            query += ' AND (experience_min IS NULL OR experience_min <= ?)'
            params.append(max_experience)

        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_all_jobs(self) -> List[StructuredJob]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM jobs ORDER BY created_at DESC')
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def delete_job(self, job_id: str) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
            return cursor.rowcount > 0

    def count_jobs(self) -> int:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM jobs')
            return cursor.fetchone()[0]

    def insert_candidate(self, candidate: CandidateProfile) -> None:
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT OR REPLACE INTO candidates
                (id, skills, experience_years, seniority, location_preference,
                 remote_preferred, salary_expected, weights_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                candidate.id,
                json.dumps(candidate.skills),
                candidate.experience_years,
                candidate.seniority.value if candidate.seniority else None,
                candidate.location_preference,
                candidate.remote_preferred,
                candidate.salary_expected,
                None,  # weights_json is managed separately
            ))

    def get_candidate(self, candidate_id: str) -> Optional[CandidateProfile]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM candidates WHERE id = ?', (candidate_id,))
            row = cursor.fetchone()
            return self._row_to_candidate(row) if row else None

    def get_all_candidates(self) -> List[CandidateProfile]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM candidates ORDER BY created_at DESC')
            return [self._row_to_candidate(row) for row in cursor.fetchall()]

    def delete_candidate(self, candidate_id: str) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute('DELETE FROM candidates WHERE id = ?', (candidate_id,))
            return cursor.rowcount > 0

    def update_candidate_weights(self, candidate_id: str, weights: WeightConfig) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute('''
                UPDATE candidates SET weights_json = ? WHERE id = ?
            ''', (json.dumps(weights.model_dump()), candidate_id))
            return cursor.rowcount > 0

    def get_candidate_weights(self, candidate_id: str) -> Optional[WeightConfig]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT weights_json FROM candidates WHERE id = ?', (candidate_id,))
            row = cursor.fetchone()
            if row and row['weights_json']:
                return WeightConfig(**json.loads(row['weights_json']))
            return None

    def insert_feedback(self, feedback: FeedbackRecord) -> int:
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO feedback
                (candidate_id, job_id, feedback_type, preset_used, weights_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                feedback.candidate_id,
                feedback.job_id,
                feedback.feedback_type,
                feedback.preset_used,
                json.dumps(feedback.weights_used.model_dump()) if feedback.weights_used else None,
                feedback.timestamp.isoformat() if feedback.timestamp else datetime.utcnow().isoformat(),
            ))
            return cursor.lastrowid

    def get_feedback_by_candidate(
        self,
        candidate_id: str,
        feedback_type: Optional[str] = None,
    ) -> List[FeedbackRecord]:
        query = 'SELECT * FROM feedback WHERE candidate_id = ?'
        params: List = [candidate_id]

        if feedback_type:
            query += ' AND feedback_type = ?'
            params.append(feedback_type)

        query += ' ORDER BY created_at DESC'

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_feedback(row) for row in cursor.fetchall()]

    def get_feedback_by_job(self, job_id: str) -> List[FeedbackRecord]:
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM feedback WHERE job_id = ? ORDER BY created_at DESC',
                (job_id,)
            )
            return [self._row_to_feedback(row) for row in cursor.fetchall()]

    def get_all_feedback(self) -> List[FeedbackRecord]:
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM feedback ORDER BY created_at DESC')
            return [self._row_to_feedback(row) for row in cursor.fetchall()]

    def delete_feedback(self, feedback_id: int) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute('DELETE FROM feedback WHERE id = ?', (feedback_id,))
            return cursor.rowcount > 0


    def _row_to_job(self, row: sqlite3.Row) -> StructuredJob:
        # Parse posted_date
        posted_date = None
        if row['posted_date']:
            try:
                posted_date = datetime.fromisoformat(row['posted_date'])
            except (ValueError, TypeError):
                pass

        # Parse created_at
        created_at = datetime.utcnow()
        if row['created_at']:
            try:
                created_at = datetime.fromisoformat(row['created_at'])
            except (ValueError, TypeError):
                pass

        # Parse seniority
        seniority = None
        if row['seniority']:
            try:
                seniority = SeniorityLevel(row['seniority'])
            except ValueError:
                pass

        # Parse skills JSON
        skills = []
        if row['skills']:
            try:
                skills = json.loads(row['skills'])
            except json.JSONDecodeError:
                pass

        return StructuredJob(
            id=row['id'],
            source=row['source'],
            external_id=row['external_id'],
            title=row['title'],
            company=row['company'],
            description=row['description'] or '',
            requirements=ExtractedRequirements(
                skills=skills,
                experience_min=row['experience_min'],
                experience_max=row['experience_max'],
                seniority=seniority,
                location=row['location'],
                remote=bool(row['remote']),
                salary_min=row['salary_min'],
                salary_max=row['salary_max'],
                needs_review=bool(row['needs_review']) if 'needs_review' in row.keys() else False,
            ),
            posted_date=posted_date,
            url=row['url'],
            created_at=created_at,
        )

    def _row_to_candidate(self, row: sqlite3.Row) -> CandidateProfile:
        # Parse seniority
        seniority = None
        if row['seniority']:
            try:
                seniority = SeniorityLevel(row['seniority'])
            except ValueError:
                pass

        # Parse skills JSON
        skills = []
        if row['skills']:
            try:
                skills = json.loads(row['skills'])
            except json.JSONDecodeError:
                pass

        return CandidateProfile(
            id=row['id'],
            skills=skills,
            experience_years=row['experience_years'] or 0,
            seniority=seniority,
            location_preference=row['location_preference'],
            remote_preferred=bool(row['remote_preferred']),
            salary_expected=row['salary_expected'],
        )

    def _row_to_feedback(self, row: sqlite3.Row) -> FeedbackRecord:
        # Parse weights JSON
        weights = None
        if row['weights_json']:
            try:
                weights = WeightConfig(**json.loads(row['weights_json']))
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse timestamp
        timestamp = datetime.utcnow()
        if row['created_at']:
            try:
                timestamp = datetime.fromisoformat(row['created_at'])
            except (ValueError, TypeError):
                pass

        return FeedbackRecord(
            candidate_id=row['candidate_id'],
            job_id=row['job_id'],
            feedback_type=row['feedback_type'],
            preset_used=row['preset_used'],
            weights_used=weights,
            timestamp=timestamp,
        )

    def job_to_dict(self, job: StructuredJob) -> dict:
        return {
            'id': job.id,
            'source': job.source,
            'external_id': job.external_id,
            'title': job.title,
            'company': job.company,
            'description': job.description,
            'skills': json.dumps(job.requirements.skills),
            'experience_min': job.requirements.experience_min,
            'experience_max': job.requirements.experience_max,
            'seniority': job.requirements.seniority.value if job.requirements.seniority else None,
            'location': job.requirements.location,
            'remote': job.requirements.remote,
            'salary_min': job.requirements.salary_min,
            'salary_max': job.requirements.salary_max,
            'needs_review': job.requirements.needs_review,
            'posted_date': job.posted_date.isoformat() if job.posted_date else None,
            'url': job.url,
            'created_at': job.created_at.isoformat() if job.created_at else None,
        }

    def dict_to_job(self, data: dict) -> StructuredJob:
        # Parse skills
        skills = data.get('skills', [])
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except json.JSONDecodeError:
                skills = []

        # Parse seniority
        seniority = None
        if data.get('seniority'):
            try:
                seniority = SeniorityLevel(data['seniority'])
            except ValueError:
                pass

        # Parse dates
        posted_date = None
        if data.get('posted_date'):
            if isinstance(data['posted_date'], datetime):
                posted_date = data['posted_date']
            else:
                try:
                    posted_date = datetime.fromisoformat(data['posted_date'])
                except (ValueError, TypeError):
                    pass

        created_at = datetime.utcnow()
        if data.get('created_at'):
            if isinstance(data['created_at'], datetime):
                created_at = data['created_at']
            else:
                try:
                    created_at = datetime.fromisoformat(data['created_at'])
                except (ValueError, TypeError):
                    pass

        return StructuredJob(
            id=data['id'],
            source=data['source'],
            external_id=data['external_id'],
            title=data['title'],
            company=data['company'],
            description=data.get('description', ''),
            requirements=ExtractedRequirements(
                skills=skills,
                experience_min=data.get('experience_min'),
                experience_max=data.get('experience_max'),
                seniority=seniority,
                location=data.get('location'),
                remote=bool(data.get('remote', False)),
                salary_min=data.get('salary_min'),
                salary_max=data.get('salary_max'),
                needs_review=bool(data.get('needs_review', False)),
            ),
            posted_date=posted_date,
            url=data.get('url'),
            created_at=created_at,
        )

    def candidate_to_dict(self, candidate: CandidateProfile) -> dict:
        return {
            'id': candidate.id,
            'skills': json.dumps(candidate.skills),
            'experience_years': candidate.experience_years,
            'seniority': candidate.seniority.value if candidate.seniority else None,
            'location_preference': candidate.location_preference,
            'remote_preferred': candidate.remote_preferred,
            'salary_expected': candidate.salary_expected,
        }

    def feedback_to_dict(self, feedback: FeedbackRecord) -> dict:
        return {
            'candidate_id': feedback.candidate_id,
            'job_id': feedback.job_id,
            'feedback_type': feedback.feedback_type,
            'preset_used': feedback.preset_used,
            'weights_json': json.dumps(feedback.weights_used.model_dump()) if feedback.weights_used else None,
            'created_at': feedback.timestamp.isoformat() if feedback.timestamp else None,
        }
