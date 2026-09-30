"""SA-120 — Benchmark de latência do Decision Engine por engine.

Mede o custo de UMA decisão do critic (o gargalo de latência declarado
no roadmap: "critic com LLM ~68s" vs "rules sub-segundo") usando a
mesma entrada representativa para todos os engines.

Uso:
    python -m tools.benchmark                     # rules (instantâneo)
    python -m tools.benchmark --engine typed      # endpoint OpenAI-compat
    python -m tools.benchmark --engine llm        # via router/Ollama
    python -m tools.benchmark --engine all -n 3   # todos (llm/typed custam $)

Saída: tabela humana + JSON com n/mean/p50/p95/min/max por engine.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

from core.config import Config
from core.decisions import DecisionEngine

# Entrada representativa: um step real de run (caso analise.py).
GOAL = "Execute o script analise.py que ja existe no workspace e resuma a saida dele."
OBJECTIVE = "executar analise.py no sandbox e resumir a saida"
RESULT = (
    "A media de [4, 7, 10] e 7.0\n"
    "exit_code=0\n"
)
EXTRA = '<sandbox_output path="analise.py">\nA media de [4, 7, 10] e 7.0\n</sandbox_output>'


def bench(engine, n: int) -> dict:
    samples: list[float] = []
    decisions: list[str] = []
    for _ in range(n):
        started = time.perf_counter()
        decision = engine.decide(GOAL, OBJECTIVE, RESULT, EXTRA)
        samples.append((time.perf_counter() - started) * 1000)
        decisions.append(decision.decision)

    ordered = sorted(samples)
    return {
        "engine": engine.name,
        "n": n,
        "mean_ms": round(statistics.mean(samples), 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(ordered[max(0, min(len(ordered) - 1, int(0.95 * len(ordered)) - 1))], 2),
        "min_ms": round(ordered[0], 2),
        "max_ms": round(ordered[-1], 2),
        "decisions": {d: decisions.count(d) for d in sorted(set(decisions))},
    }


def fmt_ms(ms: float) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    if ms >= 1:
        return f"{ms:.2f}ms"
    return f"{ms:.3f}ms"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", choices=["rules", "llm", "typed", "all"], default="rules"
    )
    parser.add_argument(
        "-n", "--iterations", type=int, default=None,
        help="iterações (default: rules=500, llm/typed=3)",
    )
    parser.add_argument("--output", type=str, help="grava o JSON em arquivo")
    args = parser.parse_args()

    config = Config()
    kinds = ["rules", "llm", "typed"] if args.engine == "all" else [args.engine]

    router = None
    if "llm" in kinds:
        from core.model_router import ModelRouter

        router = ModelRouter(config)

    results: list[dict] = []
    report: dict = {"input": {"goal": GOAL, "objective": OBJECTIVE},
                    "results": results}
    print(f"{'engine':<8} {'n':>4} {'mean':>10} {'p50':>10} {'p95':>10} "
          f"{'min':>10} {'max':>10}  decisões")

    for kind in kinds:
        n = args.iterations or (500 if kind == "rules" else 3)
        engine: DecisionEngine
        if kind == "rules":
            from core.decisions import RuleDecisionEngine

            engine = RuleDecisionEngine()
        elif kind == "llm":
            from core.decisions import LLMDecisionEngine

            if router is None:
                raise SystemExit("engine llm requer router (use --engine llm|all)")
            engine = LLMDecisionEngine(router)
        else:
            from core.decisions import TypedDecisionEngine

            engine = TypedDecisionEngine(config)
        result = bench(engine, n)
        results.append(result)
        # Gravação incremental: um engine que estoura não perde os outros.
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                )
        print(
            f"{result['engine']:<8} {result['n']:>4} "
            f"{fmt_ms(result['mean_ms']):>10} {fmt_ms(result['p50_ms']):>10} "
            f"{fmt_ms(result['p95_ms']):>10} {fmt_ms(result['min_ms']):>10} "
            f"{fmt_ms(result['max_ms']):>10}  {result['decisions']}"
        )

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print()
    print(payload)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")


if __name__ == "__main__":
    main()
