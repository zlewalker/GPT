# Corsi terminati e completamento rapido

## Regole

Un corso corrisponde alla coppia professore-materia già registrata. In Gestione si può segnare come terminato oppure riaprirlo. Tutti i corsi esistenti restano inizialmente aperti: non vengono chiusi automaticamente.

Un corso terminato non accetta nuove lezioni. Le lezioni passate restano votabili e correggibili; riaprire un corso non cancella voti o partecipazioni.

Nella scheda Vota, dopo l'accesso, scegliere **Corso terminato**. Il sito mostra il numero di lezioni totali, già votate e mancanti. Lo studente sceglie un voto e conferma esplicitamente che venga applicato a tutte le lezioni mancanti di quel corso.

- Ogni lezione non ancora votata riceve quel voto una sola volta.
- I voti precedenti non vengono modificati.
- I nuovi voti hanno lo stesso peso degli invii singoli: aggiornano la media del professore, la tier list e i grafici delle lezioni. Non esiste una media separata del corso.
- Se non mancano lezioni, il pulsante di invio non è disponibile.
- Se il corso viene riaperto, si aggiungono lezioni e poi si richiude, lo studente può completare solo quelle nuove non votate.
- Se il numero di lezioni mancanti è cambiato rispetto all'anteprima, il salvataggio è annullato: occorre ricaricare e confermare la nuova situazione.

Il salvataggio è atomico e serializzato con gli altri invii. Se una scrittura fallisce, non vengono conservati voti o partecipazioni parziali. Il registro delle partecipazioni è separato dalle valutazioni, che contengono solo identificatore casuale, lezione e voto; nessun codice, token, orario o identificativo comune di invio viene aggiunto.

## Prestazioni

Si mantiene il pool PostgreSQL esistente, il caricamento della sola scheda attiva e il fragment di votazione. I conteggi personali dei corsi sono letti in una singola query soltanto quando si sceglie il completamento del corso: non sono messi nella cache condivisa.

Il completamento usa un'unica transazione e inserimenti multipli, due per blocco fino a 200 lezioni, evitando una connessione o coppia di query per ciascuna lezione. Autorizzazione, stato del corso e partecipazioni sono verificati nuovamente nel database. La cache pubblica dei risultati è invalidata soltanto dopo commit riuscito, come per il voto singolo. Gli elenchi dei corsi in Gestione usano la cache pubblica degli insegnanti già esistente.

## Migrazione e backup

La migrazione additiva `sql/course_reviews.sql` crea solo `course_state` e il controllo che impedisce inserimenti su corsi chiusi. Il runtime conserva i permessi minimi; nessun accesso a PUBLIC/anon/authenticated. Nessuna riga preesistente viene modificata. Su SQLite la nuova tabella è inizializzata automaticamente.

I backup applicativi `migrate.py --export` includono anche `course_state`. I voti completati sono normali righe di votes e participation, già incluse nei backup. Il ripristino accetta anche i vecchi backup, che non contengono stati corso; in quel caso tutti i corsi sono aperti. Le sessioni temporanee continuano a richiedere un nuovo accesso dopo il ripristino su una nuova destinazione.

Backup prima dell'intervento:

- Sorgenti locali: `C:/codex/backups/source_before_course_reviews_20261111_171637.zip`.
- Snapshot riservata del database: `private/before_course_reviews_2026_11_11.json`, con chiavi e dati da non pubblicare.
- Commit precedente: `2e9e31de228dc754ab63ee31eb95359b05d3fc68`.
- Branch GitHub: `rollback/before-course-reviews-2026-11-11`.

## Rollback senza perdere nuovi voti

Ripristinare il codice tramite un nuovo commit/revert oppure distribuire il branch di rollback con gli stessi Secrets. Non ripristinare il vecchio database: cancellerebbe i voti ricevuti dopo il rilascio, inclusi quelli completati in un invio unico.

Conservare la tabella course_state: è additiva e il vecchio codice può ignorarla. Il controllo nel database continua a bloccare le nuove lezioni dei corsi chiusi anche se il vecchio codice non offre la riapertura. Se serve riaprire corsi, farlo dalla nuova Gestione prima del rollback, oppure con intervento amministrativo mirato; non cancellare voti.

La snapshot pre-rilascio serve per un ripristino d'emergenza controllato, non per annullare normalmente gli aggiornamenti del codice.
