"""Consistent SQLite snapshot, transactional PostgreSQL import, private backups."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

import postgres

TABLES = {
    'teachers': ('id', 'name', 'subject'),
    'lessons': ('id', 'teacher_id', 'lesson_date', 'slot', 'topic', 'duration_hours'),
    'students': ('voter_digest', 'initials'),
    'participation': ('lesson_id', 'voter_digest'),
    'votes': ('id', 'lesson_id', 'rating'),
    'settings': ('key', 'value'),
    'course_state': ('teacher_id', 'closed'),
}
COURSE_TABLES = ('course_state',)
CONTROL_KEYS = {'schema_version', 'migration_ready'}


def validate(data):
    """Validate before writing anything; never print roster or key material."""
    settings = dict(data['settings'])
    if settings.get('school_year') != '2026/2027' or not settings.get('voter_key'):
        raise ValueError('Anno o chiave dei codici mancanti/non supportati.')
    if not data['students']:
        raise ValueError('Nessuno studente registrato: importazione annullata.')
    teachers = {row[0] for row in data['teachers']}
    students = {row[0] for row in data['students']}
    lessons = {row[0] for row in data['lessons']}
    for row in data['lessons']:
        if row[1] not in teachers or row[5] != 4:
            raise ValueError('Lezioni incoerenti o durata diversa da quattro ore.')
    participation_counts, vote_counts = {}, {}
    for lesson, digest in data['participation']:
        if lesson not in lessons or digest not in students:
            raise ValueError('Partecipazione senza lezione o studente.')
        participation_counts[lesson] = participation_counts.get(lesson, 0) + 1
    for _, lesson, rating in data['votes']:
        if lesson not in lessons or rating not in range(1, 6):
            raise ValueError('Voto incoerente.')
        vote_counts[lesson] = vote_counts.get(lesson, 0) + 1
    if participation_counts != vote_counts:
        raise ValueError('Partecipazioni e voti non coincidono per lezione.')
    for teacher, closed in data.get('course_state', []):
        if teacher not in teachers or closed not in (0, 1):
            raise ValueError('Stato corso non valido.')


def read_rows(con):
    data = {}
    for table, columns in TABLES.items():
        # Read historical SQLite backups without creating or modifying anything.
        if table in COURSE_TABLES and isinstance(con, sqlite3.Connection):
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                data[table] = []
                continue
        rows = [list(row) for row in con.execute(f'SELECT {", ".join(columns)} FROM {table}')]
        if table == 'settings':
            rows = [row for row in rows if row[0] not in CONTROL_KEYS]
        data[table] = sorted(rows)
    return data


def read_sqlite(path):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
        # Online backup API captures committed WAL contents without changing the source.
        with closing(sqlite3.connect(':memory:')) as snapshot:
            source.backup(snapshot)
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database SQLite danneggiato.')
            if snapshot.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Relazioni SQLite non valide.')
            if {row[1] for row in snapshot.execute('PRAGMA table_info(votes)')} != {'id', 'lesson_id', 'rating'}:
                raise ValueError('Schema SQLite precedente: completare prima la migrazione locale.')
            data = read_rows(snapshot)
    validate(data)
    return data


def summary(data):
    return {table: len(rows) for table, rows in data.items()}


def save_backup(data, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    path = directory / f'votes_private_{stamp}.json'
    with path.open('x', encoding='utf-8') as file:
        json.dump({'format': 1, 'data': data}, file, ensure_ascii=False, indent=2)
    return path


def verify(con, data):
    if read_rows(con) != {table: data.get(table, []) for table in TABLES}:
        raise ValueError('Confronto integrale fallito: transazione annullata.')


def import_postgres(data):
    validate(data)
    with postgres.connect() as con:
        postgres.begin_write(con)
        con.execute('LOCK TABLE teachers, lessons, students, participation, votes, settings, course_state IN ACCESS EXCLUSIVE MODE')
        version = con.execute("SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
        if not version or version[0] != '1':
            raise ValueError('Applicare prima sql/schema.sql.')
        existing = read_rows(con)
        if any(existing.values()) or con.execute("SELECT 1 FROM settings WHERE key = 'migration_ready'").fetchone():
            raise ValueError('Destinazione già popolata: nessun dato sovrascritto.')
        for table, columns in TABLES.items():
            placeholders = ', '.join('?' for _ in columns)
            for row in data.get(table, []):
                con.execute(f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders})', row)
        verify(con, data)
        for table in ('teachers', 'lessons'):
            # IDs copied from SQLite must not collide with future identity values.
            con.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM {table}")
        con.execute("INSERT INTO settings VALUES ('migration_ready', '1')")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='data/tierlist.sqlite3')
    parser.add_argument('--apply', action='store_true', help='Import into an empty PostgreSQL destination')
    parser.add_argument('--verify', action='store_true', help='Compare source with PostgreSQL, without writes')
    parser.add_argument('--export', action='store_true', help='Export a consistent private PostgreSQL backup')
    parser.add_argument('--restore', type=Path, help='Restore a private JSON backup into an empty destination')
    parser.add_argument('--backup-dir', default='data/backups')
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.apply, args.verify, args.export, args.restore)) > 1:
        parser.error('Scegli una sola operazione.')
    try:
        if args.export:
            with postgres.connect() as con:
                con.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                data = read_rows(con)
            validate(data)
            print('Backup riservato:', save_backup(data, args.backup_dir))
        else:
            if args.restore:
                document = json.loads(args.restore.read_text(encoding='utf-8'))
                if document.get('format') != 1:
                    raise ValueError('Formato backup non supportato.')
                data = document['data']
                validate(data)
            else:
                data = read_sqlite(args.source)
            print('Conteggi:', json.dumps(summary(data)))
            if args.verify:
                with postgres.connect() as con:
                    con.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    verify(con, data)
                print('Verifica integrale completata.')
            elif args.apply or args.restore:
                print('Backup riservato:', save_backup(data, args.backup_dir))
                import_postgres(data)
                print('Importazione verificata e confermata.')
            else:
                print('Simulazione completata. Nessuna scrittura; usa --apply solo al passaggio definitivo.')
        return 0
    except Exception:
        # Driver errors can include connection details: do not print them in shared logs.
        print('Operazione non completata. Controlla configurazione, schema e coerenza dei dati. Nessuna importazione parziale viene confermata.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
