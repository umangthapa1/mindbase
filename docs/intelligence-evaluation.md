# Intelligence quality baseline

Mindbase keeps its action boundary deterministic: a natural-language message is
classified locally, converted into a validated plan, and only then allowed to
reach a bounded handler. This evaluation corpus measures that boundary before
any future model or self-evolution changes are introduced.

## Run the offline evaluation

From the repository root:

```bash
venv/bin/python backend/tests/run_isolated.py -q backend/tests/test_offline_intelligence_eval.py --tb=short --disable-warnings
```

The evaluation blocks sockets and Ollama calls in the test module. The isolated
runner also uses disposable storage, stub embeddings, and blocked network
access. It is safe to run without changing the real workspace database.

## Current corpus

The corpus covers these observable behaviors:

| Area | Cases | What it checks |
| --- | ---: | --- |
| Routing | 13 | Tool selection, explicit task wrappers, email lookups, widget deletion, and chat fallbacks |
| Intent | 7 | Document, calendar, planning, coding, research, and general prompts |
| Clarification | 9 | Ambiguity, missing details, and answers that resume the original request |
| Reminder planning | 12 | Relative durations, informal units, bounds, and unsupported timing |
| Valid workflow planning | 4 | Ordered task/reminder/notification plans and linked dependencies |
| Invalid workflow planning | 4 | Missing timing, unsupported actions, invalid delays, and empty workflows |
| Safety boundaries | 8 | Negation, cancellation, ambiguity, and refusal to execute partial plans |
| Schema safety | 6 | Unknown actions, unsafe dependencies, bad links, duplicate IDs, executable fields, and zero delays |

The test suite reports each concern separately. A failing corpus entry includes
its case name and the observed mismatch, so an intelligence change must improve
the intended behavior without silently weakening another boundary.

## What this does not claim

This is an offline deterministic baseline, not a measure of model prose quality.
It does not call Ollama, evaluate embeddings, measure document or memory
retrieval relevance, connect to IMAP, or exercise the full chat mutation path.
Those paths remain covered by the existing backend integration and browser
tests. New intelligence proposals should add a corpus case first, then change
behavior only when the expected result is explicit.

## Evolution rule

The corpus is a guardrail for future intelligence work. A proposal must not
generate executable code, bypass clarification, silently mutate user data, or
grant new permissions. Any approved behavior change must update the corpus,
pass the full offline suite, and retain an auditable rollback path.
