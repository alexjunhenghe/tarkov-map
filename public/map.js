// Tarkov Map — Interchange client script.
//
// The page itself is server-rendered by Proa. This one script adds the
// interactive layer: it fetches the bundled marker snapshot from
// /data/interchange.json, draws markers into the inlined basemap SVG,
// and implements pan / zoom, floor switching, layer toggles and the
// marker detail card. No framework, no build step.
(() => {
    "use strict";

    const stage = document.getElementById("map-stage");
    if (!stage) return;
    const svg = stage.querySelector("svg");
    if (!svg) return;

    const SVG_NS = "http://www.w3.org/2000/svg";
    const FLOOR_GROUPS = {
        exterior: "Ground_Level",
        garage: "Ground_Level",
        mall1: "First_Floor",
        mall2: "Second_Floor",
    };
    const FLOOR_NAMES = {
        exterior: "Exterior",
        garage: "Parking Garage",
        mall1: "Mall Floor 1",
        mall2: "Mall Floor 2",
    };
    const CATEGORY_NAMES = {
        extract: "Extract",
        pmc_spawn: "PMC spawn",
        scav_spawn: "Scav spawn",
        boss: "Boss area",
        lock: "Locked door",
        switch: "Switch",
        hazard: "Hazard",
        transit: "Transit",
        loot: "Loot container",
    };
    // Teardrop pin: tip at the marker point, head centered at (0, -15).
    const PIN_D =
        "M0 0 C -4.6 -6.8 -8.5 -9.8 -8.5 -15 A 8.5 8.5 0 1 1 8.5 -15 C 8.5 -9.8 4.6 -6.8 0 0 Z";
    // White pictograms drawn in a -5..5 box at the pin head. Stroke
    // icons use class pin-icon; filled ones pin-icon-fill.
    const PIN_ICONS = {
        extract: [
            ["path", { d: "M-3.4 3.4 L3.4 -3.4 M-1 -3.4 H3.4 V1" }],
        ],
        transit: [
            ["path", { d: "M-4.2 -1.9 H2.8 M0.9 -4.1 L3.1 -1.9 L0.9 0.3" }],
            ["path", { d: "M4.2 1.9 H-2.8 M-0.9 4.1 L-3.1 1.9 L-0.9 -0.3" }],
        ],
        boss: [
            ["polygon", { class: "pin-icon-fill", points: "0,-4.6 1.35,-1.6 4.4,-1.45 2.1,0.95 3,4.1 0,2.3 -3,4.1 -2.1,0.95 -4.4,-1.45 -1.35,-1.6" }],
        ],
        lock: [
            ["rect", { x: -3.1, y: -0.6, width: 6.2, height: 5.4, rx: 1 }],
            ["path", { d: "M-2 -0.6 V-2 A2 2 0 0 1 2 -2 V-0.6" }],
        ],
        switch: [
            ["polygon", { class: "pin-icon-fill", points: "1.6,-4.6 -2.9,0.9 -0.7,0.9 -1.6,4.6 2.9,-0.9 0.7,-0.9" }],
        ],
        hazard: [
            ["path", { d: "M0 -4.2 L4.2 3.6 H-4.2 Z M0 -1.2 V0.9" }],
            ["circle", { class: "pin-icon-fill", cy: 2.4, r: 0.85 }],
        ],
        pmc_spawn: [
            ["circle", { class: "pin-icon-fill", cy: -1.9, r: 1.8 }],
            ["path", { class: "pin-icon-fill", d: "M-3.6 3.8 A 3.9 3.9 0 0 1 3.6 3.8 Z" }],
        ],
        scav_spawn: [
            ["circle", { class: "pin-icon-fill", cy: -1.9, r: 1.8 }],
            ["path", { class: "pin-icon-fill", d: "M-3.6 3.8 A 3.9 3.9 0 0 1 3.6 3.8 Z" }],
        ],
        loot: [
            ["rect", { x: -3.3, y: -2.8, width: 6.6, height: 5.6 }],
            ["path", { d: "M-3.3 -2.8 L3.3 2.8 M3.3 -2.8 L-3.3 2.8" }],
        ],
    };

    const vb = svg.viewBox.baseVal;
    const FULL = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
    let view = { ...FULL };
    let activeFloor = "exterior";
    let snapshot = null;
    let builtCluster = null; // cluster mode used by the last buildMarkers()
    let markerEls = []; // {el, marker}
    let selectedEl = null;
    let userMoved = false; // true once the user pans/zooms manually
    const enabledCategories = new Set();

    // ---------- view / camera ----------
    function stageAspect() {
        const rect = stage.getBoundingClientRect();
        return rect.height > 0 ? rect.width / rect.height : FULL.w / FULL.h;
    }

    function applyView() {
        const aspect = stageAspect();
        view.h = view.w / aspect;
        svg.setAttribute(
            "viewBox",
            `${view.x} ${view.y} ${view.w} ${view.h}`,
        );
    }

    function maxViewWidth() {
        // The stage is usually wider than the basemap's native aspect,
        // so fitting the full height can require a view wider than
        // FULL.w (with empty margin at the sides). Clamping the width
        // to FULL.w cropped the map's top and bottom and made it
        // impossible to zoom out to the whole floor.
        return Math.max(FULL.w, FULL.h * stageAspect());
    }

    function setView(cx, cy, w) {
        view.w = Math.max(40, Math.min(maxViewWidth(), w));
        view.h = view.w / stageAspect();
        view.x = cx - view.w / 2;
        view.y = cy - view.h / 2;
        applyView();
        refreshMarkerVisibility();
    }

    function fitRect(rect, padRatio) {
        const pad = Math.max(rect.w, rect.h) * (padRatio ?? 0.05);
        // Fit both axes: the padded rect's height must fit too, which
        // on a wide stage means a wider view than the rect itself.
        const w = Math.max(rect.w + pad * 2, (rect.h + pad * 2) * stageAspect());
        setView(rect.x + rect.w / 2, rect.y + rect.h / 2, w);
    }

    function clientToSvg(clientX, clientY) {
        const rect = stage.getBoundingClientRect();
        return {
            x: view.x + ((clientX - rect.left) / rect.width) * view.w,
            y: view.y + ((clientY - rect.top) / rect.height) * view.h,
        };
    }

    // Project a game position into SVG coords with the same transform
    // tarkov.dev uses (mirrors scripts/fetch_data.py). Only needed here
    // for the garage fit rectangle (the mall footprint).
    function projectGame(x, z, t) {
        const rad = ((t.rotation || 0) * Math.PI) / 180;
        const rx = x * Math.cos(rad) - z * Math.sin(rad);
        const rz = x * Math.sin(rad) + z * Math.cos(rad);
        return {
            px: t.scale * rx + t.marginX,
            py: -t.scale * rz + t.marginY,
        };
    }

    function gameRectToSvg(x0, z0, x1, z1, t) {
        const corners = [
            projectGame(x0, z0, t),
            projectGame(x0, z1, t),
            projectGame(x1, z0, t),
            projectGame(x1, z1, t),
        ];
        const bounds = t.bounds;
        const proj = bounds.map(([bx, bz]) => projectGame(bx, bz, t));
        const minPx = Math.min(...proj.map((p) => p.px));
        const maxPx = Math.max(...proj.map((p) => p.px));
        const minPy = Math.min(...proj.map((p) => p.py));
        const maxPy = Math.max(...proj.map((p) => p.py));
        const toSvg = (p) => ({
            x: ((p.px - minPx) / (maxPx - minPx)) * FULL.w + FULL.x,
            y: ((maxPy - p.py) / (maxPy - minPy)) * FULL.h + FULL.y,
        });
        const pts = corners.map(toSvg);
        const xs = pts.map((p) => p.x);
        const ys = pts.map((p) => p.y);
        return {
            x: Math.min(...xs),
            y: Math.min(...ys),
            w: Math.max(...xs) - Math.min(...xs),
            h: Math.max(...ys) - Math.min(...ys),
        };
    }

    function fitFloor(floor) {
        if (floor === "exterior" || !snapshot) {
            fitRect(FULL, 0.01);
            return;
        }
        if (floor === "garage") {
            // The garage lives under the mall footprint from the map
            // config's floor extents: x in [-222, 120], z in [-327, 218].
            fitRect(gameRectToSvg(-222, -327, 120, 218, snapshot.transform), 0.08);
            return;
        }
        // Interior floors: the SVG floor groups include wide empty
        // aprons and ramps around the building, so fitting the raw
        // artwork bounds leaves the actual mall tiny in the middle of
        // the pane — worst on wide screens. The floor's own labels
        // (store and area names) tile the usable interior, so fit
        // those, expanded to take in the walls and the markers just
        // outside them.
        const floorLabels = (snapshot.labels || []).filter((l) => l.floor === floor);
        if (floorLabels.length) {
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            for (const l of floorLabels) {
                minX = Math.min(minX, l.sx);
                minY = Math.min(minY, l.sy);
                maxX = Math.max(maxX, l.sx);
                maxY = Math.max(maxY, l.sy);
            }
            const M = 70;
            fitRect(
                { x: minX - M, y: minY - M, w: maxX - minX + 2 * M, h: maxY - minY + 2 * M },
                0.04,
            );
            return;
        }
        const group = document.getElementById(FLOOR_GROUPS[floor]);
        if (group) {
            try {
                const box = group.getBBox();
                fitRect({ x: box.x, y: box.y, w: box.width, h: box.height }, 0.06);
                return;
            } catch (err) {
                /* fall through to full fit */
            }
        }
        fitRect(FULL, 0.01);
    }

    // ---------- floors ----------
    function setFloor(floor, refit) {
        activeFloor = floor;
        for (const [id, groupId] of Object.entries(FLOOR_GROUPS)) {
            const group = document.getElementById(groupId);
            if (group) {
                group.style.display = groupId === FLOOR_GROUPS[floor] ? "" : "none";
            }
            void id;
        }
        document.querySelectorAll("[data-floor-tab]").forEach((btn) => {
            btn.classList.toggle("is-active", btn.dataset.floorTab === floor);
        });
        if (refit) {
            userMoved = false;
            fitFloor(floor);
        }
        refreshMarkerVisibility();
    }

    // ---------- markers ----------
    function el(name, attrs) {
        const node = document.createElementNS(SVG_NS, name);
        for (const [key, value] of Object.entries(attrs || {})) {
            node.setAttribute(key, value);
        }
        return node;
    }

    function refreshMarkerVisibility() {
        for (const { el: node, marker } of markerEls) {
            const visible =
                marker.floor === activeFloor &&
                enabledCategories.has(marker.category);
            node.style.display = visible ? "" : "none";
        }
        const labels = svg.querySelectorAll(".map-label");
        labels.forEach((label) => {
            label.style.display = label.dataset.floor === activeFloor ? "" : "none";
        });
    }

    function selectMarker(node, marker) {
        if (selectedEl) selectedEl.classList.remove("is-selected");
        selectedEl = node;
        if (node) node.classList.add("is-selected");
        document.getElementById("detail-name").textContent = marker.name;
        document.getElementById("detail-meta").textContent =
            `${CATEGORY_NAMES[marker.category] || marker.category} · ${FLOOR_NAMES[marker.floor] || marker.floor}`;
        document.getElementById("detail-note").textContent =
            marker.note || "No extra conditions — just walk in and loot.";
    }

    function buildMarkers() {
        const old = svg.querySelectorAll(".marker-layer, .label-layer");
        old.forEach((node) => node.remove());
        markerEls = [];

        const labelLayer = el("g", { class: "label-layer" });
        for (const label of snapshot.labels || []) {
            const text = el("text", {
                class: "map-label",
                x: label.sx,
                y: label.sy,
                "text-anchor": "middle",
            });
            text.dataset.floor = label.floor;
            text.textContent = label.name;
            labelLayer.appendChild(text);
        }
        svg.appendChild(labelLayer);

        const layer = el("g", { class: "marker-layer" });
        const markers = snapshot.markers || [];

        // Loot containers are dense (~800): bucket them into a grid and
        // draw one cluster dot per cell until the player zooms in.
        const CLUSTER_CELL = 26;
        const clusterLoot = view.w > 520;
        builtCluster = clusterLoot;
        const lootCells = new Map();
        const singles = [];
        for (const marker of markers) {
            if (marker.category === "loot" && clusterLoot) {
                const key = `${marker.floor}:${Math.floor(marker.sx / CLUSTER_CELL)}:${Math.floor(marker.sy / CLUSTER_CELL)}`;
                if (!lootCells.has(key)) lootCells.set(key, []);
                lootCells.get(key).push(marker);
            } else {
                singles.push(marker);
            }
        }

        for (const marker of singles) {
            layer.appendChild(makeMarker(marker));
        }
        for (const cell of lootCells.values()) {
            const cx = cell.reduce((sum, m) => sum + m.sx, 0) / cell.length;
            const cy = cell.reduce((sum, m) => sum + m.sy, 0) / cell.length;
            const rep = { ...cell[0], sx: cx, sy: cy };
            const node = makeMarker(rep, cell.length);
            node.addEventListener("click", (event) => {
                if (dragMoved) return;
                event.stopPropagation();
                setView(cx, cy, 300);
            });
            layer.appendChild(node);
        }
        svg.appendChild(layer);
        refreshMarkerVisibility();
    }

    function makeMarker(marker, clusterCount) {
        const g = el("g", {
            class: `marker cat-${marker.category}${clusterCount ? " is-cluster" : ""}`,
            transform: `translate(${marker.sx} ${marker.sy})`,
        });
        g.appendChild(el("ellipse", { class: "pin-shadow", cx: 0, cy: 0.8, rx: 5.2, ry: 1.9 }));
        g.appendChild(el("circle", { class: "hit", cx: 0, cy: -13, r: 12.5 }));
        if (clusterCount) {
            g.appendChild(el("circle", { class: "badge", cx: 0, cy: -13, r: 10 }));
            const text = el("text", { class: "cluster-count", y: -9.6, "text-anchor": "middle" });
            text.textContent = clusterCount;
            g.appendChild(text);
        } else {
            g.appendChild(el("path", { class: "pin", d: PIN_D }));
            const icon = el("g", { class: "pin-icon", transform: "translate(0 -15)" });
            for (const [tag, attrs] of PIN_ICONS[marker.category] || PIN_ICONS.loot) {
                icon.appendChild(el(tag, attrs));
            }
            g.appendChild(icon);
            const title = el("title");
            title.textContent = marker.name;
            g.appendChild(title);
            g.addEventListener("click", (event) => {
                if (dragMoved) return;
                event.stopPropagation();
                selectMarker(g, marker);
            });
        }
        markerEls.push({ el: g, marker });
        return g;
    }

    // ---------- pan / zoom ----------
    let dragMoved = false;
    const pointers = new Map();
    let lastPinchDist = null;

    // NOTE: no setPointerCapture on the stage. Capturing the pointer
    // retargets every following pointer event (including the click) to
    // the stage element, so clicks never reached the markers. Moves and
    // ups are tracked on window instead, which also keeps pans alive
    // when the pointer leaves the stage.
    stage.addEventListener("pointerdown", (event) => {
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        userMoved = true;
        dragMoved = false;
        lastPinchDist = null;
    });

    window.addEventListener("pointermove", (event) => {
        if (!pointers.has(event.pointerId)) return;
        const prev = pointers.get(event.pointerId);
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        if (pointers.size === 1) {
            const dx = event.clientX - prev.x;
            const dy = event.clientY - prev.y;
            if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
            const rect = stage.getBoundingClientRect();
            view.x -= (dx / rect.width) * view.w;
            view.y -= (dy / rect.height) * view.h;
            applyView();
        } else if (pointers.size === 2) {
            dragMoved = true;
            const [a, b] = [...pointers.values()];
            const dist = Math.hypot(a.x - b.x, a.y - b.y);
            if (lastPinchDist) {
                const mid = clientToSvg((a.x + b.x) / 2, (a.y + b.y) / 2);
                zoomAt(mid, lastPinchDist / dist);
            }
            lastPinchDist = dist;
        }
    });

    function scheduleClusterRebuild() {
        clearTimeout(scheduleClusterRebuild._timer);
        scheduleClusterRebuild._timer = setTimeout(() => {
            if (snapshot && (view.w > 520) !== builtCluster) buildMarkers();
        }, 180);
    }

    function endPointer(event) {
        pointers.delete(event.pointerId);
        if (pointers.size < 2) lastPinchDist = null;
        scheduleClusterRebuild();
    }
    window.addEventListener("pointerup", endPointer);
    window.addEventListener("pointercancel", endPointer);

    function zoomAt(svgPoint, factor) {
        const newW = Math.max(40, Math.min(maxViewWidth(), view.w * factor));
        const ratio = newW / view.w;
        view.x = svgPoint.x - (svgPoint.x - view.x) * ratio;
        view.y = svgPoint.y - (svgPoint.y - view.y) * ratio;
        view.w = newW;
        applyView();
    }

    stage.addEventListener(
        "wheel",
        (event) => {
            event.preventDefault();
            userMoved = true;
            const point = clientToSvg(event.clientX, event.clientY);
            zoomAt(point, event.deltaY > 0 ? 1.15 : 1 / 1.15);
            scheduleClusterRebuild();
        },
        { passive: false },
    );

    stage.addEventListener("click", () => {
        if (dragMoved) return;
        if (selectedEl) {
            selectedEl.classList.remove("is-selected");
            selectedEl = null;
        }
    });

    // ---------- controls ----------
    document.querySelectorAll("[data-floor-tab]").forEach((btn) => {
        btn.addEventListener("click", () => setFloor(btn.dataset.floorTab, true));
    });
    document.querySelector("[data-fit-button]")?.addEventListener("click", () => {
        userMoved = false;
        fitFloor(activeFloor);
    });

    document.querySelectorAll("[data-layer]").forEach((input) => {
        input.checked = input.dataset.defaultOn === "true";
        if (input.checked) enabledCategories.add(input.dataset.layer);
        input.addEventListener("change", () => {
            if (input.checked) enabledCategories.add(input.dataset.layer);
            else enabledCategories.delete(input.dataset.layer);
            refreshMarkerVisibility();
        });
    });

    document.querySelectorAll("[data-extract-name]").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!snapshot) return;
            const marker = (snapshot.markers || []).find(
                (m) => m.category === "extract" && m.name === btn.dataset.extractName,
            );
            if (!marker) return;
            setFloor(marker.floor, false);
            userMoved = true; // a deliberate jump: don't refit over it
            setView(marker.sx, marker.sy, 320);
            const found = markerEls.find(
                ({ marker: m }) => m === marker || (m.name === marker.name && m.category === "extract"),
            );
            if (found) selectMarker(found.el, marker);
        });
    });

    window.addEventListener("resize", () => {
        // Until the user takes over the camera, keep the floor fitted:
        // the stage's aspect can still be settling while the page loads
        // (fonts, scrollbar, sidebar layout), and a fit computed against
        // a stale aspect leaves the map cropped.
        if (!userMoved && snapshot) fitFloor(activeFloor);
        else applyView();
    });

    // ---------- init ----------
    setFloor("exterior", false);
    applyView();
    fetch("/data/interchange.json")
        .then((resp) => {
            if (!resp.ok) throw new Error(`snapshot fetch failed: ${resp.status}`);
            return resp.json();
        })
        .then((data) => {
            snapshot = data;
            const counts = {};
            for (const marker of data.markers || []) {
                counts[marker.category] = (counts[marker.category] || 0) + 1;
            }
            document.querySelectorAll("[data-count-for]").forEach((span) => {
                span.textContent = counts[span.dataset.countFor] || 0;
            });
            buildMarkers();
            fitFloor("exterior");
            // Refit once layout has settled (see the resize handler):
            // the first fit can run before the stage reaches its final
            // size, which cropped the map's top and bottom on load.
            requestAnimationFrame(() => {
                if (!userMoved) fitFloor(activeFloor);
            });
            setTimeout(() => {
                if (!userMoved) fitFloor(activeFloor);
            }, 350);
        })
        .catch((error) => {
            document.getElementById("detail-note").textContent =
                `Marker data failed to load (${error.message}). The basemap still works.`;
        });
})();
