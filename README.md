# SuperAgent

[![CI](https://github.com/Sanflow10/SuperAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/Sanflow10/SuperAgent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> ### O LLM propõe. A política decide. O humano escala.

**SuperAgent é um runtime limitado para agentes LLM — um firewall para agentes.**
Toda decisão cruza um motor *fail-closed* (`APPROVE | REJECT | ESCALATE`), toda
ação roda dentro de um sandbox do sistema operacional, todo run termina em log
auditável. **O modelo nunca tem a última palavra.**

**The model proposes. Policy disposes. Humans escalate.**
A bounded runtime for LLM agents: fail-closed decision engine, OS-level sandbox,
full audit trail. The LLM never gets the last word.

```bash
git clone git@github.com:Sanflow10/SuperAgent.git && cd SuperAgent
python main.py "seu objetivo" --output resultado.json
```

- **Fail-closed por design** — confidence não é autorização: abaixo do limiar,
  APPROVE vira `ESCALATE` e o run **para** na mão de um humano.
- **Sandbox do SO** — bwrap com namespaces, sem rede, sem herdar segredos do host;
  deny-by-default (`ALLOW_SANDBOX=false`).
- **Decision engine pluggable** — `llm` (clássico), `rules` (determinístico,
  offline), `typed` (endpoint OpenAI-compatible: Jev, Laya, classificador local).
- **Prova real** — runs executados contra LLM de verdade, `COMPLETED`, com
  sandbox e critic; 86 testes; `audit.sh` com 10 checagens.

## Novidades da V0.6 — sandbox de execução

A tool `sandbox.execute` executa scripts Python gerados pelo coder com
isolamento em camadas (deny by default — exige `ALLOW_SANDBOX=true`):

- **bwrap** (preferido): namespaces user/pid/net/ipc/uts, filesystem
  read-only (somente script + venv montados), tmpfs em `/tmp`, **sem rede**.
- **plain** (fallback, quando não há bwrap): subprocess com `RLIMIT_CPU`,
  `RLIMIT_AS`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`, process group e timeout
  com `killpg` — isolamento reduzido (não nega rede), documentado.
- Limites: `SANDBOX_TIMEOUT`, `SANDBOX_MEMORY_MB`, `SANDBOX_MAX_OUTPUT`,
  `SANDBOX_BACKEND` (auto|bwrap|plain).
- **Fallback declarado, nunca silencioso** (auditoria externa SA-004): o modo
  `auto` loga o evento `sandbox_backend_fallback` ao cair para `plain`, e
  `SANDBOX_REQUIRE_ISOLATION=true` **nega o fallback** (exige bubblewrap —
  `plain` explícito também é recusado nesse modo).
- O stdout/exit code volta como `<sandbox_output>` no contexto do step e
  é avaliado pelo Critic como qualquer outro resultado.

## Novidades da V0.6 — Decision Engine (camada de decisão tipada)

O Critic agora delega a avaliação a um `DecisionEngine` pluggable
(`core/decisions.py`), selecionável por `DECISION_ENGINE`:

| Engine | O que é | Rede | Uso |
|---|---|---|---|
| `llm` (default) | LLM gera JSON estrito (`APPROVE`/`REJECT`) | Ollama | Comportamento clássico |
| `rules` | Sanity gate determinístico: vazio, `[TIMEOUT]`, `[exit_code=]`, traceback → REJECT | nenhuma | Offline / fallback / auditoria |
| `typed` | Endpoint OpenAI-compatible de decisão tipada (Jev via gateway, Laya, classificador local), temperature 0 | HTTP | Decisão barata e rápida |

Princípios (fail-closed, alinhado ao padrão decision-layer):

- **Confidence não é autorização.** Se o motor retorna
  `confidence < DECISION_MIN_CONFIDENCE`, o orquestrador converte APPROVE
  em `ESCALATE` e **interrompe o run** para revisão humana — probabilidade
  nunca vira efeito colateral sozinha.
- **Conjunto fechado de decisões**: `APPROVE | REJECT | ESCALATE`;
  qualquer valor desconhecido é normalizado para `REJECT`.
- **Autorização continua no Supervisor/Policy (código)** — o motor de
  decisão só emite sinais; tools e limites nunca dependem dele.
- `rules` e `typed` resolvem o problema do critic lento: sem LLM (rules)
  ou decisão tipada em um único POST (typed).

### Números — latência do critic por engine (SA-120)

Mesma entrada, mesmo dia, NIM real (`z-ai/glm-5.3-flash`), 2026-09-30 —
`python -m tools.benchmark`, dados brutos em `benchmarks/results.json`:

| Engine | n | mean | p50 | max | Decisões |
|---|---|---|---|---|---|
| `rules` | 500 | **0.00 ms** | 0.00 ms | 0.03 ms | APPROVE×500 |
| `llm` | 3 | 201.3 s | 107.5 s | 394.1 s | REJECT×3 |
| `typed` (NIM) | 3 | 72.8 s | 70.9 s | 77.8 s | APPROVE×3 |

- **De minutos para sub-milissegundo**: o gate determinístico é a ordem de
  grandeza que torna run de CI/teste viável sem LLM.
- `typed` fez POST direto (sem hop de shim) e foi **consistente**
  (69.7–77.8s, sem estouro) — com classificador **local** (Jev/Laya na
  mesma máquina) essa mesma interface cai para o tempo do modelo local.
- Decisões divergem **por desenho**: `rules` é gate de marcadores
  (vazio / timeout / exit≠0 / traceback), `llm` julga semântica —
  REJECT×3 na mesma entrada que `rules` aprovou é julgamento, não bug.

## Arquitetura

```
main.py
  └── Orchestrator (core/orchestrator.py)
        ├── Supervisor   (core/supervisor.py)   → limites + política
        ├── Planner      (agents/planner.py)    → plano JSON validado
        ├── Researcher   (agents/researcher.py) → análise
        ├── Coder        (agents/coder.py)      → proposta de arquivos
        ├── Critic       (agents/critic.py)     → fachada sobre o DecisionEngine
        │     └── DecisionEngine (core/decisions.py) → llm | rules | typed
        ├── ToolRegistry (tools/registry.py)
        │     └── FilesystemTool (tools/filesystem.py)
        ├── MemoryStore  (core/memory.py)       → SQLite (WAL)
        └── ModelRouter  (core/model_router.py) → Ollama /api/chat
```

## Fluxo de execução

1. O objetivo passa pela política (`core/policy.py`).
2. O Planner gera um plano JSON, validado por Pydantic + `validate_plan`.
3. Cada step é autorizado pelo Supervisor (steps, tempo, profundidade, tool).
4. `filesystem.read` injeta o conteúdo do arquivo no contexto do step.
5. Researcher ou Coder executam o step; o Critic avalia (APPROVE / REJECT).
6. REJECT → feedback volta ao Planner → replan (máximo `MAX_REPLANS`).
7. Coder com `tool: filesystem.write` → escrita transacional no workspace,
   com rollback se qualquer arquivo falhar.

## Modelo de segurança (defense-in-depth)

- Política de conteúdo bloqueia objetivos maliciosos (patterns PT/EN).
- Allowlist de tools: `filesystem.read`, `filesystem.write` e
  `sandbox.execute` (deny by default, exige `ALLOW_SANDBOX=true`).
- Caminhos relativos, sem `..`, sem absolutos, sem symlink, `relative_to`
  obrigatório no workspace (protege contra travessia e prefixo).
- Escrita multiarquivo transacional com rollback.
- `ALLOW_SHELL` / `ALLOW_NETWORK` desligados por padrão; WebTool e
  SandboxTool desabilitadas na V0.5.
- Docker: non-root (`USER agent`), `read_only`, `cap_drop: ALL`,
  `no-new-privileges`, limites de memória/CPU, `restart: "no"`.
- Injeção de prompt: conteúdo lido vai entre tags `<file>` tratado como DADO;
  o Critic é o backstop de cada step.
- Limites de execução: steps, replans, profundidade, tempo de vida,
  tamanho de contexto e de leitura.

## Requisitos

- Python >= 3.11
- Ollama rodando localmente com os modelos do `.env`
  (`qwen3:8b`, `qwen2.5-coder:7b` por padrão)

## Instalação

```bash
make install
```

## Uso

```bash
# planeja sem executar nada
python main.py --dry-run "crie um script de backup incremental"

# executa
python main.py "crie um script de backup incremental"

# com saída em arquivo
python main.py "objetivo" --output resultado.json

# via make
make run GOAL="seu objetivo"
```

## Testes e auditoria

```bash
make test        # pytest
make lint        # ruff
make typecheck   # mypy
./audit.sh       # auditoria estrutural + testes
```

## Docker

```bash
docker compose up --build -d
docker compose exec superagent python main.py "objetivo"
```

## Configuração

- `.env` → precedência máxima (variáveis de ambiente)
- `config/config.yaml` → valores default
- Ver `.env.example` para a lista completa de chaves.

## Estrutura

| Caminho            | Função                                  |
|--------------------|-----------------------------------------|
| `core/`            | config, política, supervisor, roteamento |
| `agents/`          | planner, researcher, coder, critic       |
| `tools/`           | filesystem (registry, web, sandbox)      |
| `tests/`           | pytest (unit + integração com fakes)     |
| `workspace/`       | arquivos produzidos pelo coder           |
| `memory/`          | SQLite de memória por run                |
| `logs/`            | logs JSON rotativos                      |

## Licença

[MIT](LICENSE) — fork, use comercialmente e contribua liberamente.
GitHub mostra a licença na barra lateral; sem ela, usar o projeto seria
tecnicamente violação de direitos autorais.
