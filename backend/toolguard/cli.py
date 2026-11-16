import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .db import ROOT, Database
from .seed import seed


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Agent Tool Guard local synthetic demo")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Initialize synthetic data, without resetting existing work")
    init.add_argument("--database", default=os.getenv("ATG_DATABASE", "var/guard.sqlite3"))
    serve = sub.add_parser("serve", help="Run on 127.0.0.1 (one worker)")
    serve.add_argument("--port", type=int, default=8000)
    ev = sub.add_parser("evaluate", help="Run isolated A/B/C evaluation; never uses the demo database")
    ev.add_argument("--split", choices=["dev", "holdout"], default="dev")
    ev.add_argument("--repeats", type=int, choices=[1, 2, 3], default=1)
    ev.add_argument("--provider", choices=["mock", "openai"], default="mock")
    ev.add_argument(
        "--allow-paid-model",
        action="store_true",
        help="Explicitly authorize sending synthetic fixtures to the configured API",
    )
    ev.add_argument("--output", default="var/results/latest.json")
    args = parser.parse_args()
    if args.command == "init":
        path = Path(args.database)
        db = Database(path if path.is_absolute() else ROOT / path)
        seed(db)
        print("Synthetic database initialized (existing data preserved).")
        print(db.path)
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("toolguard.api:app", host="127.0.0.1", port=args.port, access_log=False, workers=1)
    else:
        if args.provider == "openai" and not args.allow_paid_model:
            parser.error(
                "Real model experiments require --allow-paid-model. Mock is available without a key."
            )
        from .evaluation import evaluate

        result = evaluate(args.split, args.repeats, args.provider)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(output),
                    "provider": result["provider"],
                    "samples": result["sample_count"],
                    "metrics": result["metrics"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
