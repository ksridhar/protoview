## ProtoView Trace Stream (PVTS)

### Description

**ProtoView Trace Stream (PVTS)** is a **canonical, event-oriented JSON Lines (JSONL) format** for representing **observed protocol interactions** reconstructed from packet captures (pcap/pcapng).

PVTS is designed to sit **between raw packet capture and human- or machine-facing renderers**. It captures *what happened on the wire* in a normalized, time-ordered, and navigable form, without embedding presentation concerns or relying on application-level instrumentation.

Each line in a PVTS file represents a **single semantic event** (for example, an HTTP request, an HTTP response, or an SSE data event), enriched with enough transport and protocol context to allow correlation, sequencing, and later visualization.

PVTS is **not a packet format**, **not a logging format**, and **not an API description**. It is a *trace narrative format* derived from passive observation.

---

### Objectives

PVTS is designed with the following explicit objectives:

#### 1. Establish a single canonical intermediate format

PVTS serves as the **single source of truth** from which multiple representations can be generated, including:

* Markdown and plain text (for inspection and versioning)
* Sequence-diagram–style views (D3, Mermaid, Graphviz)
* PDFs or reports
* Programmatic analysis pipelines

By centralizing interpretation into PVTS, all downstream renderers remain simple, deterministic transformations.

---

#### 2. Preserve wire-level reality while enabling semantic reconstruction

PVTS retains enough transport-level context (for example, TCP stream identifiers and directionality) to remain **auditably grounded in the packet capture**, while also recording **derived semantic relationships** (such as request–response pairing or SSE sub-events).

All higher-level links in PVTS are **explicitly marked as derived**, not claimed as wire-level truth.

---

#### 3. Support temporal and narrative understanding

PVTS is inherently:

* **time-ordered**
* **event-based**
* **append-only**

This makes it suitable for:

* narrative reconstruction (“what happened, in what order”)
* sequence diagrams
* incremental or streaming processing

PVTS favors *narrative clarity* over exhaustive protocol detail.

---

#### 4. Remain protocol-aware but transport-agnostic

PVTS:

* models **events**, not protocols
* allows protocol-specific fields (HTTP, SSE, multipart, etc.) to live in **clearly scoped sub-objects**
* does not hard-code assumptions about future transports

This allows PVTS to grow beyond HTTP without redesigning the core format.

---

#### 5. Enable correlation without requiring instrumentation

PVTS does **not** depend on:

* OpenTelemetry
* W3C Trace Context
* application-generated IDs

Correlation is achieved using:

* transport context (e.g., TCP stream)
* ordering guarantees of the protocol
* analyzer-derived relationships

Optional enrichment (such as trace headers) may be included when present, but is never required.

---

#### 6. Be friendly to both humans and machines

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

### Non-Goals

PVTS explicitly does **not** aim to:

* replace pcap/pcapng as ground truth
* standardize all protocol fields exposed by tshark
* act as a real-time tracing system
* serve as an API contract or schema language

Those problems are intentionally left to other layers and tools.

---

### Positioning Summary

In one sentence:

> **PVTS is a structured, event-stream representation of observed protocol interactions, designed to bridge packet capture and narrative visualization without conflating capture, interpretation, or presentation.**

---

### PVTS 0.1 JSON Schema

Below is a **PVTS 0.1 JSON Schema** for a single line (record). It covers:

* `trace_start`
* `event` (HTTP request/response, SSE event, multipart part)
* `trace_end`

It is deliberately **small and extensible**:

* top-level structure is controlled (`additionalProperties: false`)
* protocol-specific content lives under `proto` and `payload`, where we allow controlled extensibility

[PVTS 0.1 Schema](./pvts-0.1.schema.json)

### Notes you should adopt as policy (not code)

* **JSONL validation**: validate each line against this schema.
* **Comments**: use `$comment` + `description`. That’s the standards-compliant way.
* **Extensibility**: PVTS 0.1 is intentionally minimal. PVTS 0.2 can add kinds (websocket, grpc, dns), and expand `conn` beyond TCP.

---

### PVTS 0.1 JSONL file

#### Simple Example

Here is a **minimal, clean PVTS 0.1 example** for a **simple HTTP request + response** (no SSE, no multipart).

This is the smallest useful unit that still demonstrates request/response correlation.

[PVTS 0.1 SIMPLE HTTP Example](./pvts-0.1.simple-http.example.jsonl)

### Why this example is important

* Shows **ordering** via `seq`
* Shows **correlation** via `links.in_response_to`
* Uses **tcp.stream** as the transport anchor
* Keeps payload simple and readable
* Validates cleanly against the PVTS 0.1 schema

This is the canonical “hello world” for PVTS.

#### Multipart Example

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

#### SSE Example

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

