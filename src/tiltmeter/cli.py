"""How does a person drive this thing?

The command-line interface. Two commands exist so far:

  tiltmeter ingest   — poll every outlet's feed once and store new articles
  tiltmeter status   — show how many articles we hold per outlet

Later milestones add: snapshot, run, validate, report.
"""

import argparse
import logging
import sys

from tiltmeter import db, ingest

DEFAULT_CONFIG = "config/outlets.yaml"
DEFAULT_DB = "data/tiltmeter.db"


def cmd_ingest(args: argparse.Namespace) -> int:
    results = ingest.ingest_all(args.config, args.db, fetch_text=not args.no_text)
    failed = [r for r in results if "error" in r]
    for r in results:
        if "error" in r:
            print(f"  FAIL {r['outlet']}: {r['error']}")
        else:
            print(f"  ok   {r['outlet']}: {r['seen']} in feed, {r['new']} new")
    return 1 if len(failed) == len(results) and results else 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    rows = db.outlet_counts(conn)
    if not rows:
        print("no articles collected yet")
        return 0
    width = max(len(o) for o, _ in rows)
    for outlet, count in rows:
        print(f"  {outlet:<{width}}  {count}")
    print(f"  {'TOTAL':<{width}}  {sum(c for _, c in rows)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tiltmeter", description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="path to the article database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="poll all outlet feeds once")
    p_ingest.add_argument("--config", default=DEFAULT_CONFIG)
    p_ingest.add_argument(
        "--no-text", action="store_true", help="skip full-text fetch (feed metadata only)"
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_status = sub.add_parser("status", help="article counts per outlet")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
