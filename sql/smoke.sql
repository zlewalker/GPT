-- Disposable transaction. Leaves no rows behind; run as migration administrator.
BEGIN;
INSERT INTO votes_app.teachers(id, name, subject) VALUES (-100, 'Smoke test', 'Test');
INSERT INTO votes_app.lessons(id, teacher_id, lesson_date, slot, topic) VALUES (-100, -100, '2026-11-10', 1, 'Test');
INSERT INTO votes_app.students VALUES (repeat('0', 64), 'SMOKE_TEST');
DO $$
BEGIN
    IF has_schema_privilege('anon', 'votes_app', 'USAGE') OR
       has_schema_privilege('authenticated', 'votes_app', 'USAGE') THEN
        RAISE EXCEPTION 'Public schema access';
    END IF;
    IF has_table_privilege('votes_runtime', 'votes_app.students', 'INSERT') OR
       has_table_privilege('votes_runtime', 'votes_app.votes', 'DELETE') THEN
        RAISE EXCEPTION 'Excessive runtime permissions';
    END IF;
    INSERT INTO votes_app.participation VALUES (-100, repeat('0', 64));
    INSERT INTO votes_app.votes VALUES ('smoke_vote', -100, 5);
    BEGIN
        INSERT INTO votes_app.participation VALUES (-100, repeat('0', 64));
        RAISE EXCEPTION 'Duplicate vote accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO votes_app.votes VALUES ('invalid_vote', -100, 6);
        RAISE EXCEPTION 'Invalid rating accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    IF (SELECT avg(rating) FROM votes_app.votes WHERE lesson_id = -100) <> 5 THEN
        RAISE EXCEPTION 'Wrong average';
    END IF;
    UPDATE votes_app.lessons SET topic = 'Corrected', slot = 5 WHERE id = -100;
    IF (SELECT count(*) FROM votes_app.participation WHERE lesson_id = -100) <> 1 THEN
        RAISE EXCEPTION 'Participation lost';
    END IF;
END $$;
ROLLBACK;
