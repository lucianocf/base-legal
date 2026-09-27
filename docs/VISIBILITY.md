# Visibility Strategy

> Status: **draft for approval**.

## 1. Name

**Base Legal** (repo `base-legal`, PyPI `base-legal`, import `base_legal`,
CLI `base-legal`; all available on PyPI as of 2026-09-26).

- **Why:** a double meaning that every privacy professional gets instantly.
  *Base legal* is the LGPD's legal basis for processing (arts. 7 and 11), and
  it is also a legal knowledge base. It is short and pronounceable in English.
- **Weakness:** "base legal" is a common phrase, so the name alone does little
  for search. Mitigation: a strong description, topics and a tagline that
  carries the hook ("cites down to the inciso").
- **Also considered:** `inciso` (precision, brandable), `citalei` (strong in
  Brazil, weak abroad), `lexcite` (global, generic), `lgpd-grounded` (best for
  search, no brand), `vigente` (tied to the Phase 3 point-in-time feature).
- **Rule:** never use "ANPD" or "gov" in names, logos or domains, since that
  suggests official endorsement.

## 2. Repository metadata

- **Description:** *Grounded, verifiable Q&A over Brazilian data protection law
  (LGPD + ANPD). Every answer cites the exact article and inciso, machine-checked.
  Privacy-by-design, threat-modeled, eval-gated. MCP server included.*
- **Topics:** `lgpd`, `rag`, `llm`, `claude`, `mcp`, `mcp-server`,
  `privacy-engineering`, `data-protection`, `llm-security`, `owasp-llm`,
  `pgvector`, `fastapi`, `legal-tech`, `brazil`, `retrieval-augmented-generation`
  (GitHub allows 20).
- **Social preview image:** a dark card with the name, the tagline and a
  sample verified citation.
- **Website field:** the GitHub Pages URL.

## 3. README structure (EN, mirrored in README.pt-BR.md)

1. **Hero:** name, one-line tagline, badges (CI, evals, OpenSSF Scorecard,
   license, Python version), and a GIF of a question → answer → verified
   citations → a refusal on an unsupported question.
2. **Why this is different:** three bullets: verified citations with strict
   refusal; privacy by design (it complies with the LGPD it explains);
   threat-modeled and eval-gated.
3. **Quickstart:** three commands (`docker compose up -d`, `base-legal ingest`,
   `base-legal ask "..."`), plus the MCP config snippet for Claude Desktop/Code.
4. **How it works:** the architecture diagram and a link to ARCHITECTURE.md.
5. **Evaluation:** a metrics table generated from the last CI run and a link to
   the full report on Pages.
6. **Security and privacy:** summary with links to THREAT_MODEL.md, PRIVACY.md and SECURITY.md.
7. **Corpus and legal notice:** the sources, the redistribution basis, and
   "not legal advice; not affiliated with the ANPD".
8. **Roadmap:** with LAI × LGPD highlighted as next.
9. **Author:** name, "DPO and information security, public sector" (no
   employer), and links to LinkedIn and Upwork.

## 4. Launch plan

| When | Channel | Content |
|---|---|---|
| v0.1.0 day | **LinkedIn** (PT) | Launch post: problem → hook → GIF → link. Tag privacy and AI communities. |
| +3 days | LinkedIn (PT) | "Why my RAG refuses to answer": strict grounding and the validator |
| +1 week | LinkedIn (EN) | "Threat modeling an LLM app with STRIDE + OWASP LLM Top 10", with the table |
| +2 weeks | LinkedIn (PT) | "Privacy by design in practice: the RAG's own ROPA" |
| +2 weeks | **dev.to / Medium** (EN) | Technical deep dive: structural chunking of statutes and verified citations |
| After MCP is tested | **Official MCP Registry**, `awesome-mcp-servers` | Listing as a legal/privacy MCP server |
| After evals stabilize | `awesome-llm-security`, `awesome-rag` (or similar lists) | PRs following each list's contribution rules |
| Ongoing | Brazilian privacy communities (e.g. ANPPD, IAPP Brazil KnowledgeNet, Data Privacy Brasil events), OWASP Brazil chapters, Python Brasil groups | Talks, lightning talks, posts |
| Phase 2 | LinkedIn + public-sector forums | LAI × LGPD launch: the public-sector angle |

Every community and list above must be checked for **existence, activity and
contribution rules** before posting. Never spam; one quality post per channel.

## 5. Signals that build credibility

- A green CI and eval badge on the first screen.
- ADRs that explain trade-offs honestly (what was rejected and why).
- Small, focused commits with Conventional Commit messages; releases with changelogs.
- Security features that are **tested**, not only claimed.
- Issues labeled `good first issue` (e.g. "add a resolution parser") to invite contributors.
