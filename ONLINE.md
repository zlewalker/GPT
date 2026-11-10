# Project Votes: percorso gratuito per andare online

Stato: piano di pubblicazione. Nessun servizio creato, nessuna pubblicazione e nessuna modifica al database in uso.

## Servizi scelti

- GitHub: repository privato con il solo codice sorgente.
- Streamlit Community Cloud: esecuzione dell'app.
- Supabase Free: database PostgreSQL persistente.

Gli studenti mantengono gli attuali codici di quattro cifre, senza nuovi account applicativi. Un repository privato protegge il sorgente, ma non rende automaticamente privata l'app ospitata: la visibilità dell'app va configurata separatamente. La modalità privata di Streamlit richiede un accesso dei visitatori; per mantenere il solo codice studente si può scegliere un'app raggiungibile tramite link, sapendo che il link non è una protezione di accesso alla classifica.

## Lavoro tecnico ancora da eseguire

1. Conservare SQLite come modalità locale e aggiungere il collegamento PostgreSQL per l'online, senza modificare il database attuale durante lo sviluppo.
2. Adattare connessioni, schema, query, vincoli e transazioni; conservare il limite PIN e la separazione tra partecipazioni e voti.
3. Preparare una migrazione controllata per teachers, lessons, students, participation, votes e settings. Conservare identificativi, assegnazioni e voter_key: rigenerare quest'ultima invaliderebbe la verifica dei codici esistenti.
4. Configurare un accesso server al database con TLS; conservare le credenziali nei Secrets di Streamlit. Nessuna chiave database nel browser degli studenti.
5. Tenere le tabelle applicative fuori dall'accesso pubblico delle API Supabase: scegliere uno schema privato o revocare esplicitamente gli accessi anon/authenticated, verificando la configurazione.
6. Evitare che la versione online importi il CSV degli studenti a ogni avvio; le assegnazioni saranno già nel database migrato. Non pubblicare private/, data/, backup o segreti.
7. Provare su un database separato codici, duplicati, invii simultanei, modifica lezioni e riavvii. Confrontare conteggi e medie con la copia locale.
8. Preparare backup esportabili e una procedura di ripristino.

Il limite ai tentativi dei codici studente è rinviato per scelta dell'utente; il limite del PIN amministratore rimane.

## Passaggio dal servizio locale

La rete locale rimane operativa durante la preparazione. Al passaggio definitivo:

1. Fermare brevemente le votazioni locali.
2. Creare un backup SQLite consistente e migrare l'ultimo stato.
3. Verificare codici, conteggi, medie, relazioni e assenza di collegamenti diretti codice-voto.
4. Abilitare le votazioni online e distribuire il nuovo link.
5. Evitare due database indipendenti attivi: la versione locale va fermata oppure collegata allo stesso database online.

Il rollback successivo al lancio deve considerare gli eventuali nuovi voti online: ripristinare semplicemente il vecchio file locale li perderebbe.

## Primi passi dell'amministratore

Creare o usare gli account GitHub e Supabase, e accedere a Streamlit Community Cloud tramite GitHub. Le integrazioni GitHub e Supabase sono facoltative ma facilitano l'assistenza diretta. Non inviare password in chat.

Non creare ancora tabelle manualmente o caricare il database su GitHub: prima si prepara e verifica il codice PostgreSQL e lo script di migrazione.

## Limiti dei piani gratuiti

Streamlit può mettere in pausa l'app dopo 12 ore senza traffico. Supabase può sospendere un progetto gratuito con poca attività nell'arco di una settimana. Per il piano gratuito Supabase i backup vanno organizzati autonomamente. Non è previsto un dominio personalizzato per partire: si può usare l'indirizzo Streamlit assegnato.

Riferimenti:

- https://docs.streamlit.io/deploy/streamlit-community-cloud
- https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/trust-and-security
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://supabase.com/docs/guides/platform/backups
