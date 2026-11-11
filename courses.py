"""Course completion and atomic recovery of missing lesson ratings."""
import secrets

import database as db


SQLITE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS course_state (
    teacher_id INTEGER PRIMARY KEY REFERENCES teachers(id),
    closed INTEGER NOT NULL CHECK(closed IN (0, 1))
);
'''


def set_closed(teacher_id, closed):
    if type(closed) is not bool:
        raise ValueError('Stato del corso non valido.')
    with db.connect() as con:
        db.begin_write(con)
        if con.execute('SELECT 1 FROM teachers WHERE id = ?', (teacher_id,)).fetchone() is None:
            raise ValueError('Corso non trovato.')
        con.execute('''INSERT INTO course_state(teacher_id, closed) VALUES (?, ?)
                       ON CONFLICT(teacher_id) DO UPDATE SET closed = excluded.closed''',
                    (teacher_id, int(closed)))


def list_for_digest(con, digest, include_completed=False):
    # One personal query, never shared through the public cache.
    rows = db._dicts(con.execute('''
        SELECT t.id, t.name, t.subject, COUNT(l.id) AS total_lessons,
               COUNT(p.lesson_id) AS voted_lessons,
               SUM(CASE WHEN l.id IS NOT NULL AND p.lesson_id IS NULL THEN 1 ELSE 0 END) AS missing_lessons
        FROM teachers t JOIN course_state s ON s.teacher_id=t.id
        LEFT JOIN lessons l ON l.teacher_id=t.id
        LEFT JOIN participation p ON p.lesson_id=l.id AND p.voter_digest=?
        WHERE s.closed=1 GROUP BY t.id, t.name, t.subject
        ORDER BY LOWER(t.subject), LOWER(t.name), t.id
    ''', (digest,)))
    return rows if include_completed else [row for row in rows if row['missing_lessons'] > 0]


def complete_missing(con, teacher_id, digest, rating, expected_count):
    """Record ordinary anonymous lesson ratings, never overwriting an old vote.

    Called under the writer lock, after checking session expiry/revocation.
    Two batched inserts avoid a round trip per lesson. No shared batch ID,
    timestamp, code or session is stored in ratings.
    """
    if type(rating) is not int or rating not in range(1, 6):
        raise ValueError('Il voto deve essere compreso tra 1 e 5.')
    state = con.execute('SELECT closed FROM course_state WHERE teacher_id=?', (teacher_id,)).fetchone()
    if state is None or state['closed'] != 1:
        raise ValueError('Puoi completare i voti in un unico invio solo per i corsi terminati.')
    lessons = [row['id'] for row in con.execute('''
        SELECT l.id FROM lessons l WHERE l.teacher_id=?
        AND NOT EXISTS (SELECT 1 FROM participation p WHERE p.lesson_id=l.id AND p.voter_digest=?)
        ORDER BY l.id
    ''', (teacher_id, digest)).fetchall()]
    if not lessons:
        raise ValueError('Hai già votato tutte le lezioni di questo corso.')
    if type(expected_count) is not int or expected_count != len(lessons):
        raise ValueError('Il numero di lezioni da completare è cambiato. Aggiorna la pagina e conferma di nuovo.')
    for start in range(0, len(lessons), 200):
        batch = lessons[start:start + 200]
        con.execute('INSERT INTO participation(lesson_id, voter_digest) VALUES ' + ','.join('(?, ?)' for _ in batch),
                    tuple(value for lesson in batch for value in (lesson, digest)))
        con.execute('INSERT INTO votes(id, lesson_id, rating) VALUES ' + ','.join('(?, ?, ?)' for _ in batch),
                    tuple(value for lesson in batch for value in (secrets.token_hex(16), lesson, rating)))
    return len(lessons)
