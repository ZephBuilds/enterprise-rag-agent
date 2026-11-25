# Case study: a trustworthy offline RAG baseline

## Problem

An enterprise search assistant must answer operational questions without making
unsupported claims. The smallest useful public proof is therefore not a chat
interface: it is an executable path from a query to governed evidence, an
extractive answer, and a citation, with a safe abstention when evidence is weak.

## Constraints

- The demo must be reproducible offline with no credentials, paid services, or
  sensitive documents. Its corpus is entirely fictional.
- Answers must remain traceable to current, authoritative evidence, including
  when a query contains an instruction injection or conflicting obsolete text.
- Evaluation failures must be useful in CI, while malformed evaluation inputs
  must fail closed without echoing their contents or local paths.
- The slice cannot claim production-scale relevance, latency, or model quality:
  it has a tiny lexical index and no generative model.

The precise controls and explicit non-production boundary are documented in
the [trust and security boundaries](architecture.md#trust-and-security-boundaries).

## Decisions and trade-offs

The baseline uses dependency-free lexical retrieval and copies one sentence
verbatim from evidence. This sacrifices fluent synthesis and semantic recall in
exchange for deterministic behavior and an exact grounding check. A currency
filter removes obsolete sources before authority affects ranking; this makes the
governance rule explicit instead of hoping relevance scoring resolves conflicts.
The agent exposes only two actions, `retrieve` and `abstain`, keeping failure
behavior inspectable. Versioned fixtures and evaluation specifications make the
acceptance contract reviewable alongside the code.

## Reproducible results

The current implementation passes the repository's offline gates. The figures
below are acceptance results and budgets encoded in the linked, versioned
specifications—not production benchmarks or an SLA:

The [canonical verification summary](verify-output.v1.json) is a sanitized,
versioned record of the offline gate results.
The [sanitized invalid-evaluation artifact](invalid-evaluation-output.v1.json)
demonstrates fail-closed behavior without exposing a traceback, local paths, or
input contents.

- Recall gate: **100% recall@2** ([specification](../evaluation/retrieval.v1.json)).
- Grounding gate: **100% grounding** ([specification](../evaluation/agent.v1.json)).
- Adversarial gate: **100% pass rate** in both the general and dedicated
  authority/currency sets ([general specification](../evaluation/agent.v1.json),
  [conflict specification](../evaluation/agent.authority-adversarial.v1.json)).
- External-cost budget: **USD 0.00** for the offline retrieval evaluation.
- In-process retrieval latency guard: **p95 ≤ 50 ms**. It excludes startup,
  file loading, parsing, and any network work.

Reproduce the evidence from the project root:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m enterprise_rag.cli verify
```

These are the same three required gates run by CI. The canonical verification
command already includes the retrieval, general-agent, and dedicated
authority/currency adversarial evaluations, so they do not need to be invoked
again individually.

## Limitations and learnings

The fixtures are deliberately small and cannot establish behavior on a real
enterprise corpus. Lexical matching will miss paraphrases, and exact extraction
cannot combine evidence across passages. The latency guard catches regressions
on this fixture but says nothing about production load. The useful learning is
that source currency, authority, abstention, and adversarial expectations can be
made testable before adding a model-backed synthesizer. A next increment should
compare such a synthesizer against this unchanged deterministic safety baseline.
