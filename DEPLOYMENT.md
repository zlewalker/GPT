# Project Votes: PostgreSQL e pubblicazione

Questa guida aggiorna il piano in ONLINE.md. Il codice supporta SQLite locale e
PostgreSQL online. Lo schema votes_app versione 1 e' applicato al progetto Supabase
Project Votes (hnbocosevtygsyuvpprt, eu-west-1, Lewalker org). Dati reali non trasferiti;
pubblicazione Streamlit non ancora eseguita.

## Configurazione

Python 3.11+, `python -m pip install -r requirements.txt`.
Copiare .streamlit/secrets.toml.example in .streamlit/secrets.toml e impostare
DATABASE_URL, DATABASE_SCHEMA e ADMIN_PIN. In Cloud usare i Secrets di Streamlit.
Non inserire credenziali in chat, nel repository o nella riga di comando.
Le variabili d'ambiente hanno precedenza sui Secrets.

Senza DATABASE_URL viene usato SQLite. Se la connessione online fallisce, l'app non
ripiega su un SQLite vuoto. L'avvio online verifica versione, anno, chiave dei codici
e migrazione completata. L'importazione automatica del CSV avviene solo in locale.

La stringa esatta si trova in Supabase > Connect > Session pooler (porta 5432,
compatibile IPv4). Aggiungere sslmode=require; codificare i caratteri speciali
della password nell'URL. Le chiavi API anon/service_role non sono password PostgreSQL.
Prepared statements disabilitati; search_path limitato alla singola transazione.

Migrazioni e ripristino richiedono una connessione amministratore. Per l'app usare
un login PostgreSQL dedicato, con password casuale, membro del gruppo votes_runtime:
`GRANT votes_runtime TO nome_login`. Non concedere il gruppo ad anon/authenticated.
Il gruppo puo' leggere, inserire professori/lezioni/voti/partecipazioni, correggere
titolo/fascia e aggiornare impostazioni. Non puo' eliminare voti o partecipazioni, inserire studenti
o modificare lo schema. La tabella delle sessioni permette anche DELETE per il logout. RLS attiva; policy riservate al gruppo server.
PUBLIC, anon e authenticated non hanno accesso allo schema o alle tabelle.
L'app comunica dal server Python direttamente con PostgreSQL, senza Data API.

## Trasferimento definitivo

1. `python migrate.py` simula il trasferimento su una snapshot SQLite consistente.
   Verifica integrita', relazioni, anno, chiave e voti/partecipazioni per lezione.
2. Fermare brevemente l'app locale prima del trasferimento definitivo: il database
   attuale sta ricevendo nuovi voti. Non raccoglierli su due database indipendenti.
3. Configurare la connessione amministratore. Applicare sql/schema.sql una sola
   volta alla destinazione vuota; su Project Votes e' gia' applicato. Applicare poi
   sql/student_sessions.sql per abilitare l'accesso persistente.
4. `python migrate.py --apply` crea prima un backup JSON riservato in data/backups/.
   Importa tutto in una transazione, preservando identificativi, digest, chiave HMAC,
   voti e blocco PIN. Rifiuta destinazioni popolate. Confronta tutte le righe prima
   del commit e aggiorna le sequenze degli identificativi.
5. `python migrate.py --verify` ripete il confronto dopo il commit, prima di
   accettare nuovi voti online.
6. Configurare Streamlit con il login runtime. Provare codice, doppioni, classifica,
   grafico, PIN e correzione lezioni, poi distribuire il link.
7. Lasciare ferma la versione locale o collegarla allo stesso database online.

## Backup e ripristino

`python migrate.py --export` esporta una snapshot PostgreSQL con isolamento repeatable
read. Il JSON contiene dati riservati e la chiave dei codici: tenerlo fuori da GitHub.
Per provare il ripristino usare un nuovo database/schema vuoto con versione 1,
poi `python migrate.py --restore data/backups/NOME.json`. Il ripristino e' atomico,
verificato e rifiuta destinazioni popolate. Conservare il backup originale.
Non ripristinare il vecchio SQLite dopo il lancio senza recuperare i nuovi voti online.

## Collaudo

`python -m unittest discover -s tests -v` esegue i test SQLite e migrazione.
Con TEST_DATABASE_URL esegue anche PostgreSQL reale in uno schema temporaneo votes_test_*,
poi lo elimina. Richiede un amministratore con permessi di creazione schema e ruoli.
Non usa ne' svuota votes_app. GitHub Actions prepara un database isolato con TLS.
sql/smoke.sql verifica vincoli e permessi dichiarati con rollback di tutti i dati
di prova; non sostituisce i test del driver Python.

## Streamlit Community Cloud

Collegare zlewalker/GPT, branch main, entrypoint app.py, Python 3.12.
Inserire i Secrets e riavviare. Escludere data/, private/, .venv/ e Secrets.
Il repository privato non rende privata l'app: scegliere la visibilita' separatamente.
Classifica e grafici sono visibili a chiunque raggiunga l'app; il codice serve a votare.
L'accesso studente usa sessioni revocabili di 30 giorni. Applicare sql/student_sessions.sql
prima del rilascio; cinque tentativi errati nel periodo di 15 minuti bloccano i nuovi
accessi globalmente. Dettagli e rollback in STUDENT_SESSIONS.md.

Riferimenti:
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://www.psycopg.org/psycopg3/docs/basic/usage.html
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
