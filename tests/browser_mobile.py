"""Responsive browser regression checks using disposable data, not production."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request


def assert_fits(page, locator, label):
    box = locator.bounding_box()
    assert box and box['x'] >= -1 and box['x'] + box['width'] <= page.viewport_size['width'] + 1, (label, box)
    return box


def assert_no_overflow(page):
    sizes = page.evaluate("""() => {
        const main = document.querySelector('[data-testid="stMain"]');
        return {window: innerWidth, document: document.documentElement.scrollWidth,
                main: main?.clientWidth, mainScroll: main?.scrollWidth};
    }""")
    assert sizes['document'] <= sizes['window'] + 1, sizes
    assert not sizes['main'] or sizes['mainScroll'] <= sizes['main'] + 1, sizes


def main():
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).parents[1]
    output = root / 'mobile-screenshots'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        os.environ['DATABASE_URL'] = ''
        os.environ['ITS_TIER_DB'] = str(Path(folder) / 'mobile.sqlite3')
        os.environ['ADMIN_PIN'] = 'mobile-test-only'
        sys.path.insert(0, str(root))
        import database as db
        db.init_db()
        roster = Path(folder) / 'codes.csv'
        roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        db.import_student_codes(roster)
        title = 'Architetture dei sistemi distribuiti e progettazione di applicazioni con interfacce accessibili: esercitazione completa e discussione dei risultati'
        for teacher in range(6):
            name = f'Professore {teacher + 1} Alessandra Maria Francesca di San Giovanni e delle Tecnologie'
            db.add_teacher(name, 'Tecnologie e progettazione di sistemi informatici')
            teacher_id = next(t['id'] for t in db.list_teachers() if t['name'] == name)
            for day in range(1, 13 if teacher == 0 else 2):
                db.add_lesson(teacher_id, f'2026-10-{day:02d}', 1, title)
                lesson_id = db.list_lessons()[0]['id']
                for code, rating in [('1234', 3), ('2345', 4), ('3456', 5)]:
                    db.add_vote(lesson_id, code, rating)
        server = subprocess.Popen(
            [sys.executable, '-m', 'streamlit', 'run', 'app.py', '--server.headless=true',
             '--server.address=127.0.0.1', '--server.port=8520', '--browser.gatherUsageStats=false'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=root, env=dict(os.environ),
        )
        try:
            deadline = time.monotonic() + 40
            while True:
                try:
                    urllib.request.urlopen('http://127.0.0.1:8520/_stcore/health', timeout=1).close()
                    break
                except Exception:
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError('Mobile test app did not start') from None
                    time.sleep(.25)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                profiles = [(320, 740, 'light'), (390, 844, 'light'), (430, 932, 'dark'), (1280, 900, 'light')]
                for width, height, theme in profiles:
                    label = f'{width}-{theme}'
                    context = browser.new_context(viewport={'width': width, 'height': height},
                                                  is_mobile=width <= 640, has_touch=width <= 640,
                                                  device_scale_factor=1, color_scheme=theme)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto('http://127.0.0.1:8520')
                    field = page.get_by_label('Il tuo codice personale (4 cifre)', exact=True)
                    expect(field).to_be_visible(timeout=30000)
                    expect(field).to_have_attribute('inputmode', 'numeric')
                    expect(field).to_have_attribute('type', 'password')
                    submit = page.get_by_role('button', name='Accedi per votare', exact=True)
                    expect(submit).to_be_in_viewport()
                    assert_fits(page, field, 'login field')
                    assert_no_overflow(page)
                    page.screenshot(path=str(output / f'{label}-login.png'), full_page=True)
                    field.fill('0123')
                    submit.click()
                    expect(page.get_by_text('Accesso studente attivo', exact=True)).to_be_visible()
                    refresh = page.get_by_role('button', name=re.compile('Aggiorna risultati'))
                    logout = page.get_by_role('button', name='Esci', exact=True)
                    for control in [refresh, logout]:
                        box = assert_fits(page, control, 'main action')
                        assert width > 640 or box['height'] >= 44, box
                    lesson = page.get_by_role('article', name='Riepilogo della lezione')
                    expect(lesson).to_contain_text(title)
                    assert_fits(page, lesson, 'full lesson title')
                    page.screenshot(path=str(output / f'{label}-vote.png'), full_page=True)
                    radios = page.locator('label').filter(has=page.locator('input[type="radio"]'))
                    if radios.count() != 5:
                        print('Radio structure:', page.get_by_role('radio').first.evaluate('e => e.parentElement.parentElement.outerHTML'))
                    expect(radios).to_have_count(5)
                    if width <= 640:
                        for radio in radios.all():
                            box = assert_fits(page, radio, 'rating choice')
                            assert box['width'] >= 43 and box['height'] >= 44, box
                    # Native inputs are visually hidden by React Aria; people tap the label.
                    five = radios.filter(has=page.get_by_role('radio', name='5', exact=True))
                    if width <= 640:
                        five.tap()
                    else:
                        five.click()
                    expect(page.get_by_role('radio', name='5', exact=True)).to_be_checked()
                    page.screenshot(path=str(output / f'{label}-vote.png'), full_page=True)
                    page.get_by_role('button', name='Invia il voto', exact=True).click()
                    expect(page.get_by_text('Voto salvato! Grazie.', exact=True)).to_be_visible()
                    page.get_by_role('tab', name='🏆 Classifica', exact=True).click()
                    cards = page.locator('.mobile-rankings')
                    if width <= 640:
                        expect(cards).to_be_visible()
                        expect(cards.locator('article')).to_have_count(6)
                        assert_fits(page, cards, 'ranking cards')
                        expect(page.locator('.st-key-ranking_table')).to_be_hidden()
                    else:
                        expect(cards).to_be_hidden()
                        expect(page.locator('.st-key-ranking_table')).to_be_visible()
                    assert_no_overflow(page)
                    page.screenshot(path=str(output / f'{label}-ranking.png'), full_page=True)
                    page.get_by_role('tab', name='📈 Grafici', exact=True).click()
                    expect(page.get_by_text('Medie delle singole lezioni per materia', exact=True)).to_be_visible()
                    charts = page.get_by_test_id('stVegaLiteChart').locator('canvas, svg')
                    try:
                        expect(charts).to_have_count(2, timeout=15000)
                    except AssertionError:
                        page.screenshot(path=str(output / f'{label}-charts-debug.png'), full_page=True)
                        print('Chart page errors:', errors)
                        print('Chart roots:', page.locator('canvas, svg').evaluate_all(
                            'elements => elements.map(e => ({tag:e.tagName, cls:e.getAttribute("class"), role:e.getAttribute("role"), testid:e.closest("[data-testid]")?.getAttribute("data-testid")}))'
                        ))
                        print('Chart messages:', page.locator('[data-testid="stException"], [role="alert"]').all_text_contents())
                        raise
                    for chart in charts.all():
                        assert_fits(page, chart, 'chart canvas')
                    assert_no_overflow(page)
                    page.get_by_text('Conteggi dei voti per professore', exact=True).click()
                    expect(page.get_by_text('1★: 0', exact=False).first).to_be_visible()
                    page.screenshot(path=str(output / f'{label}-charts.png'), full_page=True)
                    page.get_by_role('tab', name='⚙️ Gestione', exact=True).click()
                    admin = page.get_by_label('PIN amministratore', exact=True)
                    expect(admin).to_be_visible()
                    assert_fits(page, admin, 'admin input')
                    assert_no_overflow(page)
                    logout.click()
                    page.get_by_role('tab', name='🗳️ Vota', exact=True).click()
                    expect(field).to_be_visible()
                    assert not errors, errors
                    context.close()
                    print(f'Responsive checks passed: {label}')
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
