"""End-to-end browser check against a temporary local app, never production."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    from playwright.sync_api import sync_playwright, expect
    with tempfile.TemporaryDirectory() as folder:
        os.environ['DATABASE_URL'] = ''
        os.environ['ITS_TIER_DB'] = str(Path(folder) / 'browser.sqlite3')
        os.environ['ADMIN_PIN'] = 'browser-test-only'
        # Running the file directly adds tests/, not the repository root.
        sys.path.insert(0, str(Path(__file__).parents[1]))
        import database as db
        db.init_db()
        roster = Path(folder) / 'codes.csv'
        roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        db.import_student_codes(roster)
        db.add_teacher('Docente test', 'Matematica')
        db.add_lesson(db.list_teachers()[0]['id'], '2026-11-10', 1, 'Lezione browser')
        server = subprocess.Popen(
            [sys.executable, '-m', 'streamlit', 'run', 'app.py', '--server.headless=true',
             '--server.address=127.0.0.1', '--server.port=8519', '--browser.gatherUsageStats=false'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parents[1], env=dict(os.environ),
        )
        try:
            deadline = time.monotonic() + 40
            while True:
                try:
                    urllib.request.urlopen('http://127.0.0.1:8519/_stcore/health', timeout=1).close()
                    break
                except Exception:
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError('Test app did not start') from None
                    time.sleep(0.25)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context()
                page = context.new_page()
                page.goto('http://127.0.0.1:8519')
                field = page.get_by_label('Il tuo codice personale (4 cifre)', exact=True)
                expect(field).to_be_visible(timeout=30000)
                field.fill('0123')
                page.get_by_role('button', name='Accedi per votare', exact=True).click()
                expect(page.get_by_text('Accesso studente attivo', exact=True)).to_be_visible()
                key = 'project-votes:2026-2027:student-session:/'
                page.wait_for_function('(key) => localStorage.getItem(key) !== null', arg=key)
                saved = page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', key)
                assert saved['token'] != '0123' and len(saved['token']) == 43
                page.reload()
                expect(page.get_by_text('Accesso studente attivo', exact=True)).to_be_visible(timeout=30000)
                expect(page.get_by_role('button', name='Invia il voto', exact=True)).to_be_visible()
                # Opening another tab/browser page restores the saved credential.
                another = context.new_page()
                another.goto('http://127.0.0.1:8519')
                expect(another.get_by_text('Accesso studente attivo', exact=True)).to_be_visible(timeout=30000)
                page.get_by_role('button', name='Invia il voto', exact=True).click()
                expect(page.get_by_text('Voto salvato! Grazie.', exact=True)).to_be_visible()
                page.reload()
                expect(page.get_by_text('Non ci sono lezioni da votare. Potresti averle già valutate tutte.', exact=True)).to_be_visible(timeout=30000)
                assert db.teacher_stats()[0]['total_votes'] == 1
                page.get_by_role('button', name='Esci', exact=True).click()
                expect(field).to_be_visible()
                page.wait_for_function('(key) => localStorage.getItem(key) === null', arg=key)
                # A copied token is unusable after logout, not just hidden in the UI.
                page.evaluate('([key, value]) => localStorage.setItem(key, JSON.stringify(value))', [key, saved])
                page.reload()
                expect(field).to_be_visible(timeout=30000)
                expect(page.get_by_text('Accesso studente attivo', exact=True)).to_have_count(0)
                # A different browser never inherits this login.
                other_context = browser.new_context()
                other = other_context.new_page()
                other.goto('http://127.0.0.1:8519')
                expect(other.get_by_label('Il tuo codice personale (4 cifre)', exact=True)).to_be_visible(timeout=30000)
                # Rate limiting survives a new page/connection.
                for _ in range(5):
                    other.get_by_label('Il tuo codice personale (4 cifre)', exact=True).fill('9999')
                    other.get_by_role('button', name='Accedi per votare', exact=True).click()
                    other.wait_for_timeout(250)
                expect(other.get_by_text('Troppi tentativi errati.', exact=False)).to_be_visible()
                other.reload()
                other.get_by_label('Il tuo codice personale (4 cifre)', exact=True).fill('0123')
                other.get_by_role('button', name='Accedi per votare', exact=True).click()
                expect(other.get_by_text('Troppi tentativi errati.', exact=False)).to_be_visible()
                browser.close()
                print('Browser checks passed: persistence, tabs, vote, duplicate block, logout/replay, isolation, login limit.')
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
