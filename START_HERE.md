# Start the revised Legal Radar tests

The company routes are in `config.example.json`.
When upgrading, replace the code, tests and data folders; keep office `.env` and `config.json`.
Neither local settings file is included in this update ZIP.

Open PowerShell in your test repository and run:

```powershell
if (!(Test-Path config.json)) { Copy-Item config.example.json config.json }
if (!(Test-Path .env)) { Copy-Item .env.example .env }
py -3 benchmark.py --models qwen3_30b --suite smoke
```

Then run the revised quality/stability and new workflow/RAG tests:

```powershell
py -3 benchmark.py --models qwen3_30b --suite quality,stability,dummy,rag --repeats 3 --samples 20 --max-output-tokens 4096
```

Open the new `reports/<timestamp>/comparison.html`.
Review strict and allowed-alias scores separately.
Review the dummy workflow/RAG component checks and `human_review.csv`.
A pass on mechanical summary checks does not mean the summary is faithful.

The 4096-token setting is a new recorded experiment, not a confirmed fix.
For a controlled output-cap comparison, repeat the same command with 2048 and 4096.

To test only the new dummy workflow and RAG paths:

```powershell
py -3 benchmark.py --models qwen3_30b --suite dummy,rag --repeats 3 --max-output-tokens 4096
```

All new rules and archive passages are fictional. No real tasks or notifications are created.
The RAG index is a tiny local lexical baseline, separate from production Legal Radar retrieval.
Keys remain local. No company endpoint was contacted while building this update.
See `README.md` for complete configuration, limitations, scoring and interpretation.
