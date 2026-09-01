"""Register `context-note watch` as a background service.

macOS gets a launchd agent, Linux a systemd user unit. Windows is left to the
user (Task Scheduler) rather than shipping a half-tested COM script.
"""

import platform
import subprocess
import sys
from pathlib import Path

LAUNCHD_LABEL = "com.contextnote.watch"

LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>-m</string><string>context_note.cli</string><string>watch</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""

SYSTEMD_UNIT = """[Unit]
Description=context-note export watcher

[Service]
ExecStart={python} -m context_note.cli watch
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""


def install_macos(log: Path) -> int:
    target = Path.home() / "Library/LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        LAUNCHD_PLIST.format(label=LAUNCHD_LABEL, python=sys.executable, log=log)
    )
    subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(target)], capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode().strip())
        return 1
    print(f"launch agent installed: {target}")
    print(f"logs: {log}")
    print(f"stop with: launchctl unload {target}")
    return 0


def install_linux(log: Path) -> int:
    target = Path.home() / ".config/systemd/user/context-note.service"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SYSTEMD_UNIT.format(python=sys.executable))
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "context-note.service"],
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stderr.decode().strip())
        return 1
    print(f"systemd unit installed: {target}")
    print("logs: journalctl --user -u context-note -f")
    print("stop with: systemctl --user disable --now context-note")
    return 0


def install_service(log: Path) -> int:
    system = platform.system()
    if system == "Darwin":
        return install_macos(log)
    if system == "Linux":
        return install_linux(log)
    print("Automatic service install is not supported on this platform.")
    print("Run `context-note watch` manually, or register it with Task Scheduler:")
    print(f"  {sys.executable} -m context_note.cli watch")
    return 1
