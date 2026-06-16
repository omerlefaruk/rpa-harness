"""RPA Challenge shortest-path workflow.

Production mode uses the challenge backend. Fixture mode exists only to prove
the browser/form path when the public challenge API is unavailable.
"""

from __future__ import annotations

import html
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from harness import RPAWorkflow


TARGET_URL = "https://rpachallenge.com/assets/shortestPath/public/shortestpath.html"
BACKEND_URL = "http://uipath509.westeurope.cloudapp.azure.com:4444/api/v1"
DEFAULT_OUTPUT_JSON = "runs/rpa_challenge_shortest_path/shortest_path_report.json"
DEFAULT_OUTPUT_HTML = "reports/rpa_challenge_shortest_path/shortest_path_report.html"
DEFAULT_EVIDENCE_DIR = "runs/rpa_challenge_shortest_path/evidence"
DEFAULT_RECON_DIR = "runs/rpa_challenge_shortest_path/recon"

SUPPLIES = [
    {
        "_id": "G-1001",
        "name": "Swagelok",
        "address1": "32100 Diamond Pkwy",
        "address2": "Ste 1488",
        "city": "Solon",
        "state": "OH",
        "zip": 44139,
        "color": "green",
        "type": "supply",
        "lat": "41.3563197",
        "lng": "-81.4535158",
    },
    {
        "_id": "G-1004",
        "name": "TwitchTV",
        "address1": "225 Bush St",
        "address2": "Floor 18",
        "city": "San Francisco",
        "state": "CA",
        "zip": 94104,
        "color": "green",
        "type": "supply",
        "lat": "37.7908821",
        "lng": "-122.4015519",
    },
    {
        "_id": "G-1006",
        "name": "GE Gas Turbine",
        "address1": "4045 Scenic Hwy",
        "address2": "Warehouse",
        "city": "Baton Rouge",
        "state": "LA",
        "zip": 70805,
        "color": "green",
        "type": "supply",
        "lat": "30.4860721",
        "lng": "-91.1697231",
    },
]

FIXTURE_DEMANDS = [
    {
        "_id": "D-2001",
        "name": "Cleveland Foundry",
        "address1": "50 Public Sq",
        "address2": "Dock 4",
        "city": "Cleveland",
        "state": "OH",
        "zip": 44113,
        "cargo": "Valve parts",
        "color": "red",
        "type": "demand",
        "lat": "41.49932",
        "lng": "-81.69436",
    },
    {
        "_id": "D-2002",
        "name": "Bay Media Lab",
        "address1": "1 Market St",
        "address2": "Pier 3",
        "city": "San Francisco",
        "state": "CA",
        "zip": 94105,
        "cargo": "Studio equipment",
        "color": "red",
        "type": "demand",
        "lat": "37.79357",
        "lng": "-122.39533",
    },
    {
        "_id": "D-2003",
        "name": "Delta Compressor",
        "address1": "100 River Rd",
        "address2": "Bay 2",
        "city": "Baton Rouge",
        "state": "LA",
        "zip": 70802,
        "cargo": "Turbine tooling",
        "color": "red",
        "type": "demand",
        "lat": "30.45147",
        "lng": "-91.18715",
    },
    {
        "_id": "D-2004",
        "name": "Detroit Assembly",
        "address1": "200 Woodward Ave",
        "address2": "Gate A",
        "city": "Detroit",
        "state": "MI",
        "zip": 48226,
        "cargo": "Line sensors",
        "color": "red",
        "type": "demand",
        "lat": "42.33143",
        "lng": "-83.04575",
    },
    {
        "_id": "D-2005",
        "name": "Reno Esports",
        "address1": "300 Center St",
        "address2": "Suite 8",
        "city": "Reno",
        "state": "NV",
        "zip": 89501,
        "cargo": "Broadcast racks",
        "color": "red",
        "type": "demand",
        "lat": "39.52963",
        "lng": "-119.8138",
    },
]


class RPAChallengeShortestPathWorkflow(RPAWorkflow):
    name = "rpa_challenge_shortest_path"
    tags = ["rpa", "browser", "external", "public-site", "rpa-challenge"]
    max_retries_per_record = 0

    async def setup(self):
        variables = getattr(self.config, "variables", {}) or {}
        self.mode = str(
            os.getenv("RPA_SHORTEST_PATH_MODE")
            or variables.get("shortest_path_mode")
            or "live"
        ).lower()
        self.target_url = str(variables.get("shortest_path_url") or TARGET_URL)
        self.backend_url = str(variables.get("shortest_path_backend_url") or BACKEND_URL).rstrip("/")
        self.timeout_seconds = float(variables.get("shortest_path_timeout_seconds") or 10)
        self.run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_json = artifact_path(
            variables.get("shortest_path_output_json") or DEFAULT_OUTPUT_JSON,
            mode=self.mode,
            timestamp=self.run_label,
        )
        self.output_html = artifact_path(
            variables.get("shortest_path_output_html") or DEFAULT_OUTPUT_HTML,
            mode=self.mode,
            timestamp=self.run_label,
        )
        self.evidence_dir = Path(variables.get("shortest_path_evidence_dir") or DEFAULT_EVIDENCE_DIR)
        self.recon_dir = Path(variables.get("shortest_path_recon_dir") or DEFAULT_RECON_DIR)
        self.rows: list[dict[str, Any]] = []
        self.preflight: dict[str, Any] = {}
        self.run_started_at = datetime.now().isoformat(timespec="seconds")

    def get_records(self):
        yield {"id": f"shortest_path_{self.mode}"}

    async def process_record(self, record: dict) -> dict:
        if self.mode == "fixture":
            demands = [dict(item) for item in FIXTURE_DEMANDS]
            self.preflight = fixture_preflight(self.target_url, self.backend_url)
            backend_evidence = {"mode": "fixture", "source": "local deterministic fixture"}
            backend_answers = {}
        else:
            self.preflight, demands, backend_answers = live_preflight(
                target_url=self.target_url,
                backend_url=self.backend_url,
                timeout_seconds=self.timeout_seconds,
            )
            if self.preflight["status"] != "passed":
                blocker = await capture_page_recon(
                    self.target_url,
                    self.evidence_dir,
                    headless=bool(getattr(self.config, "headless", True)),
                    browser_name=str(getattr(self.config, "browser", "chromium")),
                )
                self.preflight.setdefault("artifacts", {}).update(blocker)
                self.preflight["artifacts"]["preflight_json"] = write_recon_artifact(
                    self.preflight, self.recon_dir, mode=self.mode, timestamp=self.run_label
                )
                row = {
                    "record_id": record["id"],
                    "status": "failed",
                    "failure_kind": "backend_unavailable",
                    "reason": self.preflight["reason"],
                    "backend": f"{self.backend_url}/places",
                    "preflight": self.preflight,
                    "evidence": blocker,
                    "side_effects": side_effect_summary(self.mode),
                    "next_action": self.preflight["next_action"],
                }
                self.rows.append(row)
                self.record_evidence(row, record=record, stage="backend_preflight")
                return {"status": "failed", "reason": row["reason"], "details": row}
            self.preflight["artifacts"]["preflight_json"] = write_recon_artifact(
                self.preflight, self.recon_dir, mode=self.mode, timestamp=self.run_label
            )
            backend_evidence = self.preflight["backend"]

        plan = build_round_plan(demands)
        if len(plan) != 5:
            row = {
                "record_id": record["id"],
                "status": "failed",
                "failure_kind": "unexpected_demand_count",
                "reason": f"expected 5 demand points, got {len(plan)}",
                "backend": backend_evidence,
                "preflight": self.preflight,
                "side_effects": side_effect_summary(self.mode),
                "next_action": "Check the challenge backend data shape before rerunning.",
            }
            self.rows.append(row)
            return {"status": "failed", "reason": row["reason"], "details": row}

        if self.mode == "fixture":
            backend_answers = {item["demand"]["_id"]: item["supply"]["_id"] for item in plan}
            self.preflight["artifacts"]["preflight_json"] = write_recon_artifact(
                self.preflight, self.recon_dir, mode=self.mode, timestamp=self.run_label
            )

        run = await run_browser_challenge(
            target_url=self.target_url,
            demands=demands,
            valid_pairs=backend_answers,
            evidence_dir=self.evidence_dir,
            headless=bool(getattr(self.config, "headless", True)),
            browser_name=str(getattr(self.config, "browser", "chromium")),
        )
        row = {
            "record_id": record["id"],
            "status": run["status"],
            "mode": self.mode,
            "backend": backend_evidence,
            "rounds": run["rounds"],
            "success_text": run.get("success_text", ""),
            "success_details": run.get("success_details", ""),
            "screenshots": run.get("screenshots", []),
            "preflight": self.preflight,
            "side_effects": side_effect_summary(self.mode),
            "next_action": next_action_for_run(self.mode, run["status"]),
        }
        if run["status"] != "passed":
            row["failure_kind"] = run.get("failure_kind", "challenge_validation_failed")
            row["reason"] = run.get("reason", "challenge did not pass")
        self.rows.append(row)
        self.record_evidence(row, record=record, stage="browser_challenge")
        return {
            "status": run["status"],
            "reason": row.get("reason", ""),
            "details": row,
            "evidence_path": str(self.output_json),
        }

    async def teardown(self):
        report = write_shortest_path_report(
            rows=self.rows,
            output_json=self.output_json,
            output_html=self.output_html,
            metadata={
                "workflow": self.name,
                "mode": getattr(self, "mode", "unknown"),
                "target_url": getattr(self, "target_url", TARGET_URL),
                "backend_url": getattr(self, "backend_url", BACKEND_URL),
                "preflight": getattr(self, "preflight", {}),
                "started_at": getattr(self, "run_started_at", ""),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        self.result.output_files.extend([str(self.output_json), str(self.output_html)])
        for row in self.rows:
            self.result.screenshots.extend(row.get("screenshots", []))
        self.log(f"Shortest Path report JSON: {report['json']}")
        self.log(f"Shortest Path report HTML: {report['html']}")


def fetch_places(backend_url: str, timeout_seconds: float) -> list[dict[str, Any]]:
    payload = fetch_text(f"{backend_url}/places", timeout_seconds)
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("backend /places response is not a list")
    return [dict(item) for item in data if item.get("type") == "demand"]


def live_preflight(
    *,
    target_url: str,
    backend_url: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    preflight = {
        "status": "failed",
        "mode": "live",
        "decision": "blocked",
        "target_url": target_url,
        "backend_url": backend_url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "checks": [],
        "artifacts": {},
        "next_action": "Fix the target dependency, then rerun live mode.",
    }
    page_check = check_http(target_url, timeout_seconds)
    preflight["checks"].append({"name": "target_page", **page_check})
    if page_check["status"] != "passed":
        preflight["reason"] = page_check["reason"]
        return preflight, [], {}

    try:
        demands = fetch_places(backend_url, timeout_seconds)
        answers = validate_backend_answers(
            backend_url,
            demands,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        preflight["checks"].append(
            {
                "name": "backend_places",
                "status": "failed",
                "url": f"{backend_url}/places",
                "reason": str(exc),
            }
        )
        preflight["reason"] = str(exc)
        preflight[
            "next_action"
        ] = f"Retry live mode when {backend_url}/places is reachable, or provide a working backend URL."
        return preflight, [], {}

    preflight.update(
        {
            "status": "passed",
            "decision": "run_live",
            "reason": "",
            "next_action": "Run the live browser workflow and verify the final score report.",
            "backend": {
                "mode": "live",
                "source": f"{backend_url}/places",
                "demand_count": len(demands),
                "validated_pairs": len(answers),
            },
        }
    )
    preflight["checks"].append(
        {
            "name": "backend_places",
            "status": "passed",
            "url": f"{backend_url}/places",
            "demand_count": len(demands),
            "validated_pairs": len(answers),
        }
    )
    return preflight, demands, answers


def fixture_preflight(target_url: str, backend_url: str) -> dict[str, Any]:
    return {
        "status": "passed",
        "mode": "fixture",
        "decision": "run_fixture",
        "target_url": target_url,
        "backend_url": backend_url,
        "reason": "",
        "checks": [
            {
                "name": "fixture_data",
                "status": "passed",
                "demand_count": len(FIXTURE_DEMANDS),
                "supply_count": len(SUPPLIES),
            },
            {
                "name": "backend_places",
                "status": "skipped",
                "reason": "fixture mode validates browser/form behavior only",
            },
        ],
        "backend": {"mode": "fixture", "source": "local deterministic fixture"},
        "artifacts": {},
        "next_action": "Use live mode when the challenge backend is reachable.",
    }


def check_http(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "rpa-harness/shortest-path"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return {"status": "passed", "url": url, "http_status": response.status}
    except Exception as exc:
        return {"status": "failed", "url": url, "reason": str(exc)}


def write_recon_artifact(
    preflight: dict[str, Any],
    recon_dir: Path,
    *,
    mode: str,
    timestamp: str,
) -> str:
    recon_dir.mkdir(parents=True, exist_ok=True)
    path = recon_dir / f"preflight_{mode}_{timestamp}.json"
    path.write_text(json.dumps(preflight, indent=2, default=str), encoding="utf-8")
    return str(path)


def artifact_path(value: Any, *, mode: str, timestamp: str) -> Path:
    return Path(str(value).format(mode=mode, timestamp=timestamp))


def side_effect_summary(mode: str) -> list[str]:
    if mode == "fixture":
        return [
            "external_read: load public challenge page",
            "local_only: inject deterministic fixture data into browser session",
            "none: no challenge backend write",
        ]
    return [
        "external_read: load public challenge page",
        "external_read: read challenge backend places and pair validation endpoints",
        "none: no non-idempotent external write",
    ]


def next_action_for_run(mode: str, status: str) -> str:
    if status == "passed" and mode == "live":
        return "Archive the report and screenshots as production evidence."
    if status == "passed":
        return "Use live mode when the challenge backend is reachable; fixture proof is not production success."
    return "Inspect the preflight and screenshot artifacts, then rerun after the blocker is fixed."


def validate_backend_answers(
    backend_url: str,
    demands: list[dict[str, Any]],
    *,
    timeout_seconds: float,
) -> dict[str, str]:
    answers = {}
    for item in build_round_plan(demands):
        demand_id = item["demand"]["_id"]
        supply_id = item["supply"]["_id"]
        answer = fetch_text(f"{backend_url}/place/{demand_id}/{supply_id}", timeout_seconds)
        if not answer:
            raise ValueError(f"backend rejected closest pair {demand_id} -> {supply_id}")
        answers[demand_id] = supply_id
    return answers


def fetch_text(url: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"User-Agent": "rpa-harness/shortest-path"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"cannot reach challenge backend {url}: {exc}") from exc


def build_round_plan(demands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for demand in demands:
        supply = closest_supply(demand)
        plan.append(
            {
                "demand": demand,
                "supply": supply,
                "distance_km": round(distance_km(demand, supply), 2),
            }
        )
    return plan


def closest_supply(demand: dict[str, Any]) -> dict[str, Any]:
    return min(SUPPLIES, key=lambda supply: distance_km(demand, supply))


def distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lng"]))
    lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lng"]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


async def capture_page_recon(
    target_url: str,
    evidence_dir: Path,
    *,
    headless: bool,
    browser_name: str,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot = evidence_dir / f"{stamp}_backend_blocked.png"
    body_path = evidence_dir / f"{stamp}_body.txt"
    html_path = evidence_dir / f"{stamp}_page.html"
    console: list[dict[str, str]] = []
    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = await browser_type.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:500]}))
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(screenshot), full_page=True)
        body_text = await page.locator("body").inner_text(timeout=10000)
        body_path.write_text(body_text, encoding="utf-8")
        html_path.write_text(await page.content(), encoding="utf-8")
        data_length = await page.evaluate("() => Array.isArray(window.data) ? window.data.length : null")
        await browser.close()
    return {
        "screenshot": str(screenshot),
        "body_text": str(body_path),
        "page_html": str(html_path),
        "console": console[-10:],
        "page_data_length": data_length,
    }


async def run_browser_challenge(
    *,
    target_url: str,
    demands: list[dict[str, Any]],
    valid_pairs: dict[str, str],
    evidence_dir: Path,
    headless: bool,
    browser_name: str,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[str] = []
    rounds: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = await browser_type.launch(headless=headless, slow_mo=0)
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(500)
        injected = await inject_points(page, demands, valid_pairs)
        if injected["marker_count"] != len(SUPPLIES) + len(demands):
            await browser.close()
            return {
                "status": "failed",
                "failure_kind": "marker_injection_failed",
                "reason": f"expected {len(SUPPLIES) + len(demands)} markers, got {injected['marker_count']}",
                "rounds": [],
            }

        initial = evidence_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_initial.png"
        await page.screenshot(path=str(initial), full_page=True)
        screenshots.append(str(initial))
        await page.locator(".btn-launchgame").click(timeout=10000)

        for index, item in enumerate(build_round_plan(demands), start=1):
            demand = item["demand"]
            supply = item["supply"]
            await select_marker(page, demand["_id"])
            await select_marker(page, supply["_id"])
            selected = await selected_payload(page, demand["_id"], supply["_id"])
            await fill_form(page, selected["demand"], selected["supply"])
            form = await form_snapshot(page)
            await page.locator(".submit-form").click(timeout=10000)
            await page.locator("#CTRDV").wait_for(state="visible", timeout=10000)
            contract = (await page.locator("#CTRNR").inner_text(timeout=10000)).strip()
            await page.locator("#contract_table input[type=text]").fill(contract)
            await page.locator(".btn-create").click(timeout=10000)
            rounds.append(
                {
                    "round": index,
                    "demand_id": demand["_id"],
                    "supply_id": supply["_id"],
                    "distance_km": item["distance_km"],
                    "contract": contract,
                    "form_readback": form,
                }
            )
            if index == 1:
                shot = evidence_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_round_1_created.png"
                await page.screenshot(path=str(shot), full_page=True)
                screenshots.append(str(shot))

        await page.locator(".success-score").wait_for(state="visible", timeout=10000)
        success_text = (await page.locator(".success-score").inner_text(timeout=10000)).strip()
        success_details = (await page.locator(".success-details").inner_text(timeout=10000)).strip()
        final = evidence_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_final.png"
        await page.screenshot(path=str(final), full_page=True)
        screenshots.append(str(final))
        await browser.close()

    passed = "100.00%" in success_text and "80 out of 80" in success_details
    return {
        "status": "passed" if passed else "failed",
        "failure_kind": "" if passed else "challenge_score_mismatch",
        "reason": "" if passed else f"{success_text} / {success_details}",
        "success_text": success_text,
        "success_details": success_details,
        "rounds": rounds,
        "screenshots": screenshots,
    }


async def inject_points(page, demands: list[dict[str, Any]], valid_pairs: dict[str, str]) -> dict[str, int]:
    return await page.evaluate(
        """({supplies, demands, validPairs}) => {
            window.__rpaShortestPath = {supplies, demands, validPairs};
            window.httpGet = function(url) {
                if (url.indexOf('/api/v1/places') !== -1) {
                    return JSON.stringify(window.__rpaShortestPath.demands);
                }
                const match = url.match(/\\/api\\/v1\\/place\\/([^/]+)\\/([^/]+)$/);
                if (match) {
                    return window.__rpaShortestPath.validPairs[match[1]] === match[2] ? 'true' : '';
                }
                return '';
            };
            if (window.markers) {
                Object.keys(window.markers).forEach((id) => {
                    if (id !== 'count' && window.markers[id]) {
                        try { window.mymap.removeLayer(window.markers[id]); } catch (err) {}
                    }
                });
            }
            window.markers = [];
            window.markers.count = 0;
            window.data = [];
            window.supplySelection = '';
            window.demandSelection = '';
            window.supply_flag = false;
            window.demand_flag = false;
            window.create();
            window.addMarkers(supplies);
            window.addMarkers(demands);
            return {data_length: window.data.length, marker_count: window.markers.count};
        }""",
        {"supplies": SUPPLIES, "demands": demands, "validPairs": valid_pairs},
    )


async def select_marker(page, marker_id: str) -> None:
    await page.evaluate(
        """(id) => {
            if (!window.markers[id]) throw new Error(`missing marker ${id}`);
            window.markers[id].openPopup();
        }""",
        marker_id,
    )
    await page.locator(f'.leaflet-popup button.select-button[id="{marker_id}"]').click(timeout=10000)


async def selected_payload(page, demand_id: str, supply_id: str) -> dict[str, Any]:
    return await page.evaluate(
        """({demandId, supplyId}) => {
            const demand = window.data.find((item) => item._id === demandId);
            const supply = window.data.find((item) => item._id === supplyId);
            return {demand, supply};
        }""",
        {"demandId": demand_id, "supplyId": supply_id},
    )


async def fill_form(page, demand: dict[str, Any], supply: dict[str, Any]) -> None:
    texts = page.locator("#gamecontainer input[type=text]")
    selects = page.locator("#gamecontainer select")
    await page.locator("#gamecontainer textarea").fill(str(demand["cargo"]))
    await texts.nth(0).fill(str(demand["shipDate"]))
    for value in ("Premit Required", "Urgent"):
        checkbox = page.locator(f'#gamecontainer input[type=checkbox][value="{value}"]')
        if await checkbox.is_checked():
            await checkbox.uncheck()
    await page.locator(f'#gamecontainer input[type=checkbox][value="{demand["shipPref"]}"]').check()
    await page.locator(f'#gamecontainer input[type=radio][value="{demand["cargoPref"]}"]').check()

    for index, value in enumerate(
        [demand["name"], demand["address1"], demand["address2"], demand["city"], demand["zip"]],
        start=1,
    ):
        await texts.nth(index).fill(str(value))
    await selects.nth(0).select_option(str(demand["state"]))

    for index, value in enumerate(
        [supply["name"], supply["address1"], supply["address2"], supply["city"], supply["zip"]],
        start=6,
    ):
        await texts.nth(index).fill(str(value))
    await selects.nth(1).select_option(str(supply["state"]))


async def form_snapshot(page) -> dict[str, Any]:
    return await page.evaluate(
        """() => ({
            cargo: document.querySelector('#gamecontainer textarea')?.value || '',
            text_values: [...document.querySelectorAll('#gamecontainer input[type=text]')].map((item) => item.value),
            select_values: [...document.querySelectorAll('#gamecontainer select')].map((item) => item.value),
            checked_values: [...document.querySelectorAll('#gamecontainer input:checked')].map((item) => item.value),
        })"""
    )


def write_shortest_path_report(
    *,
    rows: list[dict[str, Any]],
    output_json: Path,
    output_html: Path,
    metadata: dict[str, Any],
) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in rows if row.get("status") == "passed")
    report = {
        "metadata": metadata,
        "summary": {
            "total": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "status": "passed" if rows and passed == len(rows) else "failed",
            "mode": metadata.get("mode"),
            "dependency_status": dependency_status(rows, metadata),
            "next_action": first_value(rows, "next_action"),
        },
        "records": rows,
    }
    output_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    output_html.write_text(render_shortest_path_html(report), encoding="utf-8")
    return {"json": str(output_json), "html": str(output_html)}


def render_shortest_path_html(report: dict[str, Any]) -> str:
    rows = report.get("records", [])
    cards = []
    for row in rows:
        rounds = "".join(
            "<tr>"
            f"<td>{html.escape(str(item.get('round', '')))}</td>"
            f"<td>{html.escape(str(item.get('demand_id', '')))}</td>"
            f"<td>{html.escape(str(item.get('supply_id', '')))}</td>"
            f"<td>{html.escape(str(item.get('distance_km', '')))}</td>"
            f"<td>{html.escape(str(item.get('contract', '')))}</td>"
            "</tr>"
            for item in row.get("rounds", [])
        )
        screenshots = "".join(
            f'<li><code>{html.escape(str(path))}</code></li>' for path in row.get("screenshots", [])
        )
        preflight_artifact = (
            row.get("preflight", {}).get("artifacts", {}).get("preflight_json")
            or report.get("metadata", {}).get("preflight", {}).get("artifacts", {}).get("preflight_json")
            or ""
        )
        side_effects = "".join(
            f"<li>{html.escape(str(item))}</li>" for item in row.get("side_effects", [])
        )
        cards.append(
            f"<section><h2>{html.escape(str(row.get('record_id', 'record')))}</h2>"
            f"<p><strong>Status:</strong> {html.escape(str(row.get('status', '')))}</p>"
            f"<p><strong>Success:</strong> {html.escape(str(row.get('success_text', row.get('reason', ''))))}</p>"
            f"<p><strong>Details:</strong> {html.escape(str(row.get('success_details', '')))}</p>"
            f"<p><strong>Next action:</strong> {html.escape(str(row.get('next_action', '')))}</p>"
            f"<p><strong>Preflight:</strong> <code>{html.escape(str(preflight_artifact))}</code></p>"
            f"<h3>Side effects</h3><ul>{side_effects}</ul>"
            "<table><thead><tr><th>Round</th><th>Demand</th><th>Supply</th><th>Km</th><th>Contract</th></tr></thead>"
            f"<tbody>{rounds}</tbody></table><h3>Screenshots</h3><ul>{screenshots}</ul></section>"
        )
    summary = report.get("summary", {})
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>RPA Challenge Shortest Path</title>"
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px;background:#f6f7f9;color:#1f2937}"
        "main{max-width:1100px;margin:auto;background:white;padding:28px;border:1px solid #d1d5db}"
        "section{border-top:1px solid #e5e7eb;margin-top:24px;padding-top:16px}"
        "table{border-collapse:collapse;width:100%;margin-top:12px}td,th{border:1px solid #e5e7eb;padding:8px;text-align:left}"
        "th{background:#f3f4f6}code{font-size:12px}</style></head><body><main>"
        "<h1>RPA Challenge Shortest Path</h1>"
        f"<p><strong>Status:</strong> {html.escape(str(summary.get('status', 'unknown')))}</p>"
        f"<p><strong>Mode:</strong> {html.escape(str(summary.get('mode', 'unknown')))}</p>"
        f"<p><strong>Dependency status:</strong> {html.escape(str(summary.get('dependency_status', 'unknown')))}</p>"
        f"<p><strong>Next action:</strong> {html.escape(str(summary.get('next_action', '')))}</p>"
        f"<p><strong>Passed:</strong> {summary.get('passed', 0)} / {summary.get('total', 0)}</p>"
        f"{''.join(cards)}</main></body></html>"
    )


def first_value(rows: list[dict[str, Any]], key: str) -> str:
    for row in rows:
        if row.get(key):
            return str(row[key])
    return ""


def dependency_status(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    preflight = metadata.get("preflight") or {}
    if not preflight and rows:
        preflight = rows[0].get("preflight") or {}
    return str(preflight.get("status") or "unknown")
