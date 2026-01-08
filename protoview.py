#!/usr/bin/env python3
"""
protoview: capture network traffic into a pcap file (v1).

Usage:
  protoview capture [--verbose] [--output FILE] PORT [PORT ...]
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Optional


def _default_pcap_name() -> str:
    # ISO-ish, filesystem-safe (no ':')
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".pcap"


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
    if os.geteuid() != 0:
        print(
            "ERROR: packet capture typically requires root. Re-run with sudo.",
            file=sys.stderr,
        )
        return 2

    ports = args.ports
    if not ports:
        # argparse enforces this, but keep it explicit.
        print("ERROR: at least one PORT is required.", file=sys.stderr)
        return 2

    bpf = _build_bpf_filter(ports)
    out = args.output

    _vprint(args.verbose, f"ports          : {ports}")
    _vprint(args.verbose, f"bpf filter     : {bpf}")
    _vprint(args.verbose, f"output pcap    : {out}")
    _vprint(args.verbose, "interface      : lo")
    _vprint(args.verbose, "transport      : tcp")

    tshark_cmd = [
        "tshark",
        "-i",
        "lo",
        "-f",
        bpf,
        "-w",
        out,
    ]

    # Run tshark as a child process so we can forward Ctrl+C / SIGTERM to it.
    # This helps ensure tshark closes the pcap cleanly (flush/finalize) on exit.
    _vprint(args.verbose, f"exec           : {shlex.join(tshark_cmd)}")

    proc: Optional[subprocess.Popen[bytes]] = None

    def _shutdown(signum: int, _frame) -> None:
        nonlocal proc
        if proc is None:
            return

        sig_name = signal.Signals(signum).name if signum in signal.Signals else str(signum)
        _vprint(args.verbose, f"received signal : {sig_name} ({signum})")
        _vprint(args.verbose, "forwarding to tshark for graceful shutdown...")

        # Forward the same signal to tshark.
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            return

        # Give tshark time to close the capture file properly.
        try:
            proc.wait(timeout=3.0)
            return
        except subprocess.TimeoutExpired:
            _vprint(args.verbose, "tshark did not exit in time; escalating to SIGTERM...")
            try:
                proc.terminate()
            except ProcessLookupError:
                return

        try:
            proc.wait(timeout=2.0)
            return
        except subprocess.TimeoutExpired:
            _vprint(args.verbose, "tshark still running; escalating to SIGKILL...")
            try:
                proc.kill()
            except ProcessLookupError:
                return

    # Install signal handlers so Ctrl+C and kill/stop signals are forwarded to tshark.
    # SIGINT: Ctrl+C in terminal
    # SIGTERM: common "kill" / supervisor stop signal
    old_sigint = signal.signal(signal.SIGINT, _shutdown)
    old_sigterm = signal.signal(signal.SIGTERM, _shutdown)

    try:
        try:
            proc = subprocess.Popen(tshark_cmd)
        except FileNotFoundError:
            print(
                "ERROR: tshark not found on PATH. Install wireshark/tshark.",
                file=sys.stderr,
            )
            return 127

        # Wait for tshark to finish normally (or via signals handled above).
        while True:
            rc = proc.poll()
            if rc is not None:
                _vprint(args.verbose, f"tshark exit code: {rc}")
                return int(rc)
            time.sleep(0.1)

    finally:
        # Restore prior handlers (important if this grows to run multiple commands).
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="protoview")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Capture TCP traffic on loopback into a pcap file.")
    cap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit debug traces to stderr.",
    )
    cap.add_argument(
        "--output",
        "-o",
        default=_default_pcap_name(),
        help="Output pcap file (default: YYYY-MM-DD-HH-MM-SS.pcap).",
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

