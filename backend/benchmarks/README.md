# Chat routing benchmark

From the repository root, with the existing environment and local Ollama running:

```sh
venv/bin/python backend/benchmarks/benchmark_chat_routing.py --samples 3 --timeout 75
```

The script copies source into a disposable workspace (no existing data, uploads,
credentials, or `.env`), uses fresh in-memory SQL per turn, and invokes the real
chat handler. Background mailbox sync, auto-memory, and auto-titling are excluded.
It validates the expected task count and presence of a due date. It never changes
mailbox settings or the application's selected-model preference.

Each workload has one excluded warmup and three measured runs. Output includes
all samples, the median milliseconds until the first SSE content chunk, counts
of model-discovery/generation calls, and their aggregate duration. Requests have
a 75-second ceiling; a timed-out request is an incomplete run, not a valid sample.

## Recorded comparison

Environment: Python 3.14.7, Linux, existing local `qwen2.5-coder:7b` model.
Baseline: `1fbe9c6` runtime code before the routing changes (the pre-existing test
header edit does not affect this workload). After: working-tree routing changes.
The same script, synthetic inputs, warmup, and sample count were used. The final
after measurement ran without the regression/browser suites running concurrently.

| Workload | Before samples (ms) | After samples (ms) | Before median | After median |
| --- | --- | --- | --- | --- |
| `add task: Buy milk tomorrow` | 7644.58, 9213.34, 9323.36 | 7.10, 5.50, 8.15 | 9213.34 ms | 7.10 ms |
| `any new mail?` (empty local inbox) | 12.34, 11.21, 10.54 | 8.68, 6.38, 4.12 | 11.21 ms | 6.38 ms |

The task bottleneck was model-based action extraction: generation alone took
7630.08–9300.19 ms per warm baseline request. After routing explicit task creation
directly to the existing parser/store, discovery and generation calls are both
zero for that request. It also succeeds when Ollama is unavailable. This removes
the routing-model prompt entirely for the simple path; no smaller model or model
switch is necessary. Local-only conversations use a request-derived title rather
than starting another model call solely for a title.

Inbox listing was already model-free; its small timing change is not a claim of
a meaningful independent speedup. Existing answer streaming and parallel context
retrieval remain in place. General chat, summaries/drafts, and complex scheduling
still use the selected model and were not shown to generate tokens faster.

These are **server-side handler measurements**, not browser end-to-end latency.
Real workspace size, disk-backed SQL, model contention, networking, and rendering
can add latency. Smaller post-change differences vary with host load; the reliable
improvement is eliminating the multi-second extraction call for explicit tasks.
