-- Additive migration. Apply after schema.sql and student_sessions.sql.
-- Keep course_state on rollback. Recovery writes ordinary lesson votes.
SET lock_timeout = '5s';
CREATE TABLE votes_app.course_state (
    teacher_id BIGINT PRIMARY KEY REFERENCES votes_app.teachers(id) ON DELETE RESTRICT,
    closed INTEGER NOT NULL CHECK (closed IN (0, 1))
);
ALTER TABLE votes_app.course_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON votes_app.course_state FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON votes_app.course_state TO votes_runtime;
CREATE POLICY runtime_course_state ON votes_app.course_state TO votes_runtime USING (true) WITH CHECK (true);

-- Enforce closure even for old app instances during a rolling deployment.
-- Same advisory lock/order as application writes; no SECURITY DEFINER.
CREATE FUNCTION votes_app.check_course_open() RETURNS trigger
LANGUAGE plpgsql SET search_path = votes_app, pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('votes_app'), 1);
    IF EXISTS (SELECT 1 FROM course_state WHERE teacher_id=NEW.teacher_id AND closed=1) THEN
        RAISE EXCEPTION 'Corso terminato: impossibile aggiungere lezioni' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION votes_app.check_course_open() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION votes_app.check_course_open() TO votes_runtime;
CREATE TRIGGER course_open_before_lesson BEFORE INSERT ON votes_app.lessons
FOR EACH ROW EXECUTE FUNCTION votes_app.check_course_open();
