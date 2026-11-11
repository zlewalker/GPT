# Project Votes — TODO per la pubblicazione

Analisi del 10 novembre 2026. Stack attuale: Python, Streamlit, SQLite. Progetto già in uso nella rete locale della classe; conservare dati reali e codici, backup prima degli aggiornamenti e test su database separati.

## Verificato

- [x] Letti app.py, database.py, script Windows, README e test.
- [x] Superati 22 test automatici su database temporanei, inclusi PIN, soglie tier, durata lezioni e minimo voti.
- [x] Verificata la sintassi Python e gli import di Streamlit, pandas e del fuso Europe/Rome.
- [x] Presenti: inserimento professori/lezioni, voto 1–5, classifica, grafico e gestione con PIN.
- [x] Vincolo database contro il doppio voto dello stesso codice sulla stessa lezione.
- [x] Classifica e grafico con aggiornamento manuale; caricamento delle sole schede aperte.

Verificata con Streamlit AppTest anche la UI: voto valido, doppione e codice errato. Resta la prova manuale da browser e telefono.

## 1. Codici assegnati agli studenti

- [x] Registrati i 27 codici assegnati; importazione riservata e ripetibile senza rigenerarli.
- [x] Generati e verificati 27 codici casuali univoci di quattro cifre; file riservati in private/, esclusa da Git.
- [ ] Preparare l'elenco riservato iniziali → codice, distinguendo iniziali duplicate.
- [x] Rimossa la generazione libera dei codici.
- [x] Accettati soltanto codici autorizzati di quattro cifre, inclusi eventuali zeri iniziali.
- [x] Accesso studente con token persistente di 30 giorni e revoca al logout; cinque errori nel periodo di 15 minuti bloccano globalmente i nuovi accessi.
- [ ] Definire sostituzione/revoca dei codici persi preservando la partecipazione già registrata.

## 2. Separazione tra partecipazione e valutazioni

- [x] Registro participation separato con vincolo univoco codice/lezione.
- [x] Valutazioni senza codice, iniziali o timestamp; identificatori casuali.
- [x] Partecipazione e voto salvati nella stessa transazione; verificato rollback e invio simultaneo.
- [ ] Evitare identificatori condivisi e orari precisi che permettano di riassociare direttamente i due registri; verificare anche i log.
- [x] Migrati i dati precedenti preservando risultati e partecipazioni; backup locale prima della migrazione.

La separazione è implementata. Il backup `.before_anonymous.bak` conserva lo schema precedente e va tenuto riservato: non rappresenta un database anonimizzato. La separazione non garantisce anonimato assoluto contro chi controlla il server o osserva gli aggiornamenti.


## 3. Regole di lezioni, anno e statistiche

- [x] Ogni lezione inserita vale una sola votazione per studente, indipendentemente dalla durata. Ora iniziale e durata sono dati descrittivi.
- [x] Tutti i dati sono assegnati all’anno 2026/2027, salvato nelle impostazioni e mostrato nella UI. La gestione 2027/2028 resta rinviata.
- [x] Ogni voto ha uguale peso, senza moltiplicarlo per la durata della lezione.
- [x] Confermare le soglie S ≥ 4,5; A ≥ 4; B ≥ 3; C ≥ 2; D < 2.
- [x] Media arrotondata a due decimali con mezzi centesimi verso l’alto; il tier usa la stessa media mostrata. Esempio: 4,495 -> 4,50 -> S.
- [x] Voti senza scadenza per tutte le lezioni non ancora valutate dal codice; filtro opzionale per mostrare le già votate.
- [x] Confermata visibilità dopo 3 voti: per professore nella classifica, per lezione nel grafico.
- [x] Aggiornamento manuale con pulsante o ricaricamento, dopo la soglia minima.
- [x] Correzione del titolo della lezione dalla Gestione, senza perdere voti e partecipazioni.
- [x] Menu lezioni con ricerca e scorrimento, ultime inserite per prime.
- [x] Fasce Mattina/Pomeriggio e durata fissa di 4 ore, senza selettore di durata.
- [ ] Valutare in seguito l'annullamento delle lezioni; non incluso nella modifica del titolo.

## 4. Database e accesso online

- [ ] Scegliere hosting e database persistente; adattare database.py al servizio scelto. Le query e le connessioni sono attualmente specifiche per SQLite.
- [ ] Versionare lo schema e preparare una migrazione controllata, con backup e verifica dei dati.
- [ ] Configurare segreti fuori dal repository e backup con prova di ripristino.
- [ ] Proteggere l'accesso all'app della classe e decidere chi può consultare classifica e grafici. Oggi sono visibili a chiunque raggiunga l'app, senza codice.
- [x] Limite PIN: dopo 5 errori consecutivi blocco globale dei nuovi accessi per 15 minuti, persistente nel database; accesso riuscito azzera gli errori.
- [ ] Configurare una credenziale amministratore robusta per la pubblicazione e valutare la scadenza della sessione.
- [ ] Verificare che credenziali e database locali siano esclusi dai file pubblicati.

## 5. Collaudo e lancio

- [ ] Aggiornare README e testi UI alle nuove regole e al nome Project Votes.
- [x] Testati codici autorizzati/non autorizzati, zeri iniziali e duplicati. Revoca ancora da implementare.
- [x] Testati invii simultanei e rollback: nessun voto doppio o partecipazione senza voto.
- [ ] Verificare separazione dei dati, filtri annuali, soglie dei tier e finestre di voto.
- [ ] Provare UI e messaggi di errore nel browser e da telefono.
- [ ] Verificare conservazione dei dati dopo un riavvio sul servizio scelto.
- [ ] Fare una prova con pochi compagni e dati fittizi.
- [ ] Preparare una breve spiegazione di funzionamento, visibilità dei dati e limiti dell'anonimato.
- [ ] Pubblicare, consegnare privatamente i codici e distribuire il link alla classe.

## Prossima attività consigliata

Provare l'app con i codici assegnati; completare la gestione delle sostituzioni dei codici, quindi preparare l'hosting.

Modifica lezioni: in Gestione si possono correggere insieme titolo e fascia Mattina/Pomeriggio, mantenendo voti e partecipazioni. Se la fascia di destinazione contiene una lezione dello stesso professore nella stessa data, la modifica viene rifiutata senza salvare cambiamenti parziali.

- [x] Guida studenti nella schermata Vota: tre passaggi iniziali, regole, lezioni già votate, risultati, riservatezza e assistenza. Verificata con AppTest.


## Aggiornamento corsi

- [x] Chiusura/riapertura professore-materia senza perdita di voti.
- [x] Blocco di nuove lezioni per corsi terminati.
- [x] Completamento atomico delle sole lezioni mancanti con lo stesso voto, conferma esplicita e conservazione dei voti precedenti.
- [x] Nessuna media separata del corso; riuso delle statistiche esistenti e invalidazione della cache dopo il salvataggio.
- [x] Backup sorgenti e snapshot privata prima dell'intervento; branch GitHub di rollback.
