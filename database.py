"""SQLite storage for ITS Teacher Tier List.

Participation and ratings are stored separately. Assigned codes are stored as
HMAC digests; ratings contain neither student identifiers nor timestamps.
"""

import csv
import hashlib
import hmac
import os
from contextlib import contextmanager, closing
from pathlib import Path
import secrets
import sqlite3
import time
import postgres

try:
    from psycopg import IntegrityError as PostgresIntegrityError
except ImportError:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, PostgresIntegrityError)

SCHOOL_YEAR = "2026/2027"
ADMIN_MAX_ATTEMPTS = 5
ADMIN_LOCK_SECONDS = 15 * 60

DB_PATH = Path(os.getenv('ITS_TIER_DB', str(Path(__file__).resolve().parent / 'data' / 'tierlist.sqlite3')))


@contextmanager
def connect():
    if postgres.enabled():
        with postgres.connect() as connection:
            yield connection
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 15000')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    if postgres.enabled():
        postgres.check_ready()
        return
    with connect() as con:
        con.execute('PRAGMA journal_mode = WAL')
        con.executescript('''
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                UNIQUE(name, subject)
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
                lesson_date TEXT NOT NULL,
                slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 12),
                topic TEXT NOT NULL DEFAULT '',
                UNIQUE(teacher_id, lesson_date, slot)
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE RESTRICT,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        con.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                voter_digest TEXT PRIMARY KEY,
                initials TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS participation (
                lesson_id INTEGER NOT NULL REFERENCES lessons(id),
                voter_digest TEXT NOT NULL,
                PRIMARY KEY (lesson_id, voter_digest)
            );
        """)
        vote_columns = {row['name'] for row in con.execute('PRAGMA table_info(votes)')}
        if 'voter_digest' in vote_columns:
            backup_path = DB_PATH.with_name(DB_PATH.name + '.before_anonymous.bak')
            if not backup_path.exists():
                with closing(sqlite3.connect(backup_path)) as backup:
                    con.backup(backup)
            con.execute('BEGIN IMMEDIATE')
            con.execute('INSERT OR IGNORE INTO participation SELECT lesson_id, voter_digest FROM votes')
            old_votes = con.execute('SELECT lesson_id, rating FROM votes').fetchall()
            secrets.SystemRandom().shuffle(old_votes)
            con.execute('ALTER TABLE votes RENAME TO votes_legacy')
            con.execute('CREATE TABLE votes (id TEXT PRIMARY KEY, lesson_id INTEGER NOT NULL REFERENCES lessons(id), rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5))')
            con.executemany('INSERT INTO votes VALUES (?, ?, ?)', [(secrets.token_hex(16), row['lesson_id'], row['rating']) for row in old_votes])
            con.execute('DROP TABLE votes_legacy')
            con.commit()
        columns = {row['name'] for row in con.execute('PRAGMA table_info(lessons)')}
        if 'duration_hours' not in columns:
            con.execute('ALTER TABLE lessons ADD COLUMN duration_hours INTEGER NOT NULL DEFAULT 4 CHECK(duration_hours BETWEEN 1 AND 12)')
        con.execute("UPDATE lessons SET duration_hours = 4 WHERE duration_hours <> 4")
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('school_year', ?)", (SCHOOL_YEAR,))
        con.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('voter_key', ?)",
            (secrets.token_hex(32),),
        )


def _dicts(cursor):
    rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        if row.get('average_rating') is not None:
            # PostgreSQL AVG(integer) returns Decimal; charts expect plain numbers.
            row['average_rating'] = float(row['average_rating'])
    return rows


def begin_write(con):
    if postgres.enabled():
        postgres.begin_write(con)
    else:
        con.execute('BEGIN IMMEDIATE')


def list_teachers():
    with connect() as con:
        return _dicts(con.execute('SELECT * FROM teachers ORDER BY LOWER(name), LOWER(subject)'))


def add_teacher(name, subject):
    name, subject = name.strip(), subject.strip()
    if not name or not subject or len(name) > 100 or len(subject) > 100:
        raise ValueError('Inserisci nome e materia (massimo 100 caratteri ciascuno).')
    with connect() as con:
        con.execute('INSERT INTO teachers (name, subject) VALUES (?, ?)', (name, subject))


def add_lesson(teacher_id, lesson_date, slot, topic='', duration_hours=4):
    if duration_hours != 4:
        raise ValueError('La durata della lezione deve essere di 4 ore.')
    if not (1 <= int(slot) <= 12):
        raise ValueError('La fascia oraria deve essere tra 1 e 12.')
    if len(topic) > 150:
        raise ValueError('Argomento troppo lungo (massimo 150 caratteri).')
    with connect() as con:
        begin_write(con)
        con.execute('''
            INSERT INTO lessons (teacher_id, lesson_date, slot, topic, duration_hours)
            VALUES (?, ?, ?, ?, ?)
        ''', (teacher_id, lesson_date, int(slot), topic.strip(), duration_hours))


def lessons_on(lesson_date):
    with connect() as con:
        return _dicts(con.execute('''
            SELECT l.id, l.teacher_id, l.lesson_date, l.slot, l.topic, l.duration_hours,
                   t.name AS teacher_name, t.subject
            FROM lessons l JOIN teachers t ON t.id = l.teacher_id
            WHERE l.lesson_date = ?
            ORDER BY l.slot, LOWER(t.name)
        ''', (lesson_date,)))


def code_digest(con, code):
    key = con.execute("SELECT value FROM settings WHERE key = 'voter_key'").fetchone()['value']
    return hmac.new(key.encode(), code.encode('utf-8'), hashlib.sha256).hexdigest()


def import_student_codes(path):
    """Import the assigned roster atomically; never overwrite an existing assignment."""
    with Path(path).open(encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file, delimiter=';'))
    codes = [row['Codice'] for row in rows]
    initials = [row['Iniziali'].strip() for row in rows]
    if not rows or len(set(codes)) != len(rows) or len(set(initials)) != len(rows):
        raise ValueError('Elenco studenti vuoto o con duplicati.')
    if any(len(code) != 4 or not code.isascii() or not code.isdigit() for code in codes) or not all(initials):
        raise ValueError('Ogni codice deve avere esattamente 4 cifre e iniziali valide.')
    with connect() as con:
        begin_write(con)
        for label, code in zip(initials, codes):
            digest = code_digest(con, code)
            existing = con.execute('SELECT voter_digest FROM students WHERE initials = ?', (label,)).fetchone()
            if existing and existing['voter_digest'] != digest:
                raise ValueError('Assegnazione esistente diversa: importazione annullata.')
            con.execute('INSERT INTO students VALUES (?, ?) ON CONFLICT DO NOTHING', (digest, label))
        return len(rows)


def student_count():
    with connect() as con:
        return con.execute('SELECT COUNT(*) FROM students').fetchone()[0]


def add_vote(lesson_id, voter_code, rating, current_date=None):
    code = voter_code.strip()
    if len(code) != 4 or not code.isascii() or not code.isdigit():
        raise ValueError('Inserisci il codice personale di 4 cifre ricevuto.')
    if rating not in (1, 2, 3, 4, 5):
        raise ValueError('Il voto deve essere compreso tra 1 e 5.')
    with connect() as con:
        begin_write(con)
        digest = code_digest(con, code)
        if con.execute('SELECT 1 FROM students WHERE voter_digest = ?', (digest,)).fetchone() is None:
            raise ValueError('Codice non autorizzato.')
        lesson = con.execute('SELECT lesson_date FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
        if lesson is None:
            raise ValueError('La lezione selezionata non esiste.')
        con.execute('INSERT INTO participation VALUES (?, ?)', (lesson_id, digest))
        con.execute('INSERT INTO votes VALUES (?, ?, ?)', (secrets.token_hex(16), lesson_id, int(rating)))


def teacher_stats():
    with connect() as con:
        return _dicts(con.execute('''
            SELECT t.id, t.name, t.subject,
                   COUNT(v.id) AS total_votes,
                   COUNT(DISTINCT CASE WHEN v.id IS NOT NULL THEN l.id END) AS rated_lessons,
                   SUM(CASE WHEN v.rating = 1 THEN 1 ELSE 0 END) AS rating_1,
                   SUM(CASE WHEN v.rating = 2 THEN 1 ELSE 0 END) AS rating_2,
                   SUM(CASE WHEN v.rating = 3 THEN 1 ELSE 0 END) AS rating_3,
                   SUM(CASE WHEN v.rating = 4 THEN 1 ELSE 0 END) AS rating_4,
                   SUM(CASE WHEN v.rating = 5 THEN 1 ELSE 0 END) AS rating_5,
                   AVG(v.rating) AS average_rating
            FROM teachers t
            LEFT JOIN lessons l ON l.teacher_id = t.id
            LEFT JOIN votes v ON v.lesson_id = l.id
            GROUP BY t.id, t.name, t.subject
            ORDER BY (AVG(v.rating) IS NULL), AVG(v.rating) DESC, COUNT(v.id) DESC,
                     LOWER(t.name)
        '''))


def teacher_history(teacher_id, min_votes_per_lesson=3):
    with connect() as con:
        return _dicts(con.execute('''
            SELECT l.lesson_date, l.slot, l.topic,
                   COUNT(v.id) AS total_votes,
                   AVG(v.rating) AS average_rating
            FROM lessons l
            JOIN votes v ON v.lesson_id = l.id
            WHERE l.teacher_id = ?
            GROUP BY l.id, l.lesson_date, l.slot, l.topic
            HAVING COUNT(v.id) >= ?
            ORDER BY l.lesson_date, l.slot, l.id
        ''', (teacher_id, min_votes_per_lesson)))


def admin_login(entered, expected, now=None):
    """Persistent global limit: five failures block new logins for 15 minutes."""
    if not expected:
        return False, 0, 0
    now = time.time() if now is None else now
    with connect() as con:
        begin_write(con)
        values = dict(con.execute("SELECT key, value FROM settings WHERE key IN ('admin_failures', 'admin_locked_until')").fetchall())
        failures = int(values.get('admin_failures', 0))
        locked_until = float(values.get('admin_locked_until', 0))
        if locked_until > now:
            return False, 0, max(1, int(locked_until - now + 0.999))
        if locked_until:
            failures = 0
        success = hmac.compare_digest(entered.encode('utf-8'), expected.encode('utf-8'))
        failures = 0 if success else failures + 1
        locked_until = now + ADMIN_LOCK_SECONDS if failures >= ADMIN_MAX_ATTEMPTS else 0
        for key, value in [('admin_failures', failures), ('admin_locked_until', locked_until)]:
            con.execute('INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, str(value)))
        return success, max(0, ADMIN_MAX_ATTEMPTS - failures), ADMIN_LOCK_SECONDS if locked_until else 0


def period_label(slot):
    # Legacy hourly slots remain unchanged to preserve IDs and existing votes.
    return 'Mattina' if slot <= 4 else 'Pomeriggio'


def list_lessons(voter_code=None, include_voted=False):
    """Newest insertions first, independently of the lesson date."""
    with connect() as con:
        if voter_code is not None:
            code = voter_code.strip()
            if len(code) != 4 or not code.isascii() or not code.isdigit():
                raise ValueError('Inserisci il codice personale di 4 cifre ricevuto.')
            digest = code_digest(con, code)
            if con.execute('SELECT 1 FROM students WHERE voter_digest = ?', (digest,)).fetchone() is None:
                raise ValueError('Codice non autorizzato.')
            rows = _dicts(con.execute("""
                SELECT l.*, t.name AS teacher_name, t.subject,
                       EXISTS(SELECT 1 FROM participation p WHERE p.lesson_id=l.id AND p.voter_digest=?) AS has_voted
                FROM lessons l JOIN teachers t ON t.id=l.teacher_id
                ORDER BY l.id DESC
            """, (digest,)))
            return rows if include_voted else [row for row in rows if not row['has_voted']]
        return _dicts(con.execute("""
            SELECT l.*, t.name AS teacher_name, t.subject
            FROM lessons l JOIN teachers t ON t.id=l.teacher_id ORDER BY l.id DESC
        """))


def update_lesson_title(lesson_id, title):
    title = title.strip()
    if not title or len(title) > 150:
        raise ValueError('Inserisci un titolo da 1 a 150 caratteri.')
    with connect() as con:
        cursor = con.execute('UPDATE lessons SET topic = ? WHERE id = ?', (title, lesson_id))
        if cursor.rowcount != 1:
            raise ValueError('La lezione selezionata non esiste.')


def update_lesson(lesson_id, title, period):
    title = title.strip()
    if not title or len(title) > 150:
        raise ValueError('Inserisci un titolo da 1 a 150 caratteri.')
    if period not in ('Mattina', 'Pomeriggio'):
        raise ValueError('Seleziona Mattina o Pomeriggio.')
    with connect() as con:
        begin_write(con)
        lesson = con.execute('SELECT * FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
        if lesson is None:
            raise ValueError('La lezione selezionata non esiste.')
        # Preserve legacy slots when the period is unchanged.
        slot = lesson['slot'] if period_label(lesson['slot']) == period else (1 if period == 'Mattina' else 5)
        if period_label(lesson['slot']) != period:
            others = con.execute('SELECT slot FROM lessons WHERE teacher_id = ? AND lesson_date = ? AND id <> ?', (lesson['teacher_id'], lesson['lesson_date'], lesson_id)).fetchall()
            if any(period_label(row['slot']) == period for row in others):
                raise ValueError('Esiste già una lezione per questo professore, data e fascia. Nessuna modifica salvata.')
        con.execute('UPDATE lessons SET topic = ?, slot = ? WHERE id = ?', (title, slot, lesson_id))
