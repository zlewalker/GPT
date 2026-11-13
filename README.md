# Project Votes

Web app Python + Streamlit per valutare le lezioni della classe ITS nell'anno **2026/2027**. Il progetto è già utilizzato online; supporta anche SQLite per lo sviluppo locale.

- **App:** https://projecyvotes.streamlit.app/
- **Codice:** https://github.com/zlewalker/GPT — branch `main`, entrypoint `app.py`.
- **Ambiente locale corrente:** `C:/codex/project_votes_performance`.
- **Database operativo:** PostgreSQL su Supabase, schema privato `votes_app`.

Questo README riunisce le precedenti guide su pubblicazione, sessioni, mobile, prestazioni, corsi e TODO. Le vecchie copie del progetto non devono essere usate per sovrascrivere il database online.

## Indice

- [Uso studenti](#uso-studenti)
- [Regole e risultati](#regole-e-risultati)
- [Gestione amministratore](#gestione-amministratore)
- [Corsi terminati](#corsi-terminati)
- [Accesso e riservatezza](#accesso-e-riservatezza)
- [Avvio locale](#avvio-locale)
- [Configurazione online](#configurazione-online)
- [Database e migrazioni](#database-e-migrazioni)
- [Trasferimento iniziale](#trasferimento-iniziale)
- [Backup e ripristino](#backup-e-ripristino)
- [Prestazioni](#prestazioni)
- [Uso da telefono](#uso-da-telefono)
- [Test e verifiche](#test-e-verifiche)
- [Rollback](#rollback)
- [Struttura del progetto](#struttura-del-progetto)
- [Attivita aperte](#attivita-aperte)

## Uso studenti

1. Apri l'app e accedi con il codice personale di **quattro cifre** ricevuto privatamente. Inserisci soltanto i numeri, senza le iniziali; conserva eventuali zeri iniziali.
2. In **Vota**, scegli **Singole lezioni** e controlla data, Mattina/Pomeriggio, professore, materia e titolo. Le ultime lezioni inserite sono in cima; il menu permette di cercare e scorrere quelle precedenti.
3. Seleziona un voto da 1 a 5, premi **Invia il voto** e attendi la conferma. Scegliere soltanto il numero non salva la valutazione.

Le lezioni già votate sono nascoste per impostazione iniziale: puoi mostrarle con l'apposita casella. Non puoi inviare un secondo voto né modificare quello precedente. Il voto precedente non viene mostrato.

Il browser può ricordare l'accesso per 30 giorni. Sui dispositivi condivisi premi **Esci**. Se il codice non funziona, è stato perso oppure manca una lezione, contatta l'amministratore: non puoi creare un nuovo codice autonomamente.

## Regole e risultati

- Un voto per studente e lezione, **senza scadenza**.
- Ogni lezione appartiene alla coppia professore-materia e alla fascia **Mattina** o **Pomeriggio**; la durata descrittiva è fissa a **4 ore**.
- Ogni voto ha uguale peso. La durata non moltiplica la valutazione.
- La **Classifica** mostra la media dopo almeno **3 voti per professore**. La Top 3 usa la stessa soglia.
- Nei **Grafici** si confrontano le distribuzioni dei voti dei professori; il grafico per materia mostra punti collegati delle medie di ogni lezione, con almeno **3 voti per lezione**.
- La media riepilogativa del grafico per materia considera i voti delle sole lezioni visibili; la classifica considera tutti i voti del professore.
- Per vedere nuovi risultati premi **Aggiorna risultati** nella pagina o ricaricala. Non esiste più un aggiornamento periodico ogni 15 secondi.

La media viene arrotondata a due decimali con i mezzi centesimi verso l'alto prima di assegnare il tier: `4,495 → 4,50 → S`.

| Tier | Media arrotondata |
| --- | --- |
| S | Da 4,50 |
| A | Da 4,00 a meno di 4,50 |
| B | Da 3,00 a meno di 4,00 |
| C | Da 2,00 a meno di 3,00 |
| D | Sotto 2,00 |

Tutti i dati appartengono al **2026/2027**. La gestione di altri anni scolastici resta da progettare.

## Gestione amministratore

La scheda **Gestione** richiede il PIN configurato sul server. Permette di aggiungere professori e materie, pianificare lezioni, correggere titolo e fascia e gestire lo stato dei corsi.

- Pianifica una sola voce per lezione, scegliendo data e fascia. La durata è fissa: non è disponibile un selettore.
- La modifica di titolo o fascia mantiene identificativo, voti e partecipazioni. Non cambia l'ordine di inserimento del menu.
- Uno spostamento di fascia viene rifiutato se esiste già una lezione dello stesso professore nella stessa data e fascia. Non vengono salvate modifiche parziali.
- I vecchi slot orari sono conservati: 1–4 si mostrano come Mattina, 5–12 come Pomeriggio. Le nuove lezioni usano internamente 1 e 5. Le lezioni precedenti non vengono unite automaticamente.
- Dopo **5 PIN errati consecutivi**, i nuovi accessi alla Gestione sono bloccati globalmente per **15 minuti**, anche dopo un riavvio. Un accesso riuscito azzera il contatore. Le sessioni amministratore già aperte restano attive.

La modifica del professore associato e l'eliminazione delle lezioni non sono operazioni disponibili nella normale interfaccia. Gli interventi manuali sui dati richiedono backup e verifica mirata.

## Corsi terminati

Un corso corrisponde a una **coppia professore-materia**. In Gestione puoi segnarlo come terminato o riaprirlo. Nessun corso viene chiuso automaticamente.

Un corso terminato non accetta nuove lezioni; quelle esistenti restano votabili e correggibili. La riapertura non cancella dati.

Per recuperare rapidamente i voti, lo studente sceglie **Vota → Corso terminato**:

1. Seleziona il corso; l'app mostra lezioni totali, già votate e mancanti.
2. Sceglie un voto e conferma esplicitamente che venga applicato a tutte le lezioni mancanti.
3. L'app registra quel voto **una sola volta su ciascuna lezione non ancora votata**, lasciando identici tutti i voti precedenti.

Non esiste una media separata del corso: i voti completati aggiornano normalmente media, tier list e grafici. Quando tutte le lezioni sono votate, non è possibile inviare altro. Se il corso viene riaperto, ampliato e richiuso, si possono recuperare solo le nuove lezioni ancora non votate.

Il numero di lezioni viene ricontrollato al salvataggio: se l'anteprima è cambiata, occorre ricaricare e confermare di nuovo. Il salvataggio è atomico: un errore annulla l'intero invio, senza voti o partecipazioni parziali.

## Accesso e riservatezza

I 27 codici assegnati sono registrati nel database come digest HMAC. L'elenco riservato iniziali–codice e i messaggi individuali, se presenti localmente, appartengono a `private/` e non devono essere pubblicati. Il CSV ha colonne `Iniziali;Codice`.

Dopo l'accesso, il browser conserva un **token casuale di 256 bit**, non il codice. La sessione dura 30 giorni senza rinnovo automatico. Il token è salvato nel `localStorage` della stessa origine e percorso dell'app, su HTTPS o localhost. Se il browser blocca la memoria, resta disponibile solo la sessione della pagina; la navigazione privata può cancellarla alla chiusura.

Il server conserva soltanto hash SHA-256 del token, digest dello studente e scadenza. **Esci** revoca subito quella sessione e rimuove la copia locale; gli altri dispositivi mantengono i propri accessi. Scadenza e revoca sono ricontrollate nella transazione del voto.

Dopo **5 accessi studente errati nel periodo di 15 minuti**, i nuovi accessi sono bloccati fino alla fine del periodo, su tutta l'app. I successi non azzerano gli errori; gli studenti già connessi continuano a votare. Il limite è persistente e non si azzera cambiando browser o indirizzo. Può quindi bloccare temporaneamente anche compagni con codice corretto.

La separazione dei dati funziona così:

| Tabella | Contenuto |
| --- | --- |
| `students` | Iniziali e digest del codice |
| `student_sessions` | Hash del token, digest dello studente e scadenza |
| `participation` | Lezione e digest dello studente: indica soltanto se ha votato |
| `votes` | Identificativo casuale, lezione e voto; nessun codice, studente, sessione o orario |
| `course_state` | Corso e stato aperto/terminato |

Partecipazione e valutazione sono registrate nella stessa transazione, ma non condividono un identificativo del voto. Anche il completamento rapido usa identificativi casuali indipendenti, senza aggiungere un identificativo comune di invio. La separazione elimina il collegamento diretto nel database attivo; l'osservazione del server o delle variazioni dei risultati può comunque consentire deduzioni.

Token, codici, password e chiavi non vanno inseriti in URL, log, screenshot o repository. Il componente del browser usa JavaScript statico del progetto: non aggiungere script non fidati alla stessa origine.

## Avvio locale

Usare Python **3.11 o successivo**; per il deployment Streamlit è configurato Python **3.12**.

Dalla cartella corrente del progetto, in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Configura prima il PIN tramite variabile d'ambiente o file `.streamlit/secrets.toml`. Il modello è [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example). Non pubblicare il file compilato.

È disponibile anche `avvia_windows.bat`: crea l'ambiente, installa le librerie quando mancano Streamlit/pandas e chiede il PIN. Dopo aggiornamenti delle dipendenze, eseguire comunque l'installazione da `requirements.txt`: il controllo del launcher non verifica ogni versione o driver.

Il browser usa http://localhost:8501. Per fermare il server premi **Ctrl+C** nel terminale.

- Con `DATABASE_URL` configurata si usa PostgreSQL.
- Senza `DATABASE_URL` si usa SQLite in `data/tierlist.sqlite3`, oppure nel percorso `ITS_TIER_DB`.
- Per forzare SQLite quando esistono Secrets online, impostare una variabile d'ambiente `DATABASE_URL` vuota: le variabili d'ambiente hanno precedenza.
- L'importazione automatica del CSV dei codici avviene **solo su SQLite**, se il file `private/codici_studenti_2026_2027.csv` è presente. Un database nuovo senza assegnazioni non accetta votanti.
- Se PostgreSQL non è raggiungibile, l'app non ripiega su un database locale vuoto.

Usare dati temporanei per lo sviluppo. Non raccogliere voti contemporaneamente su due database indipendenti: la versione locale deve rimanere ferma oppure collegarsi allo stesso database operativo.

## Configurazione online

L'app usa **Streamlit Community Cloud + Supabase**. Gli studenti non devono creare account sui due servizi. Il repository contiene il sorgente; codici, database, backup e Secrets sono esclusi dai file pubblicati.

In Streamlit: repository `zlewalker/GPT`, branch `main`, entrypoint `app.py`, Python 3.12. Impostare nei **Secrets**:

| Impostazione | Funzione |
| --- | --- |
| `DATABASE_URL` | Stringa di connessione PostgreSQL con TLS |
| `DATABASE_SCHEMA` | `votes_app` |
| `ADMIN_PIN` | Credenziale amministratore robusta |
| `DATABASE_POOL_ENABLED` | Facoltativa; `0` disabilita il pool, mantenendo le altre ottimizzazioni |

Le variabili d'ambiente prevalgono sui Secrets. Riavviare dopo modifiche alla configurazione o alle dipendenze.

Usare la stringa esatta **Supabase → Connect → Session pooler**, porta 5432, compatibile IPv4. Richiedere `sslmode=require` e codificare i caratteri speciali della password nell'URL. Le chiavi API anon/service_role non sono password PostgreSQL.

Per il runtime usare un login PostgreSQL dedicato, membro del gruppo `votes_runtime`. Migrazioni e ripristino richiedono invece una connessione amministratore. Il runtime può gestire le normali operazioni dell'app e chiudere/riaprire i corsi; non può eliminare voti o partecipazioni, inserire studenti o alterare lo schema. È consentita la cancellazione delle sessioni per logout e pulizia delle scadute.

RLS e permessi proteggono lo schema privato: `PUBLIC`, `anon` e `authenticated` non accedono alle tabelle. Il server Python comunica direttamente con PostgreSQL, senza esporre credenziali al browser o usare la Data API per queste tabelle.

La visibilità dell'app è distinta da quella del repository. Classifica e grafici sono consultabili da chi raggiunge l'app; il codice serve a votare. Per limitare anche la consultazione va configurato separatamente l'accesso all'app. I piani gratuiti possono avere sospensioni per inattività e limiti di risorse; prevedere backup propri.

## Database e migrazioni

Oltre alle tabelle di accesso e voto, `teachers` contiene le coppie professore-materia, `lessons` le lezioni e `settings` le impostazioni, compresa la chiave dei codici.

Su una **nuova destinazione PostgreSQL**, applicare come amministratore, nell'ordine:

1. [sql/schema.sql](sql/schema.sql): schema base e ruolo runtime.
2. [sql/student_sessions.sql](sql/student_sessions.sql): accesso persistente e relativi permessi.
3. [sql/course_reviews.sql](sql/course_reviews.sql): stato corsi e controllo contro nuove lezioni nei corsi chiusi.

La terza migrazione è additiva: non modifica voti o lezioni. Lo schema base resta versione 1. L'app non esegue DDL PostgreSQL all'avvio. Non rieseguire lo schema base su una destinazione già operativa; le migrazioni necessarie sono già applicate al progetto corrente.

SQLite aggiunge automaticamente le tabelle locali al primo avvio. Per un vecchio database che collegava direttamente codice e voto, crea prima una copia `.before_anonymous.bak` e migra le valutazioni mantenendo i risultati. Quella copia conserva i vecchi collegamenti: tenerla riservata.

## Trasferimento iniziale

Questa procedura serve solo per creare una nuova destinazione o un ambiente di ripristino, non per sovrascrivere il servizio già operativo.

1. Applicare tutte le migrazioni a una destinazione vuota e configurare la connessione amministratore.
2. Eseguire `python migrate.py` per simulare il trasferimento di una snapshot SQLite consistente. Si verificano integrità, relazioni, anno, durata, chiave dei codici e corrispondenza tra voti e partecipazioni.
3. Fermare brevemente le votazioni locali prima del passaggio definitivo e acquisire l'ultimo stato.
4. Eseguire `python migrate.py --apply`: crea un backup riservato, importa tutto in una transazione, confronta le righe e aggiorna le sequenze degli identificativi. Rifiuta destinazioni popolate.
5. Eseguire `python migrate.py --verify` **prima** di accettare nuovi voti online.
6. Configurare il login runtime, provare l'app e distribuire un unico link operativo.

Si preservano identificativi, digest e chiave HMAC: rigenerare la chiave invaliderebbe la verifica degli attuali codici. Il confronto integrale con il vecchio SQLite non è più atteso dopo che il database online ha ricevuto nuovi voti.

## Backup e ripristino

Prima di modifiche a dati o schema creare un backup consistente e conservare una versione del codice da ripristinare. Database e backup appartengono a `data/` o `private/`, mai al repository.

Con la connessione PostgreSQL amministratore configurata:

```powershell
python migrate.py --export
```

Esporta una snapshot con isolamento `repeatable read` in `data/backups/`. Il JSON contiene dati riservati e la chiave dei codici. Sono inclusi professori, lezioni, studenti, partecipazioni, voti, impostazioni e stato dei corsi. Le sessioni temporanee non vengono esportate: dopo un ripristino su una nuova destinazione gli studenti devono accedere di nuovo, senza perdere i voti.

Per provare il ripristino, preparare una nuova destinazione vuota con tutte le migrazioni e usare:

```powershell
python migrate.py --restore data/backups/NOME.json
```

Il ripristino è atomico, verificato e rifiuta destinazioni popolate. I vecchi backup senza `course_state` restano accettati: i corsi risultano aperti. Conservare l'originale. Per SQLite, copiare la cartella `data/` a programma chiuso o usare l'API di backup SQLite; non copiare soltanto il file principale mentre riceve scritture in WAL.

La snapshot riservata pre-corsi è `private/pre_course_migration_2026_11_11.json`; la copia precedente `private/before_course_reviews_2026_11_11.json` e il manifest di rilascio sono anch'essi riservati. Queste snapshot acquisite tramite gli strumenti di gestione hanno un formato operativo distinto dai JSON `format: 1` di `migrate.py`: non passarle direttamente a `--restore` senza conversione verificata.

## Prestazioni

- Si carica solo la scheda aperta; i grafici non sono costruiti all'apertura di Vota.
- Il modulo Vota usa un fragment; le interazioni locali non rieseguono tutto il sito. Un voto riuscito aggiorna l'intera pagina.
- Le statistiche pubbliche, l'elenco professori e lo storico per materia usano cache in memoria del server per **10 secondi**, separata per database/schema. Nessun dato viene scritto su disco dalla cache.
- Aggiorna risultati invalida subito la cache; voti e modifiche amministrative la invalidano dopo il commit riuscito. Altri processi possono servire aggregati precedenti fino alla scadenza della propria cache.
- Autenticazione, revoca, token, codici, lezioni personali e conteggi dei corsi da completare non entrano nella cache condivisa.
- Le statistiche sono condivise tra Top 3, Classifica e Grafici. Lo storico della materia usa una sola query, non una per professore.
- PostgreSQL mantiene un pool per processo da 0 a 4 connessioni, con inattività massima di 60 secondi e vita massima di 10 minuti. Ogni utilizzo ha commit/rollback e impostazioni `SET LOCAL`; le connessioni sono controllate prima dell'uso.
- Prepared statements disabilitati; `search_path`, timeout e lock sono circoscritti alle transazioni. Le scritture non vengono ritentate automaticamente dopo errori di rete.
- Il completamento di un corso usa una transazione e due inserimenti multipli per blocco fino a 200 lezioni. Il test con 30 lezioni verifica sei comandi database, evitando due inserimenti separati per ogni lezione.

I test misurano query evitate e correttezza; non promettono un numero fisso di millisecondi sull'hosting reale. Tempi percepiti dipendono anche dalla rete e dall'avvio dopo inattività.

## Uso da telefono

Accesso e voto sono all'inizio della pagina; istruzioni e Top 3 restano nei riquadri espandibili. Aggiorna risultati ed Esci funzionano anche con la barra laterale chiusa.

Il campo del codice è mascherato e suggerisce la tastiera numerica senza convertirlo in numero. I principali controlli hanno almeno 44 pixel CSS di altezza. La lezione selezionata mostra un riepilogo completo; la classifica usa schede sul telefono e una tabella su desktop. Grafici con etichette compatte, dettagli delle lezioni e conteggi leggibili senza passare il mouse sulle barre.

## Test e verifiche

Dalla cartella del progetto, con le dipendenze installate:

```powershell
python -m unittest discover -s tests -v
```

I test usano database temporanei per voti, duplicati, sessioni, privacy, chiusura corsi, completamento atomico, cache, migrazione e ripristino. Senza `TEST_DATABASE_URL`, i test PostgreSQL vengono saltati. Con quella variabile usano uno schema temporaneo `votes_test_*` e un ruolo dedicato, poi li eliminano: richiedono permessi amministratore e non svuotano `votes_app`.

Il [workflow GitHub Actions](.github/workflows/tests.yml) prepara PostgreSQL isolato con TLS ed esegue anche AppTest. La suite funzionale del rilascio corsi è passata; per lo stato completo e corrente di ogni esecuzione consultare Actions. L'esito dei soli test funzionali non implica che le prove Chromium e mobile siano completate: verificarne separatamente lo stato nel workflow.

Con Playwright e Chromium installati sono disponibili:

```powershell
python tests/browser_sessions.py
python tests/browser_mobile.py
```

Verificano persistenza, nuova scheda, voto, logout, rifiuto di token revocati, limite ai tentativi e layout a 320×740, 390×844, 430×932 e 1280×900. Il workflow conserva screenshot temporanei nell'artefatto `mobile-screenshots`. L'emulazione touch non sostituisce un collaudo su telefoni fisici o Safari iOS.

[sql/smoke.sql](sql/smoke.sql) verifica i vincoli di base con rollback dei dati di prova; non sostituisce test del driver o delle migrazioni successive.

## Rollback

**Ripristinare normalmente soltanto il codice, conservando il database attuale.** Ricaricare un vecchio database cancellerebbe i voti ricevuti nel frattempo, compresi quelli completati in un invio unico.

Usare un nuovo commit di revert/ripristino oppure distribuire il branch di sicurezza con gli stessi Secrets. Evitare reset forzati della cronologia. Questi riferimenti identificano versioni precedenti alle rispettive modifiche, non versioni da sommare tra loro:

| Intervento da annullare | Branch di sicurezza | Commit precedente |
| --- | --- | --- |
| Ottimizzazioni iniziali | `rollback/before-performance-2026-11-10` | `478e324e68ee2c8316e788e9072f6565c578292b` |
| Sessioni persistenti | `rollback/before-student-sessions-2026-11-10` | `c52078d7bd4d3222b5de0f67d5f1628bb6aec529` |
| Rifinitura mobile | `rollback/before-mobile-polish-2026-11-10` | `3caab1c8c4d2d868e777ade679998d4dbe00e6db` |
| Cache e navigazione dell'11 novembre | `rollback/pre-performance-2026-11-11` | `f33fd85bde5a808b9ed8bb521560530e494cfcbf` |
| Corsi terminati e completamento rapido | `rollback/before-course-reviews-2026-11-11` | `2e9e31de228dc754ab63ee31eb95359b05d3fc68` |
| Unificazione documentazione | `rollback/before-readme-consolidation-2026-11-11` | `f91f327601b5eeb99eb2436c1c2fdc08b2ff59c1` |

Le tabelle additive delle sessioni e dei corsi possono restare durante un rollback. Il controllo del database continua a bloccare nuove lezioni dei corsi chiusi anche quando il vecchio codice non permette di riaprirli: riaprirli prima dalla nuova Gestione, se necessario, oppure con un intervento amministrativo mirato.

Per invalidare tutte le sessioni, un amministratore può eliminare le righe di `votes_app.student_sessions`; questo disconnette gli studenti ma non cancella voti. Non è una normale operazione del runtime dell'interfaccia.

Backup locali di riferimento, esterni al repository:

- `C:/codex/backups/source_before_course_reviews_20261111_171637.zip`: sorgenti prima dei corsi.
- `C:/codex/backups/documentation_before_readme_20261111_174005.zip`: gli otto documenti prima del consolidamento.

## Struttura del progetto

| File o cartella | Ruolo |
| --- | --- |
| `app.py` | Interfaccia e navigazione Streamlit |
| `database.py` | Operazioni, query e modalità SQLite/PostgreSQL |
| `postgres.py` | Configurazione, connessioni, pool e transazioni PostgreSQL |
| `voter_auth.py`, `browser_session.py`, `session_storage.js` | Accesso studente e persistenza sul browser |
| `courses.py` | Stato corsi e completamento delle lezioni mancanti |
| `read_cache.py` | Cache dei soli dati pubblici |
| `mobile_ui.py`, `mobile.css` | Presentazione e controlli mobile |
| `rules.py` | Arrotondamento e assegnazione tier |
| `migrate.py`, `sql/` | Trasferimento, backup, ripristino e migrazioni SQL |
| `tests/`, `.github/workflows/` | Verifiche automatiche e browser |
| `requirements.txt`, `avvia_windows.bat` | Dipendenze e avvio Windows |
| `data/`, `private/` | Dati e file riservati, esclusi da Git |

## Attivita aperte

- [ ] Sostituzione/revoca dei codici persi mantenendo tutte le partecipazioni già registrate.
- [ ] Automatizzare i backup periodici e documentare una prova di ripristino operativa.
- [ ] Valutare una scadenza esplicita della sessione amministratore.
- [ ] Completare le prove manuali su telefoni reali e verificare i risultati dei workflow browser.
- [ ] Definire l'annullamento delle lezioni nell'interfaccia, con trattamento esplicito dei voti esistenti.
- [ ] Progettare il passaggio al 2027/2028 quando necessario.

Sono già implementati hosting online, migrazione PostgreSQL, codici assegnati, separazione dei voti, sessioni, limiti ai tentativi, correzione lezioni, grafici, mobile, cache, chiusura corsi e completamento rapido. Non vanno trattati come attività ancora da iniziare.

Riferimenti ufficiali per eventuali aggiornamenti della piattaforma:

- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Secrets Streamlit](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Connessione PostgreSQL Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Backup Supabase](https://supabase.com/docs/guides/platform/backups)
- [Transazioni Psycopg](https://www.psycopg.org/psycopg3/docs/basic/usage.html)
