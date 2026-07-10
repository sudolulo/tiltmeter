"""How does a person drive this thing?

The command-line interface:

  tiltmeter ingest     — poll every outlet's feed once and store new articles
  tiltmeter status     — show how many articles we hold per outlet
  tiltmeter snapshot   — freeze a window of the corpus into a manifest
  tiltmeter reference  — fetch congressional floor speeches (the D5 anchor)
  tiltmeter run        — manifest → ratings.json + evidence pages
  tiltmeter serve      — read-only HTTP API over computed releases

Later milestones add: validate (the M3 gate).
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


def cmd_snapshot(args: argparse.Namespace) -> int:
    from tiltmeter import __version__, snapshot

    conn = db.connect(args.db)
    manifest = snapshot.create(conn, args.start, args.end, __version__)
    path = snapshot.write(manifest, args.out)
    print(
        f"snapshot {manifest['snapshot_id']}: {manifest['n_articles']} articles, "
        f"{len(manifest['outlets'])} outlets\n  corpus_hash {manifest['corpus_hash']}\n  {path}"
    )
    return 0


def cmd_reference(args: argparse.Namespace) -> int:
    from tiltmeter import reference

    conn = db.connect(args.db)
    totals = reference.fetch_range(conn, args.end, args.days, args.congress)
    print(
        f"  {totals['days']} session days, {totals['speeches']} speeches stored, "
        f"{totals['unmatched']} unmatched speakers dropped, {totals['skipped']} recess days"
    )
    row = conn.execute(
        "SELECT party, COUNT(*) FROM reference_speeches GROUP BY party"
    ).fetchall()
    for party, count in row:
        print(f"  {party}: {count} speeches total")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from tiltmeter import __version__, report, score, snapshot

    manifest = snapshot.load(args.manifest)
    conn = db.connect(args.db)
    ratings = score.compute(conn, manifest, __version__)
    ratings_path = score.write(ratings, args.out)
    stories, matrix, articles = score.story_details(conn, manifest)
    stories_path = score.write_stories(score.stories_json(stories, articles, manifest), args.out)
    report_dir = report.write(report.render(ratings, stories, matrix, articles), ratings, args.out)

    print(f"ratings: {ratings_path}\nstories: {stories_path}\nevidence: {report_dir}/")
    o = ratings["orientation"]
    flag = "" if o["reliable"] else "  [UNRELIABLE — do not interpret]"
    print(
        f"stories: {ratings['n_stories']}, axis inertia {ratings['axis_inertia_share']:.0%}, "
        f"orientation rho {o['correlation']:+.2f}{flag}"
    )
    for entry in ratings["outlets"]:
        print(
            f"  {entry['score']:+.3f}  [{entry['ci_low']:+.3f} {entry['ci_high']:+.3f}]"
            f"  {entry['outlet']}"
        )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from tiltmeter import serve

    serve.run(args.releases, args.host, args.port)
    return 0


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

    p_snapshot = sub.add_parser("snapshot", help="freeze a corpus window into a manifest")
    p_snapshot.add_argument("--start", required=True, help="window start (ISO date/timestamp)")
    p_snapshot.add_argument("--end", required=True, help="window end, exclusive")
    p_snapshot.add_argument("--out", default="releases", help="manifest output directory")
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_reference = sub.add_parser(
        "reference", help="fetch congressional floor speeches (orientation anchor)"
    )
    p_reference.add_argument("--end", required=True, help="latest day to consider (ISO date)")
    p_reference.add_argument("--days", type=int, default=10, help="session days to collect")
    p_reference.add_argument("--congress", type=int, default=119)
    p_reference.set_defaults(func=cmd_reference)

    p_run = sub.add_parser("run", help="compute ratings + evidence pages from a manifest")
    p_run.add_argument("--manifest", required=True, help="path to a snapshot manifest")
    p_run.add_argument("--out", default="releases", help="output directory")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="read-only HTTP API over computed releases")
    p_serve.add_argument("--releases", default="releases")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8477)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
