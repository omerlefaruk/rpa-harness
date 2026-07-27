#!/usr/bin/env python3
"""ActiveGraph-native rpa-harness CLI.

Legacy YAML, DSL, autopilot, and copilot entrypoints are intentionally removed.
All automation lifecycle operations go through AutomationApplication adapters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPA Harness — ActiveGraph-native automation product",
    )
    parser.add_argument(
        "--automation-init-workspace", help="Initialize an ActiveGraph automation workspace"
    )
    parser.add_argument("--automation-inspect", help="Inspect an ActiveGraph automation run")
    parser.add_argument(
        "--automation-register-proposal",
        help="Register a validated Automation Proposal JSON file",
    )
    parser.add_argument(
        "--automation-validate-proposal",
        help="Validate an Automation Proposal JSON file through the application interface",
    )
    parser.add_argument(
        "--automation-workspace", help="Workspace for ActiveGraph automation commands"
    )
    parser.add_argument(
        "--automation-workspace-status",
        action="store_true",
        help="Show pinned ActiveGraph workspace runtime status",
    )
    parser.add_argument(
        "--automation-workspace-upgrade",
        help="Upgrade workspace runtime to a product version (immutable release pin)",
    )
    parser.add_argument(
        "--automation-workspace-rollback",
        action="store_true",
        help="Roll back workspace runtime to the previous pinned version",
    )
    parser.add_argument(
        "--automation-release-source",
        help="Immutable release source pin for workspace install/upgrade",
    )
    parser.add_argument(
        "--automation-list-operations",
        action="store_true",
        help="List versioned ActiveGraph MCP/CLI operation contracts",
    )
    parser.add_argument(
        "--automation-grant-approval",
        help="JSON file with grant_approval fields for a Definition Version",
    )
    parser.add_argument(
        "--automation-export-evidence",
        help="Export evidence references for a run id",
    )
    parser.add_argument(
        "--automation-reject-repair",
        help="JSON file describing a repair rejection {repair_id, reason}",
    )
    parser.add_argument(
        "--automation-propose",
        help="JSON request {proposal: ...} — agent-authored proposal admission",
    )
    parser.add_argument(
        "--automation-execute-read",
        help="JSON request to execute a read-only definition via capability port",
    )
    parser.add_argument(
        "--automation-execute-write",
        help="JSON request to execute an approval-gated write via capability port",
    )
    parser.add_argument(
        "--automation-reconcile",
        help="JSON request to reconcile a needs_reconciliation run",
    )
    parser.add_argument(
        "--automation-propose-repair",
        help="JSON request to open a repair proposal from failure evidence",
    )
    parser.add_argument(
        "--automation-trial-repair",
        help="JSON request to trial a repair proposal in a fork",
    )
    parser.add_argument(
        "--automation-promote-repair",
        help="JSON request {repair_id, trial_id} to promote a successful trial",
    )
    return parser.parse_args(argv)


def _require_workspace(args: argparse.Namespace, flag: str) -> None:
    if not args.automation_workspace:
        print(f"{flag} requires --automation-workspace", file=sys.stderr)
        sys.exit(2)


def _run_workspace_json(args: argparse.Namespace, request_path: str, flag: str, handler) -> None:
    """Load JSON request, open writer app, print structured result or domain error."""

    _require_workspace(args, flag)
    from harness.automation import AutomationApplication

    try:
        request = json.loads(Path(request_path).read_text(encoding="utf-8"))
        app = AutomationApplication(args.automation_workspace)
        try:
            print(json.dumps(handler(app, request), indent=2, default=str))
        finally:
            app.close()
    except Exception as exc:
        code = getattr(exc, "code", "automation_operation_failed")
        print(json.dumps({"code": code, "error": str(exc)}), file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    configure_console_encoding()
    args = parse_args(argv)

    if args.automation_list_operations:
        from harness.automation.operations import CATALOG_VERSION, list_operations

        print(
            json.dumps(
                {
                    "catalog_version": CATALOG_VERSION,
                    "operations": [item.to_dict() for item in list_operations()],
                },
                indent=2,
            )
        )
        return

    if args.automation_init_workspace:
        from harness.automation import WorkspaceRuntimeManager

        manager = WorkspaceRuntimeManager(args.automation_init_workspace)
        if args.automation_release_source:
            status = manager.initialize(release_source=args.automation_release_source)
        else:
            status = manager.initialize()
        print(json.dumps(status.to_dict(), indent=2, default=str))
        return

    if args.automation_workspace_status:
        if not args.automation_workspace:
            print("--automation-workspace-status requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import WorkspaceRuntimeManager

        print(
            json.dumps(
                WorkspaceRuntimeManager(args.automation_workspace).status().to_dict(),
                indent=2,
                default=str,
            )
        )
        return

    if args.automation_workspace_upgrade:
        if not args.automation_workspace:
            print("--automation-workspace-upgrade requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import WorkspaceRuntimeError, WorkspaceRuntimeManager, default_manifest

        manager = WorkspaceRuntimeManager(args.automation_workspace)
        target = default_manifest(
            product_version=args.automation_workspace_upgrade,
            release_source=args.automation_release_source
            or f"pypi:rpa-harness=={args.automation_workspace_upgrade}",
        )
        try:
            status = manager.upgrade(target)
        except WorkspaceRuntimeError as exc:
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "operator_action": getattr(
                            exc, "operator_action", "retry upgrade; active runtime unchanged"
                        ),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            sys.exit(2)
        print(json.dumps(status.to_dict(), indent=2, default=str))
        return

    if args.automation_workspace_rollback:
        if not args.automation_workspace:
            print("--automation-workspace-rollback requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import WorkspaceRuntimeError, WorkspaceRuntimeManager

        try:
            status = WorkspaceRuntimeManager(args.automation_workspace).rollback()
        except WorkspaceRuntimeError as exc:
            print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
            sys.exit(2)
        print(json.dumps(status.to_dict(), indent=2, default=str))
        return

    if args.automation_inspect:
        if not args.automation_workspace:
            print("--automation-inspect requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import AutomationApplication

        app = AutomationApplication(args.automation_workspace, read_only=True)
        try:
            print(
                json.dumps(
                    app.inspect_run(args.automation_inspect).to_dict(), indent=2, default=str
                )
            )
        finally:
            app.close()
        return

    if args.automation_validate_proposal:
        from harness.automation import (
            AutomationApplication,
            AutomationDefinition,
            ProposalValidationError,
            proposal_from_dict,
        )

        try:
            proposal_data = json.loads(
                Path(args.automation_validate_proposal).read_text(encoding="utf-8")
            )
            proposal = proposal_from_dict(proposal_data, AutomationDefinition)
            validation = AutomationApplication.validate_proposal(proposal)
            payload = {
                "accepted": validation.accepted,
                "errors": list(validation.errors),
                "code": None if validation.accepted else "automation_proposal_invalid",
            }
            print(json.dumps(payload, indent=2, default=str))
            if not validation.accepted:
                sys.exit(2)
        except (OSError, ValueError, ProposalValidationError, TypeError, KeyError) as exc:
            code = getattr(exc, "code", "automation_proposal_input_invalid")
            print(json.dumps({"code": code, "error": str(exc)}), file=sys.stderr)
            sys.exit(2)
        return

    if args.automation_register_proposal:
        if not args.automation_workspace:
            print("--automation-register-proposal requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import (
            AutomationApplication,
            AutomationDefinition,
            ProposalValidationError,
            proposal_from_dict,
        )

        try:
            proposal_data = json.loads(
                Path(args.automation_register_proposal).read_text(encoding="utf-8")
            )
            proposal = proposal_from_dict(proposal_data, AutomationDefinition)
            app = AutomationApplication(args.automation_workspace)
            try:
                print(json.dumps(app.register_proposal(proposal).to_dict(), indent=2, default=str))
            finally:
                app.close()
        except (OSError, ValueError, ProposalValidationError) as exc:
            code = getattr(exc, "code", "automation_proposal_input_invalid")
            print(json.dumps({"code": code, "error": str(exc)}), file=sys.stderr)
            sys.exit(2)
        return

    if args.automation_grant_approval:
        if not args.automation_workspace:
            print("--automation-grant-approval requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import ApprovalError, AuthorityError, AutomationApplication

        try:
            payload = json.loads(Path(args.automation_grant_approval).read_text(encoding="utf-8"))
            app = AutomationApplication(args.automation_workspace)
            try:
                grant = app.grant_approval(**payload)
                print(json.dumps(grant.to_dict(), indent=2, default=str))
            finally:
                app.close()
        except (OSError, ValueError, TypeError, KeyError, ApprovalError, AuthorityError) as exc:
            code = getattr(exc, "code", "automation_approval_input_invalid")
            print(json.dumps({"code": code, "error": str(exc)}), file=sys.stderr)
            sys.exit(2)
        return

    if args.automation_export_evidence:
        if not args.automation_workspace:
            print("--automation-export-evidence requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import AutomationApplication

        app = AutomationApplication(args.automation_workspace, read_only=True)
        try:
            summary = app.inspect_run(args.automation_export_evidence)
            print(
                json.dumps(
                    {
                        "run_id": summary.run_id,
                        "status": summary.status,
                        "evidence_references": [
                            item.__dict__ for item in summary.evidence_references
                        ],
                    },
                    indent=2,
                    default=str,
                )
            )
        except KeyError as exc:
            print(json.dumps({"code": "unknown_run", "error": str(exc)}), file=sys.stderr)
            sys.exit(2)
        finally:
            app.close()
        return

    if args.automation_reject_repair:
        if not args.automation_workspace:
            print("--automation-reject-repair requires --automation-workspace", file=sys.stderr)
            sys.exit(2)
        from harness.automation import AutomationApplication, RepairError

        try:
            payload = json.loads(Path(args.automation_reject_repair).read_text(encoding="utf-8"))
            app = AutomationApplication(args.automation_workspace)
            try:
                app.reject_repair(
                    payload["repair_id"],
                    reason=payload["reason"],
                    trial_id=payload.get("trial_id"),
                )
                print(json.dumps({"rejected": True, "repair_id": payload["repair_id"]}, indent=2))
            finally:
                app.close()
        except (OSError, ValueError, TypeError, KeyError, RepairError) as exc:
            code = getattr(exc, "code", "automation_repair_input_invalid")
            print(json.dumps({"code": code, "error": str(exc)}), file=sys.stderr)
            sys.exit(2)
        return

    if args.automation_propose:
        from harness.automation.agent_ops import propose_from_request

        _run_workspace_json(
            args, args.automation_propose, "--automation-propose", propose_from_request
        )
        return

    if args.automation_execute_read:
        from harness.automation.agent_ops import execute_read_only_request

        _run_workspace_json(
            args,
            args.automation_execute_read,
            "--automation-execute-read",
            execute_read_only_request,
        )
        return

    if args.automation_execute_write:
        from harness.automation.agent_ops import execute_write_request

        _run_workspace_json(
            args,
            args.automation_execute_write,
            "--automation-execute-write",
            execute_write_request,
        )
        return

    if args.automation_reconcile:
        from harness.automation.agent_ops import reconcile_request

        _run_workspace_json(
            args, args.automation_reconcile, "--automation-reconcile", reconcile_request
        )
        return

    if args.automation_propose_repair:
        from harness.automation.agent_ops import propose_repair_request

        _run_workspace_json(
            args,
            args.automation_propose_repair,
            "--automation-propose-repair",
            propose_repair_request,
        )
        return

    if args.automation_trial_repair:
        from harness.automation.agent_ops import trial_repair_request

        _run_workspace_json(
            args,
            args.automation_trial_repair,
            "--automation-trial-repair",
            trial_repair_request,
        )
        return

    if args.automation_promote_repair:
        from harness.automation.agent_ops import promote_repair_request

        _run_workspace_json(
            args,
            args.automation_promote_repair,
            "--automation-promote-repair",
            promote_repair_request,
        )
        return

    parse_args(["--help"])


def run() -> None:
    main()


if __name__ == "__main__":
    run()
