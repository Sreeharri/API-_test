# Legal Radar model API tests

Compare your deployed Llama 8B and Qwen3-30B APIs on Legal Radar work before integrating either into the backend. The suite uses **Python 3.10 or newer and no pip packages**. It runs separately from your existing project and does not read or change your PostgreSQL database, source connectors, tasks or email system.

## Your company endpoints

This update is configured from the IT message in your screenshot:

| Local profile | Route prefix provided by IT | Status stated in the message |
|---|---|---|
| `llama8b` | `https://vllm.max-boegl.biz/llama-8b-nvfp4` | Available for testing |
| `qwen3_30b` | `https://vllm.max-boegl.biz/qwen3-30b-a3b` | Currently produces thinking output without a final answer |

The screenshot contains **URLs, not API keys**, and does not specify authentication. Gemma is not included because the message says API deployment is still pending.

These are route prefixes. The checker tries `/v1/models` and `/models` under each supplied prefix, verifies a model-list JSON response, and reads the actual served model ID. It does not assume the route label is the model ID. It does not scan unrelated paths or hosts. If the list has multiple models, you must choose an exact ID in `.env`; the checker does not guess. A 401/403 discovery response stops further route probes so you can supply the required credentials.

The API adapter uses OpenAI-compatible Chat Completions. API-path detection is read-only and happens before timed benchmark requests. If IT disables `/models`, set the exact `LLAMA_MODEL` or `QWEN_MODEL` and full API base in `.env`. With an explicit model ID, a benchmark can still attempt chat while recording that model-list verification failed; a `--discover` result then means configuration is usable for a chat attempt, not that chat has been verified. The `api_base_verified` flag distinguishes this fallback.

## Start on your office laptop

Extract the ZIP and open PowerShell inside the extracted `legal_radar_model_tests` folder. `config.json` is already supplied with the company URLs and `model: auto`.

```powershell
py -3 --version
Copy-Item .env.example .env
py -3 benchmark.py --discover
```

Run this on the company laptop/network. If the response reports 401 or 403, add the key provided by IT to the corresponding local `.env` entry:

```powershell
notepad .env
```

`LLAMA_API_KEY` and `QWEN_API_KEY` are optional in this company configuration: empty entries send no Authorization header. If IT requires authentication, supply the real local values before retrying. No key or authentication scheme is inferred from the screenshot. To require a key before any HTTP call, set `api_key_required` to `true` in that model's config. `headers_env` still supports a different authentication header when specified by IT.

The screenshot provides the API prefixes; the exact model IDs and actual gateway paths will be confirmed only by your local connection check. The company services have **not** been contacted from this environment. A failed check may indicate company network, DNS, certificate, permissions, routing or unavailable model metadata; inspect the returned diagnostics before changing a setting.

First run a small connection/final-answer test on both endpoints:

```powershell
py -3 benchmark.py --suite smoke
```

A result of `reasoning_only` means the HTTP exchange completed but produced no usable final answer. This directly tests the Qwen issue mentioned by IT when the API identifies reasoning in its own field or `<think>` markup. Unmarked free-form thinking instead fails the expected final-JSON contract as a mismatch; the checker cannot infer hidden boundaries that the server does not expose. It is not counted as an authentication failure, transport failure or correct answer. The actual cause still needs diagnosis: server reasoning parser/template, model behavior and output budget are possible factors. There is no automatic mode change or hidden retry.

Start the complete project benchmark with Llama while Qwen is being investigated:

```powershell
py -3 benchmark.py --models llama8b --suite all
```

After Qwen produces a usable final answer in the smoke test, compare both:

```powershell
py -3 benchmark.py --suite all
```

If `py` is unavailable, replace `py -3` with `python`. No pip packages, virtual environment, GPU libraries or model downloads are required. Keep keys on your office computer.

Validate configuration without any HTTP calls:

```powershell
py -3 benchmark.py --dry-run
```

Environment overrides take precedence over `.env`, and `.env` overrides the template's model/base defaults through named override variables. Stale system environment values can therefore override recent `.env` edits. Leave `LLAMA_MODEL` and `QWEN_MODEL` blank for auto-discovery, unless IT supplies exact model IDs. You can restore the company config from `config.example.json` if needed; the supplied `config.json` contains no secrets.

## Recommended test order

| Step | Command | What it establishes |
|---|---|---|
| 1 | `py -3 benchmark.py --suite smoke` | Authentication, basic answer, nonstream and streaming response paths |
| 2 | `py -3 benchmark.py --suite quality --repeats 3` | Correctness and repeatability on 50 Legal Radar fixtures |
| 3 | `py -3 benchmark.py --suite latency --samples 30` | Response-time distribution and reported token throughput |
| 4 | `py -3 benchmark.py --suite context` | Retrieval at beginning, middle and end of growing inputs |
| 5 | `py -3 benchmark.py --suite concurrency --workers 1,2,4 --requests-per-worker 5` | Throughput and correctness with simultaneous requests |
| 6 | `py -3 benchmark.py --suite capabilities` | JSON mode, JSON-schema behavior and tool-call round trips |
| 7 | `py -3 benchmark.py --suite stability --samples 20` | Repeated identical multi-step question: consistency and correctness |
| 8 | `py -3 benchmark.py --suite review` | Four open-ended summaries, task proposals and evidence reviews for human scoring |

One command for all suites with small initial samples:

```powershell
py -3 benchmark.py --suite all
```

A more substantial run, after the smoke test succeeds:

```powershell
py -3 benchmark.py --suite all --repeats 3 --samples 30 --context-chars 4000,16000,32000,64000 --workers 1,2,4 --requests-per-worker 5
```

Run duration depends on your actual API. Thinking-mode generation, long prompts and queueing can increase runtime substantially; the suite does not promise a completion time. Defaults include one excluded warm-up per selected model. Initial all-suite testing makes about 100 measured requests per model; tool probes can add two conditional round trips.

Test one model or selected suites:

```powershell
py -3 benchmark.py --models llama8b --suite quality,latency
py -3 benchmark.py --models qwen3_30b --suite context,stability
```

Optional PowerShell wrapper, if your company permits running scripts:

```powershell
.\run_tests.ps1 -Suite smoke
```

The direct Python commands work without changing PowerShell execution policy.

## What the project tests cover

The 50 objective cases are clearly marked **fictional fixtures**, not quotations or interpretations of real law. Inputs and expected outputs are visible in `data/legal_radar_cases.json`.

| Category | Cases | Checks |
|---|---:|---|
| Relevance | 12 | Six retained cases, including uncertainty, and six clearly out-of-scope cases; effective recall and false negatives |
| Department classification | 8 | Fixed supplied routing policy; German, English and multiple departments; exact label set and micro F1 |
| Extraction | 5 | Effective dates versus deadlines, German dates, missing penalties, voluntary versus mandatory duties |
| Reasoning | 7 | Exceptions, numeric thresholds, calendar arithmetic, version selection and unresolved contradictions |
| Change detection | 5 | Amendment, repeal, formatting change, consolidation duplicate and draft |
| Grounded questions | 4 | Supported answers, exact evidence quotation, source ID, cross-language answers and abstention |
| Prompt injection | 2 | Ignore instructions embedded in retrieved source text |
| Relationships | 2 | Amendment direction; citation does not imply transposition |
| Task fields | 3 | Known routing and owner role, unknown owner/deadline, draft versus binding task |
| Completion evidence | 2 | Unrelated proof and proof dated after the task deadline |

These fixtures were designed around the supplied problem statement, plan and project presentations: relevance, multi-label departments, obligations, dates, source evidence, human review, tasks and auditability. The latest project presentation also describes reviewing proof of completed tasks, which is represented here. The test routing table is intentionally a fixture, not a claimed copy of Max Bögl's actual department ownership map.

No fixture is passed to the model with its expected answer. Fixtures contain an explicit schema and business policy. Most assess final fields, not prose quality. Expected labels and exact quotes are scored deterministically; another LLM does not grade the answers.

## Reading the reports

Every benchmark invocation creates a separate timestamped folder under `reports`. `--discover` and `--dry-run` print diagnostics without creating a benchmark report. Open `comparison.html` in your browser.

| File | Content |
|---|---|
| `comparison.html` | Side-by-side metrics, failed cases and detailed category results; self-contained, no external scripts |
| `summary.json` | Combined machine-readable report, model settings and metrics |
| `results.csv` | One request per row, including `transport_ok`, `final_answer_available` and error category; useful in Excel |
| `results.jsonl` | Request-level final outputs, expected answers, finish reasons, usage, timings and errors |
| `run.json` | UTC timestamps, runtime, seed/test plan, dataset/config hashes and deployment notes |
| `<model_name>/summary.json` | Individual report for that model |
| `<model_name>/results.jsonl` | Individual request records for that model |
| `human_review.csv` | Created by the review suite; blank expert-rating columns and actual model outputs |

Responses are written incrementally. Ctrl+C retains completed records and produces an interrupted report. Concurrency batches finish recording after the batch; an interruption inside a batch can lose its in-flight/unrecorded records. Process termination or power loss can leave JSONL without final HTML; preserve the JSONL for analysis. Existing reports are not overwritten.

A completed run is **not** a model approval. Exit code `0` means the runner completed without non-capability API failures, even if answers were wrong. Exit code `2` means configuration/API/runtime failure, an unusable non-capability response (including reasoning-only), or interruption. Unsupported capability probes are retained for diagnosis and do not independently fail the process exit code. Review the scores and probe results.

## Speed and runtime metrics

- `total_seconds`: request start through complete response processing, including TLS/connection setup, network, server queue, prefill and generation.
- `ttft_any_seconds`: first nonempty generated content, reasoning or tool-call delta; ignores role-only events and heartbeats.
- `ttft_content_seconds`: first nonempty answer-content delta when the server separates reasoning. Inline `<think>` output makes this unavailable because its first content is reasoning.
- `completion_tokens_per_second_e2e`: **server-reported completion tokens / total request seconds**.
- `completion_tokens_per_second_after_first_delta`: approximate `(completion_tokens - 1) / time after first generated delta`, stored per request. A delta may contain multiple tokens, so this is not exact decoder speed.
- `transport_ok` means a complete valid API exchange. `ok` means that exchange also supplied final content or a tool call. `final_answer_available` specifically records final answer text. The HTML and JSON show transport successes, usable responses and reasoning-only counts separately.
- The report includes p50/p95 and sample count, concurrency batch throughput, errors and truncation counts. Percentiles from 10 or 30 samples remain exploratory; collect more repeats for capacity planning.
- Completion-token counts can include reasoning tokens. These are not automatically final-answer-only token rates. When usage is missing, rates stay unavailable; the suite does not estimate tokens from word counts.
- Nonstream responses have no TTFT measurement. If a gateway buffers streaming or returns regular JSON despite a streaming request, the result records that behavior and leaves unavailable timings empty.

The standard-library client opens a connection for each call; it does not use a persistent HTTP connection pool. These are end-to-end measurements for this client, not a GPU performance benchmark. In production, pooling may improve timing. Warm-up is excluded; the suite does not claim to measure a true cold model load. To test a true cold load, IT must arrange an unloaded server first, and you must label that run accordingly.

## Testing context length correctly

Start with:

```powershell
py -3 benchmark.py --suite context --context-chars 4000,16000,32000 --repeats 3
```

Then grow the input if earlier sizes succeed:

```powershell
py -3 benchmark.py --suite context --context-chars 64000,128000,256000,512000 --repeats 3
```

Sizes are **characters**, not tokens. The server's `usage.prompt_tokens` gives the actual reported prompt size, including chat template overhead where the server accounts for it. The user prompt, system prompt and verification record make the total slightly larger than the filler character target. Models have different tokenizers; equal text size does not mean equal token count.

Each size tests a random verification record at the beginning, middle and end. Only the reference key appears in the question; the expected code appears once inside the archive. Distinct distractor records avoid an entirely repeated filler block. Passing all positions at a given size is an **observed retrieval result**, not proof of the maximum window or reliable legal reasoning across every document at that length.

The context budget normally includes input plus reserved output. A request can be rejected even when the input alone is below the configured window. The report records output budget, API-reported prompt tokens and acceptance/retrieval separately. Explicit context-limit rejection stops larger probes for that model. Other errors remain errors; they do not get relabeled as context limits. A server may silently truncate input: failing retrieval can reveal a problem, but does not identify its cause by itself.

Ask IT for the configured `max_model_len` or equivalent, exact checkpoint, tokenizer revision and any context extension. Add them to each model's `deployment` section in `config.json`. If `/models` exposes context metadata, `--discover` prints it; many servers do not expose it. The suite does not infer a fixed Llama or Qwen context limit from a family name.

## Qwen thinking on versus off

The optional `config.qwen_thinking.example.json` creates two profiles of the **same** Qwen endpoint. It uses the vLLM-style `chat_template_kwargs.enable_thinking` switch. This is server-specific, and must be confirmed before use; a gateway may reject or ignore it. This example is not an automatic fallback and is not used in the main config.

```powershell
py -3 benchmark.py --config config.qwen_thinking.example.json --suite smoke
py -3 benchmark.py --config config.qwen_thinking.example.json --suite quality,latency,stability --repeats 3 --samples 20
```

Both profiles use the same sampling parameters and 4096-token output cap to help isolate the requested mode change. This is a controlled starting point, not an optimized setting for every Qwen variant. Compare correctness, missing final answers, truncation, time to first answer and total time; more generated reasoning is not a quality score. If you increase the cap, record it and rerun the comparable profiles. Reasoning and final answer share a budget on many deployments.

The suite observes reasoning fields/counts when the server exposes them. It does **not** ask for or save hidden chain-of-thought text. Recognized inline `<think>` blocks are omitted and fail strict JSON compliance. Correct final answers to multi-step cases are the practical reasoning metric. Optional thinking on/off profiles cannot prove the server honored the setting without matching server configuration or telemetry.

Primary references used for the API adapter and optional switch:

- [OpenAI Chat Completions API reference](https://platform.openai.com/docs/api-reference/chat/create)
- [Qwen documentation for vLLM, thinking modes and context configuration](https://qwen.readthedocs.io/en/latest/deployment/vllm.html)

## JSON and tool capabilities

The capability suite probes JSON-object mode, a strict JSON-schema request, automatic tool selection, forced tool selection and a tool-result round trip after each successful call. Every mock lookup returns a fixed local fixture. No real tool, database query, email or task creation is executed.

A 400/422 response can mean the **server adapter or parser** lacks the feature, rather than that the underlying model is incapable. Valid schema output on one probe is only observed behavior; the server may have ignored the enforcement parameter. Quality tests use prompt-level JSON instructions by default, without forcing constrained decoding, to expose native formatting reliability.

## Human review rubric

For `--suite review`, a legal/compliance reviewer should score each dimension in `human_review.csv`:

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Faithfulness | Invented or contradicted material claim | Minor unsupported detail or ambiguity | Every material claim supported or clearly marked uncertain |
| Citation support | Missing/wrong evidence | Citation present, support incomplete | Correct citation and supporting passage for each material claim |
| Completeness | Misses core obligation | Covers core, misses useful condition | Covers obligations, conditions and uncertainty |
| Routing and dates | Wrong owner/date or unsafe completion | Some omission needing correction | Correct known fields; unknowns remain unknown |
| Clarity | Misleading or unusable | Understandable with edits | Concise and usable for intended department |

Flag a critical error for an invented binding duty, invented deadline/penalty/person, acceptance of unrelated completion evidence, unsupported compliance approval, or following source-injected instructions. Do not average away a critical error. Human ratings are not automatically combined with deterministic scores.

## Turning this into a production evaluation

The small synthetic set checks integration and basic capability. It cannot establish the project targets of >95% relevant-law detection or >90% routing/deadline accuracy. For example, the relevance set has only six retained examples: one miss changes recall by 16.7 percentage points. Repeating the same fixtures measures consistency, not additional independent evidence.

Next, create a versioned, expert-labeled held-out dataset using your actual sources and department taxonomy: EUR-Lex, GII, BGBl, BAuA, DGUV, BMAS, BMUKN, BNetzA, DIP, Bundesrat and DIBt. Use title-only, gist and article-level variants where the pipeline uses them. Include ambiguous scope, changed dates, repeals, multilingual evidence, difficult negatives and source failures. Keep examples from the same act family out of both development and evaluation sets. Use enough independent examples and confidence intervals before claiming target attainment.

For a custom deterministic fixture, append an entry to `data/legal_radar_cases.json` with a unique ID, `category`, `language`, prompt, `expected` object and an appropriate `synthetic` flag. State the response keys and routing rules in the prompt. Expected values may be strings, booleans, integers, nulls or arrays of unique strings. The built-in checker uses exact types and fields; array order does not matter, extra fields and duplicate labels fail. Optional/nullable fields, partial credit policies or richer extraction structures require extending the checker and its tests. Do not include expected values in the actual prompt.

This suite tests the generation layer with supplied evidence. It does not measure your real retriever's recall/ranking, OCR, embeddings, PostgreSQL query performance, full source ingestion, company SSO, email delivery, frontend responsiveness or end-to-end detection-to-notification latency. Those require integration tests after connecting the model. API-only access does not reveal GPU VRAM, utilization, power, KV-cache use or server-internal batching; request server telemetry from IT if needed.

For model choice, inspect stage-level results rather than selecting a single overall winner. A smaller model may be enough for screening while the larger model may improve extraction or explanations; the actual tests must establish that. Keep final compliance decisions under human review.

## Troubleshooting

| Symptom | Action |
|---|---|
| 401 or 403 | Check the local key, API permissions, VPN/company network and any required custom header |
| 404 | Inspect the `/v1/models` and `/models` probes; if discovery is disabled, ask IT for the exact chat API base and served model ID |
| TLS/certificate error | Ask IT for the company CA in PEM format and set `SSL_CERT_FILE` in `.env`; verification stays enabled |
| 400 about `stream_options` | Set `"stream_usage": false` for that model; token-rate fields may then be unavailable |
| 400 about token cap field | Set `"token_parameter": "max_completion_tokens"` if required by the gateway |
| 400/422 on tools or schema | Review the capability result and ask IT whether parsers/constrained output are enabled |
| 429 | Lower `--workers`, use smaller batches, and coordinate with IT on capacity/rate limits |
| 5xx | Preserve the report timestamp and error for IT; no retry hides the failure |
| Mostly `finish_reason=length` | Inspect output budget and thinking mode; increase budget consistently for a new comparison |
| `reasoning_only` | The API completed but returned reasoning without a final answer; preserve the report for IT. Do not count it as a successful Legal Radar result or infer the cause from this flag alone |
| Every quality output has `<think>` text or fences | Strict JSON failed; inspect model prompt/template or try server-supported constrained output in a separate experiment |
| Streaming request returns JSON | TTFT stays unknown; inspect gateway buffering/streaming support |

If authentication uses `X-API-Key` instead of Bearer, remove `api_key_env` for that model and use:

```json
"headers_env": {"X-API-Key": "LLAMA_API_KEY"}
```

Custom header **values** are read from environment variables. Never put key values in config or `request_options`. A separate `ca_bundle_env` can name a model-specific CA-file variable. Redirects are rejected to avoid forwarding credentials unexpectedly; use the final API base supplied by IT. The HTTP client respects system proxy environment settings; use your company's approved networking configuration.

Reports omit configured authorization values and base URLs, and redact known key values in errors/outputs. Final model outputs and synthetic fixture answers are retained for audit. If you add confidential company fixtures, the resulting reports will contain those outputs and labels; keep them within your approved environment. Do not commit `.env` or reports containing company material.

## Verify the runner without your AI server

```powershell
py -3 -m unittest discover -s tests -v
```

The included tests use a temporary local fake HTTP/SSE server. They verify parsing, timing fields, error handling, redaction, strict scoring, context probes, tool round trips and report generation. These are software checks, not results for your Llama or Qwen deployment.
