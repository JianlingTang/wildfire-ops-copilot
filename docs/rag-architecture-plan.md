# Production RAG plan

This phase deliberately does not implement retrieval. The running system returns
`KNOWLEDGE_REQUIRED` when the coordinator cannot satisfy an in-domain request with
an audited deterministic tool.

## 1. Retrieval contract

- Inputs: user question, AOI/region, effective time, user access scope, and conversation context.
- Outputs: either `answerable` with evidence IDs, source spans, retrieval scores, freshness and data mode, or
  `insufficient_evidence` with a clarification/escalation reason.
- The generator may only cite evidence IDs returned by retrieval. Every material claim must map to one or more
  source spans.
- Live operational data and document knowledge stay separate. Live facts come from deterministic tools; RAG is for
  document knowledge, policies, procedures, and historical reference material.

## 2. Ingestion and chunking

Use deterministic, structure-aware parsing rather than fixed character slicing:

1. Preserve document title, heading path, paragraphs, lists, table headers/rows, page number, and source offsets.
2. Retrieve on child chunks of roughly 300–500 tokens, then expand to a parent section of roughly 700–1,200 tokens
   for answer generation. This keeps retrieval precise without losing the surrounding rule or procedure.
3. Keep heading-bounded chunks near 600–900 tokens when a parent/child split is unnecessary. Start around 10–15%
   overlap, only at section boundaries; do not pay for 50% overlap by default.
4. Never split a table row from its header. Store long tables as a short table summary plus row groups sharing the
   same header metadata.
5. Attach `document_id`, `version`, `checksum`, `parent_id`, `heading_path`, `source_url`, `page`, `region`,
   `document_type`, `authority`, `effective_from`, `effective_to`, `ingested_at`, `access_scope`, and data mode.
6. Re-embed only changed chunks by checksum and retire superseded versions without silently mixing policy versions.

OpenAI's current managed vector-store baseline uses 800-token chunks with 400-token overlap by default and supports
static chunk sizes from 100 to 4,096 tokens. That is a useful baseline, but the overlap is expensive for this corpus;
the proposed structure-aware parent/child strategy should be calibrated against retrieval evaluation before release.

## 3. Efficient retrieval pipeline

1. Apply the deterministic domain gate before any model call.
2. Let the coordinator select a deterministic workflow tool or the RAG workflow. It must never answer knowledge
   questions directly.
3. Apply strict metadata filters first: access scope, active document version, region/AOI, document type, and
   effective date.
4. Run hybrid retrieval (lexical/BM25 plus dense vector search) and combine rankings with reciprocal-rank fusion.
5. Retrieve about 20 candidates, deduplicate near-identical chunks, rerank the best 8–12, and normally send only
   4–6 evidence units to generation. Tune these numbers on the evaluation set, not by intuition.
6. Expand winning child chunks to their parent section or adjacent window only when needed, then enforce a fixed
   context-token budget.
7. Cache embeddings by checksum and retrieval results by normalized query + filter set + index version. Give live
   operational data a short TTL or no cache; policy documents may use a longer version-keyed cache.

## 4. Evidence sufficiency and refusal

Do not use one guessed similarity cutoff. Train/calibrate a small evidence gate on held-out answerable and
unanswerable questions using:

- reranker score and gap between top candidates;
- query-claim coverage;
- source authority and freshness;
- agreement or conflict between sources;
- whether the answer requires facts outside the returned spans.

The gate returns `answerable`, `clarification_required`, `not_found`, or `conflicting_evidence`. Only `answerable`
reaches generation. The other states produce a deterministic refusal or human escalation. The UI should show the
source, version/effective date, AOI/data scope, Live/Cached/Demo/Fallback state, and the exact supporting span.

## 5. Evaluation and release gates

Build a versioned test set with real operator questions, paraphrases, multilingual queries, time/region ambiguity,
out-of-domain prompts, and hard negatives that sound plausible but are absent from the corpus.

- Retrieval: Recall@20, nDCG@10, MRR after reranking, metadata-filter accuracy.
- Grounding: supported-claim precision, citation correctness, citation completeness, contradiction rate.
- Safety: false-answer rate on unanswerable questions, false-positive answer rate, false-refusal rate, unsafe action
  execution rate (target: zero).
- Product: containment/hand-off rate split by `answerable` vs `not_found`, task completion, user rating after the
  conversation, operator minutes saved.
- Efficiency: p50/p95 latency, input/output tokens, retrieval and model cost per resolved conversation, cache hit rate.

Release thresholds must be set from a labeled baseline and business risk tolerance. Report every metric by intent,
language, document type, data mode, and answerability so an attractive average cannot hide a dangerous slice.

## 6. Implementation sequence

1. Corpus inventory, metadata/ACL contract, and versioning.
2. Structure-aware parser plus parent/child chunks and ingestion validation.
3. Hybrid retrieval, metadata filters, reranker, deduplication, and context budgeting.
4. Evidence sufficiency gate and deterministic refusal states.
5. Claim/evidence response schema and UI evidence highlighting.
6. Offline evaluation, shadow traffic, threshold calibration, then a guarded production rollout.
