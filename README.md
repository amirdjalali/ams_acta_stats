# ams_acta_stats

Genera grafici e un report per le statistiche di AMS Acta.

## Preparazione dei dati

Tutti i record di AMS Acta devono essere esportati in formato JSON e caricati in un database MongoDB locale (client: `admin`, database: `amsacta_documenti`).

Per l'accesso al database, è necessario collegarsi (da rete di ateneo o tramite VPN) alla macchina locale:

```bash
ssh -L 27017:localhost:27017 <utente>@<ip del server>
```

## Esecuzione

Questo progetto utilizza l'ambiente virtuale `uv` per gestire le dipendenze.

* Installare uv: curl -LsSf https://astral.sh/uv/install.sh | sh
* Installare le dipendenze: uv sync
* Avviare il file principale: uv run graph.py

## Output

Lo script genera una dashboard in formato HTML, un file Markdown per il riepilogo dei grafici.

Le query al database vengono salvate nella cartella `queries`, le immagini e le tabelle generate vengono salvate nella cartella `out`.