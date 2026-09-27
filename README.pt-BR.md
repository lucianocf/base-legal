# Base Legal

**Cada afirmação cita um inciso — e uma máquina confere.**

Perguntas e respostas verificáveis sobre a legislação brasileira de proteção
de dados (LGPD, Lei de Acesso à Informação e resoluções do Conselho Diretor da ANPD). As respostas citam o
artigo, o parágrafo e o inciso exatos; cada citação é conferida, literalmente,
contra o texto oficial antes de chegar a você, e quando nada no corpus sustenta
uma resposta, o Base Legal diz isso. Privacidade desde a concepção, modelo de
ameaças, avaliações automáticas. Inclui servidor MCP.

[![CI](https://github.com/lucianocf/base-legal/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianocf/base-legal/actions/workflows/ci.yml)
[![Evals](https://github.com/lucianocf/base-legal/actions/workflows/evals.yml/badge.svg)](https://github.com/lucianocf/base-legal/actions/workflows/evals.yml)
[![recall@5](https://img.shields.io/endpoint?url=https://lucianocf.github.io/base-legal/badges/recall-at-5.json)](https://lucianocf.github.io/base-legal/evals/)
[![red-team](https://img.shields.io/endpoint?url=https://lucianocf.github.io/base-legal/badges/redteam.json)](https://lucianocf.github.io/base-legal/evals/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/lucianocf/base-legal/badge)](https://scorecard.dev/viewer/?uri=github.com/lucianocf/base-legal)
[![Licença: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)

> **Não é aconselhamento jurídico.** O Base Legal é uma ferramenta de pesquisa,
> sem vínculo com a ANPD nem com o governo federal. Veja o
> [LEGAL_NOTICE.md](LEGAL_NOTICE.md). 🇺🇸 [Read in English](README.md).

<!-- TODO(author): substituir por um GIF de pergunta → resposta → citações verificadas → recusa. -->
![Demonstração: uma pergunta, uma resposta com citações numeradas ao texto oficial e uma recusa](docs/assets/demo-placeholder.svg)

## O que tem de diferente

- **Citações verificadas e recusa estrita.** O Claude responde a partir dos
  dispositivos recuperados, com Citations nativas; cada trecho citado é
  conferido literalmente no dispositivo que cita. O que não tiver sustentação
  é substituído por "sem base no corpus" e pelos dispositivos mais próximos
  (apenas texto oficial).
- **Cumpre a lei que explica.** As perguntas são convertidas em vetores
  **localmente** (modelo aberto `voyage-4-nano`), então nenhum provedor de
  embeddings as recebe; CPF, CNPJ, e-mail e telefone são removidos antes da
  única chamada a terceiros; nada é armazenado; os logs não têm conteúdo.
  Veja o [PRIVACY.md](docs/PRIVACY.md).
- **Modelo de ameaças e avaliações no CI.** STRIDE + OWASP Top 10 para LLMs
  ([THREAT_MODEL.md](docs/THREAT_MODEL.md)); avaliações de recuperação e de
  red team rodam em todo pull request, sem segredos; pesos de modelo e GitHub
  Actions fixados por hash.

## Início rápido

Requisitos: Docker. Uma [chave da API da Anthropic](https://console.anthropic.com/)
para respostas geradas (a busca, o modo de busca da interface web e o servidor
MCP funcionam sem ela).

```bash
git clone https://github.com/lucianocf/base-legal.git && cd base-legal
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env            # ignorado pelo git; opcional
docker compose up -d --build                         # PostgreSQL + app, em 127.0.0.1
docker compose exec app base-legal ingest            # uma vez; vetoriza a lei na sua CPU
docker compose exec app base-legal ask "Qual o prazo para comunicar um incidente de segurança à ANPD?"
```

Depois abra <http://127.0.0.1:8000> para a interface web local, ou use a API
(`POST /ask`, `POST /search`, `GET /provisions/{id}`, `GET /provisions/{id}?at=AAAA-MM-DD`
para a redação vigente numa data passada, documentação em `/docs`).

Sem Docker: `uv sync --extra local`, `uv run base-legal model fetch`, aponte
`DATABASE_URL` para um PostgreSQL com pgvector e use os mesmos comandos
`base-legal ingest` / `ask` / `serve` via `uv run`.

### MCP (Claude Desktop, Claude Code)

Um servidor MCP somente leitura oferece `search_provisions`, `get_provision` e
`verify_citation`; o modelo do seu host MCP escreve a resposta e o Base Legal
não chama nenhum terceiro:

```bash
claude mcp add base-legal \
  --env DATABASE_URL=postgresql://base_legal:base_legal@localhost:5432/base_legal \
  -- uv --directory /caminho/absoluto/para/base-legal run base-legal mcp
```

Configuração do Claude Desktop: [docs/MCP.md](docs/MCP.md).

## Como funciona

```
pergunta ─▶ remoção de PII ─▶ vetor local (voyage-4-nano) ─┐
                            └▶ busca textual no PostgreSQL ─┼▶ fusão RRF ─▶ top-k dispositivos
                                                            │   (+ consulta direta de "art. 7º, IX")
top-k ─▶ Claude (um documento citável por dispositivo) ─▶ validador de citações ─▶ resposta ou recusa
```

- **Análise estrutural** dos textos oficiais numa árvore de dispositivos com
  identificadores estáveis: `lgpd:art7:incIX`, `lgpd:art65:incI-A`,
  `res-anpd-15-2024:anx1:art6` ([ADR 0002](docs/adr/0002-structural-chunking-canonical-ids.md),
  [ADR 0010](docs/adr/0010-annex-segment-in-provision-ids.md)).
- **Recuperação híbrida** no PostgreSQL: busca textual normalizada pelo
  tamanho e pgvector, fundidas por Reciprocal Rank Fusion, com parte da
  pontuação de cada resultado propagada ao artigo a que pertence
  ([ADR 0004](docs/adr/0004-postgres-hybrid-search-rrf.md)).
- **Geração fundamentada** com Citations do Claude, um documento por
  dispositivo, de modo que cada citação aponta para um identificador canônico
  ([ADR 0005](docs/adr/0005-strict-grounding-verified-citations.md),
  [ADR 0011](docs/adr/0011-one-cited-document-per-provision.md)).
  Modelo padrão `claude-haiku-4-5`; `BASE_LEGAL_MODEL=claude-sonnet-5` para mais qualidade.

Detalhes: [ARCHITECTURE.md](docs/ARCHITECTURE.md) e os [ADRs](docs/adr/).

## Avaliação

Conjunto de referência: 45 perguntas sintéticas respondíveis e 8 que devem ser
recusadas (`evals/golden.yaml`, pendente de revisão por um DPO), divididas em
dev (usado para ajuste) e holdout (usado só para confirmar). Recuperação em
modo `local` (voyage-4-nano para documentos e perguntas), como no CI:

| Divisão | recall@5 | recall@10 | MRR | Acerto de recusas | Recusas indevidas |
|---|---|---|---|---|---|
| dev (31 + 5) | 67,7 % | 79,0 % | 0,474 | 60,0 % | 0,0 % |
| holdout (14 + 3) | 67,9 % | 82,1 % | 0,393 | 66,7 % | 0,0 % |

Antes do ajuste, o recall@5 no holdout era 42,9 %. O conjunto de red team
(injeção de prompt, dados pessoais, citações falsas, XSS, entrada gigante)
passa nas 13 verificações determinísticas. O teste de validação de embeddings
comparou cinco configurações, e vetorizar a lei com o mesmo modelo local ficou
em primeiro lugar, à frente dos vetores de documentos do `voyage-4-large`
([resultados](docs/evals/embedding-gate.md), [ADR 0013](docs/adr/0013-voyage-4-nano-for-documents-by-default.md)).
Relatórios completos: [docs/evals/](docs/evals/).

## Segurança e privacidade

- [THREAT_MODEL.md](docs/THREAT_MODEL.md): fluxos de dados, fronteiras de
  confiança, STRIDE e OWASP Top 10 para aplicações com LLM (2025), cada
  controle ligado a um teste.
- [PRIVACY.md](docs/PRIVACY.md): o inventário de dados do próprio software
  (no estilo de um ROPA): o que é tratado, para onde vai e por quanto tempo.
- [SECURITY.md](SECURITY.md): como relatar uma vulnerabilidade.

## Corpus e aviso legal

LGPD (Lei nº 13.709/2018, texto compilado), LAI (Lei nº 12.527/2011, texto
compilado) e Resoluções CD/ANPD nº 1/2021,
2/2022, 4/2023, 15/2024, 18/2024 e 19/2024 (Anexo I), obtidas de
planalto.gov.br, gov.br/anpd e do Diário Oficial da União. Atos oficiais não
são protegidos por direitos autorais (Lei nº 9.610/1998, art. 8º, IV); a
procedência e os hashes estão em `corpus/manifest.yaml`. Veja o
[LEGAL_NOTICE.md](LEGAL_NOTICE.md).

## Próximos passos

- **A seguir: LAI × LGPD.** Lei nº 12.527/2011 (Lei de Acesso à Informação) e a
  tensão entre transparência e proteção de dados no setor público.
- Remissões resolvidas ("nos termos do art. 11" vira um link).
- Anexo II da Res. CD/ANPD nº 19/2024 (cláusulas-padrão contratuais).
- Um explorador estático do corpus no GitHub Pages; um reranker local, se as
  avaliações mostrarem ganho.
- Consultas no tempo, entre as versões históricas da LGPD.

Plano completo: [PLAN.md](docs/PLAN.md). Contribuições: [CONTRIBUTING.md](CONTRIBUTING.md).

## Autoria

<!-- TODO(author): nome, "DPO e segurança da informação, setor público", links do LinkedIn e do Upwork. -->

## Licença

Código: [Apache-2.0](LICENSE). Conjuntos de avaliação e documentação: CC BY 4.0.
Leis e resoluções: atos oficiais, não protegidos por direitos autorais.
