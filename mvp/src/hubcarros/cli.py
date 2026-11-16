"""Operator CLI.

  hubcarros demo                         # create hubcarros.db with the demo dealers + stock
  hubcarros dealer add ID "Name" POSTCODE [--phone ..] [--email ..]
  hubcarros ingest DEALER_ID stock.csv   # load/refresh a dealer's stock
  hubcarros report DEALER_ID             # compliance report for the dealer
  hubcarros draft VEHICLE_ID             # draft a fact-only description
  hubcarros search "automatic suv under £15k"
  hubcarros leads [DEALER_ID]
  hubcarros metrics
  hubcarros synthetic [--dealers 30 --days 60 --seed 7]   # mercado sintético para o terminal
  hubcarros market                       # visão geral do mercado
  hubcarros ticker TOYOTA-RAV4-2020      # cotação de um ticker
  hubcarros watcher new | watcher add TOKEN search "hybrid under £10k" | watcher alerts TOKEN
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
    observed = date.fromisoformat(args.date) if args.date else None
    summary = _hub(args).ingest(args.dealer_id, parse_csv_file(args.csv, args.dealer_id), observed, args.allow_empty)
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


def cmd_synthetic(args) -> None:
    from .synthetic import SyntheticMarket

    hub = Hub(Database(args.db))
    market = SyntheticMarket(seed=args.seed, n_dealers=args.dealers, days=args.days, end=hub.today)
    result = market.run(hub, progress=lambda d: print(f"  gerando {d}", end="\r", flush=True))
    print()
    _print(result)


def cmd_market(args) -> None:
    ov = _hub(args).market_overview(args.limit)
    print(f"Mercado em {ov['day']}: {ov['active_listings']} anúncios ativos, {ov['tickers']} tickers, "
          f"{ov['sold_last_30d']} vendidos em 30 dias\n")
    def table(title, rows):
        print(title)
        for r in rows:
            ch = f"{r['change_30d_pct']:+.1f}%" if r["change_30d_pct"] is not None else "   n/a"
            print(f"  {r['ticker']:<34} £{r['median_price'] or 0:>7,}  {ch:>7}  ativos {r['active']:>3}  vendidos30d {r['sold_last_30d']:>3}")
        print()
    table("Mais anunciados", ov["most_listed"])
    table("Mais vendidos (30d)", ov["most_sold"])
    table("Maiores altas (30d)", ov["top_gainers"])
    table("Maiores quedas (30d)", ov["top_losers"])


def cmd_ticker(args) -> None:
    t = _hub(args).get_ticker(args.ticker, args.days)
    if t is None:
        raise SystemExit("Ticker desconhecido.")
    q = t["quote"]
    print(f"{t['ticker']}  mediana £{q['median_price'] or 0:,}  (mín £{q['min_price'] or 0:,} / máx £{q['max_price'] or 0:,})  "
          f"ativos {q['active']}  7d {t['change_7d_pct']}%  30d {t['change_30d_pct']}%  "
          f"dias p/ vender {t['avg_days_to_sell']}  quedas 7d {t['price_drops_last_7d']}")
    prices = [h["median_price"] for h in t["history"] if h["median_price"]]
    if prices:
        lo, hi = min(prices), max(prices)
        bars = "▁▂▃▄▅▆▇█"
        spark = "".join(bars[int((p - lo) / (hi - lo) * 7)] if hi > lo else bars[3] for p in prices)
        print(f"{t['history'][0]['day']} {spark} {t['history'][-1]['day']}")


def cmd_watcher(args) -> None:
    hub = _hub(args)
    if args.watcher_cmd == "new":
        _print(hub.create_watcher())
    elif args.watcher_cmd == "add":
        kw = {"query": args.value} if args.kind == "search" else (
            {"ticker": args.value} if args.kind == "ticker" else {"vehicle_id": int(args.value)})
        _print(hub.add_watch(args.token, args.kind, **kw))
    elif args.watcher_cmd == "list":
        _print(hub.list_watches(args.token))
    elif args.watcher_cmd == "alerts":
        _print(hub.get_alerts(args.token))


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

    ing = sub.add_parser("ingest"); ing.add_argument("dealer_id"); ing.add_argument("csv")
    ing.add_argument("--date", help="data da observação AAAA-MM-DD (padrão: hoje)")
    ing.add_argument("--allow-empty", action="store_true", help="confirma que o revendedor está sem estoque")
    ing.set_defaults(func=cmd_ingest)
    rep = sub.add_parser("report"); rep.add_argument("dealer_id"); rep.set_defaults(func=cmd_report)
    dr = sub.add_parser("draft"); dr.add_argument("vehicle_id", type=int); dr.set_defaults(func=cmd_draft)
    se = sub.add_parser("search"); se.add_argument("query"); se.add_argument("--near"); se.add_argument("--limit", type=int, default=10)
    se.set_defaults(func=cmd_search)
    le = sub.add_parser("leads"); le.add_argument("dealer_id", nargs="?"); le.set_defaults(func=cmd_leads)
    sub.add_parser("metrics").set_defaults(func=cmd_metrics)
    syn = sub.add_parser("synthetic"); syn.add_argument("--dealers", type=int, default=30)
    syn.add_argument("--days", type=int, default=60); syn.add_argument("--seed", type=int, default=7)
    syn.set_defaults(func=cmd_synthetic)
    mk = sub.add_parser("market"); mk.add_argument("--limit", type=int, default=8); mk.set_defaults(func=cmd_market)
    tk = sub.add_parser("ticker"); tk.add_argument("ticker"); tk.add_argument("--days", type=int, default=30)
    tk.set_defaults(func=cmd_ticker)
    w = sub.add_parser("watcher").add_subparsers(dest="watcher_cmd", required=True)
    w.add_parser("new").set_defaults(func=cmd_watcher)
    wa = w.add_parser("add"); wa.add_argument("token"); wa.add_argument("kind", choices=["search", "ticker", "vehicle"])
    wa.add_argument("value"); wa.set_defaults(func=cmd_watcher)
    for name in ("list", "alerts"):
        wp = w.add_parser(name); wp.add_argument("token"); wp.set_defaults(func=cmd_watcher)
    sub.add_parser("purge-leads").set_defaults(func=cmd_purge)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
