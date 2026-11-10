# Accesso studente persistente

Il codice personale esistente serve per accedere. Il browser conserva un token
casuale di 256 bit, non il codice. La sessione scade dopo 30 giorni, senza rinnovo
automatico. Esci dall'accesso studente revoca subito quella sessione sul server
e rimuove la copia locale. Gli altri dispositivi mantengono le proprie sessioni.

Il token e' conservato nel localStorage della stessa origine e del percorso
dell'app. La persistenza richiede un contesto sicuro (HTTPS o localhost).
Se il browser impedisce il salvataggio, rimane disponibile solo la sessione
della pagina corrente. La navigazione privata puo' cancellare i dati alla chiusura.

Nel database si conserva SHA-256 del token, il digest dello studente e la scadenza.
La scadenza e la revoca sono controllate nuovamente nella stessa transazione del
voto; non basta modificare il browser per autenticarsi. Non vengono aggiunti
identificativi dello studente o della sessione ai voti.

Il token e' una credenziale: non inserirlo in URL, log o screenshot. Il componente
usa solo JavaScript statico del repository; dati utente non vengono inseriti
come HTML o codice. Non aggiungere script non fidati alla stessa origine.

## Limite ai tentativi

Dopo cinque accessi studente errati nel periodo di 15 minuti, i nuovi accessi
sono bloccati fino alla fine del periodo, su tutta l'app. I successi non azzerano
gli errori del periodo. Gli studenti gia' connessi possono continuare a votare.
Il limite e' nel database: ricaricare, cancellare il browser o cambiare indirizzo
non lo azzera. Il limite globale puo' temporaneamente bloccare anche compagni
che conoscono il codice. I codici di quattro cifre restano credenziali deboli.

## Rilascio

SQLite aggiunge automaticamente la tabella student_sessions al primo avvio.
Per PostgreSQL applicare sql/student_sessions.sql come amministratore prima
di rilasciare app.py. La modifica e' additiva; schema_version resta 1, il runtime
ottiene solo SELECT/INSERT/DELETE sulla nuova tabella. RLS e revoca di ogni accesso
a PUBLIC/anon/authenticated proteggono anche questa tabella.

Il file sql/schema.sql resta la base versione 1; su database nuovi applicare
prima quello e poi sql/student_sessions.sql. L'app non esegue DDL PostgreSQL.

Backup/importazione ordinari continuano a trasferire studenti, lezioni,
partecipazioni, voti e impostazioni. Le sessioni sono credenziali temporanee e
non vengono esportate dai backup applicativi: dopo un ripristino su database
nuovo gli studenti accedono nuovamente. I voti non vengono persi.

## Verifica e rollback

I test SQLite e PostgreSQL controllano scadenza, revoca, digest dei token, limite
ai tentativi, vincoli e conservazione dei voti. Un browser Chromium reale verifica
accesso, ricaricamento, nuova scheda, voto, logout e rifiuto del vecchio token.

Versione precedente: c52078d7bd4d3222b5de0f67d5f1628bb6aec529
Branch: rollback/before-student-sessions-2026-11-10

Per annullare il rilascio usare Revert della PR delle sessioni, oppure distribuire
quel branch con gli stessi Secrets. Non ripristinare il database: le tabelle
aggiunte sono ignorate dal vecchio codice e i voti nuovi vanno conservati.
Per invalidare tutte le sessioni, un amministratore puo' eseguire:
DELETE FROM votes_app.student_sessions;
