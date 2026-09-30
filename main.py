import argparse
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from core.config import Config
from core.logging import setup_logging
from core.memory import MemoryStore
from core.model_router import ModelRouter
from core.orchestrator import Orchestrator
from core.supervisor import Supervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SuperAgent V0.6")
    parser.add_argument("goal", nargs="?", help="Objetivo do SuperAgent")
    parser.add_argument(
        "--dry-run", action="store_true", help="Cria o plano sem persistir nem executar."
    )
    parser.add_argument("--output", type=str, help="Arquivo JSON para salvar o resultado.")
    parser.add_argument("--verbose", action="store_true", help="Log em nível DEBUG.")
    return parser


def main() -> int:
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args()

    goal = args.goal
    if not goal:
        goal = input("Digite o objetivo: ").strip()
    if not goal:
        print("Erro: objetivo vazio.", file=sys.stderr)
        return 1

    run_id = str(uuid.uuid4())
    config = Config()

    level = "DEBUG" if args.verbose else config.env_str(
        "LOG_LEVEL", "application", "log_level", default="INFO"
    )

    logger = setup_logging(run_id=run_id, level=level)

    memory = MemoryStore()
    router = ModelRouter(config)
    supervisor = Supervisor(config)

    orchestrator = Orchestrator(
        config=config,
        router=router,
        memory=memory,
        supervisor=supervisor,
        logger=logger,
        run_id=run_id,
    )

    result = orchestrator.run(goal=goal, dry_run=args.dry_run)

    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)

    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        print(f"\nResultado salvo em: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
