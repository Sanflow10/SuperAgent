# ROADMAP — SuperAgent

> Issues versionadas com critério de aceitação. Status: `⬜ pendente` · `🟨 em andamento` · `✅ concluído`
> Prioridade: **P0** (bloqueia a versão) · **P1** (importa) · **P2** (desejável)

---

## V0.6 — Execução isolada de código (sandbox)

O coder passa a executar o que propõe, com isolamento em camadas.

| ID | Issue | Prioridade | Status |
|----|-------|-----------|--------|
| SA-101 | `SandboxTool` real: backend `bwrap` (unshare net/pid/user, root ro, workspace ro, tmpfs /tmp) | P0 | ✅ |
| SA-102 | Fallback sem bwrap: `subprocess` + `resource` (CPU, AS, FSIZE, NOFILE) + kill de process group no timeout — isolamento reduzido, documentado | P0 | ✅ |
| SA-103 | Tool `sandbox.execute` na allowlist (`core/policy.py`), gate por `ALLOW_SANDBOX` (default **false**) | P0 | ✅ |
| SA-104 | Planner aceita `sandbox.execute` com validação de `path` (relativo, sem `..`, sem absoluto) | P0 | ✅ |
| SA-105 | Orchestrator injeta `<sandbox_output>` no contexto do step (mesmo padrão do `filesystem.read`) | P0 | ✅ |
| SA-106 | Limites: `SANDBOX_TIMEOUT`, `SANDBOX_MEMORY_MB`, `SANDBOX_BACKEND` (auto/bwrap/plain) | P0 | ✅ |
| SA-107 | Testes: traversal, default-deny, execução real, timeout, exit code, fluxo no orquestrador | P0 | ✅ |
| SA-108 | `audit.sh`: `tools/sandbox.py` tratado à parte + checagem de limites/gate | P0 | ✅ |
| SA-109 | Backend `docker run --network none` como camada alternativa ao bwrap | P1 | ⬜ |
| SA-110 | Teste automatizado de que **rede está negada** no backend bwrap (script tenta socket → falha esperada) | P1 | ✅ |
| SA-111 | Política de wall-clock vs CPU-clock distinta (script em sleep infinito vs loop de CPU) | P1 | ⬜ |
| SA-112 | Limite de disco no sandbox (quota em dir temporário de execução) | P2 | ⬜ |
| SA-113 | Merge de steps: proposta do coder executada e criticada no mesmo step (reduz replans) | P2 | ⬜ |

**Critério de aceitação da V0.6:** SA-101..108 ✅ + `pytest` verde + `ruff`/`mypy` limpos + `audit.sh` PASS.

### V0.6 — Decision Engine (camada de decisão tipada)

O Critic vira fachada sobre um `DecisionEngine` pluggable (`core/decisions.py`).

| ID | Issue | Prioridade | Status |
|----|-------|-----------|--------|
| SA-114 | Abstração `DecisionEngine` + factory `DECISION_ENGINE=llm\|rules\|typed` (default `llm`) | P0 | ✅ |
| SA-115 | `CriticDecision.confidence` + `DECISION_MIN_CONFIDENCE`: APPROVE abaixo do limiar → `ESCALATE` e run interrompido (fail-closed, revisão humana) | P0 | ✅ |
| SA-116 | Engine `rules`: sanity gate determinístico offline (vazio / timeout / exit code / traceback → REJECT) — critic sem LLM | P1 | ✅ |
| SA-117 | Engine `typed`: endpoint OpenAI-compatible (`DECISION_URL`/`DECISION_MODEL`), temperature 0, JSON estrito — caminho de entrada para Jev/Laya/classificadores locais | P1 | ✅ |
| SA-118 | `audit.sh` [10]: decision layer fail-closed + limiar explícito | P1 | ✅ |
| SA-119 | Calibração do limiar com dados rotulados (shadow mode: engine `typed` vs `llm` comparados sem agir) | P1 | ⬜ |
| SA-120 | Metric: latência/custo do critic por engine (baseline para o benchmark "critic 68s → sub-segundo") | P2 | ✅ |

**SA-120 medido (2026-09-30, NIM real):** `rules` **0.00ms** (n=500) vs `llm` p50 **107.5s** / max 394.1s (n=3) vs `typed` p50 **70.9s** consistente (n=3) — `benchmarks/results.json`, harness `python -m tools.benchmark`.

**Critério de aceitação da Decision Engine:** SA-114..118 ✅ + run real com LLM (NIM) fechando `COMPLETED` + engine `typed` aprovado contra endpoint OpenAI-compatible real.

**Hardening do parser (2026-09-30, pós-run real):** `parse_json_llm` com `strict=False` (newline/controle literal dentro de string) e ordem **inteiro → fence → faixas** (JSON cujo `content` markdown contém fence ```` ``` ```` não é mais destruído antes do parse); diagnóstico das respostas crua em `logs/coder_unparseable.log`. Causa confirmada com as respostas reais do run `6c49b0e8`; 81 testes.

**Auditoria externa comparativa (2026-10-01, AdversaryGate × SuperAgent):** veredito "protótipo funcional, não certificado como produto". P0 do SuperAgent corrigido na sequência: build do pacote com descoberta explícita de pacotes (SA-001), `audit.sh` falha sem pytest (SA-002), CI público com matriz 3.11/3.12 + build/smoke (SA-003), fallback `auto → plain` não-silencioso com `SANDBOX_REQUIRE_ISOLATION` (SA-004). Pendências: SA-506 (TOCTOU, era SA-005) e SA-507 (era SA-006). Ver `SECURITY.md`.

---

## V0.7 — Memória e paralelismo

| ID | Issue | Prioridade | Status |
|----|-------|-----------|--------|
| SA-201 | Embeddings locais (Ollama `nomic-embed-text`) + busca semântica na memória (SQLite + sqlite-vec) | P0 | ⬜ |
| SA-202 | Retrieval: contexto montado por relevância ao objetivo, não só por recência (`core/orchestrator.py`) | P0 | ⬜ |
| SA-203 | Steps independentes do plano executados em paralelo (ThreadPool limitado por `MAX_PARALLEL_STEPS`) | P1 | ⬜ |
| SA-204 | Deduplicação de memória (hash de conteúdo) — memória vira base de conhecimento entre runs | P1 | ⬜ |
| SA-205 | Resumo de runs anteriores no início de um novo run (carry-over de lições) | P1 | ⬜ |
| SA-206 | Sub-agentes: planner pode delegar a um sub-orchestrator (depth real, hoje `depth` só valida) | P2 | ⬜ |

**Critério:** retrieval demonstradamente melhor que "últimos 20 registros" em tarefas multi-run.

---

## V0.8 — Ecossistema (MCP)

| ID | Issue | Prioridade | Status |
|----|-------|-----------|--------|
| SA-301 | Cliente MCP (`stdio`) — conectar ferramentas externas sem reescrever o core | P0 | ⬜ |
| SA-302 | Allowlist por domínio/servidor no `.env` (`MCP_ALLOWED=github,fs-read`); deny por default | P0 | ⬜ |
| SA-303 | Mapeamento ferramenta MCP → step do planner (descoberta vira capability do planner) | P0 | ⬜ |
| SA-304 | WebTool com allowlist de domínios + proxy de saída (deny by default) | P1 | ⬜ |
| SA-305 | Cache de respostas MCP + assinatura/versão pinada por servidor | P2 | ⬜ |

**Critério:** uma ferramenta MCP de terceiros roda num step com gate de política e trilha de auditoria.

---

## V1.0 — Conformidade como produto

| ID | Issue | Prioridade | Status |
|----|-------|-----------|--------|
| SA-401 | Trilha de auditoria imutável (append-only, hash encadeado por run) a partir dos logs JSON | P0 | ⬜ |
| SA-402 | Suite de evals com tarefas-ouro (golden tasks) + score por release (regressão de qualidade) | P0 | ⬜ |
| SA-403 | Relatório de compliance gerado (mapeia controles → evidências: limites, allowlist, testes) | P0 | ⬜ |
| SA-404 | Modo "humano no loop": aprovação interativa antes de `filesystem.write`/`sandbox.execute` — consumir o estado `ESCALATED` do SA-115 como ponto de pausa | P1 | ⬜ |
| SA-405 | Dashboard simples de runs (FastAPI + SQLite, local) | P2 | ⬜ |
| SA-406 | Empacotamento: `pipx install superagent` + imagem Docker assinada | P2 | ⬜ |

**Critério:** um auditor externo consegue reconstruir um run do V1.0 só com a saída do sistema.

---

## Backlog (sem versão atribuída)

- **SA-501** Fuzzing do `parse_json_llm` contra entradas maliciosas do modelo.
- **SA-502** Hot-reload de política sem reiniciar o processo.
- **SA-503** Suporte a outros runtimes locais (llama.cpp server, vLLM) atrás da interface `ModelRouter`.
- **SA-504** Multi-tenant: isolamento de workspace por tenant/run com quotas.
- **SA-505** Remoção de `restart: "no"` → wrapper de batch com retry limitado fora do compose.
- **SA-506** TOCTOU em `filesystem.write`: escrita com `O_NOFOLLOW`/`openat` (ou revalidação pós-`mkdir`) — bloqueia symlink trocado entre validação e escrita; urgente ao entrar o paralelismo (SA-203). Ver `SECURITY.md` (achado 3).
- **SA-507** Separar semanticamente `SANITY_PASS` de `APPROVE` no engine `rules` (auditoria externa 2026-10-01, SA-006): risco de produto — `APPROVE` do gate de marcadores não é revisão semântica.

## Riscos do portfólio

| Risco | Mitigação |
|---|---|
| Modelo local errar mais que cloud nos evals (SA-402) | Critic em temperatura 0 + evals antes de cada upgrade de modelo |
| Grandes frameworks copiarem o sandbox auditável | Empurrar compliance (V1.0) para produto, não código |
| Superfície crescente quebrar a promessa "audita em uma tarde" | Regra: todo código novo tem teste de regressão de segurança + linha no `audit.sh` |
