"""Operator CLI.

  hubcarros demo                         # create hubcarros.db with the demo dealers + stock
  hubcarros dealer add ID "Name" POSTCODE [--phone ..] [--email ..]
  hubcarros ingest DEALER_ID stock.csv   # load/refresh a dealer's stock
  hubcarros report DEALER_ID             # compliance report for the dealer
  hubcarros draft VEHICLE_ID             # draft a fact-only description
  hubcarros search "automatic suv under £15k"
  hubcarros leads [DEALER_ID]
  hubcarros metrics
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from .copywriter import draft_description
from .db import Database, row_to_vehicle
from .ingest import parse_csv_file
from .models import Dealer
from .risk import FixtureRiskProvider
from .service import Hub, _report_from_row

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"


def _hub(args) -> Hub:
    fixture = args.risk_fixture or os.environ.get("HUBCARROS_RISK_FIXTURE")
    provider = FixtureRiskProvider(fixture) if fixture else None
    return Hub(Database(args.db), provider)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_demo(args) -> None:
    args.risk_fixture = args.risk_fixture or str(DEMO_DIR / "risk_fixture.json")
    hub = _hub(args)
    dealers = json.loads((DEMO_DIR / "dealers.json").read_text(encoding="utf-8"))
    for d in dealers:
        hub.register_dealer(Dealer(**{k: d[k] for k in ("id", "name", "postcode", "phone", "email")}))
        summary = hub.ingest(d["id"], parse_csv_file(DEMO_DIR / d["stock_file"], d["id"]))
        _print(summary.__dict__)
    print(f"\nBanco pronto em {args.db}. Use HUBCARROS_RISK_FIXTURE={args.risk_fixture} ao rodar o servidor.")


def cmd_dealer_add(args) -> None:
    _hub(args).register_dealer(Dealer(args.id, args.name, args.postcode, args.phone, args.email))
    print(f"Revendedor {args.id} salvo.")


def cmd_ingest(args) -> None:
    summary = _hub(args).ingest(args.dealer_id, parse_csv_file(args.csv, args.dealer_id))
    _print(summary.__dict__)


def cmd_report(args) -> None:
    rows = _hub(args).compliance_report(args.dealer_id)
    for r in rows:
        mark = {"published": "OK ", "needs_review": "REV", "blocked": "BLQ"}[r["status"]]
        print(f"[{mark}] #{r['vehicle_id']} {r['reg']} {r['title']}")
        for i in r["issues"]:
            ev = f"  «{i['evidence']}»" if i.get("evidence") else ""
            print(f"       - {i['severity'].upper():5} {i['code']}: {i['message']}{ev}")


def cmd_draft(args) -> None:
    hub = _hub(args)
    row = hub.db.get_vehicle_row(args.vehicle_id)
    if row is None:
        raise SystemExit("Veículo não encontrado.")
    print(draft_description(row_to_vehicle(row), _report_from_row(row)))


def cmd_search(args) -> None:
    _print(_hub(args).search(args.query, near_postcode=args.near or "", limit=args.limit))


def cmd_leads(args) -> None:
    _print(_hub(args).dealer_leads(args.dealer_id))


def cmd_metrics(args) -> None:
    _print(_hub(args).metrics())


def cmd_purge(args) -> None:
    n = _hub(args).db.purge_expired_leads(date.today().isoformat())
    print(f"{n} leads expirados removidos.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hubcarros", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=os.environ.get("HUBCARROS_DB", "hubcarros.db"))
    p.add_argument("--risk-fixture", default=None, help="JSON de checagens simuladas")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo").set_defaults(func=cmd_demo)

    dealer = sub.add_parser("dealer").add_subparsers(dest="dealer_cmd", required=True)
    add = dealer.add_parser("add")
    add.add_argument("id"); add.add_argument("name"); add.add_argument("postcode")
    add.add_argument("--phone", default=""); add.add_argument("--email", default="")
    add.set_defaults(func=cmd_dealer_add)

    ing = sub.add_parser("ingest"); ing.add_argument("dealer_id"); ing.add_argument("csv"); ing.set_defaults(func=cmd_ingest)
    rep = sub.add_parser("report"); rep.add_argument("dealer_id"); rep.set_defaults(func=cmd_report)
    dr = sub.add_parser("draft"); dr.add_argument("vehicle_id", type=int); dr.set_defaults(func=cmd_draft)
    se = sub.add_parser("search"); se.add_argument("query"); se.add_argument("--near"); se.add_argument("--limit", type=int, default=10)
    se.set_defaults(func=cmd_search)
    le = sub.add_parser("leads"); le.add_argument("dealer_id", nargs="?"); le.set_defaults(func=cmd_leads)
    sub.add_parser("metrics").set_defaults(func=cmd_metrics)
    sub.add_parser("purge-leads").set_defaults(func=cmd_purge)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
