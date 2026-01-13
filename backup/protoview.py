#!/usr/bin/env python3
"""
protoview

Implemented subcommands:
  - capture
      Capture traffic on loopback using dumpcap (pcapng default).
      Default output is STDOUT (binary pcapng). Verbose logs go to STDERR.

  - analyze --dry-run
      Preflight a pcap/pcapng and print a summary report to STDOUT.

  - analyze (PVTS emitter)
      Consume a pcap/pcapng and emit PVTS JSONL (ProtoView Trace Stream) to STDOUT by default.

Design notes:
- analyze input defaults to STDIN (use --input FILE to read a file).
- analyze output defaults to STDOUT (use --output FILE to write a file).
- PVTS version is fixed by this build; expose via: protoview analyze --pvts-version
- Tool version is exposed via: protoview --version

Caveats (first iteration of PVTS emission):
- Best-effort HTTP/1.x extraction via tshark fields.
- Request/response correlation is inferred by per-tcp.stream ordering (Wireshark-style).
- SSE and multipart are parsed from captured response body when tshark provides it in http.file_data.
  For live/long-lived SSE streams, captures may contain partial data; PVTS reflects what was captured.
- Decompression is NOT implemented yet (gzip/br/deflate). Content-Encoding is reported as metadata only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


TOOL_VERSION = "0.1.0"
PVTS_VERSION = "0.1"


# ----------------------------
# Common helpers
# ----------------------------

def _vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"[protoview] {msg}", file=sys.stderr)


def _is_interactive_stdout() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _which(cmd: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, cmd)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _read_stdin_to_tempfile(verbose: bool, suffix: str = ".pcapng") -> str:
    """
    Read stdin (binary) to a temp file and return the path.
    Used because tshark prefers files over stdin for -r.
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


def _utc_iso_from_epoch(epoch_s: str) -> str:
    """
    Convert tshark's frame.time_epoch to RFC3339/ISO timestamp in UTC.
    """
    try:
        v = float(epoch_s)
    except Exception:
        # Fallback to "now" if parsing fails (should be rare).
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    dt = datetime.fromtimestamp(v, tz=timezone.utc)
    # Use Z suffix.
    return dt.isoformat().replace("+00:00", "Z")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_content_type(ct: str) -> str:
    ct = (ct or "").strip().lower()
    if ";" in ct:
        ct = ct.split(";", 1)[0].strip()
    return ct


def _classify_payload_kind(content_type: str) -> str:
    """
    Heuristic classifier for "text-ish" vs "binary-ish".
    """
    ct = _normalize_content_type(content_type)
    if not ct:
        return "unknown"
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
    return "binary"


def _safe_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    if "," in s:
        s = s.split(",", 1)[0].strip()
    try:
        return int(s, 10)
    except ValueError:
        return None


def _parse_headers_from_lines(lines: str) -> List[Dict[str, str]]:
    """
    Parse HTTP headers from tshark's http.request.line / http.response.line output.

    tshark typically emits multiple lines separated by '\n' with:
      - request/status line
      - headers
      - blank line

    We skip the first line (request/status line) and parse "Name: Value" headers.
    """
    if not lines:
        return []
    # Normalize line endings.
    raw_lines = lines.replace("\r\n", "\n").split("\n")

    headers: List[Dict[str, str]] = []
    for i, ln in enumerate(raw_lines):
        ln = ln.strip("\r")
        if i == 0:
            # request/status line
            continue
        if not ln.strip():
            continue
        if ":" not in ln:
            continue
        name, value = ln.split(":", 1)
        headers.append({"name": name.strip(), "value": value.lstrip()})
    return headers


def _extract_boundary(content_type_header: str) -> Optional[str]:
    """
    Extract multipart boundary from Content-Type header value.
    """
    if not content_type_header:
        return None
    m = re.search(r'boundary="?([^";]+)"?', content_type_header, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _split_multipart(body: str, boundary: str) -> List[Tuple[List[Dict[str, str]], str]]:
    """
    Very small multipart parser for first iteration (textual).
    Returns list of (part_headers, part_body_text).
    """
    # RFC-ish boundary delimiters: --boundary and final --boundary--
    delim = f"--{boundary}"
    end_delim = f"--{boundary}--"

    # We work on text. This will not be perfect for binary parts; that's OK for v1.
    parts: List[Tuple[List[Dict[str, str]], str]] = []

    # Split on boundary markers.
    chunks = body.split(delim)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk == "--" or chunk == end_delim.strip():
            continue
        if chunk.startswith("--"):
            # end marker
            continue

        # Separate headers and body by first blank line.
        # Accept either \r\n\r\n or \n\n.
        if "\r\n\r\n" in chunk:
            head, bdy = chunk.split("\r\n\r\n", 1)
        elif "\n\n" in chunk:
            head, bdy = chunk.split("\n\n", 1)
        else:
            # no clear split
            head, bdy = "", chunk

        hdrs: List[Dict[str, str]] = []
        for ln in head.replace("\r\n", "\n").split("\n"):
            ln = ln.strip()
            if not ln or ":" not in ln:
                continue
            n, v = ln.split(":", 1)
            hdrs.append({"name": n.strip(), "value": v.lstrip()})

        parts.append((hdrs, bdy.strip("\r\n")))
    return parts


def _parse_sse_events(body: str) -> List[Dict[str, Any]]:
    """
    Parse SSE events from a captured SSE response body.

    SSE framing:
      - events are separated by blank line
      - lines include: event:, id:, retry:, data:
      - multiple data: lines are concatenated with '\n'

    Returns list of dicts with keys: event, id, retry_ms, data
    """
    # Normalize
    txt = body.replace("\r\n", "\n")
    blocks = txt.split("\n\n")

    out: List[Dict[str, Any]] = []
    for blk in blocks:
        blk = blk.strip("\n")
        if not blk.strip():
            continue
        ev: Dict[str, Any] = {}
        data_lines: List[str] = []
        for ln in blk.split("\n"):
            if not ln or ln.startswith(":"):
                continue
            if ":" not in ln:
                continue
            k, v = ln.split(":", 1)
            k = k.strip()
            v = v.lstrip()
            if k == "event":
                ev["event"] = v
            elif k == "id":
                ev["id"] = v
            elif k == "retry":
                ms = _safe_int(v)
                if ms is not None:
                    ev["retry_ms"] = ms
            elif k == "data":
                data_lines.append(v)
        ev["data"] = "\n".join(data_lines)
        # Only keep if there's data or some fields.
        if ev.get("data") or any(k in ev for k in ("event", "id", "retry_ms")):
            out.append(ev)
    return out


def _write_jsonl_line(out_f, obj: Dict[str, Any]) -> None:
    out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    out_f.flush()


# ----------------------------
# capture subcommand (unchanged except stdout default)
# ----------------------------

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
# analyze helpers (tshark runner)
# ----------------------------

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


# ----------------------------
# analyze --dry-run
# ----------------------------

@dataclass
class DryRunStats:
    http_requests: int = 0
    http_responses: int = 0
    sse_responses: int = 0
    multipart_responses: int = 0

    content_length_values: List[int] = None  # type: ignore
    payload_kind_counts: Counter = None  # type: ignore
    content_type_counts: Counter = None  # type: ignore
    content_encoding_counts: Counter = None  # type: ignore
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


def _print_dry_run_report(stats: DryRunStats) -> None:
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
    print("- Decompression is not performed in dry-run; Content-Encoding is reported as a hint only.")


# ----------------------------
# analyze (PVTS emitter)
# ----------------------------

@dataclass
class _PendingReq:
    req_id: str
    root_id: str


def _make_trace_id() -> str:
    # Stable-ish, filesystem/log friendly.
    return "pvts-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _open_output_stream(path: str):
    if path == "-" or path == "" or path is None:
        return sys.stdout
    return open(path, "w", encoding="utf-8")


def _make_endpoint(host: str, port: str, name: Optional[str] = None) -> Dict[str, Any]:
    ep: Dict[str, Any] = {"host": host, "port": int(port)}
    if name:
        ep["name"] = name
    return ep


def _emit_pvts(
    *,
    verbose: bool,
    input_path: str,
    output_path: str,
    display_binary_payload: bool,
) -> int:
    """
    Emit PVTS JSONL for HTTP request/response frames, plus SSE and multipart sub-events when possible.
    """
    trace_id = _make_trace_id()

    # Minimal tshark extraction for v1.
    # NOTE: http.file_data is best-effort for reassembled body (may be empty for streaming or un-reassembled cases).
    display_filter = "http.request or http.response"

    fields = [
        "frame.time_epoch",
        "tcp.stream",
        "ip.src",
        "tcp.srcport",
        "ip.dst",
        "tcp.dstport",

        "http.request.method",
        "http.request.uri",
        "http.request.version",
        "http.host",
        "http.request.line",

        "http.response.code",
        "http.response.phrase",
        "http.response.version",
        "http.response.line",

        "http.content_type",
        "http.content_length",
        "http.content_encoding",

        "http.file_data",
    ]

    # Pairing state: per tcp.stream queue of request ids (HTTP/1.x style).
    pending: Dict[int, Deque[_PendingReq]] = {}

    # Monotonic event id counter.
    next_seq = 0
    next_msg = 1

    def new_id() -> str:
        nonlocal next_msg
        mid = f"m{next_msg:06d}"
        next_msg += 1
        return mid

    # Write PVTS lines.
    out_f = _open_output_stream(output_path)
    must_close = out_f is not sys.stdout

    try:
        # trace_start
        _write_jsonl_line(out_f, {
            "pvts": PVTS_VERSION,
            "type": "trace_start",
            "trace_id": trace_id,
            "ts": _now_utc_iso(),
            "capture": {
                "file": os.path.basename(input_path),
                "format": "pcapng" if input_path.lower().endswith(".pcapng") else "pcap",
            },
            "tool": {
                "name": "protoview",
                "version": TOOL_VERSION,
            },
        })

        event_count = 0

        for row in _run_tshark_fields(
            verbose=verbose,
            input_path=input_path,
            display_filter=display_filter,
            fields=fields,
        ):
            # Unpack defensively
            def g(i: int) -> str:
                return row[i].strip() if i < len(row) else ""

            frame_time = g(0)
            tcp_stream_s = g(1)
            ip_src = g(2) or "0.0.0.0"
            src_port = g(3) or "0"
            ip_dst = g(4) or "0.0.0.0"
            dst_port = g(5) or "0"

            req_method = g(6)
            req_uri = g(7)
            req_ver = g(8)
            http_host = g(9)
            req_lines = g(10)

            resp_code = g(11)
            resp_phrase = g(12)
            resp_ver = g(13)
            resp_lines = g(14)

            content_type_raw = g(15)
            content_length_s = g(16)
            content_encoding = g(17)
            file_data = g(18)

            try:
                tcp_stream = int(tcp_stream_s) if tcp_stream_s else -1
            except Exception:
                tcp_stream = -1

            ts_iso = _utc_iso_from_epoch(frame_time)

            # Build src/dst endpoints for this frame (as observed).
            src_ep = {"host": ip_src, "port": int(src_port)}
            dst_ep = {"host": ip_dst, "port": int(dst_port)}

            conn_obj: Dict[str, Any] = {
                "transport": "tcp",
                "stream": max(tcp_stream, 0),
                "five_tuple": {"src": src_ep, "dst": dst_ep},
            }

            # Determine if request or response.
            is_request = bool(req_method)
            is_response = bool(resp_code)

            if is_request:
                # Request event
                eid = new_id()
                next_seq_local = next_seq
                next_seq += 1

                # Headers: from request lines, plus include Host if tshark provided it.
                headers = _parse_headers_from_lines(req_lines)
                # Ensure Host header exists (some captures may omit in request.line extraction).
                if http_host and not any(h["name"].lower() == "host" for h in headers):
                    headers.insert(0, {"name": "Host", "value": http_host})

                ev = {
                    "pvts": PVTS_VERSION,
                    "type": "event",
                    "trace_id": trace_id,
                    "id": eid,
                    "ts": ts_iso,
                    "seq": next_seq_local,
                    "kind": "http_request",
                    "summary": f"{req_method} {req_uri}".strip(),
                    "conn": conn_obj,
                    "src": src_ep,
                    "dst": dst_ep,
                    "proto": {
                        "http": {
                            "version": (req_ver or "1.1"),
                            "headers": headers,
                            "method": req_method,
                            "target": req_uri or "/",
                        }
                    },
                }

                # Track request for pairing with later response.
                if tcp_stream not in pending:
                    pending[tcp_stream] = deque()
                pending[tcp_stream].append(_PendingReq(req_id=eid, root_id=eid))

                _write_jsonl_line(out_f, ev)
                event_count += 1
                continue

            if is_response:
                # Response event
                eid = new_id()
                next_seq_local = next_seq
                next_seq += 1

                headers = _parse_headers_from_lines(resp_lines)

                # Correlate to a pending request on same tcp_stream (best-effort).
                in_resp_to: Optional[str] = None
                root: Optional[str] = None
                if tcp_stream in pending and pending[tcp_stream]:
                    pr = pending[tcp_stream].popleft()
                    in_resp_to = pr.req_id
                    root = pr.root_id

                links_obj: Dict[str, Any] = {}
                if in_resp_to:
                    links_obj["in_response_to"] = in_resp_to
                if root:
                    links_obj["root"] = root

                ct_norm = _normalize_content_type(content_type_raw)
                kind = _classify_payload_kind(content_type_raw)

                # Payload policy for first iteration:
                # - text: include file_data if present
                # - binary: include only if --display-binary-payload; else include placeholder message
                payload_obj: Dict[str, Any] = {
                    "mime": content_type_raw.strip() or None,
                    "encoding": (content_encoding.strip().lower() if content_encoding else "identity"),
                }

                cl = _safe_int(content_length_s)
                if cl is not None:
                    payload_obj["size_bytes"] = cl

                if file_data:
                    if kind == "binary" and not display_binary_payload:
                        payload_obj["data"] = "<<binary payload omitted (use --display-binary-payload)>>"
                        payload_obj["truncated"] = True
                    else:
                        payload_obj["data"] = file_data
                        payload_obj["truncated"] = False
                else:
                    # No body captured/extracted.
                    payload_obj["data"] = ""
                    payload_obj["truncated"] = False

                # Remove null-ish mime if absent (schema allows absent fields).
                if payload_obj.get("mime") is None:
                    payload_obj.pop("mime", None)

                ev = {
                    "pvts": PVTS_VERSION,
                    "type": "event",
                    "trace_id": trace_id,
                    "id": eid,
                    "ts": ts_iso,
                    "seq": next_seq_local,
                    "kind": "http_response",
                    "summary": f"{resp_code} {ct_norm or ''}".strip(),
                    "conn": conn_obj,
                    "src": src_ep,
                    "dst": dst_ep,
                    "links": links_obj if links_obj else None,
                    "proto": {
                        "http": {
                            "version": (resp_ver or "1.1"),
                            "headers": headers,
                            "status": int(resp_code),
                            "reason": resp_phrase or "",
                        }
                    },
                    "payload": payload_obj,
                }
                if ev.get("links") is None:
                    ev.pop("links", None)

                _write_jsonl_line(out_f, ev)
                event_count += 1

                # SSE sub-events (best-effort): only if text/event-stream AND file_data present AND not suppressed as binary.
                if ct_norm == "text/event-stream" and file_data:
                    # If we suppressed binary payload, we still parse nothing.
                    if not (kind == "binary" and not display_binary_payload):
                        sse_events = _parse_sse_events(file_data)
                        # Link SSE events to parent response (this response event).
                        for idx, sse in enumerate(sse_events):
                            sid = new_id()
                            next_seq_local = next_seq
                            next_seq += 1

                            sse_proto: Dict[str, Any] = {}
                            if sse.get("event"):
                                sse_proto["event"] = sse["event"]
                            if sse.get("id"):
                                sse_proto["id"] = sse["id"]
                            if sse.get("retry_ms") is not None:
                                sse_proto["retry_ms"] = sse["retry_ms"]

                            # payload for SSE: typically JSON for A2UI, but could be arbitrary text.
                            data_text = sse.get("data", "")

                            sse_payload: Dict[str, Any] = {
                                "mime": "text/event-stream",
                                "encoding": "identity",
                                "data": data_text,
                                "truncated": False,
                            }

                            links = {"parent": eid}
                            if root:
                                links["root"] = root
                            if in_resp_to:
                                # root already points to request; keep root.
                                pass

                            sev = {
                                "pvts": PVTS_VERSION,
                                "type": "event",
                                "trace_id": trace_id,
                                "id": sid,
                                "ts": ts_iso,  # best-effort: same frame timestamp (we don't have per-event ts here)
                                "seq": next_seq_local,
                                "kind": "sse_event",
                                "summary": f"SSE {sse.get('event') or 'message'}".strip(),
                                "conn": {"transport": "tcp", "stream": max(tcp_stream, 0)},
                                "src": src_ep,
                                "dst": dst_ep,
                                "links": links,
                                "proto": {"sse": sse_proto} if sse_proto else {"sse": {}},
                                "payload": sse_payload,
                            }

                            _write_jsonl_line(out_f, sev)
                            event_count += 1

                # Multipart sub-events (best-effort)
                if ct_norm.startswith("multipart/") and file_data:
                    boundary = _extract_boundary(content_type_raw)
                    if boundary:
                        parts = _split_multipart(file_data, boundary)
                        for pidx, (phdrs, pbody) in enumerate(parts):
                            pid = new_id()
                            next_seq_local = next_seq
                            next_seq += 1

                            # Determine part content-type (if present)
                            part_ct = ""
                            for h in phdrs:
                                if h["name"].lower() == "content-type":
                                    part_ct = h["value"]
                                    break
                            part_kind = _classify_payload_kind(part_ct)

                            # Payload policy for multipart part:
                            # - If binary and not allowed, omit with placeholder (and mark truncated true).
                            part_payload: Dict[str, Any] = {
                                "mime": part_ct.strip() or None,
                                "encoding": "identity",
                            }
                            if pbody:
                                if part_kind == "binary" and not display_binary_payload:
                                    part_payload["data"] = "<<binary payload omitted (use --display-binary-payload)>>"
                                    part_payload["truncated"] = True
                                    part_payload["size_bytes"] = len(pbody.encode("utf-8", errors="ignore"))
                                else:
                                    part_payload["data"] = pbody
                                    part_payload["truncated"] = False
                                    part_payload["size_bytes"] = len(pbody.encode("utf-8", errors="ignore"))
                            else:
                                part_payload["data"] = ""
                                part_payload["truncated"] = False
                                part_payload["size_bytes"] = 0

                            if part_payload.get("mime") is None:
                                part_payload.pop("mime", None)

                            links = {"parent": eid}
                            if root:
                                links["root"] = root

                            pev = {
                                "pvts": PVTS_VERSION,
                                "type": "event",
                                "trace_id": trace_id,
                                "id": pid,
                                "ts": ts_iso,
                                "seq": next_seq_local,
                                "kind": "multipart_part",
                                "summary": f"part[{pidx}] {_normalize_content_type(part_ct) or ''}".strip(),
                                "conn": {"transport": "tcp", "stream": max(tcp_stream, 0)},
                                "src": src_ep,
                                "dst": dst_ep,
                                "links": links,
                                "proto": {
                                    "multipart": {
                                        "boundary": boundary,
                                        "part_index": pidx,
                                        "part_headers": phdrs,
                                    }
                                },
                                "payload": part_payload,
                            }

                            _write_jsonl_line(out_f, pev)
                            event_count += 1

                continue

        # trace_end
        _write_jsonl_line(out_f, {
            "pvts": PVTS_VERSION,
            "type": "trace_end",
            "trace_id": trace_id,
            "ts": _now_utc_iso(),
            "stats": {"events": event_count},
        })
        return 0

    finally:
        if must_close:
            try:
                out_f.close()
            except Exception:
                pass


def cmd_analyze(args: argparse.Namespace) -> int:
    # Informational flag: print PVTS version and exit.
    if args.pvts_version:
        print(PVTS_VERSION)
        return 0

    # Enforce: --output is not allowed with --dry-run (per your requirement).
    # (We treat an explicit -o as "specified", even if it's '-', to keep it simple and strict.)
    if args.dry_run and args.output_provided:
        print("ERROR: --output cannot be used with --dry-run (dry-run prints report to stdout).", file=sys.stderr)
        return 2

    # Input defaults to stdin.
    input_path: Optional[str] = args.input
    temp_path: Optional[str] = None

    try:
        if not input_path or input_path == "-":
            temp_path = _read_stdin_to_tempfile(args.verbose, suffix=".pcapng")
            input_path = temp_path

        if args.dry_run:
            # Dry-run report
            stats = DryRunStats()
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
                    if method:
                        ep = f"{method} {uri or ''}".strip()
                        stats.endpoint_bytes[ep] += cl

            _print_dry_run_report(stats)
            return 0

        # PVTS emitter (non-dry-run)
        out_path = args.output if args.output else "-"
        return _emit_pvts(
            verbose=args.verbose,
            input_path=input_path,
            output_path=out_path,
            display_binary_payload=args.display_binary_payload,
        )

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

    an = sub.add_parser("analyze", help="Analyze a pcap/pcapng. Use --dry-run for a report, otherwise emit PVTS JSONL.")
    an.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit debug traces to stderr.",
    )
    an.add_argument(
        "--pvts-version",
        dest="pvts_version",
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
    an.add_argument(
        "--output",
        "-o",
        default="-",
        help="PVTS JSONL output file path, or '-' for stdout (default). Not allowed with --dry-run.",
    )
    an.add_argument(
        "--display-binary-payload",
        action="store_true",
        help="Include binary payload bytes in PVTS (default: omit binary payload and emit a placeholder message).",
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

    # Track whether user explicitly provided --output for analyze (to enforce the dry-run rule).
    if args.command == "analyze":
        args.output_provided = False
        for i, tok in enumerate(argv):
            if tok in ("--output", "-o"):
                args.output_provided = True
                break

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

