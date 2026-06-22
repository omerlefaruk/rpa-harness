#!/usr/bin/env python3
"""
RPA Harness CLI entry point.

Usage:
    python main.py --discover ./tests --run --report html
    python main.py --agent "Login to example.com and verify dashboard" --headless
    python main.py --run-workflows --discover-wf projects/example_data_verification
    python main.py --browser-selector-swarm https://example.com/login
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from harness.config import HarnessConfig
from harness.orchestrator import AutomationHarness
from harness.reporting.run_artifacts import (
    live_tail,
    print_run_logs,
    print_run_manifest,
    print_runs_list,
    retry_run,
    run_report_path,
)


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args():
    parser = argparse.ArgumentParser(
        description="RPA Harness — AI-powered automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --discover ./tests --run --report html
  python main.py --run --tags browser --headless
  python main.py --agent "Login and verify dashboard" --headless
  python main.py --browser-selector-swarm https://example.com/login
        """,
    )
    parser.add_argument("--config", "-c", help="Path to YAML config file")
    parser.add_argument("--init-workspace", help="Initialize an agent-ready rpa-harness workspace")
    parser.add_argument("--discover", "-d", help="Test discovery directory")
    parser.add_argument("--discover-wf", "-dw", help="Workflow discovery directory")
    parser.add_argument("--run", "-r", action="store_true", help="Run tests")
    parser.add_argument("--run-workflows", "-rw", action="store_true", help="Run workflows")
    parser.add_argument("--agent", "-a", help="Agent task (natural language)")
    parser.add_argument("--tags", "-t", help="Comma-separated tag filter")
    parser.add_argument("--test-name", "-n", help="Specific test name")
    parser.add_argument("--workflow-name", "-wn", help="Specific workflow name")
    parser.add_argument("--report", default="html,json", help="Report formats (html,json)")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--browser-cdp", help="Attach to an existing Chromium CDP endpoint, for example http://127.0.0.1:9222")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=0)
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--no-agent", action="store_true")
    parser.add_argument("--vision-model", default="gpt-4o")
    parser.add_argument("--agent-model", default="gpt-4o")
    parser.add_argument("--agent-max-steps", type=int)
    parser.add_argument("--copilot", action="store_true", help="Ask live operator questions instead of ending at YAML pauses")
    parser.add_argument("--copilot-question-mode", choices=["console"], help="Question channel for --copilot")
    parser.add_argument("--copilot-build", help="Start a phase-by-phase copilot automation build from a task markdown file")
    parser.add_argument("--copilot-session", help="Show a copilot builder session JSON state")
    parser.add_argument("--copilot-answer", help="Answer a copilot session question")
    parser.add_argument("--copilot-question-id", help="Question id for --copilot-answer")
    parser.add_argument("--copilot-response", help="Answer text for --copilot-answer")
    parser.add_argument("--copilot-advance", help="Advance a copilot session to the next automatic phase")
    parser.add_argument("--copilot-auto", help="Start a task path or continue a session until a copilot question/review gate")
    parser.add_argument("--copilot-try-url", help="Start the fast copilot URL path for a browser automation target")
    parser.add_argument("--copilot-try-workflow", help="Workflow YAML to use with --copilot-try-url")
    parser.add_argument("--copilot-try-intent", help="Discovery intent to use with --copilot-try-url")
    parser.add_argument("--autopilot-build", help="Agent-facing build/run task markdown file")
    parser.add_argument("--autopilot-workflow", help="Workflow YAML for --autopilot-build")
    parser.add_argument("--autopilot-policy", default=".agents/config/autopilot.yaml", help="Policy YAML for --autopilot-build")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--browser-selector-swarm",
        help="Run browser selector swarm discovery for a URL",
    )
    parser.add_argument(
        "--browser-selector-swarm-output",
        default="runs/browser_recon",
        help="Output directory for browser selector swarm artifacts",
    )
    parser.add_argument(
        "--browser-selector-swarm-max-candidates",
        type=int,
        default=50,
        help="Maximum selector candidates to validate",
    )
    parser.add_argument(
        "--browser-selector-swarm-intent",
        help="Element/action intent to prioritize, for example 'Save'",
    )
    parser.add_argument(
        "--browser-selector-swarm-wait-until",
        choices=["commit", "domcontentloaded", "load", "networkidle"],
        default="domcontentloaded",
        help="Page readiness strategy for browser selector swarm discovery",
    )
    parser.add_argument(
        "--browser-selector-swarm-use-subagents",
        action="store_true",
        help="Enable tiered local Codex CLI subagent escalation",
    )
    parser.add_argument(
        "--browser-selector-swarm-subagent-policy",
        choices=["auto", "focused", "all"],
        default="auto",
        help="Subagent policy when local Codex CLI subagents are enabled",
    )
    parser.add_argument(
        "--browser-selector-swarm-safe-click",
        action="store_true",
        help="Allow safe click validation; requires an expected URL or text check",
    )
    parser.add_argument(
        "--browser-selector-swarm-expect-url-contains",
        help="Expected URL fragment after safe click validation",
    )
    parser.add_argument(
        "--browser-selector-swarm-expect-text",
        help="Expected visible text after safe click validation",
    )
    parser.add_argument(
        "--browser-selector-swarm-save-raw-html",
        action="store_true",
        help="Save a redacted DOM map artifact during browser selector swarm discovery",
    )
    parser.add_argument("--run-yaml", "-y", help="Run a YAML workflow file")
    parser.add_argument("--preflight-yaml", help="Run YAML workflow preflight only")
    parser.add_argument("--phase", help="Run only steps in this YAML phase")
    parser.add_argument("--pause-before", help="Pause before this YAML step id")
    parser.add_argument("--pause-after-phase", help="Pause after this YAML phase")
    parser.add_argument("--until-step", help="Stop after this YAML step id")
    parser.add_argument("--only-record", help="Run only YAML steps for this record_id")
    parser.add_argument("--validate-yaml", help="Validate a YAML workflow file")
    parser.add_argument("--validate-dsl", help="Validate a tiny .rpa DSL workflow file")
    parser.add_argument("--compile-dsl", help="Compile a tiny .rpa DSL workflow file to YAML")
    parser.add_argument("--audit-workflow", help="Audit a YAML workflow against the RPA rulebook")
    parser.add_argument("--migrate-workflow", help="Migrate a legacy flat workflow to the default schema")
    parser.add_argument("--workflow-output", help="Output path for --migrate-workflow or --compile-dsl")
    parser.add_argument("--migration-report", help="Markdown report path for --migrate-workflow")
    parser.add_argument("--workflow-graph", help="Generate workflow graph JSON from a workflow YAML file")
    parser.add_argument("--workflow-graph-output", help="Output path for --workflow-graph")
    parser.add_argument("--observability-index", action="store_true", help="Index run artifacts into SQLite")
    parser.add_argument("--observability-rebuild", action="store_true", help="Rebuild the observability SQLite index")
    parser.add_argument("--observability-stats", action="store_true", help="Print observability summary")
    parser.add_argument("--observability-db-path", action="store_true", help="Print observability database path")
    parser.add_argument("--observability-db", help="Override observability database path")
    parser.add_argument("--runs-dir", default="runs", help="Run artifact directory")
    parser.add_argument("--live-tail", help="Tail timeline events for a run id or run directory")
    parser.add_argument("--new-workflow", help="Create a workflow YAML file from a template")
    parser.add_argument(
        "--workflow-template",
        default="browser_login_export",
        help="Template for --new-workflow",
    )
    parser.add_argument("--workflow-id", help="Workflow id for --new-workflow")
    parser.add_argument("--workflow-owner", default="ops", help="Workflow owner for templates")
    parser.add_argument("--target-system", default="target-system", help="Target system for templates")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt interactively for --new-workflow fields",
    )
    parser.add_argument("--render-failure-report", help="Render failure_report.json to HTML")
    parser.add_argument("--failure-report-output", help="Output path for rendered failure HTML")
    parser.add_argument("--bundle-run", help="Create a zip evidence bundle from a run directory")
    parser.add_argument("--bundle-output", help="Output path for --bundle-run")
    parser.add_argument("--runs-list", action="store_true", help="List recent YAML run folders")
    parser.add_argument("--runs-show", help="Show run_manifest.json for a run id or run directory")
    parser.add_argument("--logs-show", help="Show logs.jsonl for a run id or run directory")
    parser.add_argument("--logs-tail", type=int, help="Show only the last N log lines")
    parser.add_argument("--log-step", help="Filter --logs-show by step id")
    parser.add_argument("--report-open", help="Print report.html path for a run id or run directory")
    parser.add_argument("--build-start", help="Create a minimal builder session from a task markdown file")
    parser.add_argument("--builder-session-id", help="Optional session id for --build-start")
    parser.add_argument("--capture-desktop", help="Create a blocked desktop capture session for an app/window")
    parser.add_argument("--capture-session-dir", help="Builder session directory for --capture-desktop")
    parser.add_argument("--desktop-ai-assist", help="Run governed desktop AI assist against an evidence session")
    parser.add_argument(
        "--desktop-ai-mode",
        "--mode",
        dest="desktop_ai_mode",
        choices=["inspect", "draft", "repair", "execute-approved"],
        default="inspect",
        help="Desktop AI assist mode",
    )
    parser.add_argument(
        "--desktop-ai-proposal",
        help="Approved proposal JSON for --desktop-ai-mode execute-approved",
    )
    parser.add_argument("--discovery-validate-fixtures", action="store_true", help="Validate local discovery fixtures")
    parser.add_argument("--repair-selector", help="Run directory containing selector repair evidence")
    parser.add_argument("--repair-approve", action="store_true", help="Allow validated selector patch application")
    parser.add_argument("--retry-run", help="Retry a manifest-backed YAML run id or directory")
    parser.add_argument("--failed-records", action="store_true", help="With --retry-run, retry safe failed records")
    parser.add_argument("--resume-ledger-status", help="Show resume ledger summary JSON")
    parser.add_argument(
        "--telegram-message",
        help="Send one Telegram bot message using RPA_TELEGRAM_BOT_TOKEN and RPA_TELEGRAM_CHAT_ID",
    )
    parser.add_argument(
        "--telegram-question",
        help="Send a question message to the Telegram bot channel",
    )
    parser.add_argument(
        "--telegram-rant",
        action="append",
        help="Send one frustration item. Repeat for multiple items.",
    )
    parser.add_argument(
        "--telegram-source",
        default="rpa-harness",
        help="Source label for Telegram question/rant messages",
    )
    parser.add_argument(
        "--telegram-topic",
        help="Telegram group topic name, for example reports, questions, or rants",
    )
    parser.add_argument(
        "--telegram-discover-chat",
        action="store_true",
        help="List recent Telegram chats visible to the bot using getUpdates",
    )
    return parser.parse_args()


def build_config(args) -> HarnessConfig:
    config = HarnessConfig.from_yaml(args.config) if args.config else HarnessConfig.from_env()

    if args.browser:
        config.browser = args.browser
    if args.browser_cdp:
        config.browser_cdp_endpoint = args.browser_cdp
    if args.headless:
        config.headless = True
    if args.slow_mo:
        config.slow_mo = args.slow_mo
    if args.no_vision:
        config.enable_vision = False
    if args.no_agent:
        config.enable_agent = False
    if args.vision_model:
        config.vision_model = args.vision_model
    if args.agent_model:
        config.agent_model = args.agent_model
    if args.agent_max_steps:
        config.agent_max_steps = args.agent_max_steps
    if args.copilot:
        config.copilot_enabled = True
    if args.copilot_question_mode:
        config.copilot_question_mode = args.copilot_question_mode
    if args.max_workers:
        config.max_workers = args.max_workers
    if args.log_level:
        config.log_level = args.log_level

    return config


def load_local_env(paths=(".env", ".env.local")):
    original_keys = set(os.environ)
    loaded = {}
    for env_path in paths:
        path = Path(env_path)
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in original_keys:
                continue
            loaded[key] = _strip_env_quotes(value.strip())
    os.environ.update(loaded)


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def has_run_failures(summary: dict) -> bool:
    tests = summary.get("tests") or {}
    workflows = summary.get("workflows") or {}
    return (
        tests.get("failed", 0) > 0
        or workflows.get("failed", 0) > 0
        or workflows.get("failed_records", 0) > 0
    )


async def main():
    configure_console_encoding()
    args = parse_args()
    if args.init_workspace:
        from harness.product_init import init_workspace

        target = Path(args.init_workspace)
        init_workspace(target)
        print(f"Initialized rpa-harness workspace at {target.resolve()}")
        return

    load_local_env()

    if (
        args.telegram_message
        or args.telegram_question
        or args.telegram_rant
        or args.telegram_discover_chat
    ):
        import json

        from harness.notifications import TelegramBotChannel

        channel = TelegramBotChannel()
        if args.telegram_message:
            await channel.send_message(
                args.telegram_message,
                topic=args.telegram_topic,
                strict=True,
            )
            print("Telegram message sent")
            return
        if args.telegram_question:
            await channel.ask_question(
                args.telegram_question,
                context=f"source={args.telegram_source}",
                topic=args.telegram_topic or "questions",
                strict=True,
            )
            print("Telegram question sent")
            return
        if args.telegram_rant:
            await channel.send_frustration_report(
                args.telegram_source,
                args.telegram_rant,
                topic=args.telegram_topic or "rants",
                strict=True,
            )
            print("Telegram frustration report sent")
            return
        result = await channel.discover_chat_id(strict=True)
        print(json.dumps(result, indent=2, default=str))
        return

    if args.browser_selector_swarm:
        import json

        if args.browser_selector_swarm_safe_click and not (
            args.browser_selector_swarm_expect_url_contains
            or args.browser_selector_swarm_expect_text
        ):
            print(
                "--browser-selector-swarm-safe-click requires "
                "--browser-selector-swarm-expect-url-contains or "
                "--browser-selector-swarm-expect-text",
                file=sys.stderr,
            )
            sys.exit(2)

        config = build_config(args)
        from harness.selectors.browser_swarm import run_browser_selector_swarm

        report = await run_browser_selector_swarm(
            args.browser_selector_swarm,
            output_dir=args.browser_selector_swarm_output,
            browser_name=config.browser,
            headless=config.headless,
            wait_until=args.browser_selector_swarm_wait_until,
            max_candidates=args.browser_selector_swarm_max_candidates,
            intent=args.browser_selector_swarm_intent,
            use_subagents=args.browser_selector_swarm_use_subagents,
            subagent_policy=args.browser_selector_swarm_subagent_policy,
            safe_click=args.browser_selector_swarm_safe_click,
            expect_url_contains=args.browser_selector_swarm_expect_url_contains,
            expect_text=args.browser_selector_swarm_expect_text,
            save_raw_html=args.browser_selector_swarm_save_raw_html,
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "url": report["url"],
                    "interactive_elements": report["summary"]["interactive_elements"],
                    "intent": report["summary"]["intent"],
                    "candidates": report["summary"]["candidates"],
                    "validated": report["summary"]["validated"],
                    "subagent_policy": report["summary"]["subagent_policy"],
                    "subagent_escalation_reasons": report["summary"]["subagent_escalation_reasons"],
                    "winner": report["validation"]["winner"],
                    "report": report["artifacts"]["report"],
                    "html_report": report["artifacts"]["html_report"],
                    "screenshot": report["artifacts"]["screenshot"],
                },
                indent=2,
                default=str,
            )
        )
        if not report["validation"]["winner"]:
            sys.exit(1)
        return

    if args.new_workflow:
        from harness.rpa.templates import prompt_for_workflow, write_workflow_template

        if args.interactive:
            path = prompt_for_workflow(args.new_workflow)
        else:
            workflow_id = args.workflow_id or Path(args.new_workflow).stem
            path = write_workflow_template(
                args.new_workflow,
                template=args.workflow_template,
                workflow_id=workflow_id,
                owner=args.workflow_owner,
                target_system=args.target_system,
            )
        print(f"Workflow written: {path}")
        return

    if args.render_failure_report:
        from harness.reporting.failure_html import render_failure_report_html

        output = render_failure_report_html(
            args.render_failure_report,
            output_path=args.failure_report_output,
        )
        print(f"Failure HTML written: {output}")
        return

    if args.bundle_run:
        from harness.reporting.evidence_bundle import bundle_run

        output = bundle_run(args.bundle_run, output_path=args.bundle_output)
        print(f"Evidence bundle written: {output}")
        return

    if args.runs_list:
        print_runs_list()
        return

    if args.runs_show:
        print_run_manifest(args.runs_show)
        return

    if args.logs_show:
        print_run_logs(args.logs_show, tail=args.logs_tail, step=args.log_step)
        return

    if args.report_open:
        print(run_report_path(args.report_open))
        return

    if args.build_start:
        print(f"Builder session: {_start_builder_session(args.build_start, args.builder_session_id)}")
        return

    if args.copilot_build:
        import json

        from harness.copilot_session import read_copilot_session, start_copilot_session

        session_dir = start_copilot_session(
            args.copilot_build,
            session_id=args.builder_session_id,
        )
        print(json.dumps(read_copilot_session(session_dir.name), indent=2, default=str))
        return

    if args.copilot_session:
        import json

        from harness.copilot_session import read_copilot_session

        print(json.dumps(read_copilot_session(args.copilot_session), indent=2, default=str))
        return

    if args.copilot_answer:
        import json

        from harness.copilot_session import answer_copilot_question

        if not args.copilot_question_id or args.copilot_response is None:
            print("--copilot-answer requires --copilot-question-id and --copilot-response", file=sys.stderr)
            sys.exit(2)
        result = answer_copilot_question(
            args.copilot_answer,
            args.copilot_question_id,
            args.copilot_response,
        )
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") in {"blocked", "failed"}:
            sys.exit(1)
        return

    if args.copilot_advance:
        import contextlib
        import json

        from harness.copilot_session import advance_copilot_session

        with contextlib.redirect_stdout(sys.stderr):
            result = await advance_copilot_session(args.copilot_advance, config=build_config(args))
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") in {"blocked", "failed"}:
            sys.exit(1)
        return

    if args.copilot_auto:
        import contextlib
        import json

        from harness.copilot_session import run_copilot_auto

        with contextlib.redirect_stdout(sys.stderr):
            result = await run_copilot_auto(
                args.copilot_auto,
                session_id=args.builder_session_id,
                config=build_config(args),
            )
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") in {"blocked", "failed"}:
            sys.exit(1)
        return

    if args.copilot_try_url:
        import contextlib
        import json

        from harness.copilot_session import run_copilot_try_url

        with contextlib.redirect_stdout(sys.stderr):
            result = await run_copilot_try_url(
                args.copilot_try_url,
                workflow_path=args.copilot_try_workflow,
                intent=args.copilot_try_intent,
                session_id=args.builder_session_id,
                config=build_config(args),
            )
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") in {"blocked", "failed"}:
            sys.exit(1)
        return

    if args.capture_desktop:
        print(f"Capture session: {_capture_desktop(args.capture_desktop, args.capture_session_dir)}")
        return

    if args.desktop_ai_assist:
        import json

        from harness.desktop.ai_controller import DesktopAIController

        result = DesktopAIController(args.desktop_ai_assist).run(
            mode=args.desktop_ai_mode,
            proposal_path=args.desktop_ai_proposal,
        )
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") == "blocked":
            sys.exit(1)
        return

    if args.discovery_validate_fixtures:
        import json

        from harness.builder import validate_discovery_fixtures

        print(json.dumps(validate_discovery_fixtures(), indent=2, default=str))
        return

    if args.repair_selector:
        import json

        from harness.selectors.repair import production_selector_repair

        result = production_selector_repair(args.repair_selector, approve=args.repair_approve)
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") not in {"applied", "ready"}:
            sys.exit(1)
        return

    if args.autopilot_build:
        import contextlib
        import json

        from harness.autopilot import run_autopilot_build

        config = build_config(args)
        with contextlib.redirect_stdout(sys.stderr):
            result = await run_autopilot_build(
                args.autopilot_build,
                workflow_path=args.autopilot_workflow,
                config=config,
                policy_path=args.autopilot_policy,
            )
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") != "passed":
            sys.exit(1)
        return

    if args.retry_run:
        import json

        result = await retry_run(args.retry_run, failed_records=args.failed_records, config=build_config(args))
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") != "passed":
            sys.exit(1)
        return

    if args.resume_ledger_status:
        import json

        from harness.rpa.ledger import ResumeLedger

        print(json.dumps(ResumeLedger(args.resume_ledger_status).summary(), indent=2))
        return

    if args.audit_workflow:
        import json

        from harness.core import audit_workflow_rulebook
        from harness.rpa.yaml_runner import load_workflow_yaml
        from harness.verification import validate_workflow_report

        wf = load_workflow_yaml(args.audit_workflow)
        validation = validate_workflow_report(wf)
        validation_errors = validation["errors"]
        audit = audit_workflow_rulebook(wf).to_dict()
        result = {
            "workflow_id": wf.get("id", "unknown"),
            "workflow_name": wf.get("name", wf.get("id", "unknown")),
            "validation_status": "invalid" if validation_errors else "valid",
            "validation_errors": validation_errors,
            "validation": validation,
            "rulebook_audit": audit,
        }
        print(json.dumps(result, indent=2, default=str))
        if validation_errors:
            sys.exit(1)
        return

    if args.migrate_workflow:
        import json

        from harness.rpa.schema import migrate_legacy_workflow

        output = args.workflow_output
        if not output:
            source_path = Path(args.migrate_workflow)
            output = str(source_path.with_name(f"{source_path.stem}.schema.yaml"))
        result = migrate_legacy_workflow(
            args.migrate_workflow,
            output,
            report_path=args.migration_report,
        )
        print(json.dumps({"status": result["status"], "output": output, "report": args.migration_report}, indent=2))
        return

    if args.workflow_graph:
        import json
        import yaml

        from harness.rpa.schema import generate_workflow_graph

        workflow = yaml.safe_load(Path(args.workflow_graph).read_text(encoding="utf-8")) or {}
        graph = generate_workflow_graph(workflow)
        if args.workflow_graph_output:
            Path(args.workflow_graph_output).write_text(
                json.dumps(graph, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"Workflow graph written: {args.workflow_graph_output}")
        else:
            print(json.dumps(graph, indent=2, default=str))
        return

    if (
        args.observability_index
        or args.observability_rebuild
        or args.observability_stats
        or args.observability_db_path
    ):
        import json

        from harness.observability import ObservabilityDB, index_runs, rebuild_runs

        db_path = Path(args.observability_db) if args.observability_db else Path(args.runs_dir) / "observability.db"
        if args.observability_db_path:
            print(db_path.resolve())
            return
        if args.observability_rebuild:
            print(json.dumps(rebuild_runs(args.runs_dir, db_path), indent=2, default=str))
            return
        if args.observability_index:
            print(json.dumps(index_runs(args.runs_dir, db_path), indent=2, default=str))
            return
        db = ObservabilityDB(db_path)
        try:
            print(json.dumps({
                "runs": db.get_recent_runs(limit=10),
                "failure_kinds": db.get_failure_kinds_summary(),
                "record_failures": db.get_record_failures(),
            }, indent=2, default=str))
        finally:
            db.close()
        return

    if args.live_tail:
        live_tail(args.live_tail, runs_dir=args.runs_dir)
        return

    if args.validate_dsl or args.compile_dsl:
        import yaml

        from harness.dsl import compile_dsl_to_workflow, parse_dsl
        from harness.rpa.schema import validate_workflow_schema

        source = Path(args.validate_dsl or args.compile_dsl)
        workflow = compile_dsl_to_workflow(parse_dsl(source.read_text(encoding="utf-8")))
        validation = validate_workflow_schema(workflow)
        errors = validation["errors"]
        if errors:
            print(f"INVALID DSL: {'; '.join(errors)}")
            sys.exit(1)
        if args.compile_dsl:
            if not args.workflow_output:
                print("--compile-dsl requires --workflow-output")
                sys.exit(2)
            output = Path(args.workflow_output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
            print(f"DSL workflow written: {output}")
        else:
            print(
                f"VALID DSL: {workflow.get('id', 'unknown')} "
                f"({validation['total_steps']} steps) "
                f"{validation['steps_with_success_checks']} checked"
            )
        return

    if args.validate_yaml:
        from harness.rpa.yaml_runner import load_workflow_yaml
        from harness.verification import validate_workflow_report

        wf = load_workflow_yaml(args.validate_yaml)
        validation = validate_workflow_report(wf)
        errors = validation["errors"]
        if errors:
            print(f"INVALID: {'; '.join(errors)}")
            sys.exit(1)
        else:
            print(
                f"VALID: {wf.get('id', 'unknown')} "
                f"({validation['total_steps']} steps) "
                f"{validation['steps_with_success_checks']} checked"
            )
        return

    if args.preflight_yaml:
        import json

        config = build_config(args)
        from harness.rpa.yaml_runner import YamlWorkflowRunner

        result = await YamlWorkflowRunner(config).preflight(args.preflight_yaml)
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") != "passed":
            sys.exit(1)
        return

    if args.run_yaml:
        config = build_config(args)
        from harness.rpa.yaml_runner import YamlWorkflowRunner
        runner = YamlWorkflowRunner(config)
        result = await runner.run(
            args.run_yaml,
            phase=args.phase,
            pause_before=args.pause_before,
            pause_after_phase=args.pause_after_phase,
            until_step=args.until_step,
            only_record=args.only_record,
        )
        print(f"\nStatus: {result['status']}")
        if result.get("run_dir"):
            print(f"Run folder: {result['run_dir']}")
            print(f"Report: {Path(result['run_dir']) / 'report.html'}")
        for step in result.get("steps", []):
            status = "PASS" if step.get("status") == "passed" else "FAIL"
            checks = len(step.get("checks", []))
            print(
                f"  {status} {step.get('step_id')} "
                f"({step.get('duration_ms', 0):.0f}ms, {checks} check(s))"
            )
        if result.get("status") != "passed":
            print(f"Reason: {result.get('reason', 'Workflow failed')}")
            if result.get("step"):
                print(f"Failed step: {result['step']}")
            if result.get("failure_report"):
                print(f"Failure report: {result['failure_report']}")
            if result.get("missing_secrets"):
                missing = ", ".join(
                    f"{item['name']} ({item['env']})" for item in result["missing_secrets"]
                )
                print(f"Missing secrets: {missing}")
            if result.get("unsupported_actions"):
                print(f"Unsupported actions: {', '.join(result['unsupported_actions'])}")
            sys.exit(1)
        return

    config = build_config(args)
    harness = AutomationHarness(config)

    # Discover
    if args.discover:
        harness.discover_tests(args.discover)
    if args.discover_wf:
        harness.discover_workflows(args.discover_wf)

    # Agent mode
    if args.agent:
        print(f"\n{'='*60}")
        print(f"Agent Task: {args.agent}")
        print(f"{'='*60}\n")

        from harness.drivers.playwright import PlaywrightDriver

        driver = None
        try:
            driver = await PlaywrightDriver.launch(config=config)
            result = await harness.run_agent(
                task=args.agent,
                playwright_driver=driver,
            )
            await _notify_agent_result(result)
            print(f"\n{'='*60}")
            print(f"Status: {result['status']}")
            print(f"Steps: {result['successful_steps']}/{result['total_steps']} passed")
            print(f"Duration: {result['duration_seconds']}s")
            print(f"{'='*60}")
        finally:
            if driver:
                await driver.close()

    # Run tests
    if args.run and harness.test_classes:
        tags = args.tags.split(",") if args.tags else None
        test_names = [args.test_name] if args.test_name else None
        await harness.run(tags=tags, test_names=test_names)

    # Run workflows
    if args.run_workflows and harness.workflow_classes:
        tags = args.tags.split(",") if args.tags else None
        wf_names = [args.workflow_name] if args.workflow_name else None
        await harness.run_workflows(tags=tags, workflow_names=wf_names)

    # Report
    if (args.run or args.run_workflows) and args.report:
        formats = [f.strip() for f in args.report.split(",")]
        reports = harness.report(formats=formats)
        print("\nReports:")
        for fmt, path in reports.items():
            print(f"  [{fmt.upper()}] {path}")
        await _notify_run_report(config, harness.summary(), reports)

    # Summary
    if args.run or args.run_workflows:
        summary = harness.summary()
        print(f"\n{'='*50}")

        if summary.get("tests") and summary["tests"]["total"] > 0:
            t = summary["tests"]
            print(f"TESTS: {t['passed']}/{t['total']} passed ({t['pass_rate']}%)")

        if summary.get("workflows"):
            w = summary["workflows"]
            print(
                f"WORKFLOWS: {w['processed_records']} records processed, "
                f"{w['failed_records']} mismatches, "
                f"{w.get('failed', 0)} failed workflow(s)"
            )

        if has_run_failures(summary):
            sys.exit(1)

    # Show discovery
    if not any(
        [
            args.agent,
            args.run,
            args.run_workflows,
            args.preflight_yaml,
            args.runs_list,
            args.runs_show,
            args.live_tail,
            args.autopilot_build,
            args.browser_selector_swarm,
        ]
    ):
        print(
            f"Discovered {len(harness.test_classes)} test(s), "
            f"{len(harness.workflow_classes)} workflow(s). "
            "Use --run, --run-workflows, --agent, "
            "or --browser-selector-swarm."
        )


def _telegram_channel_or_skip():
    from harness.notifications import TelegramBotChannel, TelegramNotificationConfig

    telegram_config = TelegramNotificationConfig.from_env()
    if not telegram_config.enabled:
        return None, telegram_config
    if not telegram_config.configured:
        print(
            "Telegram notification skipped: set RPA_TELEGRAM_BOT_TOKEN and "
            "RPA_TELEGRAM_CHAT_ID.",
            file=sys.stderr,
        )
        return None, telegram_config
    return TelegramBotChannel(telegram_config), telegram_config


def _start_builder_session(task_path: str, session_id: str | None = None) -> Path:
    from harness.builder import create_builder_session

    try:
        return create_builder_session(task_path, session_id=session_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


def _capture_desktop(app: str, session_dir: str | None = None) -> Path:
    from harness.builder import capture_desktop_session

    target_dir = Path(session_dir) if session_dir else Path("builder_sessions") / "desktop_capture"
    return capture_desktop_session(app=app, session_dir=target_dir)


async def _notify_run_report(config: HarnessConfig, summary: dict, reports: dict[str, str]):
    channel, telegram_config = _telegram_channel_or_skip()
    if channel is None:
        return
    try:
        result = await channel.send_run_report(
            suite_name=config.name,
            summary=summary,
            report_paths=reports,
        )
        if result is None:
            print("Telegram notification failed.", file=sys.stderr)
    except Exception as exc:
        if telegram_config.strict:
            raise
        print(f"Telegram notification failed: {exc}", file=sys.stderr)


async def _notify_agent_result(result: dict):
    channel, telegram_config = _telegram_channel_or_skip()
    if channel is None:
        return
    try:
        telegram_result = await channel.send_agent_report(result)
        if telegram_result is None:
            print("Telegram notification failed.", file=sys.stderr)
    except Exception as exc:
        if telegram_config.strict:
            raise
        print(f"Telegram notification failed: {exc}", file=sys.stderr)


def run() -> None:
    configure_console_encoding()
    asyncio.run(main())


if __name__ == "__main__":
    run()
