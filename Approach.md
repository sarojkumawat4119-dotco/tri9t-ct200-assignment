# CT-200 Document Intelligence — Technical Approach

## 1. Objective

Build a document intelligence system that extracts structured requirements from CT-200 PDF versions, identifies changes between versions, supports pinned requirement selections, generates test cases using an LLM, and exposes requirement-change impact through REST APIs.

## 2. Technology Stack

- **Python:** Core application logic
- **FastAPI:** REST API and interactive Swagger documentation
- **Pydantic:** Request and response validation
- **SQLAlchemy and SQLite:** Persistent storage
- **PyMuPDF:** PDF text extraction
- **LLM API:** Test-case generation
- **Pytest:** Automated testing

## 3. Document Ingestion

The system accepts PDF documents and extracts their textual content. Extracted content is processed to identify headings, sections, requirement text, and relevant table content. The goal is to preserve document hierarchy and retain traceability to the source document.

## 4. Versioning and Change Detection

Each ingested document is associated with a version. Requirements are represented as structured nodes with identifiers and relationships to their parent sections. Nodes across document versions are compared to identify additions, modifications, and removals. Logical matching should account for numbering changes and repeated headings without incorrectly merging distinct requirements.

## 5. Pinned Selections

Users can select and persist requirement nodes for later use. Selections retain references to their source requirements so that subsequent document changes can be evaluated against the selected content.

## 6. LLM-Based Test-Case Generation

The generation workflow uses requirement context to produce structured test cases. Responses should be validated against the expected schema, with retry handling for invalid responses. API credentials are supplied through environment variables and must not be committed to version control.

## 7. Staleness and Impact Analysis

Generated test cases are associated with their source requirement nodes. When a requirement changes, the system can identify potentially stale generated cases and expose relevant change information through its API.

## 8. API and Persistence

FastAPI exposes endpoints for document ingestion, requirement retrieval, searching, version comparison, selections, and test-case generation. SQLAlchemy and SQLite provide persistence for application records.

## 9. Testing

Pytest covers document-structure reconstruction, numbering gaps, out-of-order headings, split paragraphs, table extraction, and version-change scenarios. Additional tests should cover API validation, generation failures, and persistence where applicable.

## 10. Security and Configuration

Local environment secrets belong in `.env`, which must be excluded from Git. The committed `.env.example` should contain placeholder values only. Dependencies are listed in `requirements.txt`.

## 11. Limitations and Future Improvements

PDF extraction and logical requirement matching may require refinement for complex layouts and ambiguous wording. Further improvements could include richer semantic matching, stronger LLM output validation, broader API integration tests, and more detailed change-impact explanations.
