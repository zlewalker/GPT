"""Opaque, revocable sessions. Server-side storage contains hashes, not credentials."""
import hashlib
import re
import secrets
import time

import database as db

SESSION_SECONDS = 30 * 24 * 60 * 60
LOGIN_WINDOW = 15 * 60
MAX_FAILURES = 5
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}')


def _hash_token(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def login(code, now=None):
    """Return (token, expiry, retry_seconds); failed attempts must COMMIT too.

    A database-wide limit cannot be bypassed by clearing storage, changing IP,
    or restarting Streamlit. Successful logins do not reset other failures.
    """
    now = int(time.time()) if now is None else int(now)
    with db.connect() as con:
        db.begin_write(con)
        values = dict(con.execute(
            "SELECT key, value FROM settings WHERE key IN ('student_login_window', 'student_login_failures')"
        ).fetchall())
        window = int(values.get('student_login_window', now))
        failures = int(values.get('student_login_failures', 0))
        if now < window or now - window >= LOGIN_WINDOW:
            window, failures = now, 0
        if failures >= MAX_FAILURES:
            return None, None, max(1, LOGIN_WINDOW - (now - window))
        code = code.strip() if isinstance(code, str) else ''
        digest = None
        if len(code) == 4 and code.isascii() and code.isdigit():
            digest = db.code_digest(con, code)
            if con.execute('SELECT 1 FROM students WHERE voter_digest = ?', (digest,)).fetchone() is None:
                digest = None
        if digest is None:
            failures += 1
        for key, value in [('student_login_window', window), ('student_login_failures', failures)]:
            con.execute(
                'INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (key, str(value)),
            )
        if digest is None:
            retry = max(1, LOGIN_WINDOW - (now - window)) if failures >= MAX_FAILURES else 0
            return None, None, retry
        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_SECONDS
        con.execute('DELETE FROM student_sessions WHERE expires_at <= ?', (now,))
        con.execute('INSERT INTO student_sessions VALUES (?, ?, ?)', (_hash_token(token), digest, expires_at))
        return token, expires_at, 0


def _session_digest(con, token, now=None):
    token_hash = _hash_token(token)
    if token_hash is None:
        return None
    now = int(time.time()) if now is None else int(now)
    row = con.execute(
        'SELECT s.voter_digest FROM student_sessions s JOIN students t ON t.voter_digest=s.voter_digest '
        'WHERE s.token_hash = ? AND s.expires_at > ?', (token_hash, now)
    ).fetchone()
    return row['voter_digest'] if row else None


def is_authenticated(token, now=None):
    if _hash_token(token) is None:
        return False
    with db.connect() as con:
        return _session_digest(con, token, now) is not None


def logout(token):
    token_hash = _hash_token(token)
    if token_hash is None:
        return
    with db.connect() as con:
        db.begin_write(con)
        con.execute('DELETE FROM student_sessions WHERE token_hash = ?', (token_hash,))


def reset_login_failures(now=None):
    now = int(time.time()) if now is None else int(now)
    with db.connect() as con:
        db.begin_write(con)
        for key, value in [('student_login_window', now), ('student_login_failures', 0)]:
            con.execute(
                'INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (key, str(value)),
            )


def list_lessons(token, include_voted=False):
    with db.connect() as con:
        digest = _session_digest(con, token)
        if digest is None:
            raise ValueError('Accesso scaduto o terminato. Accedi di nuovo con il tuo codice.')
        return db._lessons_for_digest(con, digest, include_voted)


def add_vote(lesson_id, token, rating):
    # Expiry/revocation check and both inserts share one transaction and write lock.
    with db.connect() as con:
        db.begin_write(con)
        digest = _session_digest(con, token)
        if digest is None:
            raise ValueError('Accesso scaduto o terminato. Accedi di nuovo con il tuo codice.')
        db._record_vote(con, lesson_id, digest, rating)


def list_courses(token, include_completed=False):
    import courses
    with db.connect() as con:
        digest = _session_digest(con, token)
        if digest is None:
            raise ValueError('Accesso scaduto o terminato. Accedi di nuovo con il tuo codice.')
        return courses.list_for_digest(con, digest, include_completed)


def complete_course(teacher_id, token, rating, expected_count):
    import courses
    with db.connect() as con:
        db.begin_write(con)
        digest = _session_digest(con, token)
        if digest is None:
            raise ValueError('Accesso scaduto o terminato. Accedi di nuovo con il tuo codice.')
        return courses.complete_missing(con, teacher_id, digest, rating, expected_count)
