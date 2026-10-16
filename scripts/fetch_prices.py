#!/usr/bin/env python3
"""Refresh data/prices.json — the item price index behind /items.

Design: the page does no live per-item API calls. This offline pipeline
produces ONE compact JSON index; the browser fetches it once and runs
search + detail entirely client-side (instant typeahead, zero network
per lookup, immune to API outages).

Sources, in preference order:

1. tarkov.dev GraphQL API (https://api.tarkov.dev/graphql) — live flea
   market averages and real trader offers, when it is reachable.

2. SPT seed (fallback) — the Single Player Tarkov project's open game
   database (github.com/sp-tarkov/server, project/assets/database):
     * flea prices: templates/prices.json (id -> rouble price snapshot)
     * base prices + categories: templates/handbook.json
     * names: locales/global/en.json
     * sizes: templates/items.json (Git LFS; resolved through the LFS
       server named in the repo's .lfsconfig)
     * trader sell-to prices are DERIVED the way SPT's own
       TraderHelper.getHighestSellToTraderPrice does it: a trader buys
       an item when the item's template ancestry intersects the
       trader's items_buy categories/id_list (minus items_buy_prohibited),
       and pays round(handbookPrice * (100 - buy_price_coef) / 100) at
       loyalty level 1, in the trader's currency (converted at the
       handbook currency course). Trader buy-from offers come from each
       trader's assort.json (cash offers only; barter offers are
       omitted in seed mode).
   Seed values are a snapshot and the trader prices are approximations
   of the live game — the output is marked source="spt-seed" and the
   page labels it as such.

Usage:  python3 scripts/fetch_prices.py [--attempts N] [--delay S]
On total failure the existing index is left untouched.
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.tarkov.dev/graphql"
OUT_PATH = ROOT / "data" / "prices.json"

SPT_RAW = "https://raw.githubusercontent.com/sp-tarkov/server/master"
SPT_DB = f"{SPT_RAW}/project/assets/database"
CURRENCY_TEMPLATES = {
    "5449016a4bdc2d6f028b456f": "RUB",
    "5696686a4bdc2da3298b456a": "USD",
    "569668774bdc2da2298b4568": "EUR",
}
# The eight standard traders (SPT template ids). Event/SPT-only traders
# (Lightkeeper, BTR driver, Ref) are excluded from the seed derivation.
TRADER_IDS = [
    "54cb50c76803fa8b248b4571",  # Prapor
    "54cb57776803fa99248b456e",  # Therapist
    "579dc571d53a0658a154fbec",  # Fence
    "58330581ace78e27b8b10cee",  # Skier
    "5935c25fb3acc3127c3d8cd9",  # Peacekeeper
    "5a7c2eca46aef81a7ca2145d",  # Mechanic
    "5ac3b934156ae10c4430e83c",  # Ragman
    "5c0647fdd443bc2504c2d371",  # Jaeger
]

API_QUERY_FULL = """
{
  items {
    id name shortName normalizedName width height
    avg24hPrice lastLowPrice low24hPrice high24hPrice changeLast48hPercent
    fleaMarketFee basePrice iconLink
    sellFor { price priceRUB currency vendor { name } }
    buyFor { price priceRUB currency vendor { name } requirements { type value } }
  }
}
"""
# Trim ladder if the live schema rejects a field: drop buy requirements,
# then the newer price-stat fields.
API_QUERY_NO_REQ = """
{
  items {
    id name shortName normalizedName width height
    avg24hPrice lastLowPrice low24hPrice high24hPrice changeLast48hPercent
    fleaMarketFee basePrice iconLink
    sellFor { price priceRUB currency vendor { name } }
    buyFor { price priceRUB currency vendor { name } }
  }
}
"""
API_QUERY_CORE = """
{
  items {
    id name shortName normalizedName width height
    avg24hPrice lastLowPrice iconLink
    sellFor { price currency vendor { name } }
    buyFor { price currency vendor { name } }
  }
}
"""


def fetch_bytes(url, payload=None, timeout=60):
    data = None
    headers = {"User-Agent": "tarkov-map-app fetch_prices.py"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url, payload=None, timeout=60):
    return json.loads(fetch_bytes(url, payload, timeout).decode())


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- API path


def offer_sort_key(offer):
    return offer.get("r", offer["p"])


def build_from_api(items):
    out = []
    for it in items:
        sell = []
        for offer in it.get("sellFor") or []:
            vendor = (offer.get("vendor") or {}).get("name")
            price = offer.get("price")
            if not vendor or not price:
                continue
            entry = {"t": vendor, "p": price, "c": offer.get("currency") or "RUB"}
            rub = offer.get("priceRUB")
            if entry["c"] != "RUB" and rub:
                entry["r"] = rub
            sell.append(entry)
        sell.sort(key=offer_sort_key, reverse=True)

        buy = []
        for offer in it.get("buyFor") or []:
            vendor = (offer.get("vendor") or {}).get("name")
            price = offer.get("price")
            if not vendor or not price:
                continue
            entry = {"t": vendor, "p": price, "c": offer.get("currency") or "RUB"}
            rub = offer.get("priceRUB")
            if entry["c"] != "RUB" and rub:
                entry["r"] = rub
            req = None
            for requirement in offer.get("requirements") or []:
                if requirement.get("type") in ("loyaltyLevel", "loyalty"):
                    req = f"LL{requirement.get('value')}"
            if req:
                entry["req"] = req
            buy.append(entry)
        buy.sort(key=offer_sort_key)

        flea_avg = it.get("avg24hPrice")
        if not flea_avg and not sell:
            continue
        record = {
            "id": it["id"],
            "name": it.get("name") or it.get("shortName") or it["id"],
            "short": it.get("shortName") or "",
            "w": it.get("width") or 1,
            "h": it.get("height") or 1,
            "fleaAvg": flea_avg,
            "fleaLow": it.get("lastLowPrice"),
            "fleaChange48": it.get("changeLast48hPercent"),
            "fee": it.get("fleaMarketFee"),
            "icon": it.get("iconLink"),
            "sell": sell,
            "buy": buy,
        }
        out.append(record)
    return out


def try_api(attempts, delay):
    queries = [API_QUERY_FULL, API_QUERY_NO_REQ, API_QUERY_CORE]
    last_error = None
    for attempt in range(1, attempts + 1):
        for qi, query in enumerate(queries):
            try:
                print(f"Querying tarkov.dev API (attempt {attempt}/{attempts}, query v{qi + 1})")
                result = fetch_json(API_URL, {"query": query}, timeout=120)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(f"  failed: {exc}")
                break
            errors = result.get("errors") or []
            if not errors:
                items = (result.get("data") or {}).get("items") or []
                if items:
                    return items
                last_error = "API returned no items"
                print(f"  failed: {last_error}")
                break
            message = "; ".join(str(e) for e in errors)[:300]
            last_error = message
            print(f"  API errors: {message}")
            if "unavailable" in message.lower():
                break  # server down — trimming the query will not help
            # otherwise assume a schema mismatch and try the trimmed query
        if attempt < attempts:
            time.sleep(delay)
    print(f"tarkov.dev API unusable: {last_error}")
    return None


# ---------------------------------------------------------------- SPT seed


def download_spt():
    """Fetch the SPT database files the seed derivation needs."""
    print("Downloading SPT seed data (sp-tarkov/server)...")
    prices = fetch_json(f"{SPT_DB}/templates/prices.json")
    handbook = fetch_json(f"{SPT_DB}/templates/handbook.json")
    en = fetch_json(f"{SPT_DB}/locales/global/en.json")

    # items.json is Git LFS in that repo; the pointer file carries the
    # object id, and the repo's .lfsconfig names the LFS server.
    pointer = fetch_bytes(f"{SPT_DB}/templates/items.json").decode()
    oid = re.search(r"oid sha256:([0-9a-f]{64})", pointer)
    size = re.search(r"size (\d+)", pointer)
    if not oid:
        raise RuntimeError("templates/items.json was not an LFS pointer")
    lfsconfig = fetch_bytes(f"{SPT_RAW}/.lfsconfig").decode()
    lfs_url = re.search(r"url\s*=\s*(\S+)", lfsconfig).group(1).rstrip("/")
    batch = fetch_json(
        f"{lfs_url}/objects/batch",
        {
            "operation": "download",
            "transfers": ["basic"],
            "objects": [{"oid": oid.group(1), "size": int(size.group(1))}],
        },
    )
    href = batch["objects"][0]["actions"]["download"]["href"]
    items_raw = fetch_bytes(href, timeout=300)
    if len(items_raw) != int(size.group(1)):
        raise RuntimeError("items.json download size mismatch")
    items = json.loads(items_raw.decode())

    traders = {}
    for trader_id in TRADER_IDS:
        base = fetch_json(f"{SPT_DB}/traders/{trader_id}/base.json")
        assort = fetch_json(f"{SPT_DB}/traders/{trader_id}/assort.json")
        traders[trader_id] = {"base": base, "assort": assort}
    print(
        f"  prices: {len(prices)}, handbook items: {len(handbook['Items'])}, "
        f"templates: {len(items)}, traders: {len(traders)}"
    )
    return prices, handbook, en, items, traders


def build_from_spt(prices, handbook, en, items, traders):
    handbook_by_id = {entry["Id"]: entry for entry in handbook["Items"]}
    courses = {}
    for tpl, code in CURRENCY_TEMPLATES.items():
        entry = handbook_by_id.get(tpl)
        if entry:
            courses[code] = entry["Price"]
    courses.setdefault("RUB", 1)

    # Template ancestry (item -> baseclasses), memoised.
    chain_cache = {}

    def chain(tpl):
        if tpl in chain_cache:
            return chain_cache[tpl]
        out = []
        seen = set()
        cur = tpl
        while cur and cur in items and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = items[cur].get("_parent")
        chain_cache[tpl] = out
        return out

    # Per-trader static data for the derivation.
    trader_info = []
    for trader_id, bundle in traders.items():
        base = bundle["base"]
        name = base.get("nickname") or base.get("name") or trader_id
        coef = (base.get("loyaltyLevels") or [{}])[0].get("buy_price_coef")
        if coef is None:
            continue
        buy_cfg = base.get("items_buy") or {}
        prohib_cfg = base.get("items_buy_prohibited") or {}
        trader_info.append(
            {
                "id": trader_id,
                "name": name,
                "currency": base.get("currency") or "RUB",
                # SPT TraderHelper: buyback percent is 100 - buy_price_coef.
                "pct": (100 - coef) / 100.0,
                "buy_categories": set(buy_cfg.get("category") or []),
                "buy_ids": set(buy_cfg.get("id_list") or []),
                "prohib_categories": set(prohib_cfg.get("category") or []),
                "prohib_ids": set(prohib_cfg.get("id_list") or []),
                "assort": bundle["assort"],
            }
        )

    def trader_buys(info, tpl, ancestors):
        if tpl in info["prohib_ids"] or ancestors & info["prohib_categories"]:
            return False
        return tpl in info["buy_ids"] or bool(ancestors & info["buy_categories"])

    records = {}
    for tpl, template in items.items():
        if template.get("_type") != "Item":
            continue
        name = (en.get(f"{tpl} Name") or "").strip()
        short = (en.get(f"{tpl} ShortName") or "").strip()
        if not name:
            continue
        props = template.get("_props") or {}
        hb = handbook_by_id.get(tpl)
        base_price = hb["Price"] if hb else 0
        ancestors = set(chain(tpl))

        sell = []
        if base_price:
            for info in trader_info:
                if info["pct"] <= 0 or not trader_buys(info, tpl, ancestors):
                    continue
                roubles = round(base_price * info["pct"])
                if roubles < 1:
                    continue
                currency = info["currency"]
                if currency == "RUB" or currency not in courses:
                    sell.append({"t": info["name"], "p": roubles, "c": "RUB"})
                else:
                    sell.append(
                        {
                            "t": info["name"],
                            "p": round(roubles / courses[currency]),
                            "c": currency,
                            "r": roubles,
                        }
                    )
        sell.sort(key=offer_sort_key, reverse=True)

        flea = prices.get(tpl)
        if not flea and not sell:
            continue
        records[tpl] = {
            "id": tpl,
            "name": name,
            "short": short,
            "w": props.get("Width") or 1,
            "h": props.get("Height") or 1,
            "fleaAvg": flea,
            "fleaLow": None,
            "fleaChange48": None,
            "fee": None,
            "icon": None,
            "sell": sell,
            "buy": [],
        }

    # Buy-from offers: cash entries in each trader's assort. Barter
    # schemes (payment in items, not currency) are skipped in seed mode.
    for info in trader_info:
        assort = info["assort"]
        scheme = assort.get("barter_scheme") or {}
        loyalty = assort.get("loyal_level_items") or {}
        best = {}
        for entry in assort.get("items") or []:
            if entry.get("parentId") != "hideout":
                continue
            tpl = entry.get("_tpl")
            if tpl not in records:
                continue
            levels = scheme.get(entry["_id"]) or []
            if not levels or not levels[0]:
                continue
            payment = levels[0][0]
            currency = CURRENCY_TEMPLATES.get(payment.get("_tpl"))
            if not currency:
                continue  # barter offer
            ll = loyalty.get(entry["_id"])
            # Assort dollar/euro counts can be fractional in the source
            # data; the game charges whole units.
            offer = {"t": info["name"], "p": round(payment["count"]), "c": currency}
            if currency != "RUB":
                offer["r"] = round(payment["count"] * courses.get(currency, 1))
            if ll:
                offer["req"] = f"LL{ll}"
            key = (ll or 1, offer_sort_key(offer))
            if tpl not in best or key < best[tpl][0]:
                best[tpl] = (key, offer)
        for tpl, (_, offer) in best.items():
            records[tpl]["buy"].append(offer)
    for record in records.values():
        record["buy"].sort(key=offer_sort_key)

    trader_names = [info["name"] for info in trader_info]
    return list(records.values()), trader_names, courses


# ---------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()

    records = None
    meta = {"fetchedAt": now_iso()}
    api_items = try_api(args.attempts, args.delay)
    if api_items:
        records = build_from_api(api_items)
        meta["source"] = "tarkov.dev"
        meta["sourceNote"] = (
            "Live snapshot of the tarkov.dev GraphQL API "
            "(api.tarkov.dev/graphql): flea averages and trader offers."
        )
    else:
        print("Falling back to the SPT seed dataset.")
        try:
            seed = download_spt()
            records, trader_names, courses = build_from_spt(*seed)
        except Exception as exc:  # noqa: BLE001
            print(f"SPT seed failed too: {exc}", file=sys.stderr)
            print("Existing price index left untouched.", file=sys.stderr)
            return 1
        meta["source"] = "spt-seed"
        meta["sourceNote"] = (
            "Seed snapshot from the SPT open game database "
            "(github.com/sp-tarkov/server). Flea prices are an SPT "
            "snapshot; trader sell prices are derived from handbook "
            "base prices x each trader's loyalty-1 buyback percentage "
            "(SPT TraderHelper model) and trader assort cash offers — "
            "approximations of the live game. Refresh against the "
            "tarkov.dev API when it is reachable for live values."
        )
        meta["seedTraders"] = trader_names
        meta["seedCurrencyCourse"] = courses

    meta["itemCount"] = len(records)
    payload = {"meta": meta, "items": records}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT_PATH.write_text(text + "\n")
    size_kb = len(text.encode()) / 1024

    print(f"Wrote {OUT_PATH}: {len(records)} items, {size_kb:.0f} KiB, source={meta['source']}")
    by_id = {r["id"]: r for r in records}
    samples = [
        by_id.get("5c0530ee86f774697952d952"),  # LEDX Skin Transilluminator
        by_id.get("544fb45d4bdc2dee738b4568"),  # Salewa first aid kit
        next((r for r in records if r["buy"]), None),
    ]
    for sample in samples:
        if not sample:
            continue
        best = sample["sell"][0] if sample["sell"] else None
        print(
            f"  sample {sample['name']!r}: fleaAvg={sample['fleaAvg']}, "
            f"bestSell={best}, buyOffers={len(sample['buy'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
