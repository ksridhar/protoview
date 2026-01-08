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
import subprocess
import sys
from datetime import datetime
from typing import List


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
        "-i", "lo",
        "-f", bpf,
        "-w", out,
    ]

    _vprint(args.verbose, f"exec            : {shlex.join(tshark_cmd)}")

    try:
        proc = subprocess.run(tshark_cmd, check=False)
        _vprint(args.verbose, f"tshark exit code: {proc.returncode}")
        return proc.returncode
    except FileNotFoundError:
        print(
            "ERROR: tshark not found on PATH. Install wireshark/tshark.",
            file=sys.stderr,
        )
        return 127


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="protoview")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser(
        "capture",
        help="Capture TCP traffic on loopback into a pcap file."
    )
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

