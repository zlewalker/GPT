"""Launch with: python -m streamlit run app.py"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import database as db
from rules import tier_for, rounded_score

MIN_VOTES = 3
ROME = ZoneInfo('Europe/Rome')


def today_italy():
    return datetime.now(ROME).date()


st.set_page_config(page_title='Project Votes', page_icon='🎓', layout='wide')

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

st.title('🎓 Project Votes')
st.caption(f'Anno scolastico {db.SCHOOL_YEAR} - Valuta le lezioni e segui la tier list della classe.')

with st.sidebar:
    st.subheader('ℹ️ Come funziona')
    st.write('Ogni studente può inserire **un voto per lezione usando lo stesso codice personale**.')
    st.write('Tutti i dati appartengono all’anno 2026/2027. Ogni lezione inserita si vota una sola volta, indipendentemente dalla durata.')
    st.info(f'Le medie diventano visibili dopo almeno {MIN_VOTES} voti per professore.')
    st.caption('App della classe. Conserva il tuo codice e non condividerlo. Per assistenza rivolgiti all’amministratore.')

vote_tab, leaderboard_tab, trends_tab, admin_tab = st.tabs(
    ['🗳️ Vota', '🏆 Classifica', '📈 Andamento', '⚙️ Gestione']
)

def lesson_label(row):
    date_label = datetime.strptime(row['lesson_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
    title = row['topic'] or row['subject']
    voted = ' - Già votata' if row.get('has_voted') else ''
    return f"{date_label} - {db.period_label(row['slot'])} - {row['teacher_name']} - {row['subject']} - {title} (#{row['id']}){voted}"


with vote_tab:
    st.subheader('Vota le lezioni')
    st.markdown('Lascia una valutazione delle lezioni a cui hai partecipato e segui la classifica dei professori durante l’anno **2026/2027**.')
    st.markdown('''
1. **Inserisci il codice di 4 cifre** che hai ricevuto privatamente. Scrivi solo i numeri, senza le iniziali. Usa sempre lo stesso codice.
2. **Scegli la lezione** controllando data, Mattina/Pomeriggio, professore e titolo. Le ultime inserite sono in cima: puoi scorrere il menu o scrivere per cercare quelle più vecchie.
3. **Scegli un voto da 1 a 5 e premi “Invia il voto”.** Aspetta il messaggio “Voto salvato!”: selezionare il numero da solo non invia la valutazione.
''')
    st.caption('Il codice serve a registrare soltanto se hai già votato una lezione. Il voto è salvato separatamente, senza codice o iniziali, e nell’app vengono mostrati solo risultati aggregati dopo almeno 3 voti. Questa separazione protegge la tua riservatezza.')
    st.info('Puoi recuperare anche le lezioni passate: non c’è una scadenza. Ogni lezione accetta un solo voto per codice, anche se dura 4 ore. Dopo l’invio il voto non può essere modificato.')
    with st.expander('Lezioni già votate, risultati e domande frequenti'):
        st.markdown('''
**Perché una lezione scompare?** Dopo il voto viene tolta dall’elenco delle lezioni da valutare. Attiva **“Mostra anche le lezioni già votate”** per ritrovarla: sarà indicata come già votata e non potrai inviare un altro voto. Il voto precedente non viene mostrato.

**Cosa significano i numeri?** 1 è la valutazione più bassa, 5 la più alta. Valuta l’esperienza della lezione a cui hai partecipato.

**Dove vedo i risultati?** In **Classifica** trovi la media dei voti di ogni professore e la fascia da S (più alta) a D. La media appare dopo almeno **3 voti per professore**. In **Andamento** scegli un professore per vedere le medie delle singole lezioni: ogni punto richiede almeno **3 voti su quella lezione**. I risultati si aggiornano ogni **15 secondi**; la durata della lezione non dà più peso al voto.

**Il voto è collegato alle mie iniziali?** Il registro della partecipazione tiene traccia delle lezioni già votate dal tuo codice. Le valutazioni sono conservate separatamente, senza codice o iniziali. Questa separazione protegge la riservatezza, ma non garantisce un anonimato assoluto.

**Il codice non funziona o l’ho perso?** Controlla di avere inserito tutte e quattro le cifre del codice ricevuto. Se il problema resta, chiedi all’amministratore: inventare un nuovo codice non permette di votare.

**Non vedo lezioni da votare?** Potresti averle già valutate tutte, oppure non sono ancora state inserite. Controlla l’opzione delle lezioni già votate o segnala la lezione mancante all’amministratore. La scheda **Gestione** è riservata a lui.
''')
    code = st.text_input('Il tuo codice personale (4 cifre)', type='password', max_chars=4, key='voter_code', help='Inserisci soltanto le quattro cifre ricevute, senza le iniziali. Dopo aver scritto, premi Invio o tocca fuori dal campo per caricare le lezioni.')
    include_voted = st.checkbox('Mostra anche le lezioni già votate', value=False)
    if not code:
        st.info('Inserisci il tuo codice per vedere le lezioni ancora da votare.')
    else:
        try:
            available = db.list_lessons(code, include_voted)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if not available:
                st.info('Non ci sono lezioni da votare. Potresti averle già valutate tutte.')
            else:
                lookup = {row['id']: row for row in available}
                selected = st.selectbox('Lezione', options=list(lookup), format_func=lambda lesson_id: lesson_label(lookup[lesson_id]), key='vote_lesson')
                lesson = lookup[selected]
                if lesson['has_voted']:
                    st.info('Hai già votato questa lezione. Il voto non può essere ripetuto.')
                else:
                    with st.form('form_vote'):
                        rating = st.radio('Quanto valuti questa lezione?', [1, 2, 3, 4, 5], index=3, horizontal=True)
                        submitted = st.form_submit_button('Invia il voto', type='primary')
                    if submitted:
                        try:
                            db.add_vote(selected, code, rating)
                        except ValueError as exc:
                            st.error(str(exc))
                        except db.INTEGRITY_ERRORS:
                            st.warning('Con questo codice hai già votato questa lezione.')
                        else:
                            st.session_state['vote_saved'] = True
                            st.rerun()
    if st.session_state.pop('vote_saved', False):
        st.success('Voto salvato! Grazie.')
    st.caption('La partecipazione viene registrata separatamente dalla valutazione.')


@st.fragment(run_every='15s')
def show_leaderboard():
    stats = db.teacher_stats()
    if not stats:
        st.info('Ancora nessun professore. Aggiungine uno dalla scheda Gestione.')
        return

    active = [r for r in stats if r['total_votes'] >= MIN_VOTES]
    pending = [r for r in stats if r['total_votes'] < MIN_VOTES]

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
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    else:
        st.info(f'La classifica apparirà quando almeno un professore avrà {MIN_VOTES} voti.')

    if pending:
        st.caption('Ancora fuori classifica (numero minimo di voti non raggiunto):')
        for r in pending:
            st.write(f"• {r['name']} — {r['subject']}: {r['total_votes']}/{MIN_VOTES} voti")

    st.caption('Tier: S ≥ 4,5 · A ≥ 4,0 · B ≥ 3,0 · C ≥ 2,0 · D < 2,0. Media arrotondata a 2 decimali; a parità di soglia si assegna il tier superiore. Aggiornamento automatico ogni 15 secondi.')


with leaderboard_tab:
    st.subheader('Classifica dei professori')
    show_leaderboard()


@st.fragment(run_every='15s')
def show_history():
    teachers = db.list_teachers()
    if not teachers:
        st.info('Aggiungi prima un professore dalla scheda Gestione.')
        return
    choice = st.selectbox(
        'Seleziona il professore', teachers,
        format_func=lambda row: f"{row['name']} — {row['subject']}",
        key='history_teacher',
    )
    history = db.teacher_history(choice['id'], MIN_VOTES)
    if not history:
        st.info(f'Il grafico comparirà quando almeno una lezione avrà {MIN_VOTES} voti.')
        return
    frame = pd.DataFrame([
        {'Lezione': f"{r['lesson_date'][5:]} - {db.period_label(r['slot'])} - {r['topic'] or 'Lezione'}", 'Media': r['average_rating']}
        for r in history
    ])
    st.line_chart(frame.set_index('Lezione'), y='Media')
    st.caption('Ogni punto è la media di una lezione con almeno 3 voti. Lezioni ordinate cronologicamente.')


with trends_tab:
    st.subheader('Andamento nel corso dell’anno')
    show_history()


with admin_tab:
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
                        st.success('Professore aggiunto.')
                        st.rerun()
            with b:
                st.markdown('#### 2. Pianifica una lezione')
                options = db.list_teachers()
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
                            st.success('Lezione aggiunta.')
                            st.rerun()
                else:
                    st.info('Aggiungi prima un professore.')
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
                        st.session_state['title_saved'] = True
                        st.rerun()
                if st.session_state.pop('title_saved', False):
                    st.success('Lezione aggiornata. Tutti i voti sono stati conservati.')
                st.caption('Puoi correggere titolo e fascia Mattina/Pomeriggio. I voti restano associati alla stessa lezione.')
            else:
                st.caption('Nessuna lezione inserita.')
