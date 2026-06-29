# ingester.py

Chunks PDFs or C/text files and tags each chunk with a Bloom taxonomy level.

## Usage

```bash
python3 ingester.py <input_dir> <output_dir> [--mode {pdf,c,txt}] [options]
```

### Modes

| Mode  | Globs                 | Extraction                            |
|-------|-----------------------|---------------------------------------|
| `pdf` | `*.pdf`               | pypdf + optional Tesseract OCR        |
| `c`   | `*.c`, `*.h`, `*.txt` | Read as UTF-8 text                    |
| `txt` | `*.txt`               | Read as UTF-8 text                    |

### Flags

| Flag           | Default | Description                                          |
|----------------|---------|------------------------------------------------------|
| `--mode`       | `pdf`   | Input type: `pdf`, `c`, or `txt`                     |
| `--chunk-size` | `1200`  | Characters per chunk                                 |
| `--overlap`    | `150`   | Overlap between adjacent chunks                      |
| `--csv`        | off     | Also write `chunks.csv` + `documents.csv`            |

### Examples

```bash
python3 ingester.py docs ingested
python3 ingester.py src ingested --mode c
python3 ingester.py text ingested --mode txt --csv
```

### Modes

| Mode  | Globs                 | Extraction                            |
|-------|-----------------------|---------------------------------------|
| `pdf` | `*.pdf`               | pypdf + optional Tesseract OCR        |
| `c`   | `*.c`, `*.h`, `*.txt` | Read as UTF-8 text                    |

### Flags

| Flag           | Default | Description                                          |
|----------------|---------|------------------------------------------------------|
| `--mode`       | `pdf`   | Input type: `pdf` or `c`                             |
| `--chunk-size` | `1200`  | Characters per chunk                                 |
| `--overlap`    | `150`   | Overlap between adjacent chunks                      |
| `--csv`        | off     | Also write `chunks.csv` + `documents.csv`            |

### Examples

```bash
python3 ingester.py docs ingested
python3 ingester.py src ingested --mode c
python3 ingester.py src ingested --mode c --csv
```

### Output

- `chunks.jsonl` — one JSON chunk per line (`chunk_id`, `text`, Bloom labels, offsets).
- `manifest.json` — run metadata, per-document summary, errors.
- `chunks.csv` / `documents.csv` — one row per chunk / document (only with `--csv`).
