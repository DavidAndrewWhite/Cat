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

# Issue header pattern
# Markdown level 1 header followed immediately by an unordered list
HEADER_PATTERN = re.compile(
    r'^#\s+(.+)$\n'
    r'(?:^-\s(.+)$\n)?'
    r'(?:^-\s(.+)$\n)?'
    r'(?:^-\s(.+)$\n)?'
    r'(?:^-\s(.+)$\n)?'
    r'(?:^-\s(.+)$\n)?',
    re.MULTILINE
)

ISSUE_NUMBER_PATTERN = re.compile(r'(Issue \d+)\s*')
PAGECOUNT_PATTERN = re.compile(r'(\d+ pp)\s*')
STORY_TITLE_PATTERN = re.compile(r'\*\*(.+)\*\*\s*')
COPYRIGHT_LINE_PATTERN = re.compile(r'(\u00a9.+)\s*')

def escape_special_characters(text):
    return re.sub(r'([$%&~_\^\\{}])', r'\\\1',text)

def parse_header(source_file):
    """Parse the header of a script file to extract metadata.

    Returns a dict with keys: series_title, issue_number, page_count,
    story_title, author, copyright_line.
    """
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    header = HEADER_PATTERN.search(content)
    if not header:
        return None
    
    group = 1
    metadata = {}
    metadata["series_title"] = escape_special_characters(header.group(group).strip())
    group += 1
    issue = ISSUE_NUMBER_PATTERN.match(header.group(group))
    if not issue:
        metadata["issue_number"] = ''
    else:
        metadata["issue_number"] = issue.group(1)
        group += 1
    pagecount = PAGECOUNT_PATTERN.match(header.group(group))
    metadata["page_count"] = pagecount.group(1)
    group += 1
    storytitle = STORY_TITLE_PATTERN.match(header.group(group))
    metadata["story_title"] = escape_special_characters(storytitle.group(1))
    group += 1
    metadata["author"] = escape_special_characters(header.group(group).strip())
    group += 1
    copyright = COPYRIGHT_LINE_PATTERN.match(header.group(group))
    metadata["copyright_line"] = escape_special_characters(copyright.group(1).strip())

    return metadata

def build_issue(source_file, output_path):
    """Run pandoc to convert a single Markdown file to PDF with title page.
    
    Parses metadata from the first 6 lines, strips the header, and uses
    pandoc with a custom LaTeX template to generate the PDF.
    """
    # Parse metadata
    metadata = parse_header(source_file)
    if metadata is None:
        print(f"ERROR: Could not parse metadata from {source_file}")
        return False

    # Strip metadata header from content
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    clean_content = HEADER_PATTERN.sub('',"".join(lines),1)

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
            encoding="utf-8"
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