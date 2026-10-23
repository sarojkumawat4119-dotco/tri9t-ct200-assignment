# Approach Document — Tri9T AI CT-200 Assignment

## 1. Summary

The service ingests the supplied CT-200 PDFs, reconstructs a numbered section tree, stores immutable document versions, pins selections to the source version and text snapshot, generates 3–5 structured QA ideas, and exposes source staleness during retrieval. The supplied `IMPORTANT_ASSIGNMENT_UPDATE` explicitly says to parse the PDFs rather than a Markdown file.

## 2. Inspection findings and extraction strategy

Both supplied PDFs have selectable text layers (6 pages in v1 and 7 pages in v2), so the primary extractor is PyMuPDF. Tesseract is a fallback for pages where extracted text is nearly empty; this avoids degrading good text-layer output by OCRing everything. The parser normalizes ligatures (for example, `ﬁ`), retains page start/end metadata, preserves line breaks inside section bodies, and computes a normalized text hash. A no-text result raises an error rather than silently returning an empty tree.

The parser is deliberately specific to this document. Numbered headings are recognized using a heading pattern, a top-level sequence guard prevents common numbered classification list items from becoming document sections, and parent assignment uses the nearest existing numeric prefix. Missing intermediate headings are not fabricated. Paragraph/list/table lines are preserved as source text in the owning section; table rows are line-oriented text rather than a fully reconstructed grid.

### Structural inconsistencies observed in the actual PDFs

- The heading `2.1.1.1 Battery Life Under Typical Use` jumps from `2.1` to `2.1.1.1`; there is no `2.1.1` heading. The parser attaches it to the nearest existing ancestor (`2.1`) without inventing a node.
- Section `3.4 Auto Shutoff` appears before `3.3 Result Display and Classification`. Both are retained as siblings under section 3 rather than reordered or dropped.
- `Error Codes` appears in both `4.2` and `7.1`. These are distinct nodes with distinct parents and section numbers.
- Section 3.1 has a sentence split by a page boundary; extraction retains both clauses.
- The specifications and error-code tables are extracted as line-oriented text. Column geometry is not reliably available in the flattened text layer, so a typed cell grid is not claimed. `pdfimages -list` reported no embedded raster images in v1; the current parser therefore has no figure/image-caption nodes. Any vector figures would need separate visual inspection.
- The v2 PDF changes requirements and adds content. Examples verified by text comparison include battery cycles from 300 to 250, low-battery threshold from 15% to 10%, inflation increments from 40 to 30 mmHg, E3 auto-deflation from 2 seconds to 1.5 seconds, E6 Bluetooth sync failure, and new section 5.3 Data Export. Section 4.3 also changes the E1–E5 reference to E1–E6.
- Page reflow differs between v1 and v2, including different page count and line/page boundaries. Hash normalization collapses whitespace to avoid treating only line wrapping as a content change.

## 3. Data model

- `Document`: stable identity for the CT-200 manual.
- `DocumentVersion`: immutable version number, filename, SHA-256 of PDF bytes, timestamp.
- `Node`: database ID for one node in one version, stable `logical_id` across matched versions, parent ID, heading/number/level/body, page span, node type, normalized content hash.
- `Selection`: named saved selection.
- `SelectionItem`: node and version IDs plus logical ID, hash, heading and exact source text snapshot.
- JSON generation record: unique generation ID, selection ID, source node/version/hash/snapshot, provider/model, generated cases, timestamp.

SQL stores the browsable tree and selections. JSON is the chosen NoSQL-style output store because the assignment data volume is small and JSON keeps generated records inspectable without requiring a local MongoDB service. Atomic replacement avoids partially written files, but the approach is not a multi-writer database and is documented as a production limitation.

## 4. Version matching and staleness

A logical node is matched by section number + normalized heading + ancestor path. Body hash is intentionally excluded from identity, so an edited requirement can retain the same logical ID and be flagged as changed. Version records and selection snapshots are immutable. An identical PDF SHA-256 does not create a duplicate version.

At retrieval time, every source node is matched to the latest version by logical ID. If no match exists, status is `removed_or_unmatched`; if the hash differs, status is `changed`; otherwise it is `unchanged`. Generation retrieval exposes both generation-level and per-test-case staleness based on each case's cited source node IDs. Node change responses include a token-level unified diff preview. This is conservative source-change detection, not clinical impact analysis. A spelling change and a threshold change both set the stale flag; the API says so explicitly. A later improvement would classify changes by domain-aware numeric/negation/unit deltas and link each generated case to the exact source spans it covers.

Known matching failure modes: renumbering, renamed headings, moved sections, duplicate identical heading paths, and restructured hierarchies may appear as a removal plus a new node. Repeated identical keys are matched by occurrence order, which is simple but can mismatch nodes if their order changes. A production matcher should combine layout context, text similarity, table/figure identifiers, and reviewer-confirmed match decisions.

## 5. LLM prompt and malformed-output strategy

The prompt asks for 3–5 executable test ideas grounded only in the selected text, with preconditions, steps, observable expected results, severity, and source node IDs. It instructs the model not to invent unspecified requirements or claim regulatory compliance. Pydantic validates shape and bounds, and source IDs are checked against the selection. A malformed output triggers one correction attempt with the validation error; after two failed attempts the API returns 502 and does not persist invalid output. If no provider key is configured, a clearly labelled deterministic fallback keeps the end-to-end workflow testable; it is not presented as an LLM result.

Duplicate submission policy: each generation request creates a new immutable generation ID. This supports auditability and allows comparing model outputs across repeated runs. The service does not silently return cached output; an explicit idempotency key could be added if a caller needs retry-safe request semantics.

## 6. Validation and tests

Automated tests use the actual supplied PDFs and check: duplicate Error Codes headings have different parents; the missing intermediate number is not fabricated; out-of-order 3.4/3.3 sections are retained; a page-split paragraph is not lost; v1/v2 content changes alter hashes and new section 5.3 is present; table rows remain separate lines. `pytest -q` is the validation command. For manual validation, compare section headings and changed numeric requirements against `pdftotext -layout` output and visually inspect PDF pages when OCR is used or table fidelity matters.

## 7. Required decision log

1. **Most likely silent wrong result:** a numbered list item or table row being misclassified as a heading, producing a plausible but wrong tree. Catch it with heading-count/number-sequence reports, parent-child invariants, source-page excerpts per heading, and visual comparison of every detected heading against the PDF.
2. **Where simplicity beat correctness:** table extraction preserves rows as text rather than reconstructing cell geometry, and logical matching uses numbering/path instead of a semantic matcher. Production would first fail on complex tables, renumbered sections, or substantial reorganization; it needs review queues and richer layout-aware matching.
3. **Unhandled input:** a multi-column scanned page with no text layer and poor OCR may produce incorrect reading order. OCR is attempted for low-text pages, but if the resulting content is nonempty yet wrong, the current parser cannot guarantee detection; manual visual QA is required. This is a known limitation, not claimed as solved.

## 8. What I would improve with more time

- Add bounding-box/font-size layout analysis and explicit heading confidence scores.
- Use OCR confidence and compare OCR against native text, with a review queue for uncertain pages.
- Reconstruct tables into typed row/cell structures and preserve figure crops/captions.
- Add semantic impact labels for numeric thresholds, units, negation, timing and safety terms, with human review rather than automatic approval.
- Use MongoDB or another transactional store for concurrent generation writes, plus request idempotency keys and structured logs.
- Add property-based tests, golden extracted-tree fixtures, and a PDF visual diff report.
