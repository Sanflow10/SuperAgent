#!/usr/bin/env bash
set -u

FAIL=0
SCAN=/tmp/superagent_audit_scan.txt

printf '%s\n' '============================================================'
printf '%s\n' '              SUPERAGENT V0.6 AUDIT'
printf '%s\n' '============================================================'

printf '\n[1] Python\n'
command -v python3 >/dev/null 2>&1 && python3 --version || { echo "ERRO: python3"; FAIL=1; }

printf '\n[2] Estrutura\n'
for item in agents core tools tests memory workspace sandbox config logs \
            main.py pyproject.toml Dockerfile docker-compose.yml \
            .dockerignore .env.example README.md; do
    if [[ -e "$item" ]]; then
        printf 'OK    %s\n' "$item"
    else
        printf 'FALHA %s\n' "$item"
        FAIL=1
    fi
done

printf '\n[3] .env protegido do Docker build\n'
if grep -qxF '.env' .dockerignore; then
    printf 'OK\n'
else
    printf 'FALHA\n'; FAIL=1
fi

printf '\n[4] Shell/exec arbitrarios\n'
# tools/sandbox.py é o ponto controlado de execução (V0.6) — verificado em [9]
if grep -RInE --exclude=sandbox.py 'shell=True|os\.system|os\.popen|os\.exec|os\.spawn|subprocess\.(Popen|run|call|check_call|check_output)|pty\.spawn|multiprocessing|\beval\(|\bexec\(' \
    agents core tools main.py > "$SCAN" 2>/dev/null; then
    cat "$SCAN"
    printf 'ATENCAO: possivel exec encontrada.\n'; FAIL=1
else
    printf 'OK\n'
fi

printf '\n[5] Docker non-root\n'
if grep -qE '^USER[[:space:]]+agent' Dockerfile; then
    printf 'OK\n'
else
    printf 'FALHA\n'; FAIL=1
fi

printf '\n[6] restart policy\n'
if grep -qE 'restart:[[:space:]]*unless-stopped' docker-compose.yml 2>/dev/null; then
    printf 'FALHA: restart loop em workload batch\n'; FAIL=1
else
    printf 'OK\n'
fi

printf '\n[7] Testes\n'
if command -v pytest >/dev/null 2>&1; then
    if pytest -q; then
        printf 'OK: testes passaram\n'
    else
        printf 'FALHA: testes falharam\n'; FAIL=1
    fi
else
    # Auditoria externa 2026-10-01 (SA-002): PASS sem rodar testes
    # não é auditoria. pytest ausente = falha, não aviso.
    printf 'FALHA: pytest nao instalado (testes sao obrigatorios)\n'
    FAIL=1
fi

printf '\n[8] safe_target usa relative_to\n'
if grep -q 'relative_to' tools/filesystem.py; then
    printf 'OK\n'
else
    printf 'FALHA: sandbox sem relative_to\n'; FAIL=1
fi

printf '\n[9] Sandbox V0.6 (execucao isolada)\n'
if [[ -f tools/sandbox.py ]] \
 && grep -q 'ALLOW_SANDBOX' tools/sandbox.py \
 && grep -qE 'RLIMIT_CPU|killpg' tools/sandbox.py \
 && grep -q 'unshare-net' tools/sandbox.py; then
    printf 'OK: deny-by-default + limites + bwrap\n'
else
    printf 'FALHA: sandbox sem isolamento esperado\n'; FAIL=1
fi
if grep -qxF 'ALLOW_SANDBOX=false' .env.example; then
    printf 'OK: ALLOW_SANDBOX deny by default\n'
else
    printf 'FALHA: ALLOW_SANDBOX nao e deny by default\n'; FAIL=1
fi

printf '\n[10] Decision layer V0.6 (fail-closed)\n'
if [[ -f core/decisions.py ]] \
 && grep -q 'fail_closed' core/decisions.py \
 && grep -q 'ESCALATE' core/orchestrator.py \
 && grep -qxF 'DECISION_ENGINE=llm' .env.example; then
    printf 'OK: engine pluggable + ESCALATE + fail-closed\n'
else
    printf 'FALHA: decision layer incompleta\n'; FAIL=1
fi
if grep -qxF 'DECISION_MIN_CONFIDENCE=0.0' .env.example; then
    printf 'OK: min_confidence explicito (sem autorizacao implicita)\n'
else
    printf 'FALHA: DECISION_MIN_CONFIDENCE ausente\n'; FAIL=1
fi

printf '\n============================================================\n'
if [[ "$FAIL" -eq 0 ]]; then
    printf 'AUDITORIA: PASS\n'
else
    printf 'AUDITORIA: FAIL\n'
fi
printf '============================================================\n'

exit "$FAIL"
