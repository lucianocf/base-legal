# 0009. Do not redistribute voyage-4-large document vectors (yet)

- Status: Proposed
- Date: 2026-09-27

## Context
ADR 0003 planned to commit precomputed `voyage-4-large` vectors of the law
under `corpus/embeddings/`, so end users would need no Voyage key, **if
Voyage's terms allow redistributing generated embeddings**.

Voyage AI Terms of Service, read on 2026-09-27 at
<https://www.voyageai.com/tos> ("Last Updated: May 27, 2026"):

- §3 *Content and Models*: "You retain ownership of all data and other
  information you provide to Voyage AI or otherwise load into the Service
  ('Customer Content')". The grant back to Voyage (use, including training
  unless opted out) covers Customer Content.
- **The terms do not mention outputs or embeddings at all.** Customer
  Content is defined by what the customer *provides*; nothing says who owns
  the vectors the Service returns, and nothing grants or forbids
  redistributing them.
- §9 *Other Restrictions* concerns access to the Service (scraping,
  circumventing limits, probing), not the use of outputs. §21 restricts the
  *Website's* content, not API results.
- The FAQ (<https://docs.voyageai.com/docs/faq>) covers the training opt-out
  and model compatibility, not output ownership.

The terms are therefore **silent**, not permissive. The brief for this work
says: allowed → commit; not allowed **or unclear** → do not commit.

## Decision
- The `voyage-4-large` vectors are **not committed**. `corpus/embeddings/` is
  git-ignored, and the committed `manifest.yaml` lists no embedding
  artifacts. Maintainers may still generate them locally with
  `base-legal corpus embed` (the benchmark in ADR 0003 uses them).
- The three ingest modes stay as designed. Without committed vectors, `auto`
  resolves to `api` when `VOYAGE_API_KEY` is set and to `local`
  (`voyage-4-nano` for documents and queries) otherwise.
- CI and the published retrieval evals run in **`local` mode** (nano + nano),
  which is deterministic, secret-free and reproducible from a fresh clone.
- `VoyageApiEmbedder` batches by an estimated token budget and backs off on
  rate limits, so `api` mode works on the free tier (3 RPM / 10K TPM without
  a payment method).
- This ADR is revisited if Voyage confirms **in writing** (for example via
  `legal@voyageai.com`) that customers may redistribute embeddings of
  public-domain text. That confirmation would lead to a new ADR that
  supersedes this one, and the vectors would then be committed with their
  SHA-256 in the manifest (threat S13 controls already exist).

## Consequences
- ➕ No contractual risk from publishing a vendor's outputs under an
  open-source licence the vendor never agreed to.
- ➕ CI stays free of secrets and paid calls, as before.
- ➖ The zero-key quickstart uses `local` mode, which ADR 0003 expected to be
  lower quality than B1. The gap is measured in `docs/evals/embedding-gate.md`.
- ➖ Deployers who want B1 quality need a Voyage key once per corpus snapshot
  (the corpus fits the free allowance), and Voyage then receives public law
  text only.
