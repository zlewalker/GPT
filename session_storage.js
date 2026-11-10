// Only an opaque bearer token is stored; never the student's four-digit code.
export default function(component) {
    const { data, parentElement, setStateValue } = component;
    if (data.acknowledged || parentElement.dataset.requestId === data.id) return;
    parentElement.dataset.requestId = data.id;
    const storageKey = "project-votes:2026-2027:student-session:" + window.location.pathname;
    let token = null;
    let ok = true;
    try {
        if (!window.isSecureContext) throw new Error("https_required");
        if (data.action === "set") {
            window.localStorage.setItem(storageKey, JSON.stringify({
                token: data.token, expires_at: data.expires_at
            }));
        } else if (data.action === "clear") {
            window.localStorage.removeItem(storageKey);
        } else {
            const record = JSON.parse(window.localStorage.getItem(storageKey) || "null");
            if (record && typeof record.token === "string" &&
                /^[A-Za-z0-9_-]{43}$/.test(record.token) &&
                Number.isFinite(record.expires_at) &&
                record.expires_at > Date.now() / 1000) {
                token = record.token;
            } else if (record) {
                window.localStorage.removeItem(storageKey);
            }
        }
    } catch (_) {
        ok = false; // Private mode/storage restrictions: keep only the current session.
    }
    setStateValue("event", { id: data.id, token, ok });
}
