#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

from pypdf import PdfReader


logger = logging.getLogger(__name__)


BLOOM_VERBS: dict[str, list[str]] = {
    "remember": [
        # Identify / recall facts, terms, basic concepts
        "define", "list", "name", "identify", "recall", "recognize",
        "state", "label", "match", "select", "reproduce", "enumerate",
        "describe", "outline", "record", "repeat", "quote", "memorize",
        "tell", "locate", "choose",
    ],
    "understand": [
        # Demonstrate comprehension / interpretation
        "explain", "discuss", "summarize", "paraphrase", "restate",
        "interpret", "classify", "compare", "contrast", "illustrate",
        "give examples", "example", "estimate", "extend", "generalize",
        "infer", "predict", "report", "review", "translate", "show",
        "clarify",
    ],
    "apply": [
        # Use knowledge in new but structured situations
        "apply", "use", "implement", "execute", "solve", "compute",
        "calculate", "determine", "demonstrate", "operate", "practice",
        "simulate", "sketch", "complete", "modify", "change", "manipulate",
        "organize", "schedule", "prepare", "produce", "employ", "utilize",
        "experiment", "model",
    ],
    "analyze": [
        # Break material into parts, see relationships and structure
        "analyze", "examine", "inspect", "investigate", "differentiate",
        "distinguish", "discriminate", "compare", "contrast",
        "categorize", "classify", "organize", "structure", "arrange",
        "deconstruct", "diagram", "dissect", "divide", "separate",
        "relate", "survey", "test", "question", "diagnose",
    ],
    "evaluate": [
        # Make judgments based on criteria
        "evaluate", "assess", "appraise", "judge", "critique", "criticize",
        "recommend", "justify", "argue", "defend", "support", "debate",
        "conclude", "consider", "decide", "discriminate", "measure",
        "rank", "rate", "grade", "score", "review", "validate", "verify",
        "test", "check",
    ],
    "create": [
        # Put elements together; generate new patterns or products
        "create", "design", "develop", "plan", "construct", "compose",
        "formulate", "produce", "build", "generate", "devise", "assemble",
        "collect", "combine", "compile", "configure", "hypothesize",
        "invent", "make", "model", "organize", "prepare", "propose",
        "rearrange", "reconstruct", "reorganize", "revise", "rewrite",
        "synthesize", "specify",
    ],
}


OCR_THRESHOLD = 100


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages_pypdf = []
    low_text_page_nums = []

    for page_num, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        pages_pypdf.append((page_num, text))
        if len(text) < OCR_THRESHOLD:
            low_text_page_nums.append(page_num)

    ocr_map: dict[int, str] = {}
    if low_text_page_nums and pytesseract is not None and convert_from_path is not None:
        try:
            images = convert_from_path(str(pdf_path), fmt="jpeg", use_cropbox=False)
            for page_num in low_text_page_nums:
                idx = page_num - 1
                if idx < len(images):
                    ocr_result = pytesseract.image_to_string(images[idx]).strip()
                    if len(ocr_result) > len(pages_pypdf[idx][1]):
                        ocr_map[page_num] = ocr_result
        except Exception:
            pass

    pages_text = []
    for page_num, text in pages_pypdf:
        if page_num in ocr_map:
            text = ocr_map[page_num]
        pages_text.append(f"[Page {page_num}]\n{text}")

    return "\n\n".join(pages_text)


# ponytail: these inputs are already text — read as UTF-8, no parse step needed.
TEXT_MODE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "c": (".c", ".h", ".txt"),
    "txt": (".txt",),
}


def extract_c_source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _discover_sources(input_path: Path, mode: str) -> list[Path]:
    if mode in TEXT_MODE_EXTENSIONS:
        files = []
        for ext in TEXT_MODE_EXTENSIONS[mode]:
            files.extend(input_path.rglob(f"*{ext}"))
        return sorted(files)
    return sorted(input_path.rglob("*.pdf"))


def chunk_text(
    text: str, chunk_size: int, overlap: int,
) -> list[dict]:
    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_str = text[start:end]
        suffix = _sha256(chunk_str.encode())[:12]
        chunks.append({
            "chunk_index": index,
            "start_char": start,
            "end_char": end,
            "text": chunk_str,
            "chunk_id_suffix": suffix,
        })
        index += 1
        if end == len(text):
            break
        step = chunk_size - overlap
        if step < 1:
            step = 1
        start += step

    return chunks


def classify_bloom(text: str) -> dict:
    scores: dict[str, int] = {}
    cues: dict[str, list[str]] = {}

    for level, verbs in BLOOM_VERBS.items():
        matched = set()
        for verb in verbs:
            # ponytail: crude suffix catch for common inflections (s/es/ing/ed/ies etc.)
            base = re.escape(verb)
            pattern = rf"\b{base}(?:s|es|ing|ed|d|ies|ied|ying)?\b"
            if re.search(pattern, text, re.IGNORECASE):
                matched.add(verb.lower())
        scores[level] = len(matched)
        cues[level] = sorted(matched)

    bloom_levels = [level for level, count in scores.items() if count > 0]
    total_cues = sum(scores.values())

    if not bloom_levels:
        primary = "uncategorized"
    elif total_cues <= 1:
        primary = "weakly labelled"
    else:
        max_score = max(scores.values())
        primary: str = max(
            (level for level, count in scores.items() if count == max_score),
            key=lambda l: max(v == max_score for v in [scores[l]]),
        )

    return {
        "bloom_levels": bloom_levels,
        "bloom_primary_level": primary,
        "bloom_scores": scores,
        "bloom_cues": cues,
    }


def ingest(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 1200,
    overlap: int = 150,
    mode: str = "pdf",
    write_csv: bool = False,
) -> int:
    if mode not in ("pdf", "c", "txt"):
        raise ValueError(f"unknown mode: {mode!r} (expected 'pdf', 'c', or 'txt')")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = _discover_sources(input_path, mode)
    manifest_documents: list[dict] = []
    all_chunks: list[dict] = []
    errors: list[dict] = []
    total_chunks = 0

    for src_path in source_paths:
        try:
            file_bytes = src_path.read_bytes()
            doc_id = _sha256(file_bytes)[:16]
            source_name = src_path.name
            source_rel = str(src_path)

            if mode in ("c", "txt"):
                text = extract_c_source(src_path)
            else:
                text = extract_text(src_path)
            char_count = len(text)

            chunks = chunk_text(text, chunk_size, overlap)
            level_counter: dict[str, int] = Counter()
            chunk_entries: list[dict] = []

            for chunk in chunks:
                bloom = classify_bloom(chunk["text"])
                for level in BLOOM_VERBS:
                    level_counter[level] += bloom["bloom_scores"].get(level, 0)

                bloom_scores = bloom["bloom_scores"]
                chunk_id = (
                    f"{doc_id}-{chunk['chunk_index']:05d}"
                    f"-{chunk['chunk_id_suffix']}"
                )

                entry = {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "source_path": source_rel,
                    "source_name": source_name,
                    "chunk_index": chunk["chunk_index"],
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "bloom_levels": bloom["bloom_levels"],
                    "bloom_primary_level": bloom["bloom_primary_level"],
                    "bloom_scores": bloom_scores,
                    "bloom_cues": bloom["bloom_cues"],
                    "text": chunk["text"],
                }
                chunk_entries.append(entry)
                all_chunks.append(entry)
                total_chunks += 1

            bloom_levels_present = [
                level for level in BLOOM_VERBS if level_counter[level] > 0
            ]
            if bloom_levels_present:
                primary_doc_level = max(
                    bloom_levels_present, key=lambda l: level_counter[l]
                )
            else:
                primary_doc_level = "uncategorized"

            doc_entry = {
                "document_id": doc_id,
                "source_path": source_rel,
                "source_name": source_name,
                "extension": src_path.suffix,
                "sha256": _sha256(file_bytes),
                "char_count": char_count,
                "bloom_levels": bloom_levels_present,
                "bloom_primary_level": primary_doc_level,
                "bloom_scores": dict(level_counter),
            }
            manifest_documents.append(doc_entry)
            logger.info(
                "Processed %s (%d chars, %d chunks)",
                source_name, char_count, len(chunks),
            )

        except Exception as exc:
            logger.error("Failed to process %s: %s", src_path, exc)
            errors.append({"path": str(src_path), "error": str(exc)})

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "mode": mode,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "bloom_taxonomy": {
            "levels": list(BLOOM_VERBS.keys()),
            "method": "heuristic_action_verb_match",
            "note": (
                "Bloom labels are inferred from action-verb cues and "
                "should be reviewed before use as research annotations."
            ),
        },
        "document_count": len(manifest_documents),
        "chunk_count": total_chunks,
        "error_count": len(errors),
        "documents": manifest_documents,
        "errors": errors,
    }

    chunks_path = output_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for entry in all_chunks:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if write_csv:
        bloom_levels_order = list(BLOOM_VERBS.keys())

        chunks_csv_path = output_dir / "chunks.csv"
        with chunks_csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "chunk_id", "document_id", "source_name", "source_path",
                "chunk_index", "start_char", "end_char",
                "bloom_primary_level", "bloom_levels",
                *[f"bloom_score_{lvl}" for lvl in bloom_levels_order],
                "bloom_cues", "text",
            ])
            for entry in all_chunks:
                scores = entry["bloom_scores"]
                writer.writerow([
                    entry["chunk_id"], entry["document_id"],
                    entry["source_name"], entry["source_path"],
                    entry["chunk_index"], entry["start_char"], entry["end_char"],
                    entry["bloom_primary_level"],
                    ";".join(entry["bloom_levels"]),
                    *[scores.get(lvl, 0) for lvl in bloom_levels_order],
                    json.dumps(entry["bloom_cues"], ensure_ascii=False),
                    entry["text"],
                ])

        docs_csv_path = output_dir / "documents.csv"
        with docs_csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "document_id", "source_name", "source_path", "extension",
                "sha256", "char_count", "bloom_primary_level", "bloom_levels",
                *[f"bloom_score_{lvl}" for lvl in bloom_levels_order],
            ])
            for doc in manifest_documents:
                scores = doc["bloom_scores"]
                writer.writerow([
                    doc["document_id"], doc["source_name"], doc["source_path"],
                    doc["extension"], doc["sha256"], doc["char_count"],
                    doc["bloom_primary_level"],
                    ";".join(doc["bloom_levels"]),
                    *[scores.get(lvl, 0) for lvl in bloom_levels_order],
                ])

        logger.info("CSV tables written: chunks.csv, documents.csv")

    logger.info(
        "Ingestion complete: %d documents, %d chunks, %d errors",
        len(manifest_documents), total_chunks, len(errors),
    )

    return 1 if errors else 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest PDFs or C/text files into chunks.jsonl + manifest.json.",
    )
    parser.add_argument("input_dir", type=Path, help="Directory of source files.")
    parser.add_argument("output_dir", type=Path, help="Where to write chunks.jsonl and manifest.json.")
    parser.add_argument(
        "--mode", choices=("pdf", "c", "txt"), default="pdf",
        help="Input type: 'pdf' globs *.pdf; 'c' globs *.c, *.h, *.txt; 'txt' globs *.txt (the latter two read as UTF-8 text).",
    )
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=150)
    parser.add_argument(
        "--csv", dest="write_csv", action="store_true",
        help="Also write chunks.csv and documents.csv (one row per chunk / document).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(ingest(
        args.input_dir, args.output_dir,
        chunk_size=args.chunk_size, overlap=args.overlap,
        mode=args.mode, write_csv=args.write_csv,
    ))
