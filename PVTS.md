# ProtoView Trace Stream (PVTS)

## Description

**ProtoView Trace Stream (PVTS)** is a **canonical, event-oriented JSON Lines (JSONL) format** for representing **observed protocol interactions** reconstructed from packet captures (pcap/pcapng).

PVTS is designed to sit **between raw packet capture and human- or machine-facing renderers**. It captures *what happened on the wire* in a normalized, time-ordered, and navigable form, without embedding presentation concerns or relying on application-level instrumentation.

Each line in a PVTS file represents a **single semantic event** (for example, an HTTP request, an HTTP response, or an SSE data event), enriched with enough transport and protocol context to allow correlation, sequencing, and later visualization.

PVTS is **not a packet format**, **not a logging format**, and **not an API description**. It is a *trace narrative format* derived from passive observation.

---

## Objectives

PVTS is designed with the following explicit objectives:

### 1. Establish a single canonical intermediate format

PVTS serves as the **single source of truth** from which multiple representations can be generated, including:

* Markdown and plain text (for inspection and versioning)
* Sequence-diagram–style views (D3, Mermaid, Graphviz)
* PDFs or reports
* Programmatic analysis pipelines

By centralizing interpretation into PVTS, all downstream renderers remain simple, deterministic transformations.

### 2. Preserve wire-level reality while enabling semantic reconstruction

PVTS retains enough transport-level context (for example, TCP stream identifiers and directionality) to remain **auditably grounded in the packet capture**, while also recording **derived semantic relationships** (such as request–response pairing or SSE sub-events).

All higher-level links in PVTS are **explicitly marked as derived**, not claimed as wire-level truth.

### 3. Support temporal and narrative understanding

PVTS is inherently:

* **time-ordered**
* **event-based**
* **append-only**

This makes it suitable for:

* narrative reconstruction (“what happened, in what order”)
* sequence diagrams
* incremental or streaming processing

PVTS favors *narrative clarity* over exhaustive protocol detail.

### 4. Remain protocol-aware but transport-agnostic

PVTS:

* models **events**, not protocols
* allows protocol-specific fields (HTTP, SSE, multipart, etc.) to live in **clearly scoped sub-objects**
* does not hard-code assumptions about future transports

This allows PVTS to grow beyond HTTP without redesigning the core format.

### 5. Enable correlation without requiring instrumentation

PVTS does **not** depend on:

* OpenTelemetry
* W3C Trace Context
* application-generated IDs

Correlation is achieved using:

* transport context (e.g., TCP stream)
* ordering guarantees of the protocol
* analyzer-derived relationships

Optional enrichment (such as trace headers) may be included when present, but is never required.

### 6. Be friendly to both humans and machines

PVTS is intentionally:

* line-oriented (JSONL)
* grep/jq/LLM-friendly
* robust for large traces
* easy to diff and version

It is designed so that:

* humans can read it when necessary
* machines can process it reliably
* tooling can evolve independently of capture logic

---

## Non-Goals

PVTS explicitly does **not** aim to:

* replace pcap/pcapng as ground truth
* standardize all protocol fields exposed by tshark
* act as a real-time tracing system
* serve as an API contract or schema language

Those problems are intentionally left to other layers and tools.

---

## Positioning Summary

In one sentence:

> **PVTS is a structured, event-stream representation of observed protocol interactions, designed to bridge packet capture and narrative visualization without conflating capture, interpretation, or presentation.**

---

## PVTS 0.1 JSON Schema

Below is a **PVTS 0.1 JSON Schema** for a single line (record). It covers:

* `trace_start`
* `event` (HTTP request/response, SSE event, multipart part)
* `trace_end`

It is deliberately **small and extensible**:

* top-level structure is controlled (`additionalProperties: false`)
* protocol-specific content lives under `proto` and `payload`, where we allow controlled extensibility

[PVTS 0.1 Schema](./pvts-0.1.schema.json)

## Notes you should adopt as policy (not code)

* **JSONL validation**: validate each line against this schema.
* **Comments**: use `$comment` + `description`. That’s the standards-compliant way.
* **Extensibility**: PVTS 0.1 is intentionally minimal. PVTS 0.2 can add kinds (websocket, grpc, dns), and expand `conn` beyond TCP.

---

## PVTS 0.1 JSONL examples

### Simple Example

Here is a **minimal, clean PVTS 0.1 example** for a **simple HTTP request + response** (no SSE, no multipart).

This is the smallest useful unit that still demonstrates request/response correlation.

[PVTS 0.1 SIMPLE HTTP Example](./pvts-0.1.simple-http.example.jsonl)

## Why this example is important

* Shows **ordering** via `seq`
* Shows **correlation** via `links.in_response_to`
* Uses **tcp.stream** as the transport anchor
* Keeps payload simple and readable
* Validates cleanly against the PVTS 0.1 schema

This is the canonical “hello world” for PVTS.

### Multipart Example

Here’s a **minimal PVTS 0.1 multipart example** as JSONL. It includes:

* `trace_start`
* one HTTP request
* one HTTP response with `Content-Type: multipart/mixed; boundary=...`
* two `multipart_part` sub-events, each linked to the response (parent) and request (root)
* `trace_end`

[PVTS 0.1 MULTIPART Example](./pvts-0.1.multipart.example.jsonl)

* The **multipart response is one HTTP response** (`m010002`).
* Each multipart part is modeled as a **child event** (`multipart_part`) linked via:

  * `links.parent = m010002`
  * `links.root = m010001`
* The response payload body is empty here on purpose; the parts carry the actual content. That keeps the model clean and avoids duplication.

### SSE Example

This contains

* `trace_start`
* one HTTP request
* one HTTP response establishing an SSE stream (`text/event-stream`)
* two SSE events as separate JSONL records linked to the response (and root request)
* `trace_end`

[PVTS 0.1 SSE Example](./pvts-0.1.sse.example.jsonl)

* Every record includes `pvts: "0.1"`.
* Each `event` has required: `trace_id`, `id`, `ts`, `kind`, `conn`, `src`, `dst`.
* HTTP request includes `proto.http.method` and `proto.http.target` as required by the conditional schema.
* HTTP response includes `proto.http.status` as required.
* SSE events use `kind: "sse_event"` and include `payload.data` containing the event JSON body.
* Links:
  * Response links to request using `links.in_response_to`.
  * SSE events link to the response using `links.parent`, and to the request with `links.root`.

---

## PVTS Indexing Logic

### Goal

From PVTS JSONL (events), produce a **sequence index**: one line per “message” that looks like a sequence diagram transcript and can link to details (by `id`).

The sequence index is not “truth”; it’s a **view** over PVTS.

---

### Step 0: Define what counts as a “sequence row”

For PVTS 0.1, treat these `kind` values as sequence rows:

* `http_request`
* `http_response`
* `sse_event`
* `multipart_part`

Later you can add kinds without changing the pipeline.

---

### Step 1: Read PVTS JSONL line-by-line

For each line:

* parse JSON
* ignore records where `type != "event"`
* keep only events with `kind` in the allowed list

Rationale: metadata lines shouldn’t pollute the sequence.

---

### Step 2: Choose ordering

Prefer stable ordering in this priority:

1. if `seq` exists, sort by `seq` ascending
2. else sort by `ts` ascending
3. tie-breaker: original file line order

Why:

* `seq` is the analyzer’s monotonic index (best)
* timestamps can collide or be too coarse
* file order is a safe final tie-breaker

---

### Step 3: Derive participants for each row

For each event, compute the “from → to” fields:

* `from = src.name if present else "{src.host}:{src.port}"`
* `to   = dst.name if present else "{dst.host}:{dst.port}"`

This is what creates lanes in Mermaid/D3 later too.

---

### Step 4: Derive a concise label (the human-facing part)

Use this decision tree (PVTS-friendly, renderer-stable):

#### If `summary` exists and is non-empty:

* use it verbatim as the label

Otherwise derive from protocol fields:

#### For `http_request`

* label = `"{method} {target}"`

  * from `proto.http.method` and `proto.http.target`

#### For `http_response`

* label = `"{status} {content_type_short}"`

  * status from `proto.http.status`
  * content_type_short from first `Content-Type` header if present, else `"(no content-type)"`

#### For `sse_event`

* label = `"SSE {event or 'message'}"`

  * from `proto.sse.event` if present

#### For `multipart_part`

* label = `"part[{part_index}] {content_type_short}"`

  * from `proto.multipart.part_index` and `proto.multipart.part_headers`

Keep it short. The details section carries the full payload.

---

### Step 5: Include linkable ID token

Each sequence row must include the PVTS event `id` as a plain word token (e.g., `m000123`).

This enables:

* Vim search/jump
* Markdown anchors
* ctags (optional)

Do not prefix it with `#` or punctuation if you want Vim word-jumps to behave well.

---

### Step 6: Produce the final sequence index line format

Pick one stable line grammar and never change it lightly.

A good minimal grammar:

```
{nn} {id} {from} -> {to}  {label}
```

Where:

* `{nn}` is the row number in the sequence index (01, 02, …), not necessarily the same as `seq`
* `{id}` is the PVTS event id
* `{from}`, `{to}` are participants
* `{label}` is from Step 4

Example:

```
01 m000001 Client -> Server  GET /health
02 m000002 Server -> Client  200 application/json
```

For SSE:

```
03 m000003 Server -> Client  SSE surfaceUpdate
```

For multipart:

```
04 m010003 Server -> Client  part[0] application/json
```

---

### Step 7: (Optional) show hierarchy without breaking the grammar

If you want “close to sequence diagram” *and* want to show parent/child:

Use indentation only for events that have `links.parent`, but still keep the same tokens:

* parentless events: no indent
* child events: indent by two spaces (or a single tab)

Example:

```
01 m000001 Client -> Server  GET /events
02 m000002 Server -> Client  200 text/event-stream
  03 m000003 Server -> Client  SSE surfaceUpdate
  04 m000004 Server -> Client  SSE beginRendering
```

This is readable and machine-parseable.

---

### Step 8: Validate that every sequence row can jump to details

Your Markdown details section should have headings like:

* `## m000001`
* `## m000002`

So the sequence line’s `{id}` always corresponds to a definition anchor.

That’s the “ctags-like” property.

---

### Step 9: Decide what you will NOT include in sequence lines

Be strict:

Do not include in the sequence index:

* headers
* bodies
* long URLs
* multi-line text

Otherwise the index becomes unusable.

---

### Step 10: Make it future-proof

This logic remains stable if later you add:

* WebSockets: new `kind`, new label derivation
* HTTP/2: still `http_request`/`http_response`, with different correlation under the hood
* “agents” messages: new `kind`

Renderers don’t change; they follow the same steps.

---

#### Summary of the algorithm in one sentence

Parse PVTS events → order them (`seq`/`ts`) → format each as `{id} src→dst label` → optionally indent children using `links.parent` → emit as a stable, scan-friendly index that links to per-event detail sections.


