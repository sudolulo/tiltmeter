"""How does a person drive this thing?

The command-line interface:

  tiltmeter ingest     — poll every outlet's feed once and store new articles
  tiltmeter status     — show how many articles we hold per outlet
  tiltmeter snapshot   — freeze a window of the corpus into a manifest
  tiltmeter reference  — fetch congressional floor speeches (the D5 anchor)
  tiltmeter run        — manifest → ratings.json + stories + evidence pages
  tiltmeter cycle      — one full collection cycle: ingest, reference top-up,
                         rolling snapshot + run, audit (the deployment loop,
                         so window policy lives in tested code, not in shell)
  tiltmeter validate   — the M3 gate: rank-correlate a release vs the raters
  tiltmeter sweep      — sensitivity: rescore across the threshold grid
  tiltmeter audit      — verify every content fingerprint + custody chain
  tiltmeter serve      — read-only HTTP API over computed releases
"""

import argparse
import logging
import sys

from tiltmeter import db, ingest

DEFAULT_CONFIG = "config/outlets.yaml"
DEFAULT_DB = "data/tiltmeter.db"
WINDOW_DAYS = 14  # rolling snapshot window (METHODOLOGY D6/D7 corpus policy)


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
    for party, count in conn.execute(
        "SELECT party, COUNT(*) FROM reference_speeches GROUP BY party"
    ).fetchall():
        print(f"  {party}: {count} speeches total")
    return 0


def _publish_release(conn, manifest: dict, out_dir: str):
    """Compute once, publish everything: ratings, stories, evidence pages.

    The single path both manual runs and scheduled cycles go through, so the
    two can never diverge in what a release contains.
    """
    from tiltmeter import __version__, artifacts, report, score

    result = score.compute(conn, manifest, __version__)
    ratings_path = artifacts.write(out_dir, "ratings", manifest["snapshot_id"], result.ratings)
    stories_path = artifacts.write(
        out_dir, "stories", manifest["snapshot_id"], score.stories_json(result, manifest)
    )
    report_dir = report.write(
        report.render(result.ratings, result.stories, result.matrix, result.articles),
        result.ratings,
        out_dir,
    )
    return result, ratings_path, stories_path, report_dir


def cmd_run(args: argparse.Namespace) -> int:
    from tiltmeter import snapshot

    manifest = snapshot.load(args.manifest)
    conn = db.connect(args.db)
    result, ratings_path, stories_path, report_dir = _publish_release(conn, manifest, args.out)

    print(f"ratings: {ratings_path}\nstories: {stories_path}\nevidence: {report_dir}/")
    o = result.ratings["orientation"]
    flag = "" if o["reliable"] else "  [UNRELIABLE — do not interpret]"
    print(
        f"stories: {result.ratings['n_stories']}, "
        f"axis inertia {result.ratings['axis_inertia_share']:.0%}, "
        f"orientation rho {o['correlation']:+.2f}{flag}"
    )
    for entry in result.ratings["outlets"]:
        print(
            f"  {entry['score']:+.3f}  [{entry['ci_low']:+.3f} {entry['ci_high']:+.3f}]"
            f"  {entry['outlet']}"
        )
    return 0


def cmd_cycle(args: argparse.Namespace) -> int:
    """One full collection cycle — the unit deployments repeat on a schedule.

    Window policy lives here, in code with tests: a rolling WINDOW_DAYS-day
    window ending today (exclusive), keyed on observed_at, so each day's
    re-runs are byte-identical and yesterday's window is complete.
    """
    from datetime import datetime, timedelta, timezone

    from tiltmeter import __version__, snapshot

    rc = cmd_ingest(args)

    from tiltmeter import reference

    conn = db.connect(args.db)
    # one UTC "today" for the whole cycle: observed_at values are UTC, so the
    # window must be too, and start/end must come from the same instant
    today = datetime.now(timezone.utc).date()
    try:
        reference.fetch_range(conn, today.isoformat(), args.reference_days, args.congress)
    except Exception as exc:  # noqa: BLE001 - anchor top-up must not kill collection
        print(f"  reference top-up failed (non-fatal): {exc}")

    start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    end = today.isoformat()
    try:
        manifest = snapshot.create(conn, start, end, __version__)
        snapshot.write(manifest, args.out)
        _publish_release(conn, manifest, args.out)
        print(f"  rolling release {manifest['snapshot_id']} written")
    except ValueError as exc:
        print(f"  no rolling release: {exc}")

    audit_rc = cmd_audit(argparse.Namespace(db=args.db, emit=args.audit_emit))
    return rc or audit_rc


def cmd_validate(args: argparse.Namespace) -> int:
    from pathlib import Path

    from tiltmeter import artifacts, validate

    ratings = artifacts.read_json(args.ratings)
    reference = validate.load_reference(args.reference, allow_unverified=args.allow_unverified)
    result = validate.report(ratings, reference)

    # peeks are labeled inside AND outside: a different filename that the
    # public API never serves, so a peek cannot masquerade as the gate
    prefix = "validation-peek" if result["peek"] else "validation"
    out = Path(args.ratings).parent / f"{prefix}-{result['snapshot_id']}.json"
    artifacts.write_json(out, result)

    if result["peek"]:
        print("  PEEK RUN — unverified reference values used; can never pass the gate")
        print(f"  unverified used: {len(result['unverified_used'])}")
    if result["skipped_unverified"]:
        print(f"  SKIPPED {len(result['skipped_unverified'])} unverified reference entries"
              " (verify at source to include them)")
    for rater in result["raters_missing"]:
        print(f"  {rater:10} MISSING — no verified values; gate cannot pass")
    for rater, r in result["raters"].items():
        mark = "PASS" if r["passes_gate"] else "fail"
        print(f"  {rater:10} rho={r['rho']:+.3f}  n={r['n']}  p={r['permutation_p']}  [{mark}]")
    if not result["orientation_reliable"]:
        print("  orientation UNRELIABLE — gate cannot pass regardless of rho")
    print(f"  GATE: {'PASSED' if result['gate_passed'] else 'not passed'}  -> {out}")
    # automation-friendly: 0 = gate passed, 2 = evaluated but not passed
    return 0 if result["gate_passed"] else 2


def cmd_sweep(args: argparse.Namespace) -> int:
    from tiltmeter import snapshot, sweep

    manifest = snapshot.load(args.manifest)
    conn = db.connect(args.db)
    result = sweep.run_sweep(conn, manifest)
    path = sweep.write(result, args.out)
    print(f"sweep: {path}")
    for key, rho in sorted(result["rank_correlation_vs_default"].items()):
        entry = result["thresholds"][key]
        print(f"  threshold {key}: {entry['n_stories']} stories, rank-corr vs default {rho:+.3f}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Full dataset integrity check — strictly read-only.

    Opens the store in read-only mode and refuses a missing file: an audit
    that could create an empty store and pass would be worse than no audit.
    """
    from tiltmeter import artifacts

    try:
        conn = db.connect_readonly(args.db)
    except FileNotFoundError as exc:
        print(f"  AUDIT FAILED: {exc}")
        return 1
    try:
        problems = db.custody_verify(conn) + db.verify_contents(conn)
        head = db.custody_head(conn)
        n_contents = conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0]
    except db.sqlite3.OperationalError as exc:
        print(f"  AUDIT FAILED: store unreadable or pre-custody schema ({exc})")
        return 1
    finally:
        conn.close()
    if n_contents == 0:
        print("  AUDIT FAILED: store is empty — nothing to attest"
              " (wrong --db path, or collection never ran)")
        return 1
    if args.emit:
        from pathlib import Path

        artifacts.write_json(args.emit, {
            "custody_head": head, "n_contents": n_contents,
            "intact": not problems, "problems": problems,
        })
        # append-only head log: an external copy of this file constrains any
        # future attempt to rewrite the chain wholesale
        log_path = Path(args.emit).parent / "custody-heads.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            import json as _json

            f.write(_json.dumps({"seq": head["seq"], "ts": head["ts"],
                                 "entry_hash": head["entry_hash"],
                                 "n_contents": n_contents}, sort_keys=True) + "\n")
    print(f"  contents: {n_contents} items, chain head seq {head['seq']}")
    if problems:
        for p in problems[:20]:
            print(f"  PROBLEM: {p}")
        print(f"  AUDIT FAILED ({len(problems)} problems)")
        return 1
    print("  AUDIT PASSED — every fingerprint verifies, chain intact")
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    """Adopt orphaned content into the custody chain, visibly.

    For stores damaged by pre-0.8 collector interruptions or partial
    restores: orphans are chained in an explicit 'adopt' batch, so the chain
    records the irregularity instead of hiding it. Audit afterwards.
    """
    conn = db.connect(args.db)
    entry = db.custody_adopt_orphans(conn)
    if entry is None:
        print("  nothing to repair — no orphaned content")
        return 0
    print(f"  adopted {entry['n_items']} orphaned items as chain seq {entry['seq']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from tiltmeter import serve

    serve.run(args.releases, args.host, args.port,
              outlets_config=args.config, db_path=args.db)
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

    p_cycle = sub.add_parser("cycle", help="one full collection cycle (the deployment unit)")
    p_cycle.add_argument("--config", default=DEFAULT_CONFIG)
    p_cycle.add_argument("--out", default="releases")
    p_cycle.add_argument("--no-text", action="store_true")
    p_cycle.add_argument("--reference-days", type=int, default=15)
    p_cycle.add_argument("--congress", type=int, default=119)
    p_cycle.add_argument("--audit-emit", default="releases/custody-head.json")
    p_cycle.set_defaults(func=cmd_cycle)

    p_validate = sub.add_parser("validate", help="M3 gate: rank-correlate a release vs raters")
    p_validate.add_argument("--ratings", required=True, help="path to a ratings-*.json release")
    p_validate.add_argument("--reference", default="config/reference_ratings.yaml")
    p_validate.add_argument(
        "--allow-unverified", action="store_true",
        help="peek at unverified reference values; labeled, unservable, can never pass the gate",
    )
    p_validate.set_defaults(func=cmd_validate)

    p_sweep = sub.add_parser("sweep", help="sensitivity sweep across the clustering threshold")
    p_sweep.add_argument("--manifest", required=True)
    p_sweep.add_argument("--out", default="releases")
    p_sweep.set_defaults(func=cmd_sweep)

    p_audit = sub.add_parser("audit", help="verify every content fingerprint + custody chain")
    p_audit.add_argument("--emit", help="also write an audit summary JSON to this path")
    p_audit.set_defaults(func=cmd_audit)

    p_repair = sub.add_parser(
        "repair", help="adopt custody-orphaned content into the chain (visible 'adopt' batch)"
    )
    p_repair.set_defaults(func=cmd_repair)

    p_serve = sub.add_parser("serve", help="read-only HTTP API over computed releases")
    p_serve.add_argument("--releases", default="releases")
    p_serve.add_argument("--config", default=DEFAULT_CONFIG,
                         help="outlets config for /outlets and health scoping")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8477)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
