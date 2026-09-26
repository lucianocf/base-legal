# Privacy by Design

> Status: **initial draft**. This project explains the LGPD, so it has to
> comply with it. This document is the privacy record of the software itself:
> a ROPA-style inventory of what it processes, where data goes and for how long.

## 1. Roles

Base Legal is software you run yourself. **Whoever deploys it is the
*controlador* (controller)** for any personal data in the questions
submitted to that deployment. The project maintainers operate no service and
receive no data.

In a typical deployment, the third-party APIs act as **operadores**
(processors) on behalf of the deployer:

| Processor | Purpose | Data sent | Notes |
|---|---|---|---|
| Anthropic (Claude API) | Answer generation | The **redacted** question + retrieved public provisions | Commercial API terms; `TODO(verify)` current retention period and training policy at each release |
| Voyage AI | Embeddings | Provision text (public) at ingestion; the **redacted** question at query time | **Trains on customer content by default.** Opting out is **mandatory** for Base Legal deployments (see §4) |

Both involve an international data transfer (LGPD arts. 33 to 36;
Res. CD/ANPD nº 19/2024). Choosing the mechanism is the deployer's
responsibility, and the README says so.

## 2. Data inventory

| Data | Source | Personal data? | Where it lives | Retention | Legal basis (for the deployer) |
|---|---|---|---|---|---|
| Corpus (laws, resolutions) | Official publications | No | `corpus/`, PostgreSQL | Until the next snapshot | N/A (public acts) |
| User question, original | User | **Possibly** (incidental) | Process memory only | Duration of the request | Deployer's choice (usually art. 7, V or IX) |
| User question, redacted | `privacy` module | Reduced | Sent to Voyage and Anthropic; not stored locally | Per processor terms | Same as above |
| Answer | Claude | Possibly (echoes the question) | Returned to the user; not stored | Duration of the request | Same as above |
| Operational logs | Application | **No content**: request ID, timings, token counts, redaction counts, error codes | stdout → Docker log driver | 7 days by default (log rotation) | Legitimate interest in security (art. 7, IX; art. 46) |
| Debug question log | Opt-in (`BASE_LEGAL_LOG_QUESTIONS=true`) | Redacted question | Local log | Same rotation; off by default | Deployer must justify |
| Golden/red-team eval sets | Maintainers | **No** (synthetic questions only) | `evals/` | Versioned | N/A |

**Not collected:** accounts, cookies, analytics, IP addresses in application
logs (a reverse proxy, if the deployer adds one, is outside this inventory),
and conversation history.

## 3. Controls (principles of LGPD art. 6)

| Principle | Implementation |
|---|---|
| Purpose (I) and adequacy (II) | The question is used only to answer that request |
| **Necessity (III)**: minimization | PII redaction before any processor; no persistence of questions or answers; content-free logs |
| Transparency (VI) | This document, the README and the UI notice ("do not include personal data; questions are sent to Anthropic and Voyage after redaction") |
| **Security (VII)** and prevention (VIII) | See [THREAT_MODEL.md](THREAT_MODEL.md): secrets management, supply chain controls, strict CSP, localhost binding by default |
| Accountability (X) | Tests that prove the controls: a log-capture test asserting no question text is logged, and redaction unit tests |

### PII redaction (MVP)
- **Detected:** CPF and CNPJ (with check-digit validation to reduce false
  positives), e-mail, Brazilian phone numbers.
- **Replaced by** typed placeholders (`[CPF_1]`, `[EMAIL_1]`). The mapping is
  not kept; the original value never leaves the process.
- **Known limitation:** names, addresses and free-text health data are not
  reliably detected. The UI and docs tell users not to include them.
  NER-based detection is on the roadmap if a Portuguese model of good enough
  quality fits the footprint.

## 4. Mandatory processor settings

1. **Voyage AI:** opt out of training in the dashboard (Organization → Terms of
   Service → *Opted Out*). Per Voyage's FAQ, this requires a payment method and
   an org Admin, may **void free-token credits**, and applies only to data sent
   *after* the opt-out. **Opt out before the first ingestion.** Cost impact for
   this corpus: `TODO(verify)` with current pricing (expected to be cents).
2. **Anthropic:** set a monthly spend limit in the Console; review the current
   data retention terms (`TODO(verify)`).

## 5. Why there is no RIPD (DPIA) yet

A RIPD (LGPD art. 38) assesses a *processing operation*. In the MVP, the
maintainers process no personal data; each deployer processes their own
users' questions under their own context. A generic RIPD would be theater.
Instead this project provides:
- this inventory and data-flow description, which a deployer can reuse in
  their own ROPA or RIPD;
- a **real RIPD in Phase 3**, when the maintainers operate a hosted demo and
  become controllers themselves.

## 6. Data subject rights

Because the software stores nothing about users, requests under art. 18 are
satisfied by design for local use. For a deployment, the deployer is the
point of contact. Processors' retention is governed by their terms (§1).

## 7. Review

Reviewed at every release and whenever a new processor, data flow or
interface is added. Last review: 2026-09-26 (initial draft).
