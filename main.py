#!/usr/bin/env python3
"""
RPA Harness CLI entry point.

Usage:
    python main.py --discover ./tests --run --report html
    python main.py --agent "Login to example.com and verify dashboard" --headless
    python main.py --serve --port 8080
    python main.py --rpa-memory-serve
    python main.py --autoresearch
    python main.py --autoresearch-supervisor-once
    python main.py --run-workflows --discover-wf ./tests/rpa
    python main.py --browser-selector-swarm https://example.com/login
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from harness.config import HarnessConfig
from harness.orchestrator import AutomationHarness


def parse_args():
    parser = argparse.ArgumentParser(
        description="RPA Harness — AI-powered automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --discover ./tests --run --report html
  python main.py --run --tags browser --headless
  python main.py --agent "Login and verify dashboard" --headless
  python main.py --serve --port 8080
  python main.py --rpa-memory-serve --rpa-memory-port 37777
  python main.py --autoresearch
  python main.py --autoresearch-supervisor-once
  python main.py --browser-selector-swarm https://example.com/login
        """,
    )
    parser.add_argument("--config", "-c", help="Path to YAML config file")
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
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=0)
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--no-agent", action="store_true")
    parser.add_argument("--vision-model", default="gpt-4o")
    parser.add_argument("--agent-model", default="gpt-4o")
    parser.add_argument("--agent-max-steps", type=int)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--serve", action="store_true", help="Start web dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port")
    parser.add_argument("--rpa-memory-serve", action="store_true", help="Start RPA Memory service")
    parser.add_argument("--rpa-memory-port", type=int, default=37777)
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
    parser.add_argument(
        "--autoresearch",
        action="store_true",
        help="Start autoresearch supervisor daemon",
    )
    parser.add_argument(
        "--autoresearch-supervisor",
        action="store_true",
        help="Start autoresearch supervisor daemon",
    )
    parser.add_argument(
        "--autoresearch-supervisor-once",
        action="store_true",
        help="Run one autoresearch supervisor cycle",
    )
    parser.add_argument(
        "--autoresearch-supervisor-plan",
        action="store_true",
        help="Write the next autoresearch supervisor plan",
    )
    parser.add_argument("--autoresearch-supervisor-config", help="Path to supervisor config JSON")
    parser.add_argument("--autoresearch-config", help="Path to supervisor config JSON")
    parser.add_argument("--run-yaml", "-y", help="Run a YAML workflow file")
    parser.add_argument("--validate-yaml", help="Validate a YAML workflow file")
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
        help="Telegram group topic name, for example reports, questions, rants, or memories",
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


async def main():
    args = parse_args()
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
            max_candidates=args.browser_selector_swarm_max_candidates,
            intent=args.browser_selector_swarm_intent,
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

    # Serve modes
    if args.serve:
        from harness.reporting.dashboard import run_dashboard
        run_dashboard(port=args.port)
        return

    if args.validate_yaml:
        import yaml

        from harness.verification import validate_workflow
        with open(args.validate_yaml) as f:
            wf = yaml.safe_load(f)
        errors = validate_workflow(wf)
        if errors:
            print(f"INVALID: {'; '.join(errors)}")
            sys.exit(1)
        else:
            print(f"VALID: {wf.get('id', 'unknown')} ({len(wf.get('steps', []))} steps)")
        return

    if args.run_yaml:
        config = build_config(args)
        from harness.rpa.yaml_runner import YamlWorkflowRunner
        runner = YamlWorkflowRunner(config)
        result = await runner.run(args.run_yaml)
        print(f"\nStatus: {result['status']}")
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

    if args.rpa_memory_serve:
        from harness.memory.server import serve_memory_server
        config = build_config(args)
        await serve_memory_server(db_path=config.memory.db_path, port=args.rpa_memory_port)
        return

    if (
        args.autoresearch
        or args.autoresearch_supervisor
        or args.autoresearch_supervisor_once
        or args.autoresearch_supervisor_plan
    ):
        from tools.autoresearch_supervisor import (
            build_supervisor_prompt,
            discover_improvements,
            load_config_for_supervisor,
            load_supervisor_config,
            run_daemon,
            run_supervisor_cycle,
        )

        supervisor_config = load_supervisor_config(
            args.autoresearch_config or args.autoresearch_supervisor_config,
            Path(".").resolve(),
        )
        if args.autoresearch_supervisor_plan:
            autoresearch_config = load_config_for_supervisor(supervisor_config)
            candidates = discover_improvements(supervisor_config, autoresearch_config)
            supervisor_config.session_dir.mkdir(parents=True, exist_ok=True)
            supervisor_config.plan_path.write_text(
                build_supervisor_prompt(supervisor_config, autoresearch_config, candidates),
                encoding="utf-8",
            )
            print(supervisor_config.plan_path)
            return
        if args.autoresearch_supervisor_once:
            import json

            result = run_supervisor_cycle(supervisor_config)
            print(json.dumps(result, indent=2))
            if result.get("status") not in {"planned", "committed", "merged", "pushed"}:
                sys.exit(1)
            return
        run_daemon(supervisor_config)
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
                f"{w['failed_records']} mismatches"
            )

        has_failures = (
            (summary.get("tests") and summary["tests"]["failed"] > 0)
            or (summary.get("workflows") and summary["workflows"]["failed_records"] > 0)
        )
        if has_failures:
            sys.exit(1)

    # Show discovery
    if not any(
        [
            args.agent,
            args.run,
            args.run_workflows,
            args.serve,
            args.rpa_memory_serve,
            args.autoresearch_supervisor,
            args.autoresearch_supervisor_once,
            args.autoresearch_supervisor_plan,
            args.browser_selector_swarm,
        ]
    ):
        print(
            f"Discovered {len(harness.test_classes)} test(s), "
            f"{len(harness.workflow_classes)} workflow(s). "
            "Use --run, --run-workflows, --agent, --serve, --rpa-memory-serve, "
            "--browser-selector-swarm, or --autoresearch-supervisor."
        )


async def _notify_run_report(config: HarnessConfig, summary: dict, reports: dict[str, str]):
    from harness.notifications import TelegramBotChannel, TelegramNotificationConfig

    telegram_config = TelegramNotificationConfig.from_env()
    if not telegram_config.enabled:
        return
    if not telegram_config.configured:
        print(
            "Telegram notification skipped: set RPA_TELEGRAM_BOT_TOKEN and "
            "RPA_TELEGRAM_CHAT_ID.",
            file=sys.stderr,
        )
        return
    channel = TelegramBotChannel(telegram_config)
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
    from harness.notifications import TelegramBotChannel, TelegramNotificationConfig

    telegram_config = TelegramNotificationConfig.from_env()
    if not telegram_config.enabled:
        return
    if not telegram_config.configured:
        print(
            "Telegram notification skipped: set RPA_TELEGRAM_BOT_TOKEN and "
            "RPA_TELEGRAM_CHAT_ID.",
            file=sys.stderr,
        )
        return
    channel = TelegramBotChannel(telegram_config)
    try:
        telegram_result = await channel.send_agent_report(result)
        if telegram_result is None:
            print("Telegram notification failed.", file=sys.stderr)
    except Exception as exc:
        if telegram_config.strict:
            raise
        print(f"Telegram notification failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
