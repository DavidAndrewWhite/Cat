#!/usr/bin/env python3
"""
format_script.py - Build a Cat & Company issue PDF from a Markdown source file.

Usage:
    python format_script.py <path/to/source.md>

Requirements:
    - pandoc (https://pandoc.org/)
    - xelatex (TeX distribution: TeX Live, MiKTeX, or MacTeX)
"""

import argparse
import os
import re
import subprocess
import sys

# --- Configuration ---
PANDOC_INPUT_FORMAT = "commonmark_x"
PANDOC_PDF_ENGINE = "xelatex"
PANDOC_DOCUMENTCLASS = "report"
PANDOC_TOP_LEVEL_DIVISION = "section"

# Output and template paths
OUTPUT_DIR = "pdf"
TEMPLATE_DIR = "templates"


# Issue metadata pattern - matches the first 6 lines of an issue file
ISSUE_METADATA_PATTERN = re.compile(
    r'^#\s+(.+)$\n'
    r'^-\s+Issue\s+(\d+)(?:\s*)$\n'
    r'^-\s+(\d+)\s+pp\.?\s*$\n'
    r'^-\s+\*\*(.+?)\*\*\s*$\n'
    r'^-\s+(.+?)$\n'
    r'^-\s+(\u00a9.+?)$',
    re.MULTILINE,
)


def parse_issue_metadata(source_file):
    """Parse the first 6 lines of an issue file to extract metadata.

    Returns a dict with keys: series_title, issue_number, page_count,
    story_title, author, copyright_line.
    """
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    match = ISSUE_METADATA_PATTERN.search(content)
    if not match:
        return None
    
    return {
        "series_title": match.group(1).strip(),
        "issue_number": f"Issue {match.group(2)}",
        "page_count": f"{match.group(3)} pp",
        "story_title": match.group(4).strip(),
        "author": match.group(5).strip(),
        "copyright_line": match.group(6).strip(),
    }


def build_issue(source_file, output_path):
    """Run pandoc to convert a single Markdown file to PDF with title page.
    
    Parses metadata from the first 6 lines, strips the header, and uses
    pandoc with a custom LaTeX template to generate the PDF.
    """
    # Parse metadata
    metadata = parse_issue_metadata(source_file)
    if metadata is None:
        print(f"ERROR: Could not parse metadata from {source_file}")
        return False

    # Strip metadata header from content
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    clean_content = "".join(lines[6:])

    # Check template exists
    template_path = os.path.join(TEMPLATE_DIR, "issue.tex")
    if not os.path.exists(template_path):
        print(f"ERROR: Template file not found: {template_path}")
        return False

    # Build pandoc command - read content from stdin
    cmd = [
        "pandoc",
        "-f", PANDOC_INPUT_FORMAT,
        "--pdf-engine", PANDOC_PDF_ENGINE,
        "-V", f"documentclass:{PANDOC_DOCUMENTCLASS}",
        "--top-level-division", PANDOC_TOP_LEVEL_DIVISION,
        "-o", output_path,
        "--template", template_path,
        "-V", f"title={metadata['series_title']}",
        "-V", f"issueNumber={metadata['issue_number']}",
        "-V", f"pageCount={metadata['page_count']}",
        "-V", f"storyTitle={metadata['story_title']}",
        "-V", f"authorName={metadata['author']}",
        "-V", f"copyrightLine={metadata['copyright_line']}",
        "--from", PANDOC_INPUT_FORMAT,
        "-",  # Read from stdin
    ]

    print(f"Building: {source_file} -> {output_path}")
    try:
        result = subprocess.run(
            cmd,
            input=clean_content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR: pandoc failed for {source_file}")
            if result.stderr:
                print(f"stderr: {result.stderr[:1000]}")
            return False
        return True
    except FileNotFoundError:
        print("ERROR: 'pandoc' not found in PATH. Please install pandoc.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build a Cat & Company issue PDF from a Markdown source file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "source",
        help="Path to the Markdown source file (e.g., Issue 1.md)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=OUTPUT_DIR,
        help=f"Output directory for PDFs (default: {OUTPUT_DIR})",
    )

    args = parser.parse_args()
    source_file = args.source

    if not os.path.isfile(source_file):
        print(f"ERROR: Source file not found: {source_file}")
        sys.exit(1)

    # Derive output filename from source basename
    base = os.path.splitext(os.path.basename(source_file))[0]
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"{base}.pdf")

    success = build_issue(source_file, output_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()