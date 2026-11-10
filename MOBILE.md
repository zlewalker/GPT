# Uso da telefono

Accesso e voto sono nella parte iniziale della pagina. Le istruzioni complete,
la riservatezza e la Top 3 restano consultabili aprendo i rispettivi riquadri.
Aggiorna risultati ed Esci sono nella pagina, anche con barra laterale chiusa.
La scheda Andamento si chiama ora Grafici.

Il campo del codice resta mascherato e mantiene gli zeri iniziali; inputmode
numeric suggerisce la tastiera numerica su telefono senza convertire il codice
in un numero. I principali controlli hanno un'altezza minima di 44 pixel CSS.

La lezione selezionata ha un riepilogo completo sotto il menu. Su telefono la
classifica usa schede con tutti i valori della tabella desktop, senza doverla
scorrere orizzontalmente. Le etichette dei grafici sono piu' compatte; data completa
e fascia restano nei dettagli. I conteggi delle valutazioni sono leggibili anche
senza passare il mouse sulle barre.

## Verifica

GitHub Actions verifica viewport 320x740, 390x844, 430x932 in tema scuro e
1280x900 desktop con Chromium e dati temporanei. Controlla accesso, voto,
sessione, logout, navigazione, titoli lunghi, dimensione dei controlli e assenza
di overflow orizzontale della pagina e dei grafici. Salva screenshot per sette
giorni nell'artefatto mobile-screenshots.

Queste prove emulano dimensioni e input touch: non sostituiscono un collaudo su
un dispositivo fisico o Safari iOS.

## Rollback

Branch di sicurezza: rollback/before-mobile-polish-2026-11-10
Commit precedente: 3caab1c8c4d2d868e777ade679998d4dbe00e6db

Fare Revert della PR di rifinitura mobile o distribuire quel branch.
La modifica riguarda solo presentazione e test, senza migrazioni del database.
