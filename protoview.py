#!/usr/bin/env python3
"""
protoview: capture network traffic into a capture file (v1).

This version uses `dumpcap` for capture (Wireshark's capture engine) so you can
often run without sudo, assuming your system is configured appropriately.

Output format:
- Default is pcapng (".pcapng"), which is what dumpcap writes by default.

Usage:
  protoview capture [--verbose] [--output FILE] PORT [PORT ...]
"""

from __future__ import annotations

import argparse
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Optional


def _default_capture_name() -> str:
    # ISO-ish, filesystem-safe (no ':')
    # We default to pcapng because dumpcap writes pcapng by default.
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".pcapng"


def _parse_port(s: str) -> int:
    try:
        p = int(s, 10)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid port '{s}': not an integer") from e
    if not (1 <= p <= 65535):
        raise argparse.ArgumentTypeError(f"Invalid port '{s}': must be 1..65535")
    return p


def _build_bpf_filter(ports: List[int]) -> str:
    # tcp and (port 5173 or port 8080 or ...)
    ors = " or ".join(f"port {p}" for p in ports)
    return f"tcp and ({ors})"


def _vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"[protoview] {msg}", file=sys.stderr)


def cmd_capture(args: argparse.Namespace) -> int:
    ports = args.ports
    if not ports:
        # argparse enforces this, but keep it explicit.
        print("ERROR: at least one PORT is required.", file=sys.stderr)
        return 2

    bpf = _build_bpf_filter(ports)
    out = args.output

    _vprint(args.verbose, f"ports          : {ports}")
    _vprint(args.verbose, f"bpf filter     : {bpf}")
    _vprint(args.verbose, f"output capture : {out}")
    _vprint(args.verbose, "interface      : lo")
    _vprint(args.verbose, "transport      : tcp")
    _vprint(args.verbose, "capturer       : dumpcap")
    _vprint(args.verbose, "format         : pcapng (default)")

    dumpcap_cmd = [
        "dumpcap",
        "-i",
        "lo",
        "-f",
        bpf,
        "-w",
        out,
    ]

    # Run dumpcap as a child process so we can forward Ctrl+C / SIGTERM to it.
    # This helps ensure dumpcap closes the capture file cleanly (flush/finalize) on exit.
    _vprint(args.verbose, f"exec           : {shlex.join(dumpcap_cmd)}")

    proc: Optional[subprocess.Popen[bytes]] = None

    def _shutdown(signum: int, _frame) -> None:
        nonlocal proc
        if proc is None:
            return

        sig_name = signal.Signals(signum).name if signum in signal.Signals else str(signum)
        _vprint(args.verbose, f"received signal : {sig_name} ({signum})")
        _vprint(args.verbose, "forwarding to dumpcap for graceful shutdown...")

        # Forward the same signal to dumpcap.
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            return

        # Give dumpcap time to close the capture file properly.
        try:
            proc.wait(timeout=3.0)
            return
        except subprocess.TimeoutExpired:
            _vprint(args.verbose, "dumpcap did not exit in time; escalating to SIGTERM...")
            try:
                proc.terminate()
            except ProcessLookupError:
                return

        try:
            proc.wait(timeout=2.0)
            return
        except subprocess.TimeoutExpired:
            _vprint(args.verbose, "dumpcap still running; escalating to SIGKILL...")
            try:
                proc.kill()
            except ProcessLookupError:
                return

    # Install signal handlers so Ctrl+C and stop signals are forwarded to dumpcap.
    # SIGINT: Ctrl+C in terminal
    # SIGTERM: common "kill" / supervisor stop signal
    old_sigint = signal.signal(signal.SIGINT, _shutdown)
    old_sigterm = signal.signal(signal.SIGTERM, _shutdown)

    try:
        try:
            # Note: dumpcap may be configured (capabilities / group) to allow
            # non-root capture. If not configured, it will fail with a clear error.
            proc = subprocess.Popen(dumpcap_cmd)
        except FileNotFoundError:
            print(
                "ERROR: dumpcap not found on PATH. Install wireshark/tshark (dumpcap is included).",
                file=sys.stderr,
            )
            return 127

        # Wait for dumpcap to finish normally (or via signals handled above).
        while True:
            rc = proc.poll()
            if rc is not None:
                _vprint(args.verbose, f"dumpcap exit code: {rc}")
                if rc != 0:
                    # Be explicit: users often expect "no sudo" to work automatically,
                    # but dumpcap still needs capture privileges via capabilities/group.
                    print(
                        "ERROR: dumpcap failed.\n"
                        "If you expected this to work without sudo, your system may not be configured\n"
                        "to allow non-root packet capture (e.g., dumpcap capabilities / wireshark group).",
                        file=sys.stderr,
                    )
                return int(rc)
            time.sleep(0.1)

    finally:
        # Restore prior handlers (important if this grows to run multiple commands).
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="protoview")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Capture TCP traffic on loopback into a pcapng file.")
    cap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit debug traces to stderr.",
    )
    cap.add_argument(
        "--output",
        "-o",
        default=_default_capture_name(),
        help="Output capture file (default: YYYY-MM-DD-HH-MM-SS.pcapng).",
    )
    cap.add_argument(
        "ports",
        nargs="+",
        type=_parse_port,
        metavar="PORT",
        help="One or more TCP ports to capture on (1..65535).",
    )
    cap.set_defaults(func=cmd_capture)

    return p


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

