# ingester.py

Reads source documents, splits them into overlapping text chunks, tags each
chunk with a Bloom taxonomy level, and writes `chunks.jsonl` + `manifest.json`.

## Requirements

Install dependencies (only needed for PDF mode):

```bash
pip install -r requirements.txt
```

C mode needs only the standard library — no extra packages.

## Usage

```bash
python3 ingester.py <input_dir> <output_dir> [--mode {pdf,c}] [options]
```

### Modes (`--mode`)

| Mode  | Globs                              | Extraction                              |
|-------|------------------------------------|------------------------------------------|
| `pdf` | `*.pdf`                            | pypdf + optional Tesseract OCR fallback   |
| `c`   | `*.c`, `*.h`, `*.txt`              | Read as UTF-8 text (no parsing)           |

Default is `pdf`. Use `c` for C source files or plain text.

### Examples

Ingest a folder of PDFs:

```bash
python3 ingester.py docs ingested
```

Ingest C source files:

```bash
python3 ingester.py src ingested --mode c
```

Adjust chunking:

```bash
python3 ingester.py src ingested --mode c --chunk-size 800 --overlap 0
```

### Options

| Flag             | Default | Description                                   |
|------------------|---------|-----------------------------------------------|
| `--mode`         | `pdf`   | Input type: `pdf` or `c`                      |
| `--chunk-size`   | `1200`  | Characters per chunk                          |
| `--overlap`      | `150`   | Characters of overlap between adjacent chunks |

## Output

- `chunks.jsonl` — one JSON chunk per line, with `chunk_id`, `text`, Bloom
  labels, and source offsets.
- `manifest.json` — run metadata, per-document summary, and any errors.

## As a library

```python
from pathlib import Path
from ingester import ingest, classify_bloom, extract_c_source

ingest(Path("src"), Path("ingested"), mode="c")
```

`ingest()` exits `0` on success, `1` if any file failed. Individual failures
are logged and captured in `manifest.json["errors"]`; the run continues.

## Notes

- Bloom labels are heuristic action-verb matches — review before research use.
- PDF mode honors `OCR_THRESHOLD` and runs Tesseract on low-text pages only.
- C mode performs no syntax parsing; chunks are fixed-size text windows. Add
  an AST-based splitter if you need function-granular chunks.
