# Project Votes - ITS Teacher Tier List

App Python + Streamlit con SQLite locale o PostgreSQL/Supabase online, per l'anno scolastico 2026/2027.

Per configurazione online, migrazione verificata, backup e ripristino vedere [DEPLOYMENT.md](DEPLOYMENT.md), che aggiorna il piano precedente in ONLINE.md.

## Avvio Windows

Avvia `avvia_windows.bat` e inserisci il PIN amministratore. Il browser si apre su http://localhost:8501. In alternativa, dall'ambiente virtuale: `python -m streamlit run app.py`, impostando prima la variabile ADMIN_PIN.

## Codici della classe

I 27 codici già generati sono registrati nel database locale. Usa il codice di quattro cifre ricevuto privatamente; nomi, iniziali e codici inventati non sono accettati. Non viene più offerta la generazione libera.

L'elenco riservato è `private/codici_studenti_2026_2027.csv`, con colonne Iniziali;Codice. I messaggi individuali sono nella stessa cartella. `private/` è esclusa da Git.

All'avvio, se il CSV è presente, l'app importa le assegnazioni senza duplicarle o sostituirle. Se il CSV manca, restano validi gli studenti già registrati nel database. Un database nuovo senza CSV non accetta votanti: nella Gestione è visibile il numero degli studenti registrati. Per l'hosting servirà trasferire in modo riservato le assegnazioni; non caricare il CSV in un repository pubblico.

## Regole

- Una sola valutazione da 1 a 5 per codice e lezione, senza scadenza. Dopo l’accesso si vedono prima soltanto le lezioni ancora da votare; una casella permette di vedere anche quelle già valutate.
- Ogni lezione va inserita una sola volta, scegliendo Mattina o Pomeriggio. La durata è fissa a 4 ore e non moltiplica il peso del voto.
- Tutti i dati appartengono al 2026/2027; la gestione degli anni successivi è rinviata.
- Media di tutti i voti con uguale peso; arrotondamento a due decimali con mezzi centesimi verso l'alto prima di assegnare il tier.
- S da 4,50; A da 4,00; B da 3,00; C da 2,00; D sotto 2,00.
- Classifica dopo 3 voti per professore; grafico dopo 3 voti per lezione. Nessun aggiornamento automatico: per vedere i nuovi dati, usare “Aggiorna risultati” nella barra laterale o ricaricare la pagina.
- Dopo 5 PIN errati consecutivi, nuovi accessi amministratore bloccati globalmente per 15 minuti. Un accesso riuscito azzera gli errori.

## Separazione dei dati

`students` conserva iniziali e digest HMAC del codice; `participation` registra soltanto digest e lezione. `votes` contiene identificatore casuale, lezione e valutazione, senza studente, codice o orario. Partecipazione e voto sono registrati nella stessa transazione, protetta da un vincolo contro i duplicati.

Questo elimina il collegamento diretto nel database attivo, ma non garantisce anonimato assoluto: chi controlla il server o osserva le variazioni delle medie può ricavare informazioni.

## Migrazione e backup

Alla prima apertura con un vecchio database, l'app crea una copia `.before_anonymous.bak` accanto al database, separa partecipazione e voti e conserva i risultati. Questa copia contiene ancora i vecchi collegamenti e va mantenuta riservata. Non viene eliminata automaticamente. Lezioni già inserite separatamente non vengono unite.

Il database locale è in `data/`, esclusa da Git. Eseguire i backup ordinari a programma chiuso. Hosting e database persistente online restano da configurare.

## Test

Eseguire `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Lavoro residuo

Vedi TODO.md. In particolare: sostituzione dei codici persi, gestione correzioni delle lezioni, hosting e prove manuali da telefono.


## Menu lezioni e correzioni

Il menu elenca tutte le lezioni, dalla più recentemente inserita (non dalla data di svolgimento). Il menu a tendina permette di scorrere e cercare digitando; ogni voce mostra data, fascia, professore, titolo e numero della lezione. Quelle già votate sono indicate e non possono essere votate di nuovo.

In Gestione, usa "Correggi il titolo di una lezione": il titolo viene aggiornato senza cambiare identificativo, professore, voti o partecipazioni. L'ordine del menu non cambia quando si corregge un titolo.

Le vecchie lezioni mantengono identificativi e slot originali: slot 1-4 mostrati come Mattina, slot 5-12 come Pomeriggio. Non vengono unite lezioni preesistenti. La durata descrittiva viene uniformata a 4 ore. Per nuove lezioni, Mattina usa internamente slot 1 e Pomeriggio slot 5.

Il progetto è già in uso nella rete locale della classe. Le prove automatiche usano database temporanei. Prima dell'aggiornamento è stato creato un backup SQLite consistente in data/backups/.

Modifica lezioni: in Gestione si possono correggere insieme titolo e fascia Mattina/Pomeriggio, mantenendo voti e partecipazioni. Se la fascia di destinazione contiene una lezione dello stesso professore nella stessa data, la modifica viene rifiutata senza salvare cambiamenti parziali.

## Prestazioni e rollback

Le schede caricano i contenuti solo quando aperte. Statistiche condivise nella singola esecuzione, query unica per materia e pool PostgreSQL riducono il lavoro ripetuto. Per dettagli, verifiche e ripristino della versione precedente vedere [PERFORMANCE.md](PERFORMANCE.md).

## Accesso studente

Accesso con il codice personale esistente e sessione di 30 giorni sul browser, con pulsante “Esci dall’accesso studente”. Dopo cinque accessi errati nel periodo di 15 minuti i nuovi accessi sono temporaneamente bloccati globalmente. Voti e partecipazioni restano separati. Prima del rilascio PostgreSQL applicare [sql/student_sessions.sql](sql/student_sessions.sql). Dettagli, limiti e rollback in [STUDENT_SESSIONS.md](STUDENT_SESSIONS.md).
