#!/usr/bin/env python3
"""
RPA Harness CLI entry point.

Usage:
    python main.py --discover ./tests --run --report html
    python main.py --agent "Login to example.com and verify dashboard" --headless
    python main.py --serve --port 8080
    python main.py --memory-serve
    python main.py --run-workflows --discover-wf ./tests/rpa
"""

import argparse
import asyncio
import sys
from pathlib import Path

from harness.orchestrator import AutomationHarness
from harness.config import HarnessConfig


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
  python main.py --memory-serve --port 38777
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
    parser.add_argument("--memory-serve", action="store_true", help="Start memory worker")
    parser.add_argument("--memory-port", type=int, default=38777)
    parser.add_argument("--run-yaml", "-y", help="Run a YAML workflow file")
    parser.add_argument("--validate-yaml", help="Validate a YAML workflow file")
    return parser.parse_args()


def build_config(args) -> HarnessConfig:
    if args.config:
        config = HarnessConfig.from_yaml(args.config)
    else:
        config = HarnessConfig.from_env()

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


async def main():
    args = parse_args()

    # Serve modes
    if args.serve:
        from harness.reporting.dashboard import run_dashboard
        run_dashboard(port=args.port)
        return

    if args.validate_yaml:
        from harness.verification import validate_workflow
        import yaml
        wf = yaml.safe_load(open(args.validate_yaml).read())
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
        if result.get("failures"):
            for f in result["failures"]:
                print(f"  - {f}")
        return

    if args.memory_serve:
        from harness.memory.server import run_memory_server
        run_memory_server(port=args.memory_port)
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
        print(f"\nReports:")
        for fmt, path in reports.items():
            print(f"  [{fmt.upper()}] {path}")

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
    if not any([args.agent, args.run, args.run_workflows, args.serve, args.memory_serve]):
        print(
            f"Discovered {len(harness.test_classes)} test(s), "
            f"{len(harness.workflow_classes)} workflow(s). "
            f"Use --run, --run-workflows, --agent, --serve, or --memory-serve."
        )


if __name__ == "__main__":
    asyncio.run(main())
