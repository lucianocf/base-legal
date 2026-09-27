# Base Legal — Project Plan

> Status: **v0.1.0 implemented, publication pending** · Last updated: 2026-09-27

## 1. Vision

**Base Legal** is a citation-first question-answering system over Brazilian data
protection law (LGPD — Lei nº 13.709/2018 — and the resolutions of the ANPD's
Board of Directors). Every answer is grounded in the exact provision it relies on
(article, paragraph, inciso, alínea) and every citation is **machine-verified**
against the corpus before it reaches the user. If no provision supports an
answer, the system says so instead of guessing.

It is also a reference implementation of how to build an LLM system *properly*:
privacy by design, a published threat model, evaluation gates in CI and a clean
supply chain. The system complies with the law it explains.

The name is a double meaning: *base legal* is the LGPD's term for the legal
basis of a processing operation (arts. 7 and 11), and it is also a legal
knowledge base.

## 2. Audience and positioning

| Audience | What they get | Why they star/share |
|---|---|---|
| **Developers / AI engineers** (primary) | A small, readable, typed codebase showing structural chunking, hybrid retrieval, verified citations, eval gates, LLM threat modeling | "This is how a grounded RAG should look." A reference they can copy. |
| **Clients and recruiters** (Upwork) | Evidence of production-grade AI engineering and security/privacy depth | README, ADRs, threat model, green CI, eval badge |
| **DPOs and privacy professionals** (secondary) | An MCP server for Claude Desktop/Code and docs on GitHub Pages | "Ask the LGPD and get the inciso, verified." |

**Hooks (README headline candidates):**
- *Every claim cites an inciso — and a machine checks it.*
- *The RAG that complies with the LGPD it explains.*

## 3. MVP scope (v0.1.0)

### In scope
- **Corpus:** LGPD (compiled text from Planalto) + CD/ANPD resolutions (see §7),
  normalized and versioned in the repo, with a `manifest.yaml` recording source
  URL, retrieval date, SHA-256 and legal basis for redistribution.
- **Structural parsing** into canonical provision IDs (`lgpd:art7:incIX`) with the
  hierarchy path (Chapter > Section > Article) kept on every chunk.
- **Hybrid retrieval:** PostgreSQL full-text (`portuguese`) + pgvector, fused
  with Reciprocal Rank Fusion. **Local Voyage 4 embeddings:** questions are
  embedded **locally** with the open-weight `voyage-4-nano`, so questions never
  reach Voyage (ADR 0003). The embedding gate showed that embedding the law with
  nano too beats `voyage-4-large` documents on this golden set, so `local` mode
  is the default and needs no key (ADR 0013); `api` mode stays opt-in.
- **Grounded generation** with Claude (Haiku 4.5 default, Sonnet 5 configurable),
  citations mapped to provision IDs, **strict refusal** when unsupported.
- **Citation validator:** every cited ID must exist and every quoted span must
  appear verbatim (after normalization) in that provision.
- **PII redaction** of questions before any third-party call (CPF/CNPJ with
  check-digit validation, e-mail, phone).
- **Minimal logging:** no question text in logs by default; defined retention.
- **Interfaces:** Python library core + CLI (`base-legal`) + FastAPI + MCP server
  (retrieval and verification tools) + a minimal local web UI.
- **Evals:** a golden set (~40 questions, drafted with AI and verified by a DPO)
  and a red-team set (~10 attacks), run deterministically in CI with a badge.
- **Docs:** README (EN) + README.pt-BR, ARCHITECTURE, THREAT_MODEL, PRIVACY,
  ADRs, SECURITY.md, LEGAL_NOTICE.md, published with MkDocs on GitHub Pages
  together with the latest eval report.
- **Repo hygiene:** ruff, mypy `--strict`, pytest + coverage, pre-commit,
  CodeQL, gitleaks, pip-audit, Dependabot, actions pinned by SHA, OpenSSF Scorecard.

### Explicit non-goals for the MVP
- No hosted demo with an LLM (cost, abuse and data controller role; see ADR 0006).
- No ANPD guides (irregular PDFs, licensing to confirm; see ADR 0007).
- No point-in-time queries ("in force on date X"). The schema supports them
  from day one, but the feature waits for Phase 3.
- No legal advice. The disclaimer appears in the README, the UI and every API response.
- No RAG framework (see ADR 0001).

## 4. MVP schedule (≈ 2 weekends, ≈ 20 h)

| Block | Weekend 1 (~10 h) | Weekend 2 (~10 h) |
|---|---|---|
| Foundation | Scaffold (`uv`, ruff, mypy, pytest, pre-commit), CI skeleton, Docker Compose with Postgres + pgvector | Release workflow, Pages (MkDocs), README EN/PT-BR, GIF |
| Corpus | Fetch + parse LGPD and resolutions → canonical provisions; parser unit tests on tricky cases | — |
| Retrieval | Schema + migrations, ingestion, embeddings, FTS + vector + RRF; `base-legal ingest` / `search`; **embedding validation gate** (~2 h, ADR 0003) | Tune on the golden set |
| Generation | — | Claude call with citations, validator, strict refusal, PII redaction |
| Interfaces | CLI | FastAPI, MCP server, minimal UI |
| Evals | Golden-set draft reviewed by the author | Retrieval + citation + red-team evals in CI, badge |
| Security & privacy | — | Finalize THREAT_MODEL, PRIVACY, SECURITY.md; Scorecard |

If time runs out, cut in this order: the minimal UI, then Pages polish, then the
red-team set size. **Never cut** the validator, the evals or the parser tests.

## 5. Roadmap

### Phase 2: second hook, public-sector depth
- **LAI × LGPD:** add Lei nº 12.527/2011 (Access to Information Act) and model
  the tension between transparency and data protection. This is a niche few
  projects cover and it matches the author's public-sector expertise.
- Resolved cross-references: "nos termos do art. 11" becomes a link to that provision.
- Reranking with a **local** cross-encoder (e.g. Qwen3-Reranker-0.6B or
  bge-reranker-v2-m3) **only if** the golden set shows a gain. Never a hosted
  reranker, which would send questions to a third party.
- A normative change watcher: a scheduled job diffs official sources and opens a PR.
- A static corpus explorer on GitHub Pages (browse provisions, anchor links,
  client-side search, no LLM).
- Supply chain for releases: SBOM (CycloneDX), cosign-signed images on GHCR,
  SLSA provenance.
- An eval post comparing Haiku 4.5 and Sonnet 5 on the golden set (LinkedIn/dev.to content).

### Phase 3: ambitious features
- Point-in-time queries across the historical versions of the LGPD (Leis
  13.853/2019, 14.010/2020, 14.460/2022).
- ANPD guides, with a section/page citation model, once licensing is settled.
- A hosted demo as a full privacy dogfooding case: privacy notice, RIPD
  (DPIA), rate limiting, Turnstile, a hard budget cap.
- A curated LGPD ↔ GDPR mapping (human-curated, never LLM-generated).

## 6. Ideas: impact vs effort

| Idea | Impact | Effort | Decision |
|---|---|---|---|
| Structural chunking + canonical IDs | High | Medium | **MVP** (the core) |
| Verified citations + strict refusal | Very high | Low–Med | **MVP** (the main hook) |
| Hybrid FTS + vector + RRF | High | Low | **MVP** |
| Golden set + CI evals + badge | Very high | Medium | **MVP** |
| Red-team (prompt injection) regression set | High | Low | **MVP** |
| PII redaction + minimal logs | High | Low–Med | **MVP** |
| Threat model (STRIDE + OWASP LLM Top 10) | High | Low | **MVP** |
| PRIVACY.md with a ROPA-style inventory | High | Low | **MVP** |
| MCP server | High | Low | **MVP** |
| Repo hygiene (CodeQL, Scorecard, pinned actions…) | Med–High | Low | **MVP** |
| LAI × LGPD | High (niche) | Medium | Phase 2 |
| Resolved cross-references | Med–High | Medium | Phase 2 |
| Reranking | Medium | Low | Phase 2, data-driven |
| SBOM + cosign + SLSA | Medium | Medium | Phase 2 |
| Normative change watcher | Medium | Medium | Phase 2 |
| Point-in-time queries | High (lawyers) | High | Phase 3 |
| Hosted demo + RIPD | High | High | Phase 3 |
| LGPD ↔ GDPR mapping | High (global) | High | Phase 3 |

**Rejected, with reasons:**
- **LLM-generated contextual retrieval:** for statutes, the deterministic
  hierarchy path gives most of the benefit at zero cost and without injecting
  model-generated text into the index.
- **GraphRAG / knowledge graphs:** overkill for about 200 provisions. Explicit
  cross-references (Phase 2) cover the real need.
- **LangChain / LlamaIndex / multi-agent orchestration:** a larger supply chain
  surface, and it hides the engineering this project exists to show (ADR 0001).
- **Dedicated vector database:** pgvector is ample at this scale.
- **LLM-as-judge on every PR:** costly and noisy. Generation evals run locally or on demand.
- **RIPD for a locally run tool:** there is no processing to assess. The honest
  artifact is the data inventory; the RIPD comes with the hosted demo.
- **"Compliance checklist" agent:** looks like automated legal consulting and
  carries liability risk. Left out.

## 7. Corpus (MVP)

| Document | Canonical prefix | Source (layout) |
|---|---|---|
| LGPD — Lei nº 13.709/2018 (compiled) | `lgpd` | planalto.gov.br (`planalto`) |
| Res. CD/ANPD nº 1, de 28/10/2021 — inspection and sanctioning procedure | `res-anpd-1-2021` | gov.br/anpd compiled page (`govbr`); corrected by Res. 4/2023 |
| Res. CD/ANPD nº 2, de 27/01/2022 — small processing agents | `res-anpd-2-2022` | gov.br/anpd compiled page (`govbr`); amended by Res. 15/2024 |
| Res. CD/ANPD nº 4, de 24/02/2023 — sanction dosimetry | `res-anpd-4-2023` | DOU (`dou`) |
| Res. CD/ANPD nº 15, de 24/04/2024 — security incident reporting | `res-anpd-15-2024` | DOU (`dou`) |
| Res. CD/ANPD nº 18, de 16/07/2024 — the DPO (encarregado) | `res-anpd-18-2024` | DOU (`dou`) |
| Res. CD/ANPD nº 19, de 23/08/2024 — international transfers | `res-anpd-19-2024` | gov.br/anpd compiled page (`govbr`); DOU correction of 18/08/2025 (Annex II only) |

Numbers, dates, ementas and amending acts were confirmed on 2026-09-27
against the ANPD's own index of regulations
(<https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd>).
The regulation of each resolution sits in its annex (IDs `…:anx1:…`, ADR 0010).
Res. 19/2024 Annex II (standard contractual clauses, numbered clauses rather
than articles) is not parsed yet: follow-up.

## 8. Risks

| Risk | Mitigation |
|---|---|
| **Planalto compiled HTML is irregular.** Revoked text is struck through (`<strike>`), amendments are annotated inline ("Redação dada pela Lei nº …"), and articles like "55-J" and "Parágrafo único" need care | Parser built test-first on a fixture set of the nastiest articles; normalized output committed and reviewed as a diff |
| Resolutions published in different layouts (DOU vs gov.br) | One parser per source layout behind one interface; manual checks on small resolutions |
| Voyage trains on customer data by default | Only public law text is sent to Voyage; questions are embedded locally (ADR 0003) |
| `voyage-4-nano` has few independent benchmarks | Validation gate run on the golden set: nano for documents and questions came first (ADR 0013); Qwen3-Embedding-0.6B stays plan B |
| Voyage terms may forbid redistributing vectors | Checked 2026-09-27: the terms are silent, so vectors are not committed (ADR 0009); users run `api` ingest once (free tier) or `local` mode. Written confirmation from Voyage would reopen this |
| Hallucinated citations | Validator + strict refusal; tested in CI |
| Scope creep (20 h budget) | Cut order in §4; everything else is roadmap |
| Accidental employer reference | Pre-publish grep checklist + manual review (§9) |

## 9. "Ready to publish" criteria (v0.1.0)

Status on 2026-09-27 (see `docs/progress/2026-09-27-overnight.md`):

- [ ] CI green on `main`: ruff, mypy `--strict`, pytest (≥ 85 % coverage on the
      core packages), gitleaks, pip-audit, CodeQL. *Green on the draft PR is the
      target; `main` turns green when the author merges.*
- [x] Evals in CI with a badge: recall@5 and MRR gated at the recorded
      baseline (`--min-recall-at-5 0.65`), 100 % of emitted citations validated
      by construction, refusal accuracy gated (`≥ 0.6`), red-team pass rate
      gated at 100 %. *The badge renders once Pages is enabled.*
- [ ] Fresh clone → `docker compose up` → `base-legal ingest` → `base-legal ask`
      in under 10 minutes with only an Anthropic key. *Validated up to `ask`
      (no Anthropic key in the build environment): with the image built,
      `up` → healthy in about 20 s and the default local-mode ingest in
      4 min 51 s on CPU; the image build itself (CPU torch + weights) adds
      several minutes on a fresh machine.*
- [x] Embedding validation gate run, with results published in the docs
      (`docs/evals/embedding-gate.md`).
- [x] A test proves the query path makes no network call to Voyage
      (`tests/integration/test_no_network.py`).
- [ ] MCP server tested in Claude Desktop and Claude Code. *Tested with the MCP
      SDK client over stdio; needs a run inside both hosts.*
- [ ] Docs live on GitHub Pages. *Workflow ready (`pages.yml`); Pages must be
      enabled with "GitHub Actions" as the source.* SECURITY.md,
      LEGAL_NOTICE.md and the "not legal advice" disclaimer are in place.
- [ ] Employer separation checklist passed: grep for prohibited terms, manual
      review, no internal data or names; commits use the GitHub noreply e-mail.
      *Needs the author's term list and review.*
- [ ] v0.1.0 tag, release notes, repo description and topics set. *Author.*
- [ ] Golden and red-team sets validated by a DPO (all items are `unverified`).
