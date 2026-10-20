# Run the company API tests

The endpoints from your screenshot are already in `config.json`.
No API key was shown. Leave the optional key entries blank unless IT requires them.

1. Extract the ZIP.
2. Open PowerShell inside `legal_radar_model_tests`.
3. Run:

```powershell
Copy-Item .env.example .env
py -3 benchmark.py --discover
py -3 benchmark.py --suite smoke
```

The checker finds the API base and actual model ID instead of guessing from the route name.
If authentication is required, run `notepad .env` and enter your keys locally.
If `/models` is disabled or lists multiple models, enter the exact IDs supplied by IT.

IT reports that Qwen currently returns thinking output without a final answer.
The smoke test flags this as `reasoning_only`. It does not count it as a correct answer.

Start all tests on Llama:

```powershell
py -3 benchmark.py --models llama8b --suite all
```

After Qwen passes smoke, compare both:

```powershell
py -3 benchmark.py --suite all
```

Open `comparison.html` inside the new timestamped `reports` folder.
Keep the JSON and CSV files for detailed review.
If a check fails, share the terminal diagnostics or report with key values removed.

These company endpoints have not been tested from this environment.
All supplied software checks use a temporary local fake server.
See `README.md` for test interpretation, context limits, settings and troubleshooting.
