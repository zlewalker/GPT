-- Additive deployment: run as administrator before releasing the session UI.
-- Existing code, votes and participation are unchanged; schema_version stays 1.
CREATE TABLE IF NOT EXISTS votes_app.student_sessions (
    token_hash TEXT PRIMARY KEY CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    voter_digest TEXT NOT NULL REFERENCES votes_app.students(voter_digest) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS student_sessions_expiry_idx ON votes_app.student_sessions(expires_at);
ALTER TABLE votes_app.student_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON votes_app.student_sessions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON votes_app.student_sessions TO votes_runtime;
DROP POLICY IF EXISTS runtime_student_sessions ON votes_app.student_sessions;
CREATE POLICY runtime_student_sessions ON votes_app.student_sessions TO votes_runtime
    USING (true) WITH CHECK (true);
