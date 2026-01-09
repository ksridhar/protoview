#!/usr/bin/env python3
"""
protoview

Currently implemented:
  - capture: capture traffic on loopback using dumpcap (pcapng default)
  - analyze --dry-run: preflight a pcap/pcapng and print a summary report to stdout

Design notes:
- capture defaults to stdout (binary pcapng); verbose logs go to stderr.
- analyze defaults to stdin for input and stdout for the report.
- PVTS version is fixed by the tool; expose via: protoview analyze --pvts-version
- Tool version is exposed via: protoview --version

Important:
- This is an OUTSIDE-OBSERVER tool. It infers semantics from packet captures.
- The dry-run report uses tshark’s dissectors/fields; it is best-effort and will
  not perfectly reflect “true” application payload sizes in all cases (e.g.,
  chunked transfer, compression, truncated capture, HTTP/2+).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

TOOL_VERSION = "0.1.0"
PVTS_VERSION = "0.1"


# ----------------------------
# Common helpers
# ----------------------------

def _vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"[protoview] {msg}", file=sys.stderr)


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


def _is_interactive_stdout() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _which(cmd: str) -> Optional[str]:
    # Lightweight "which" without importing shutil (keeps deps minimal).
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, cmd)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _read_stdin_to_tempfile(verbose: bool, suffix: str = ".pcapng") -> str:
    """
    Read stdin (binary) to a temp file and return the path.
    This is used because tshark is much happier reading from a file than stdin.
    """
    _vprint(verbose, "reading stdin into a temporary capture file...")
    fd, path = tempfile.mkstemp(prefix="protoview-", suffix=suffix)
    os.close(fd)
    try:
        with open(path, "wb") as f:
            while True:
                chunk = sys.stdin.buffer.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        _vprint(verbose, f"stdin saved to: {path}")
        return path
    except Exception:
        try:
            os.unlink(path)
        except Exception:
            pass
        raise


def _normalize_content_type(ct: str) -> str:
    # Keep it small: lower + strip params.
    # E.g. "application/json; charset=utf-8" -> "application/json"
    ct = (ct or "").strip().lower()
    if ";" in ct:
        ct = ct.split(";", 1)[0].strip()
    return ct


def _classify_payload_kind(content_type: str) -> str:
    """
    Heuristic classifier for "text-ish" vs "binary-ish".
    This is intentionally simple and honest.
    """
    ct = _normalize_content_type(content_type)

    if not ct:
        return "unknown"

    # Treat these as text-ish (A2UI and common web payloads).
    if ct.startswith("text/"):
        return "text"
    if ct in ("application/json", "application/ld+json", "application/schema+json"):
        return "text"
    if ct.endswith("+json"):
        return "text"
    if ct in ("text/event-stream",):
        return "text"
    if ct in ("application/xml", "text/xml") or ct.endswith("+xml"):
        return "text"
    if ct == "application/x-www-form-urlencoded":
        return "text"

    # Everything else: likely binary or structured binary.
    return "binary"


# ----------------------------
# capture subcommand
# ----------------------------

def cmd_capture(args: argparse.Namespace) -> int:
    ports = args.ports
    if not ports:
        print("ERROR: at least one PORT is required.", file=sys.stderr)
        return 2

    bpf = _build_bpf_filter(ports)

    # Default output is stdout. dumpcap uses '-' to mean stdout for -w.
    out = args.output if args.output is not None else "-"
    if out == "stdout":
        out = "-"

    _vprint(args.verbose, f"ports          : {ports}")
    _vprint(args.verbose, f"bpf filter     : {bpf}")
    _vprint(args.verbose, f"output capture : {'STDOUT' if out == '-' else out}")
    _vprint(args.verbose, "interface      : lo")
    _vprint(args.verbose, "transport      : tcp")
    _vprint(args.verbose, "capturer       : dumpcap")
    _vprint(args.verbose, "format         : pcapng (dumpcap default)")

    if out == "-" and _is_interactive_stdout():
        print(
            "ERROR: Refusing to write binary capture data to an interactive terminal.\n"
            "Redirect stdout to a file, e.g.:\n"
            "  protoview capture 5173 10002 > capture.pcapng\n"
            "or specify --output capture.pcapng",
            file=sys.stderr,
        )
        return 2

    dumpcap_cmd = ["dumpcap", "-i", "lo", "-f", bpf, "-w", out]
    _vprint(args.verbose, f"exec           : {shlex.join(dumpcap_cmd)}")

    proc: Optional[subprocess.Popen[bytes]] = None

    def _shutdown(signum: int, _frame) -> None:
        nonlocal proc
        if proc is None:
            return

        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            sig_name = str(signum)

        _vprint(args.verbose, f"received signal : {sig_name} ({signum})")
        _vprint(args.verbose, "forwarding to dumpcap for graceful shutdown...")

        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            return

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

    old_sigint = signal.signal(signal.SIGINT, _shutdown)
    old_sigterm = signal.signal(signal.SIGTERM, _shutdown)

    try:
        try:
            proc = subprocess.Popen(dumpcap_cmd)
        except FileNotFoundError:
            print(
                "ERROR: dumpcap not found on PATH. Install wireshark/tshark (dumpcap is included).",
                file=sys.stderr,
            )
            return 127
        except PermissionError as e:
            print(
                f"ERROR: cannot execute dumpcap ({e}).\n"
                "On many systems, dumpcap is executable only by the 'wireshark' group.\n"
                "Check: ls -l /usr/bin/dumpcap ; id -nG",
                file=sys.stderr,
            )
            return 126

        while True:
            rc = proc.poll()
            if rc is not None:
                _vprint(args.verbose, f"dumpcap exit code: {rc}")
                if rc != 0:
                    print(
                        "ERROR: dumpcap failed.\n"
                        "If you expected this to work without sudo, your system may not be configured\n"
                        "to allow non-root packet capture (e.g., dumpcap capabilities / wireshark group).",
                        file=sys.stderr,
                    )
                return int(rc)
            time.sleep(0.1)
    finally:
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)


# ----------------------------
# analyze --dry-run
# ----------------------------

@dataclass
class DryRunStats:
    # counts
    http_requests: int = 0
    http_responses: int = 0
    sse_responses: int = 0
    multipart_responses: int = 0

    # payload lengths (best-effort, based mostly on Content-Length header)
    content_length_values: List[int] = None  # type: ignore

    # classification
    payload_kind_counts: Counter = None  # type: ignore
    content_type_counts: Counter = None  # type: ignore
    content_encoding_counts: Counter = None  # type: ignore

    # endpoints (method+target) by count / bytes (best-effort bytes)
    endpoint_counts: Counter = None  # type: ignore
    endpoint_bytes: Counter = None  # type: ignore

    def __post_init__(self) -> None:
        if self.content_length_values is None:
            self.content_length_values = []
        if self.payload_kind_counts is None:
            self.payload_kind_counts = Counter()
        if self.content_type_counts is None:
            self.content_type_counts = Counter()
        if self.content_encoding_counts is None:
            self.content_encoding_counts = Counter()
        if self.endpoint_counts is None:
            self.endpoint_counts = Counter()
        if self.endpoint_bytes is None:
            self.endpoint_bytes = Counter()


def _run_tshark_fields(
    *,
    verbose: bool,
    input_path: str,
    display_filter: str,
    fields: List[str],
) -> Iterable[List[str]]:
    """
    Run tshark and yield each row as a list of field values (strings).

    We use:
      -T fields with tab separation
      -E occurrence=f (first) for stability
    """
    tshark = _which("tshark")
    if not tshark:
        raise RuntimeError("tshark not found on PATH. Install tshark (Wireshark CLI).")

    cmd = [
        tshark,
        "-r",
        input_path,
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "separator=\t",
        "-E",
        "occurrence=f",
    ]
    for f in fields:
        cmd.extend(["-e", f])

    _vprint(verbose, f"exec           : {shlex.join(cmd)}")

    # text=True gives us decoded strings; tshark fields are textual anyway.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    assert proc.stderr is not None

    for line in proc.stdout:
        line = line.rstrip("\n")
        yield line.split("\t")

    stderr = proc.stderr.read()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"tshark failed with exit code {rc}.\n{stderr.strip()}")


def _safe_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    # tshark may emit multiple values separated by commas; we asked occurrence=f,
    # but be defensive.
    if "," in s:
        s = s.split(",", 1)[0].strip()
    try:
        return int(s, 10)
    except ValueError:
        return None


def _print_dry_run_report(stats: DryRunStats) -> None:
    # No tables (per your preference). Keep it structured and scannable.

    def pct(part: int, whole: int) -> str:
        if whole <= 0:
            return "0%"
        return f"{(100.0 * part / whole):.1f}%"

    print("# protoview analyze --dry-run report")
    print()
    print("## HTTP summary")
    print(f"- HTTP requests:  {stats.http_requests}")
    print(f"- HTTP responses: {stats.http_responses}")

    if stats.http_responses:
        print(f"- SSE responses (Content-Type: text/event-stream): {stats.sse_responses} ({pct(stats.sse_responses, stats.http_responses)})")
        print(f"- Multipart responses (Content-Type: multipart/*): {stats.multipart_responses} ({pct(stats.multipart_responses, stats.http_responses)})")
    else:
        print(f"- SSE responses (Content-Type: text/event-stream): {stats.sse_responses}")
        print(f"- Multipart responses (Content-Type: multipart/*): {stats.multipart_responses}")

    print()
    print("## Payload size observations (best-effort)")
    if stats.content_length_values:
        vals = sorted(stats.content_length_values)
        min_v = vals[0]
        max_v = vals[-1]
        p50 = vals[len(vals) // 2]
        p90 = vals[int(len(vals) * 0.9) - 1] if len(vals) >= 10 else vals[-1]
        p99 = vals[int(len(vals) * 0.99) - 1] if len(vals) >= 100 else vals[-1]
        total = sum(vals)
        print("- Source: primarily the HTTP Content-Length header (may be absent for chunked/SSE/streaming).")
        print(f"- Observed Content-Length values: {len(vals)}")
        print(f"- Total bytes (sum of observed Content-Length): {total}")
        print(f"- Min / p50 / p90 / p99 / max: {min_v} / {p50} / {p90} / {p99} / {max_v}")
    else:
        print("- No Content-Length values were observed (common for chunked or streaming responses).")

    print()
    print("## Payload kind (heuristic via Content-Type)")
    if stats.payload_kind_counts:
        for k, c in stats.payload_kind_counts.most_common():
            print(f"- {k}: {c}")
    else:
        print("- No payload classifications available.")

    print()
    print("## Top Content-Types (normalized)")
    if stats.content_type_counts:
        for ct, c in stats.content_type_counts.most_common(15):
            print(f"- {ct}: {c}")
    else:
        print("- No Content-Type headers observed.")

    print()
    print("## Content-Encoding (compression hints)")
    if stats.content_encoding_counts:
        for enc, c in stats.content_encoding_counts.most_common(15):
            print(f"- {enc}: {c}")
    else:
        print("- No Content-Encoding headers observed.")

    print()
    print("## Top endpoints by count (request method + target)")
    if stats.endpoint_counts:
        for ep, c in stats.endpoint_counts.most_common(15):
            print(f"- {ep}: {c}")
    else:
        print("- No request endpoints observed.")

    print()
    print("## Top endpoints by bytes (best-effort)")
    if stats.endpoint_bytes:
        for ep, b in stats.endpoint_bytes.most_common(15):
            print(f"- {ep}: {b} bytes (from Content-Length when present)")
    else:
        print("- No endpoint byte totals available (requires Content-Length observations).")

    print()
    print("## Notes")
    print("- This report is derived from tshark dissectors and may not reflect exact application payload bytes in all cases.")
    print("- Streaming responses (SSE) often have no Content-Length; they can still be large over time.")
    print("- If you need a more precise body-size report later, we can add deeper extraction logic (reassembly + optional decompression).")


def cmd_analyze(args: argparse.Namespace) -> int:
    # Informational flag: print PVTS version and exit.
    if args.pvts_version:
        print(PVTS_VERSION)
        return 0

    if not args.dry_run:
        print(
            "ERROR: analyze without --dry-run is not implemented yet.\n"
            "For now, use: protoview analyze --dry-run [--input ...]",
            file=sys.stderr,
        )
        return 2

    # Input defaults to stdin.
    input_path: Optional[str] = args.input
    temp_path: Optional[str] = None
    try:
        if not input_path or input_path == "-":
            temp_path = _read_stdin_to_tempfile(args.verbose, suffix=".pcapng")
            input_path = temp_path

        stats = DryRunStats()

        # We focus on HTTP request/response frames. This is a best-effort preflight.
        # Later, the full PVTS analyzer can do deeper reassembly and SSE eventization.
        display_filter = "http.request or http.response"
        fields = [
            "http.request.method",
            "http.request.uri",
            "http.response.code",
            "http.content_type",
            "http.content_length",
            "http.content_encoding",
        ]

        for row in _run_tshark_fields(
            verbose=args.verbose,
            input_path=input_path,
            display_filter=display_filter,
            fields=fields,
        ):
            # Map row elements safely by position.
            method = row[0].strip() if len(row) > 0 else ""
            uri = row[1].strip() if len(row) > 1 else ""
            resp_code = row[2].strip() if len(row) > 2 else ""
            content_type = row[3].strip() if len(row) > 3 else ""
            content_length_s = row[4].strip() if len(row) > 4 else ""
            content_encoding = row[5].strip() if len(row) > 5 else ""

            if method:
                stats.http_requests += 1
                ep = f"{method} {uri or ''}".strip()
                stats.endpoint_counts[ep] += 1

            if resp_code:
                stats.http_responses += 1

            ct_norm = _normalize_content_type(content_type)
            if ct_norm:
                stats.content_type_counts[ct_norm] += 1
                kind = _classify_payload_kind(ct_norm)
                stats.payload_kind_counts[kind] += 1

                if ct_norm == "text/event-stream":
                    stats.sse_responses += 1
                if ct_norm.startswith("multipart/"):
                    stats.multipart_responses += 1

            if content_encoding:
                stats.content_encoding_counts[content_encoding.strip().lower()] += 1

            cl = _safe_int(content_length_s)
            if cl is not None:
                stats.content_length_values.append(cl)
                # Attribute bytes to endpoint if we can. (Best-effort.)
                if method:
                    ep = f"{method} {uri or ''}".strip()
                    stats.endpoint_bytes[ep] += cl

        _print_dry_run_report(stats)
        return 0

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


# ----------------------------
# CLI
# ----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="protoview", add_help=True)
    p.add_argument(
        "--version",
        action="store_true",
        help="Print protoview version and exit.",
    )

    sub = p.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="Capture TCP traffic on loopback (pcapng by default).")
    cap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit debug traces to stderr.",
    )
    cap.add_argument(
        "--output",
        "-o",
        default="-",
        help=(
            "Output capture destination. Use '-' for stdout (default). "
            "Example: --output capture.pcapng"
        ),
    )
    cap.add_argument(
        "ports",
        nargs="+",
        type=_parse_port,
        metavar="PORT",
        help="One or more TCP ports to capture on (1..65535).",
    )
    cap.set_defaults(func=cmd_capture)

    an = sub.add_parser("analyze", help="Analyze a pcap/pcapng and (for now) produce a dry-run report.")
    an.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit debug traces to stderr.",
    )
    an.add_argument(
        "--pvts-version",
        action="store_true",
        help="Print the PVTS version emitted by this protoview build and exit.",
    )
    an.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the capture and print a summary report to stdout (no PVTS emitted).",
    )
    an.add_argument(
        "--input",
        "-i",
        default="-",
        help="Input capture file path, or '-' for stdin (default).",
    )
    an.set_defaults(func=cmd_analyze)

    return p


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        print(TOOL_VERSION)
        return 0

    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

