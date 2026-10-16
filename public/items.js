// Tarkov Map — item price lookup client script.
//
// The page itself is server-rendered by Proa. This script fetches the
// bundled price index from data/prices.json exactly once and then does
// search and detail rendering entirely in the browser: no per-lookup
// network calls, so typeahead is instant and the page keeps working
// when the upstream price API is down. The index is produced offline
// by scripts/fetch_prices.py (tarkov.dev API snapshot, or a clearly
// labelled SPT seed snapshot when the API is unreachable).
(() => {
    "use strict";

    const input = document.getElementById("price-search-input");
    const status = document.getElementById("price-status");
    const seedNote = document.getElementById("seed-note");
    const resultsEl = document.getElementById("price-results");
    const detailBody = document.getElementById("price-detail-body");
    if (!input || !resultsEl || !detailBody) return;

    const CURRENCY_SYMBOL = { RUB: "₽", USD: "$", EUR: "€" };
    const MAX_RESULTS = 40;

    let items = [];
    let selectedId = null;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function fmtNumber(n) {
        return Math.round(n).toLocaleString("en-US");
    }

    function fmtPrice(price, currency) {
        const symbol = CURRENCY_SYMBOL[currency] || currency || "";
        if (currency === "RUB") return `${fmtNumber(price)} ₽`;
        return `${symbol}${fmtNumber(price)}`;
    }

    // Rouble value of an offer: the index stores `r` (rouble equivalent)
    // for non-rouble offers; rouble offers are their own equivalent.
    function roubles(offer) {
        if (offer.r) return offer.r;
        return offer.c === "RUB" ? offer.p : null;
    }

    function bestSell(item) {
        return item.sell && item.sell.length ? item.sell[0] : null;
    }

    function normalize(text) {
        return text.toLowerCase().replace(/[^a-z0-9]/g, "");
    }

    function rank(item, q, nq) {
        const name = item.name.toLowerCase();
        const short = item.short.toLowerCase();
        if (short && short === q) return 0;
        if (name.startsWith(q)) return 1;
        if (short && short.startsWith(q)) return 2;
        if (nq && item._n.startsWith(nq)) return 3;
        return 4;
    }

    function search(query) {
        const q = query.trim().toLowerCase();
        if (!q) return [];
        const nq = normalize(q);
        const matches = [];
        for (const item of items) {
            if (
                item.name.toLowerCase().includes(q) ||
                (item.short && item.short.toLowerCase().includes(q)) ||
                (nq && (item._n.includes(nq) || item._s.includes(nq)))
            ) {
                matches.push(item);
            }
        }
        matches.sort((a, b) => {
            const rankDiff = rank(a, q, nq) - rank(b, q, nq);
            if (rankDiff) return rankDiff;
            const fleaDiff = (b.fleaAvg || 0) - (a.fleaAvg || 0);
            if (fleaDiff) return fleaDiff;
            return a.name.localeCompare(b.name);
        });
        return matches.slice(0, MAX_RESULTS);
    }

    function renderResults() {
        resultsEl.replaceChildren();
        if (!input.value.trim()) return;
        const matches = search(input.value);
        if (!matches.length) {
            resultsEl.appendChild(
                el("p", "price-no-results", "No items match that search."),
            );
            return;
        }
        for (const item of matches) {
            const button = el("button", "price-result");
            button.type = "button";
            if (item.id === selectedId) button.classList.add("is-active");
            const main = el("span", "price-result-main");
            main.appendChild(el("span", "price-result-name", item.name));
            const sub = `${item.short ? `${item.short} · ` : ""}${item.w}×${item.h}`;
            main.appendChild(el("span", "price-result-sub", sub));
            button.appendChild(main);
            const best = bestSell(item);
            const hint = item.fleaAvg
                ? `Flea ${fmtPrice(item.fleaAvg, "RUB")}`
                : best
                  ? `${best.t} ${fmtPrice(best.p, best.c)}`
                  : "No price data";
            button.appendChild(el("span", "price-result-price", hint));
            button.addEventListener("click", () => select(item, button));
            resultsEl.appendChild(button);
        }
    }

    function priceRow(label, value, valueClass) {
        const row = el("div", "price-row");
        row.appendChild(el("span", "price-row-label", label));
        row.appendChild(el("span", `price-row-value${valueClass ? ` ${valueClass}` : ""}`, value));
        return row;
    }

    function offerRow(offer, showReq) {
        const row = el("div", "price-row");
        row.appendChild(el("span", "price-row-label", offer.t));
        let text = fmtPrice(offer.p, offer.c);
        const rub = roubles(offer);
        if (offer.c !== "RUB" && rub) text += ` (≈ ${fmtNumber(rub)} ₽)`;
        if (showReq && offer.req) text += ` · ${offer.req}`;
        row.appendChild(el("span", "price-row-value", text));
        return row;
    }

    function section(title) {
        const wrap = el("div", "price-section");
        wrap.appendChild(el("h3", "price-section-title", title));
        return wrap;
    }

    function renderDetail(item) {
        detailBody.replaceChildren();
        detailBody.appendChild(el("p", "detail-name", item.name));
        const slots = item.w * item.h;
        detailBody.appendChild(
            el(
                "p",
                "detail-meta",
                `${item.short || "—"} · ${item.w}×${item.h} · ${slots} slot${slots === 1 ? "" : "s"}`,
            ),
        );
        if (item.icon) {
            const img = document.createElement("img");
            img.className = "price-icon";
            img.src = item.icon;
            img.alt = item.name;
            img.loading = "lazy";
            detailBody.appendChild(img);
        }

        const best = bestSell(item);
        const bestRub = best ? roubles(best) : null;

        if (item.fleaAvg) {
            const flea = section("Flea market");
            flea.appendChild(priceRow("Average (24h)", fmtPrice(item.fleaAvg, "RUB")));
            flea.appendChild(
                priceRow("Last low", item.fleaLow ? fmtPrice(item.fleaLow, "RUB") : "—"),
            );
            if (item.fleaChange48 === null || item.fleaChange48 === undefined) {
                flea.appendChild(priceRow("48h change", "—"));
            } else {
                const change = item.fleaChange48;
                const sign = change > 0 ? "+" : "";
                flea.appendChild(
                    priceRow(
                        "48h change",
                        `${sign}${change.toFixed(2)}%`,
                        change > 0 ? "is-up" : change < 0 ? "is-down" : "",
                    ),
                );
            }
            flea.appendChild(
                priceRow("Listing fee", item.fee ? fmtPrice(item.fee, "RUB") : "—"),
            );
            detailBody.appendChild(flea);
        }

        if (best) {
            const callout = el("div", "price-best");
            let text = `Best trader: ${best.t} — ${fmtPrice(best.p, best.c)}`;
            if (best.c !== "RUB" && bestRub) text += ` (≈ ${fmtNumber(bestRub)} ₽)`;
            callout.appendChild(el("span", "price-best-text", text));
            detailBody.appendChild(callout);
        }

        // Verdict: flea (net of fee) versus the best trader offer.
        let verdict = null;
        if (item.fleaAvg && best && bestRub) {
            const net = item.fleaAvg - (item.fee || 0);
            if (net > bestRub) {
                verdict = `Flea pays ~${fmtNumber(net - bestRub)} ₽ more${item.fee ? " after fee" : ""}.`;
            } else if (bestRub > net) {
                verdict = `Vendor it: ${best.t} beats flea after fee by ~${fmtNumber(bestRub - net)} ₽.`;
            } else {
                verdict = "Flea and the best trader pay about the same.";
            }
        } else if (!item.fleaAvg && best) {
            verdict = `No flea data — vendor it to ${best.t}.`;
        } else if (item.fleaAvg && !best) {
            verdict = "No trader buys it — flea is the only market.";
        }
        if (verdict) {
            detailBody.appendChild(el("p", "price-verdict", verdict));
        }

        if (item.fleaAvg || bestRub) {
            const perSlot = section("Price per slot");
            if (item.fleaAvg) {
                perSlot.appendChild(
                    priceRow("Flea", `${fmtNumber(item.fleaAvg / slots)} ₽ / slot`),
                );
            }
            if (bestRub) {
                perSlot.appendChild(
                    priceRow("Best trader", `${fmtNumber(bestRub / slots)} ₽ / slot`),
                );
            }
            detailBody.appendChild(perSlot);
        }

        if (item.sell.length) {
            const sellSection = section("Sell to traders");
            for (const offer of item.sell) sellSection.appendChild(offerRow(offer, false));
            detailBody.appendChild(sellSection);
        }
        if (item.buy.length) {
            const buySection = section("Buy from traders");
            for (const offer of item.buy) buySection.appendChild(offerRow(offer, true));
            detailBody.appendChild(buySection);
        }
    }

    function select(item, button) {
        selectedId = item.id;
        for (const node of resultsEl.querySelectorAll(".price-result")) {
            node.classList.remove("is-active");
        }
        if (button) button.classList.add("is-active");
        renderDetail(item);
    }

    input.addEventListener("input", renderResults);

    fetch("data/prices.json")
        .then((response) => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then((data) => {
            items = data.items || [];
            for (const item of items) {
                item._n = normalize(item.name || "");
                item._s = normalize(item.short || "");
            }
            const meta = data.meta || {};
            const sourceLabel =
                meta.source === "spt-seed" ? "SPT seed snapshot" : "tarkov.dev snapshot";
            const date = (meta.fetchedAt || "").slice(0, 10);
            if (status) {
                status.textContent = `${items.length.toLocaleString("en-US")} items · ${sourceLabel}${date ? ` · ${date}` : ""}. Type to search.`;
            }
            if (seedNote && meta.source === "spt-seed") {
                seedNote.textContent = `Seed snapshot (SPT data, ${date || "unknown date"}) — trader prices approximate; live tarkov.dev refresh pending.`;
            }
            renderResults();
        })
        .catch((error) => {
            if (status) status.textContent = `Could not load the price index (${error.message}).`;
        });
})();
