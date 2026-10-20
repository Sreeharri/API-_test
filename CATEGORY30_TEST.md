# Thirty-category classification and summary test

This add-on tests whether your deployed Qwen endpoint can select from **30 supplied category definitions** and summarize the same sentence. It does not change the existing benchmark, config or credentials.

The catalog is a provisional example of 30 Legal Radar legal domains. It is not a claimed copy of Max Bögl's department list. Category definitions explicitly distinguish nearby subjects such as machinery inspections versus product conformity, privacy versus cybersecurity, public tenders versus supplier due diligence, and energy audits versus carbon accounting. All example provisions are fictional.

## Install in the existing API-_test folder

Copy these files into your existing checkout, preserving their paths:

- `classify_30_test.py` at the repository root, next to `benchmark.py`.
- `data/category30_catalog.json`.
- `data/category30_cases.json`.
- `tests/test_classify30.py` (local software verification).
- `CATEGORY30_TEST.md` (this guide).

Keep your existing `.env`, `config.json`, `benchmark.py` and other tests. Python 3.10 or newer is sufficient; no pip packages are required. This add-on reuses the existing benchmark's API adapter and report helpers.

## Run one test pass

In PowerShell inside `API-_test`:

```powershell
py -3 classify_30_test.py --models qwen3_30b
```

It sends 70 requests to the selected endpoint. Every request contains the full 30-option catalog and one example. It records the output budget (default 4096), model parameters, dataset hashes, prompt hashes and timings. Category order and case order are shuffled using a recorded seed. There are no automatic retries or changes to thinking mode. No real legal task, email or database write occurs.

For a very small integration check first:

```powershell
py -3 classify_30_test.py --models qwen3_30b --limit 5
```

This subset does not cover all 30 classes. For repeated testing after the first full pass:

```powershell
py -3 classify_30_test.py --models qwen3_30b --repeats 3
```

To validate the plan without an API call:

```powershell
py -3 classify_30_test.py --dry-run
```

To verify software locally:

```powershell
py -3 -m unittest discover -s tests -p test_classify30.py -v
```

## Examples and decisions

| Group | Independent examples | Expected behaviour |
|---|---:|---|
| Single subject | 60: one English and one German per category | Choose the one best matching category ID |
| Several subjects | 6 | Select all and only directly supported categories |
| Outside the catalog | 2 | `OUT_OF_SCOPE`, with an empty category array |
| Subject cannot be determined | 2 | `REVIEW`, with an empty category array |

An empty-category status is not an extra 31st category. It avoids forcing unrelated or underspecified input into the catalog. The multi-subject cases measure a separate multi-label path; the single-subject score specifically answers whether Qwen can select one category from 30 options.

Each answer must return `category_ids`, `status`, `summary`, `evidence_quote`, `dates` and `review_required`. Summaries use the input's requested English/German language, at most 60 words, and retain explicit ISO dates. No confidence threshold is inferred from the model's self-assessment.

## Results

Open `classification30.html` in the new timestamped directory under `reports`. It includes all raw source sentences, predicted categories, expected labels and generated summaries.

| File | Purpose |
|---|---|
| `classification_summary.json` | Classification accuracy by case group; single-label macro F1; per-class precision/recall/F1; multi-label micro F1; timing and mechanical summary checks |
| `confusion.csv` | Counts showing which category was confused with which other category |
| `summary_review.csv` | Original sentence, summary, evidence and blank reviewer-rating fields |
| `results.jsonl` | Complete final model outputs and request-level diagnostics |
| `comparison.html`, `summary.json`, `results.csv` | Common benchmark timing and structured-check reports |

Classification correctness and summary checks are separate. A correct category does not establish a correct summary. Conversely, a formatting problem in a summary does not automatically mean the category decision was wrong.

Summary checks only enforce basic length, date copying, obvious unsupported currency amounts and source-contained quotes. They do not establish semantic faithfulness, correct obligation strength, preserved exceptions or fluent German/English. A reviewer should score faithfulness, completeness, language and clarity from 0 (poor), 1 (needs edits), or 2 (good), and flag any unsupported claim. Never treat `summary_sanity_pass_rate` as summary accuracy.

The small balanced examples test integration and obvious category boundaries, not real-world production accuracy. There are just two single-subject examples per class. Repeating them measures consistency, not additional independent coverage. Before claiming company accuracy, replace the provisional catalog with your actual 30 category definitions, re-label a held-out dataset with experts, include genuine ambiguous/overlapping examples, and keep development examples separate.

Unknown labels, duplicate labels, incorrect dates and missing final answers fail their respective checks. The scorer does not repair a wrong category or invent a label mapping. No LLM judges its own summaries.

API timing includes the supplied catalog length, reasoning, networking and final generation. Previous 2–5 second measurements were for different prompt sizes; do not assume the same latency here. The model's actual response timing will be in this report.

The add-on has been checked locally with a fake HTTP/SSE server. No company endpoint was contacted while building it; actual Qwen results require your office run.
