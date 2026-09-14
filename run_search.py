#!/usr/bin/env python3
"""
CLI Entrypoint for the Job Search Automation Acquisition Engine.

Usage example:
    python run_search.py --role "React Developer" --location "Bangalore" --seniority mid
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import ALL_ADAPTERS
from core.models import QueryConfig
from core.orchestrator import Orchestrator
from core.storage import RunStorage


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 Modular Job Listing Acquisition Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--role",
        type=str,
        required=True,
        help="Target job title or role keywords (e.g. 'React Developer', 'Data Engineer')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="any",
        help="Target location/city (e.g. 'Bangalore', 'Remote', 'London', or 'any')",
    )
    parser.add_argument(
        "--seniority",
        type=str,
        choices=["entry", "mid", "senior", "lead", "any"],
        default="any",
        help="Seniority level filter",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="*",
        default=[],
        help="Optional additional keywords to filter (e.g. 'TypeScript' 'Python')",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="*",
        default=list(ALL_ADAPTERS.keys()),
        choices=list(ALL_ADAPTERS.keys()),
        help="List of adapters to execute",
    )
    parser.add_argument(
        "--companies",
        type=str,
        nargs="*",
        default=[],
        help="Optional custom ATS company slugs for Greenhouse & Lever (e.g. canonical stripe gitlab spotify)",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"),
        help="Optional proxy URL (e.g. http://127.0.0.1:8080 or http://user:pass@proxy:port)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results.json",
        help="Path where normalized deduplicated jobs will be saved",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="run_report.json",
        help="Path where health check and run metrics report will be saved",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the latest incomplete run from SQLite instead of starting a new one",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    storage = RunStorage()
    resume_run_id = None

    if args.resume:
        resume_run_id = storage.get_latest_incomplete_run()
        if resume_run_id:
            print(f"[*] Resuming incomplete run: {resume_run_id}")
        else:
            print("[!] No incomplete run found to resume. Starting a fresh run.")

    query = QueryConfig(
        role=args.role,
        location=args.location,
        seniority=args.seniority,
        keywords=args.keywords,
        sources=args.sources,
        companies=args.companies,
    )

    print("=" * 60)
    print("JOB SEARCH ACQUISITION ENGINE — PHASE 1")
    print(f"Role:      {query.role}")
    print(f"Location:  {query.location}")
    print(f"Seniority: {query.seniority}")
    print(f"Sources:   {', '.join(query.sources)}")
    if args.proxy:
        print(f"Proxy:     Configured ({args.proxy[:15]}...)")
    else:
        print("Proxy:     Direct Egress (None configured)")
    print("=" * 60)

    orchestrator = Orchestrator(
        storage=storage,
        proxy_url=args.proxy,
    )

    report = orchestrator.run(
        query=query,
        resume_run_id=resume_run_id,
        results_path=args.output,
        report_path=args.report,
    )

    print("\n" + "=" * 60)
    print("ACQUISITION RUN SUMMARY")
    print(f"Run ID:            {report['run_id']}")
    print(f"Duration:          {report['duration_seconds']}s")
    print(f"Unique Jobs Found: {report['results_count']}")
    print(f"Duplicates Pruned: {report['deduplication']['duplicates_pruned']} ({report['deduplication']['reduction_rate']}%)")
    print("\nSource Health Breakdown:")
    for src, h in report["sources_health"].items():
        metrics = report["source_metrics"].get(src, {})
        status_icon = "✓" if h["status"] == "ok" else ("!" if h["status"] == "degraded" else "✗")
        print(f"  [{status_icon}] {src:<15} status: {h['status']:<8} fetched: {metrics.get('fetched', 0):<4} matched: {metrics.get('matched', 0)}")
        print(f"      Evidence: {h['evidence']}")
    print(f"\n[+] Results saved to: {args.output}")
    print(f"[+] Health report saved to: {args.report}")
    print("=" * 60)


if __name__ == "__main__":
    main()
