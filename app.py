"""Launch with: python -m streamlit run app.py"""

from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import database as db
import browser_session
import mobile_ui
import voter_auth
import read_cache
import courses
from rules import tier_for, rounded_score

MIN_VOTES = 3
ROME = ZoneInfo('Europe/Rome')


def today_italy():
    return datetime.now(ROME).date()


st.set_page_config(page_title='Project Votes', page_icon='🎓', layout='wide', initial_sidebar_state='collapsed')

@st.cache_resource
def initialize_database():
    db.init_db()
    roster = Path(__file__).parent / 'private' / 'codici_studenti_2026_2027.csv'
    if not db.postgres.enabled() and roster.exists():
        db.import_student_codes(roster)
    return True

try:
    initialize_database()
except Exception:
    st.error("Database non disponibile o migrazione incompleta. Contatta l'amministratore.")
    st.stop()

storage_ready, student_token, storage_ok = browser_session.sync()
student_logged_in = voter_auth.is_authenticated(student_token)
if student_token and not student_logged_in:
    browser_session.forget()
    st.rerun()

mobile_ui.apply_layout(student_logged_in, storage_ready)

st.title('🎓 Project Votes')
st.caption(f'Anno scolastico {db.SCHOOL_YEAR} - Valuta le lezioni e segui la tier list della classe.')

with st.container(key='page_actions'):
    action_columns = st.columns(2 if student_logged_in else 1)
    with action_columns[0]:
        st.button('🔄 Aggiorna risultati', key='refresh_results', width='stretch',
                  on_click=read_cache.clear,
                  help='Carica i nuovi voti e aggiorna i risultati.')
    if student_logged_in:
        with action_columns[1]:
            if st.button('Esci', key='student_logout', width='stretch',
                         help='Termina l’accesso studente su questo browser.'):
                try:
                    voter_auth.logout(student_token)
                except Exception:
                    st.error('Uscita non completata. Riprova quando il collegamento al database è disponibile.')
                else:
                    browser_session.forget()
                    st.rerun()
if storage_ready and not storage_ok:
    st.caption('Questo browser non permette di ricordare l’accesso. La sessione resta valida finché questa pagina rimane aperta. Per ricordarla usa HTTPS e abilita la memoria del sito.')

with st.sidebar:
    st.subheader('ℹ️ Come funziona')
    st.write('Ogni studente può inserire **un voto per lezione usando lo stesso codice personale**.')
    st.write('Tutti i dati appartengono all’anno 2026/2027. Ogni lezione inserita si vota una sola volta, indipendentemente dalla durata.')
    st.info(f'Le medie diventano visibili dopo almeno {MIN_VOTES} voti per professore.')
    st.caption('Conserva il tuo codice e non condividerlo. Aggiorna i risultati con il pulsante nella pagina; non ci sono aggiornamenti periodici.')


@st.fragment
def show_top_three(stats):
    leaders = [r for r in stats if r['total_votes'] >= MIN_VOTES]
    if not leaders:
        st.caption(f'In attesa di almeno {MIN_VOTES} voti per professore.')
        return
    for position, teacher in enumerate(leaders[:3], start=1):
        st.write(f"{position}. {teacher['name']} · {teacher['subject']} — {rounded_score(teacher['average_rating']):.2f}/5")


# Public results share a short cache; explicit refresh and writes clear it.
stats = read_cache.teacher_stats()
with st.expander('🏆 Top 3 professori'):
    show_top_three(stats)


vote_tab, leaderboard_tab, trends_tab, admin_tab = st.tabs(
    ['🗳️ Vota', '🏆 Classifica', '📈 Grafici', '⚙️ Gestione'],
    key='active_tab', on_change='rerun',
)

def lesson_label(row):
    date_label = datetime.strptime(row['lesson_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
    title = row['topic'] or row['subject']
    voted = ' - Già votata' if row.get('has_voted') else ''
    return f"{date_label} - {db.period_label(row['slot'])} - {row['teacher_name']} - {row['subject']} - {title} (#{row['id']}){voted}"


def show_course_vote(student_token):
    st.caption('Scegli un voto da applicare a tutte le lezioni del corso che non hai ancora valutato. I voti già inviati non cambiano.')
    include_voted = st.checkbox('Mostra anche i corsi già completati', key='include_course_voted')
    try:
        available = voter_auth.list_courses(student_token, include_voted)
    except ValueError as exc:
        st.error(str(exc))
        return
    if not available:
        st.info('Nessun corso terminato da completare: potrebbe non essere ancora stato chiuso dall’amministratore oppure hai già votato tutte le sue lezioni.')
    else:
        lookup = {row['id']: row for row in available}
        selected = st.selectbox('Corso terminato', list(lookup),
            format_func=lambda ident: f"{lookup[ident]['subject']} — {lookup[ident]['name']} · {lookup[ident]['missing_lessons']} lezioni da completare",
            key='course_vote_selection')
        missing = lookup[selected]['missing_lessons']
        if not missing:
            st.info('Non ci sono lezioni da completare per questo corso.')
        else:
            st.write(f"**{lookup[selected]['subject']} — {lookup[selected]['name']}**")
            st.info(f"Il voto scelto verrà registrato su {missing} lezioni non ancora votate, su {lookup[selected]['total_lessons']} totali. I {lookup[selected]['voted_lessons']} voti già espressi rimarranno invariati.")
            with st.form('course_vote_form'):
                rating = st.radio('Voto per tutte le lezioni mancanti', [1, 2, 3, 4, 5], index=3, horizontal=True, key='course_rating')
                st.caption('Ogni voto conterà nella media del professore, nella tier list e nel grafico della relativa lezione, con lo stesso peso di un voto singolo. Dopo l’invio non puoi modificarli.')
                confirmed = st.checkbox(f'Confermo lo stesso voto per tutte le {missing} lezioni mancanti', key='confirm_course_vote')
                submit = st.form_submit_button('Completa i voti del corso', type='primary', width='stretch')
            if submit:
                if not confirmed:
                    st.error('Conferma l’applicazione del voto alle lezioni mancanti prima di inviare.')
                else:
                    try:
                        completed = voter_auth.complete_course(selected, student_token, rating, missing)
                    except ValueError as exc:
                        st.error(str(exc))
                    except db.INTEGRITY_ERRORS:
                        st.warning('Invio non completato. Aggiorna la pagina e controlla le lezioni ancora da votare.')
                    else:
                        read_cache.clear()
                        st.session_state['course_vote_saved'] = completed
                        st.rerun()
    completed = st.session_state.pop('course_vote_saved', None)
    if completed:
        st.success(f'Voti salvati su {completed} lezioni. Grazie!')
    st.caption('La partecipazione resta separata dalle valutazioni, come per i voti alle singole lezioni.')


@st.fragment
def show_vote(student_token, storage_ready, student_logged_in):
    st.subheader('Vota le lezioni o il corso')
    st.caption('Scegli una lezione, valuta da 1 a 5 e conferma l’invio. Puoi votare anche le lezioni passate.')
    if not storage_ready:
        st.info('Recupero dell’accesso su questo browser…')
    elif not student_logged_in:
        st.caption('Il tuo accesso dura fino a 30 giorni su questo browser. Esci sempre dai dispositivi condivisi.')
        with st.form('student_login', clear_on_submit=True):
            code = st.text_input('Il tuo codice personale (4 cifre)', type='password', max_chars=4, key='login_code', autocomplete='off', placeholder='Le tue 4 cifre')
            login_student = st.form_submit_button('Accedi per votare', type='primary', width='stretch')
        if login_student:
            try:
                token, expires_at, retry_seconds = voter_auth.login(code)
            except Exception:
                st.error('Accesso non disponibile. Riprova più tardi o contatta l’amministratore.')
            else:
                if token:
                    browser_session.remember(token, expires_at)
                    st.rerun()
                elif retry_seconds:
                    st.error(f'Troppi tentativi errati. Nuovi accessi temporaneamente bloccati: riprova tra {(retry_seconds + 59) // 60} minuti.')
                else:
                    st.error('Codice non valido. Usa le quattro cifre ricevute privatamente.')
    else:
        st.caption('Accesso studente attivo')
        vote_kind = st.selectbox('Tipo di valutazione', ['Singole lezioni', 'Corso terminato'], key='vote_kind')
        if vote_kind == 'Corso terminato':
            show_course_vote(student_token)
        else:
            include_voted = st.checkbox('Mostra anche le lezioni già votate', value=False)
            try:
                available = voter_auth.list_lessons(student_token, include_voted)
            except ValueError as exc:
                st.error(str(exc))
            else:
                if not available:
                    st.info('Non ci sono lezioni da votare. Potresti averle già valutate tutte.')
                else:
                    lookup = {row['id']: row for row in available}
                    selected = st.selectbox('Lezione', options=list(lookup), format_func=lambda lesson_id: lesson_label(lookup[lesson_id]), key='vote_lesson')
                    lesson = lookup[selected]
                    st.html(
                        '<article class="pv-lesson" aria-label="Riepilogo della lezione">'
                        f'<div class="pv-lesson-meta">{escape(datetime.strptime(lesson["lesson_date"], "%Y-%m-%d").strftime("%d/%m/%Y"))} · {escape(db.period_label(lesson["slot"]))}</div>'
                        f'<div class="pv-lesson-title">{escape(lesson["topic"] or lesson["subject"])}</div>'
                        f'<div class="pv-lesson-meta">{escape(lesson["teacher_name"])} · {escape(lesson["subject"])}</div>'
                        '</article>'
                    )
                    if lesson['has_voted']:
                        st.info('Hai già votato questa lezione. Il voto non può essere ripetuto.')
                    else:
                        with st.form('form_vote'):
                            rating = st.radio('Quanto valuti questa lezione?', [1, 2, 3, 4, 5], index=3, horizontal=True)
                            st.caption('1 = valutazione più bassa · 5 = valutazione più alta')
                            submitted = st.form_submit_button('Invia il voto', type='primary', width='stretch')
                        if submitted:
                            try:
                                voter_auth.add_vote(selected, student_token, rating)
                            except ValueError as exc:
                                st.error(str(exc))
                            except db.INTEGRITY_ERRORS:
                                st.warning('Hai già votato questa lezione.')
                            else:
                                read_cache.clear()
                                st.session_state['vote_saved'] = True
                                st.rerun()
    if st.session_state.pop('vote_saved', False):
        st.success('Voto salvato! Grazie.')
    st.caption('La partecipazione viene registrata separatamente dalla valutazione.')
    with st.expander('Come votare, regole e riservatezza'):
        st.markdown('''
    1. **Accedi con il codice di 4 cifre** che hai ricevuto privatamente. Il sito può ricordare l’accesso su questo browser per 30 giorni; sui dispositivi condivisi premi “Esci” quando hai finito.
    2. **Scegli la lezione** controllando data, Mattina/Pomeriggio, professore e titolo. Le ultime inserite sono in cima: puoi scorrere il menu o scrivere per cercare quelle più vecchie.
    3. **Scegli un voto da 1 a 5 e premi “Invia il voto”.** Aspetta il messaggio “Voto salvato!”: selezionare il numero da solo non invia la valutazione.
    ''')
        st.caption('Il codice serve a registrare soltanto se hai già votato una lezione. Il voto è salvato separatamente, senza codice o iniziali, e nell’app vengono mostrati solo risultati aggregati dopo almeno 3 voti. Questa separazione protegge la tua riservatezza.')
        st.info('Puoi recuperare anche le lezioni passate: non c’è una scadenza. Ogni lezione accetta un solo voto per codice, anche se dura 4 ore. Dopo l’invio il voto non può essere modificato.')
        st.markdown('''
**Perché una lezione scompare?** Dopo il voto viene tolta dall’elenco delle lezioni da valutare. Attiva **“Mostra anche le lezioni già votate”** per ritrovarla: sarà indicata come già votata e non potrai inviare un altro voto. Il voto precedente non viene mostrato.

**Vuoi valutare tutto il corso?** Dopo l’accesso scegli **Corso terminato**. Puoi scegliere un voto da applicare a tutte le lezioni non ancora votate di quella materia e professore. Il corso deve essere chiuso dall’amministratore. I voti precedenti non cambiano; quelli completati contano normalmente nella media, nella tier list e nei grafici delle lezioni.

**Cosa significano i numeri?** 1 è la valutazione più bassa, 5 la più alta. Valuta l’esperienza della lezione a cui hai partecipato.

**Dove vedo i risultati?** In **Classifica** trovi la media dei voti di ogni professore e la fascia da S (più alta) a D. La media appare dopo almeno **3 voti per professore**. In **Grafici** scegli una materia per vedere le medie delle singole lezioni: ogni punto richiede almeno **3 voti su quella lezione**. I risultati si aggiornano ricaricando la pagina o premendo **“Aggiorna risultati”** in alto nella pagina; la durata della lezione non dà più peso al voto.

**Il voto è collegato alle mie iniziali?** Il registro della partecipazione tiene traccia delle lezioni già votate dal tuo codice. Le valutazioni sono conservate separatamente, senza codice o iniziali. Questa separazione protegge la riservatezza, ma non garantisce un anonimato assoluto.

**Il codice non funziona o l’ho perso?** Controlla di avere inserito tutte e quattro le cifre del codice ricevuto. Se il problema resta, chiedi all’amministratore: inventare un nuovo codice non permette di votare.

**Non vedo lezioni da votare?** Potresti averle già valutate tutte, oppure non sono ancora state inserite. Controlla l’opzione delle lezioni già votate o segnala la lezione mancante all’amministratore. La scheda **Gestione** è riservata a lui.
''')


with vote_tab:
    if vote_tab.open:
        show_vote(student_token, storage_ready, student_logged_in)


@st.fragment
def show_leaderboard(stats):
    if not stats:
        st.info('Ancora nessun professore. Aggiungine uno dalla scheda Gestione.')
        return

    active = [r for r in stats if r['total_votes'] >= MIN_VOTES]
    pending = [r for r in stats if r['total_votes'] < MIN_VOTES]

    with st.container(key='ranking_metrics'):
        c1, c2, c3 = st.columns(3)
        c1.metric('Professori registrati', len(stats))
        c2.metric('Voti totali', sum(r['total_votes'] for r in stats))
        c3.metric('Professori in classifica', len(active))

    if active:
        rows = [
            {
                'Tier': tier_for(r['average_rating']),
                'Professore': r['name'],
                'Materia': r['subject'],
                'Media / 5': rounded_score(r['average_rating']),
                'Voti': r['total_votes'],
                'Lezioni votate': r['rated_lessons'],
            }
            for r in active
        ]
        with st.container(key='ranking_table'):
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        cards = [
            '<article class="pv-rank-card">'
            f'<div class="pv-rank-heading"><span class="pv-tier">{escape(row["Tier"])}</span>'
            f'<div><div class="pv-rank-name">{position}. {escape(row["Professore"])}</div>'
            f'<div class="pv-rank-meta">{escape(row["Materia"])}</div></div></div>'
            f'<div class="pv-rank-meta"><strong>{row["Media / 5"]:.2f}/5</strong> · {row["Voti"]} voti · {row["Lezioni votate"]} lezioni votate</div>'
            '</article>'
            for position, row in enumerate(rows, start=1)
        ]
        st.html('<section class="mobile-rankings" aria-label="Classifica dei professori">' + ''.join(cards) + '</section>')
    else:
        st.info(f'La classifica apparirà quando almeno un professore avrà {MIN_VOTES} voti.')

    if pending:
        st.caption('Ancora fuori classifica (numero minimo di voti non raggiunto):')
        for r in pending:
            st.write(f"• {r['name']} — {r['subject']}: {r['total_votes']}/{MIN_VOTES} voti")

    st.caption('Tier: S ≥ 4,5 · A ≥ 4,0 · B ≥ 3,0 · C ≥ 2,0 · D < 2,0. Media arrotondata a 2 decimali; a parità di soglia si assegna il tier superiore. Per aggiornare i risultati, premi “Aggiorna risultati” nella barra laterale o ricarica la pagina.')


with leaderboard_tab:
    if leaderboard_tab.open:
        st.subheader('Classifica dei professori')
        show_leaderboard(stats)




@st.fragment
def show_history(stats):
    teachers = stats
    if not teachers:
        st.info('Aggiungi prima un professore dalla scheda Gestione.')
        return
    st.markdown('#### Confronto delle votazioni dei professori')
    stats = [r for r in stats if r['total_votes'] >= MIN_VOTES]
    if stats:
        distribution = pd.DataFrame([
            {
                'Professore': f"{r['name']} · {r['subject']}",
                'Valutazione': str(rating),
                'Numero di voti': int(r[f'rating_{rating}']),
                'Percentuale': int(r[f'rating_{rating}']) / int(r['total_votes']),
                'Voti totali': int(r['total_votes']),
                'Media': float(r['average_rating']),
            }
            for r in stats for rating in range(1, 6)
        ])
        st.vega_lite_chart(distribution, {
            'height': max(220, len(stats) * 45),
            'mark': {'type': 'bar', 'cornerRadius': 3},
            'encoding': {
                'y': {'field': 'Professore', 'type': 'nominal', 'sort': distribution['Professore'].drop_duplicates().tolist(), 'axis': {'title': None, 'labelLimit': {'expr': 'max(65, min(180, width * 0.4))'}}},
                'x': {'field': 'Percentuale', 'type': 'quantitative', 'stack': 'zero', 'scale': {'domain': [0, 1]}, 'axis': {'title': 'Distribuzione dei voti ricevuti', 'format': '.0%'}},
                'color': {'field': 'Valutazione', 'type': 'nominal', 'scale': {'domain': ['1', '2', '3', '4', '5'], 'range': ['#f43f5e', '#f59e0b', '#a78bfa', '#3b82f6', '#14b8a6']}, 'legend': {'title': 'Voto', 'orient': 'top'}},
                'order': {'field': 'Valutazione', 'type': 'ordinal'},
                'tooltip': [
                    {'field': 'Professore', 'type': 'nominal'},
                    {'field': 'Valutazione', 'type': 'nominal', 'title': 'Voto'},
                    {'field': 'Numero di voti', 'type': 'quantitative'},
                    {'field': 'Percentuale', 'type': 'quantitative', 'format': '.1%'},
                    {'field': 'Voti totali', 'type': 'quantitative'},
                    {'field': 'Media', 'type': 'quantitative', 'format': '.2f'},
                ],
            },
            'config': {'view': {'stroke': None}, 'axis': {'labelFontSize': 12, 'titleFontSize': 12}, 'legend': {'labelFontSize': 12, 'titleFontSize': 12}},
        }, width='stretch')
        st.caption(f'Ogni barra mostra la percentuale di voti da 1 a 5 ricevuti dal professore, su tutte le sue lezioni. Tocca le barre o apri i conteggi per leggere i dettagli. Sono inclusi i professori con almeno {MIN_VOTES} voti totali.')
        with st.expander('Conteggi dei voti per professore'):
            for teacher in stats:
                st.write(f"**{teacher['name']} · {teacher['subject']}**")
                st.caption(' · '.join(f"{rating}★: {int(teacher[f'rating_{rating}'])}" for rating in range(1, 6)))
    else:
        st.info(f'Il confronto apparirà quando almeno un professore avrà {MIN_VOTES} voti.')

    st.divider()
    st.markdown('#### Medie delle singole lezioni per materia')
    subject = st.selectbox('Seleziona la materia', sorted({r['subject'] for r in teachers}), key='history_subject')
    history = read_cache.subject_history(subject, MIN_VOTES)
    history.sort(key=lambda r: (r['lesson_date'], r['slot'], r['teacher_name']))
    if not history:
        st.info(f'Il grafico comparirà quando almeno una lezione avrà {MIN_VOTES} voti.')
        return
    frame = pd.DataFrame([
        {
            'Ordine': index,
            'Data breve': f"{datetime.strptime(r['lesson_date'], '%Y-%m-%d'):%d/%m/%y} {'M' if db.period_label(r['slot']) == 'Mattina' else 'P'}",
            'Lezione': f"{datetime.strptime(r['lesson_date'], '%Y-%m-%d'):%d/%m/%Y} · {db.period_label(r['slot'])}",
            'Titolo': r['topic'] or 'Lezione',
            'Professore': r['teacher_name'],
            'Media': float(r['average_rating']),
            'Voti': int(r['total_votes']),
            'Tier': tier_for(r['average_rating']),
        }
        for index, r in enumerate(history)
    ])
    total_votes = int(frame['Voti'].sum())
    average = float((frame['Media'] * frame['Voti']).sum() / total_votes)
    with st.container(key='history_metrics'):
        c1, c2, c3 = st.columns(3)
        c1.metric('Media delle lezioni visibili', f'{average:.2f} / 5')
        c2.metric('Lezioni nel grafico', len(frame))
        c3.metric('Voti nelle lezioni visibili', total_votes)

    tooltip = [
        {'field': 'Professore', 'type': 'nominal'},
        {'field': 'Lezione', 'type': 'nominal', 'title': 'Data e fascia'},
        {'field': 'Titolo', 'type': 'nominal', 'title': 'Lezione'},
        {'field': 'Media', 'type': 'quantitative', 'format': '.2f', 'title': 'Media / 5'},
        {'field': 'Voti', 'type': 'quantitative', 'title': 'Voti ricevuti'},
        {'field': 'Tier', 'type': 'nominal'},
    ]
    st.vega_lite_chart(frame, {
        'height': 360,
        'encoding': {
            'x': {
                'field': 'Data breve', 'type': 'ordinal', 'sort': frame['Data breve'].drop_duplicates().tolist(),
                'axis': {'title': None, 'labelAngle': -45, 'labelOverlap': 'greedy', 'labelLimit': 95},
            },
            'y': {
                'field': 'Media', 'type': 'quantitative',
                'scale': {'domain': [1, 5], 'zero': False},
                'axis': {'title': 'Valutazione media', 'values': [1, 2, 3, 4, 5]},
            },
        },
        'layer': [
            {
                'mark': {'type': 'line', 'strokeWidth': 2.5, 'opacity': 0.8},
                'encoding': {
                    'color': {'field': 'Professore', 'type': 'nominal'},
                    'xOffset': {'field': 'Professore', 'type': 'nominal'},
                    'order': {'field': 'Ordine', 'type': 'quantitative'},
                },
            },
            {
                'mark': {'type': 'point', 'filled': True, 'size': 110, 'stroke': '#ffffff', 'strokeWidth': 1.5},
                'encoding': {
                    'color': {
                        'field': 'Professore', 'type': 'nominal',
                        'legend': {'title': 'Professore', 'orient': 'bottom', 'direction': 'vertical', 'labelLimit': {'expr': 'max(80, width - 16)'}},
                    },
                    'xOffset': {'field': 'Professore', 'type': 'nominal'},
                    'tooltip': tooltip,
                },
            },
        ],
        'config': {'view': {'stroke': None}, 'axis': {'gridOpacity': 0.15, 'domain': False, 'tickSize': 0, 'labelFontSize': 12, 'titleFontSize': 12}, 'legend': {'labelFontSize': 12, 'titleFontSize': 12}},
    }, width='stretch')
    st.caption(f'Ogni punto rappresenta una lezione con almeno {MIN_VOTES} voti, in ordine cronologico. M = mattina, P = pomeriggio. Tocca i punti o apri il dettaglio delle lezioni. La media riepilogativa pesa ogni voto allo stesso modo e include solo le lezioni visibili. Per aggiornare i risultati, premi “Aggiorna risultati” nella barra laterale o ricarica la pagina.')
    if len(frame) == 1:
        st.info('Per questa materia è disponibile una sola lezione con il minimo di voti: al momento viene mostrato un solo punto.')
    with st.expander('Dettaglio delle lezioni'):
        st.dataframe(frame.drop(columns=['Ordine', 'Data breve']), hide_index=True, width='stretch', column_config={
            'Media': st.column_config.NumberColumn('Media / 5', format='%.2f'),
        })


with trends_tab:
    if trends_tab.open:
        st.subheader('Andamento nel corso dell’anno')
        show_history(stats)


with admin_tab:
    if admin_tab.open:
        st.subheader('Gestione professori e lezioni')
        admin_pin = db.postgres.setting('ADMIN_PIN')
        if not admin_pin:
            st.warning('Area Gestione disattivata: avvia l’app impostando la variabile d’ambiente ADMIN_PIN (vedi README).')
        else:
            if not st.session_state.get('is_admin', False):
                st.caption('Dopo 5 tentativi errati, i nuovi accessi alla Gestione sono bloccati per 15 minuti, anche ricaricando la pagina.')
                with st.form('admin_login'):
                    entered = st.text_input('PIN amministratore', type='password')
                    login = st.form_submit_button('Accedi')
                if login:
                    success, remaining, locked_seconds = db.admin_login(entered, admin_pin)
                    if success:
                        st.session_state['is_admin'] = True
                        st.rerun()
                    else:
                        if locked_seconds:
                            st.error(f'Accesso bloccato dopo 5 tentativi errati. Riprova tra {(locked_seconds + 59) // 60} minuti.')
                        else:
                            st.error(f'PIN non corretto. Tentativi rimasti: {remaining}.')
            else:
                if st.button('Esci dalla Gestione'):
                    st.session_state['is_admin'] = False
                    st.rerun()
                st.success('Accesso amministratore attivo.')
                st.caption(f'Studenti con codice registrato: {db.student_count()}')
                a, b = st.columns(2)
                with a:
                    st.markdown('#### 1. Aggiungi un professore')
                    with st.form('add_teacher', clear_on_submit=True):
                        name = st.text_input('Nome da mostrare')
                        subject = st.text_input('Materia')
                        add_professor = st.form_submit_button('Aggiungi professore')
                    if add_professor:
                        try:
                            db.add_teacher(name, subject)
                        except ValueError as exc:
                            st.error(str(exc))
                        except db.INTEGRITY_ERRORS:
                            st.warning('Questo professore con questa materia è già presente.')
                        else:
                            read_cache.clear()
                            st.success('Professore aggiunto.')
                            st.rerun()
                with b:
                    st.markdown('#### 2. Pianifica una lezione')
                    options = [row for row in read_cache.list_teachers() if not row['is_closed']]
                    if options:
                        with st.form('add_lesson', clear_on_submit=False):
                            who = st.selectbox(
                                'Professore', options,
                                format_func=lambda row: f"{row['name']} — {row['subject']}"
                            )
                            lesson_date = st.date_input('Data', value=today_italy())
                            period = st.selectbox('Fascia della lezione', ['Mattina', 'Pomeriggio'])
                            slot = 1 if period == 'Mattina' else 5
                            st.caption('Durata fissa: 4 ore.')
                            st.caption('Inserisci una sola lezione anche se dura più ore: ogni studente esprime un solo voto.')
                            topic = st.text_input('Titolo della lezione', max_chars=150)
                            add_class = st.form_submit_button('Aggiungi lezione')
                        if add_class:
                            try:
                                db.add_lesson(who['id'], lesson_date.isoformat(), slot, topic)
                            except ValueError as exc:
                                st.error(str(exc))
                            except db.INTEGRITY_ERRORS:
                                st.warning('Esiste già una lezione per questo professore, data e fascia.')
                            else:
                                read_cache.clear()
                                st.success('Lezione aggiunta.')
                                st.rerun()
                    else:
                        st.info('Nessun corso aperto. Aggiungi un professore o riapri un corso terminato.')
                st.divider()
                st.markdown('#### Stato dei corsi')
                all_courses = read_cache.list_teachers()
                if all_courses:
                    course_lookup = {row['id']: row for row in all_courses}
                    course_id = st.selectbox('Corso da gestire', list(course_lookup), key='manage_course',
                        format_func=lambda ident: f"{course_lookup[ident]['subject']} - {course_lookup[ident]['name']}" + (' - Terminato' if course_lookup[ident]['is_closed'] else ' - In corso'))
                    with st.form(f'course_state_{course_id}'):
                        closed = st.checkbox('Corso terminato', value=bool(course_lookup[course_id]['is_closed']), key=f'course_closed_{course_id}')
                        st.caption('Un corso terminato non accetta nuove lezioni. Le lezioni passate restano votabili; si abilita il completamento delle lezioni mancanti con lo stesso voto. Puoi riaprire il corso senza perdere dati.')
                        save_course = st.form_submit_button('Salva stato del corso')
                    if save_course:
                        try:
                            courses.set_closed(course_id, closed)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            read_cache.clear()
                            st.session_state['course_state_saved'] = True
                            st.rerun()
                    if st.session_state.pop('course_state_saved', False):
                        st.success('Stato del corso aggiornato.')
                st.divider()
                st.markdown('#### Correggi una lezione')
                all_lessons = db.list_lessons()
                if all_lessons:
                    edit_lookup = {row['id']: row for row in all_lessons}
                    edit_id = st.selectbox('Lezione da correggere', list(edit_lookup), format_func=lambda lesson_id: lesson_label(edit_lookup[lesson_id]), key='edit_lesson')
                    with st.form(f'edit_title_{edit_id}'):
                        new_title = st.text_input('Titolo corretto', value=edit_lookup[edit_id]['topic'], max_chars=150, key=f'title_{edit_id}')
                        new_period = st.selectbox('Fascia corretta', ['Mattina', 'Pomeriggio'], index=0 if db.period_label(edit_lookup[edit_id]['slot']) == 'Mattina' else 1, key=f'period_{edit_id}')
                        save_title = st.form_submit_button('Salva modifiche')
                    if save_title:
                        try:
                            db.update_lesson(edit_id, new_title, new_period)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            read_cache.clear()
                            st.session_state['title_saved'] = True
                            st.rerun()
                    if st.session_state.pop('title_saved', False):
                        st.success('Lezione aggiornata. Tutti i voti sono stati conservati.')
                    st.caption('Puoi correggere titolo e fascia Mattina/Pomeriggio. I voti restano associati alla stessa lezione.')
                else:
                    st.caption('Nessuna lezione inserita.')
