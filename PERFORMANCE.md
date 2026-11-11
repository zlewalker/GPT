# Caricamento e ripristino

## Aggiornamento dell'11 novembre 2026

Questa sezione aggiorna il comportamento descritto sotto, mantenendo pool,
caricamento della sola scheda attiva, accesso persistente e layout esistenti.

- Cache in memoria del server, condivisa solo per statistiche aggregate, elenco
  professori e medie per materia. Durata massima di riuso: 10 secondi; nessuna
  scrittura su disco o nel localStorage del browser. La scadenza non introduce
  aggiornamenti periodici: la prossima richiesta rilegge il database.
- Il pulsante Aggiorna risultati svuota subito le cache; il voto e le modifiche
  amministrative le svuotano solo dopo il commit riuscito. I risultati aggiornati
  sono visibili al successivo caricamento senza attendere i 10 secondi.
- Autenticazione, revoca, codici, token e lezioni personali non vengono messi in
  cache: autorizzazione e vincolo contro il doppio voto restano verificati dal DB.
- Il modulo Vota e' un fragment: le interazioni con la scelta della lezione
  rieseguono solo quella sezione. Un voto riuscito aggiorna l'intera pagina.
- La cache distingue database e schema e restituisce copie indipendenti dei dati.
  Un altro processo/app puo' servire aggregati precedenti per un massimo di
  10 secondi di riuso; Aggiorna risultati forza la lettura nel processo corrente.

Nel test Vota -> Classifica -> Grafici, le letture delle statistiche scendono da
tre a una. Questo misura richieste evitate, non promette tempi in millisecondi
sull'hosting reale. Non sono state cambiate tabelle, dati o regole dei voti.

### Rollback di questo aggiornamento

Commit precedente: f33fd85bde5a808b9ed8bb521560530e494cfcbf
Branch: rollback/pre-performance-2026-11-11
Branch di lavoro: performance/connections-and-navigation

Per tornare allo stato precedente, usare il tree del branch di rollback in un
nuovo commit di ripristino su main, mantenendo la cronologia; in alternativa
distribuire quel branch con gli stessi Secrets. Non ripristinare il database:
i nuovi voti devono rimanere su Supabase. La copia locale di lavoro aggiornata
e' in C:/codex/project_votes_performance; la cartella originale non e' sovrascritta.

## Ottimizzazioni

- Streamlit 1.55 o superiore: le quattro schede mantengono la stessa interfaccia,
  ma solo la scheda aperta esegue il proprio contenuto. I grafici non vengono
  costruiti all'apertura della scheda Vota.
- Una sola lettura delle statistiche per ogni esecuzione completa, condivisa da
  Top 3, Classifica e Andamento. Nessuna cache condivisa dei risultati: il pulsante
  Aggiorna risultati legge nuovamente il database, senza attendere una scadenza.
- Le medie delle lezioni della materia selezionata vengono recuperate con una
  sola query, mantenendo la soglia di tre voti e il peso uguale di ogni voto.
- PostgreSQL usa un pool per processo, da zero a quattro connessioni. Le connessioni
  in eccesso restano inattive al massimo 60 secondi; la durata massima e' 10 minuti.
  Ogni prestito ha una transazione separata, commit/rollback e impostazioni SET LOCAL.
  Le connessioni sono controllate prima dell'uso. Non si ritentano automaticamente
  le scritture. Prepared statements disabilitati come nella versione precedente.
- DATABASE_POOL_ENABLED=0 disabilita il pool mantenendo le altre ottimizzazioni.
  Riavviare l'app dopo aver modificato i Secrets.
- Il codice studente resta nella sola sessione del browser quando si cambia scheda.
  Nessun aggiornamento periodico e' stato reintrodotto.

Aggiornare requirements.txt e riavviare il processo durante il rilascio.
Il pool e' lato server; non espone credenziali al browser. Non ci sono modifiche
allo schema, alle autorizzazioni o ai dati del database.

## Verifica

GitHub Actions esegue tutti i test SQLite, migrazione, PostgreSQL con TLS e UI
Streamlit usando dati temporanei. I test controllano il mancato caricamento dei
grafici nascosti, una sola lettura delle statistiche, la query unica per materia,
il mantenimento del codice studente, il voto e l'aggiornamento manuale, la gestione,
il riuso delle connessioni e il rollback delle transazioni fallite.

Il tempo effettivo percepito dipende anche da hosting, distanza dal database e
avvio dopo inattivita'. Per confrontare prima/dopo, provare apertura iniziale,
riapertura con server attivo e ingresso in Andamento con la stessa materia.

## Ripristino senza perdere voti

Versione precedente: 478e324e68ee2c8316e788e9072f6565c578292b
Branch di sicurezza: rollback/before-performance-2026-11-10

Per un ripristino temporaneo su Streamlit Community Cloud, impostare il branch
dell'app su rollback/before-performance-2026-11-10, entrypoint app.py, e ridistribuire
mantenendo gli stessi Secrets e DATABASE_URL. Se non e' possibile cambiare il branch
dell'app, usare il revert della pull request di ottimizzazione e ridistribuire main.

Per un ripristino permanente, fare Revert della pull request di ottimizzazione
su GitHub, poi unire la pull request di ripristino in main. Evitare reset forzati:
il revert conserva la cronologia.

Questo ripristina solo il codice. Non ripristinare vecchi backup del database:
i voti ricevuti dopo il rilascio devono restare nel database attuale.
