#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit_path="$unit_dir/rpa-harness-self-improvement.service"
mkdir -p "$unit_dir" "$repo_root/logs"

cat > "$unit_path" <<UNIT
[Unit]
Description=RPA Harness autonomous self-improvement daemon
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$repo_root
ExecStart=/bin/bash $repo_root/scripts/start_self_improving_daemon.sh
Restart=always
RestartSec=10
StandardOutput=append:$repo_root/logs/self-improvement.out.log
StandardError=append:$repo_root/logs/self-improvement.err.log

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now rpa-harness-self-improvement.service
echo "$unit_path"
