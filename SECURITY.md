# Segurança — SuperAgent

> Última auditoria: **2026-09-30** · método: leitura + reprodução local
> (nada reportado sem prova) · 86 testes · `audit.sh` PASS

## Princípios

1. **Fail-closed** — o estado seguro é REJECT/ESCALATE. Decisão desconhecida
   vira `REJECT`; confidence ausente com limiar explícito vira `ESCALATE`.
2. **Deny-by-default** — sandbox desligada por padrão (`ALLOW_SANDBOX=false`);
   allowlist de tools (`core/policy.py`); caminho de escrita confinado ao workspace.
3. **A política está em código, não no LLM** — o modelo propõe; schema pydantic,
   validação de path e Supervisor autorizam. Injeção de prompt não anda sozinha:
   qualquer conteúdo injetado ainda passa pelas mesmas validações de código.

## Auditoria 2026-09-30

### Achado 1 — ALTA · vazamento de segredos no backend `plain` · CORRIGIDO

O backend `plain` (fallback quando não há bwrap) executava o código gerado
com **o ambiente completo do processo pai** — incluindo `NVIDIA_API_KEY`,
`ANTHROPIC_API_KEY`, `DECISION_API_KEY` — e **não negava rede**. Código
gerado pelo LLM podia ler e exfiltrar credenciais do host.

- **Prova**: script no sandbox imprimia `os.environ["VAZAO_TEST_SECRET"]`
  definido no pai → retornava o valor.
- **Correção**: `tools/sandbox.py` `_spawn(inherit_env=False)` para o
  `plain` — env mínimo (`PATH`, `HOME`, `LANG`, `PYTHONDONTWRITEBYTECODE`).
  O bwrap já limpa o env interno com `--clearenv`.
- **Regressão**: `tests/test_sandbox.py::test_plain_backend_does_not_inherit_parent_env`

### Achado 2 — MÉDIA · APPROVE sem `confidence` ignorava o limiar · CORRIGIDO

Com `DECISION_MIN_CONFIDENCE > 0`, um `APPROVE` cujo motor não informa
`confidence` (ex.: engine `rules`) passava direto — o limiar exigia o número
e não recebia, mas a comparação `confidence < min` era pulada.

- **Correção**: `core/orchestrator.py` — confidence ausente + limiar
  explícito ⇒ `ESCALATE` e run interrompido para revisão humana.
- **Regressão**:
  `tests/test_orchestrator.py::test_approve_sem_confidence_escalate_com_limiar_explicito`

### Achado 3 — BAIXA · TOCTOU em `filesystem.write` · LATENTE (backlog)

`safe_target()` valida com `resolve()` + `relative_to` e a escrita acontece
depois; entre os dois, um atacante com escrita concorrente no workspace
poderia trocar um diretório por symlink. Hoje é **inalcançável** (execução
sequencial de steps; workspace montado read-only no bwrap), mas torna-se
real com steps paralelos (SA-203). Correção prevista: abrir com
`O_NOFOLLOW`/`openat` ou revalidar após `mkdir`.

### Verificado e seguro

- **Path traversal / symlink escape** — `resolve()` + `relative_to` negam
  `..`, caminho absoluto e symlink para fora; testes de traversal/absoluto.
- **Segredos no repositório** — varredura em arquivos versionados: nenhuma
  chave; `.env` ignorado; logs de runs sem `Bearer`/`nvapi-`.
- **Escape de tags de contexto** — `</sandbox_output>` e `</file>` são
  escapados antes de virarem contexto; conteúdo injetado afeta só a
  percepção do LLM, nunca o caminho de autorização (validação em código).
- **Conjunto fechado de decisão** — `fail_closed()` normaliza valor
  desconhecido para `REJECT` com log `invalid_critic_decision`.
- **Sandbox bwrap** — `--clearenv`, sem rede (`--unshare-net`), sistema
  read-only, `tmpfs /tmp`, `PATH` mínima; teste de rede: script que tenta
  socket recebe `NET_DENIED`.

## Limites declarados

- O backend `plain` **não nega rede** (só o bwrap) — use bwrap em produção.
- A política de palavras-chave (`FORBIDDEN_PATTERNS`) é heurística de
  defesa em profundidade, não barreira de segurança.
- Auditoria estática + reprodução local; não substitui pentest externo.

## Reportando uma vulnerabilidade

Abra uma **issue** no repositório com passos de reprodução. Correções são
priorizadas por: impacto (segredos > execução fora do workspace > política).
