#!/usr/bin/env python3
"""
format_script.py - Build Cat & Company issue PDFs from Markdown sources.

Cross-platform alternative to Makefile. Handles spaces in filenames,
auto-discovers Issue files, and works on Linux, macOS, and Windows.

Usage:
    python format_script.py              # Build all issues
    python format_script.py --all        # Build all issues (explicit)
    python format_script.py --issue 1    # Build only Issue 1
    python format_script.py --issue 3-5  # Build Issues 3, 4, 5
    python format_script.py --clean      # Remove all generated PDFs
    python format_script.py --list       # List available issue files

Requirements:
    - pandoc (https://pandoc.org/)
    - xelatex (TeX distribution: TeX Live, MiKTeX, or MacTeX)
    - Liberation Serif fonts
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Configuration ---
PANDOC_INPUT_FORMAT = "commonmark_x"
PANDOC_PDF_ENGINE = "xelatex"
PANDOC_DOCUMENTCLASS = "report"
PANDOC_TOP_LEVEL_DIVISION = "section"

# Output and template paths
OUTPUT_DIR = "pdf"
TEMPLATE_DIR = "templates"
TITLE_PAGE_TEMPLATE = os.path.join(TEMPLATE_DIR, "issue.tex")

# Paper size (a4, letter, legal, executive, a5, a3, b4, b5, etc.)
PAPER_SIZE = "a4"

# Issue metadata pattern - matches the first 5-6 lines of the script
ISSUE_METADATA_PATTERN = re.compile(
    r'^#\s+(.+)$\n'
    r'^-\s+Issue\s+(\d+)(?:\s*)$\n'
    r'^-\s+(\d+)\s+pp\.?\s*$\n'
    r'^-\s+\*\*(.+?)\*\*\s*$\n'
    r'^-\s+(.+?)$\n'
    r'^-\s+(\u00a9.+?)$',
    re.MULTILINE,
)

ISSUE_PATTERN = re.compile(r"^Issue\s+\d+\.md$", re.IGNORECASE)


def find_issue_files(directory="."):
    """Auto-discover Issue markdown files in the given directory."""
    issues = []
    for f in sorted(os.listdir(directory)):
        if ISSUE_PATTERN.match(f):
            match = re.search(r"\d+", f)
            if match:
                num = int(match.group())
                issues.append((num, f))
    issues.sort(key=lambda x: x[0])
    return issues


def parse_issue_metadata(source_file):
    """Parse the first 6 lines of an issue file to extract metadata.
    
    Returns a dict with keys: series_title, issue_number, page_count,
    story_title, author, copyright_line
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


def get_pandoc_args():
    """Build the full list of pandoc command-line arguments."""
    return [
        "-f", PANDOC_INPUT_FORMAT,
        "--pdf-engine", PANDOC_PDF_ENGINE,
        "-V", f"mainfont:{FONT_NAME}",
        "-V", f"mainfontoptions:BoldFont={FONT_BOLD}, ItalicFont={FONT_ITALIC}, BoldItalicFont={FONT_BOLD_ITALIC}",
        "-V", f"documentclass:{PANDOC_DOCUMENTCLASS}",
        "--top-level-division", PANDOC_TOP_LEVEL_DIVISION,
        "-V", f"papersize:{PAPER_SIZE}",
    ]


def build_issue(source_file, output_path):
    """Run pandoc to convert a single Markdown file to PDF with title page.
    
    Parses metadata from the first 6 lines, strips the header, and uses
    pandoc with a custom LaTeX template to generate the PDF.
    """
    # Parse metadata
    metadata = parse_issue_metadata(source_file)
    if metadata is None:
        print(f"  ERROR: Could not parse metadata from {source_file}")
        return False
    
    # Strip metadata header from content
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    clean_content = "".join(lines[6:])
    
    # Check template exists
    template_path = os.path.join(TEMPLATE_DIR, "issue.tex")
    if not os.path.exists(template_path):
        print(f"  ERROR: Template file not found: {template_path}")
        return False
    
    # Build pandoc command - read content from stdin
    cmd = ["pandoc"] + get_pandoc_args() + [
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
    
    print(f"  Building: {source_file} -> {output_path}")
    try:
        result = subprocess.run(
            cmd,
            input=clean_content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR: pandoc failed for {source_file}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:1000]}")
            return False
        return True
    except FileNotFoundError:
        print(f"  ERROR: 'pandoc' not found in PATH. Please install pandoc.")
        return False


def build_all(issue_files, output_dir):
    """Build all discovered issue files."""
    os.makedirs(output_dir, exist_ok=True)
    success_count = 0
    fail_count = 0

    for num, filename in issue_files:
        source = os.path.join(".", filename)
        base = os.path.splitext(filename)[0]
        output = os.path.join(output_dir, f"{base}.pdf")

        if build_issue(source, output):
            success_count += 1
        else:
            fail_count += 1

    print(f"\nDone: {success_count} succeeded, {fail_count} failed.")
    return fail_count == 0


def build_specific(issue_files, numbers_str, output_dir):
    """Build specific issue(s) by number or range."""
    os.makedirs(output_dir, exist_ok=True)

    # Parse numbers_str (supports "3" or "3-5")
    if "-" in numbers_str:
        start, end = map(int, numbers_str.split("-"))
        target_numbers = set(range(start, end + 1))
    else:
        target_numbers = {int(numbers_str)}

    # Filter to only valid issues
    targets = [(num, fn) for num, fn in issue_files if num in target_numbers]

    if not targets:
        print(f"No issues found matching: {numbers_str}")
        print(f"Available: {[f'{n}' for n, _ in issue_files]}")
        return False

    success_count = 0
    fail_count = 0
    for num, filename in targets:
        source = os.path.join(".", filename)
        base = os.path.splitext(filename)[0]
        output = os.path.join(output_dir, f"{base}.pdf")

        if build_issue(source, output):
            success_count += 1
        else:
            fail_count += 1

    print(f"\nDone: {success_count} succeeded, {fail_count} failed.")
    return fail_count == 0


def clean_pdfs(issue_files, output_dir):
    """Remove all generated PDF files."""
    pdf_dir = Path(output_dir)
    if not pdf_dir.exists():
        print(f"Output directory '{output_dir}' does not exist. Nothing to clean.")
        return

    removed = 0
    for num, filename in issue_files:
        base = os.path.splitext(filename)[0]
        pdf_path = pdf_dir / f"{base}.pdf"
        if pdf_path.exists():
            pdf_path.unlink()
            print(f"  Removed: {pdf_path}")
            removed += 1

    print(f"\nCleaned: {removed} PDF(s) removed.")


def list_issues(issue_files):
    """List all discovered issue files."""
    if not issue_files:
        print("No issue files found.")
        return

    print("Discovered issue files:")
    for num, filename in issue_files:
        size = os.path.getsize(os.path.join(".", filename))
        print(f"  Issue {num}: {filename} ({size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description="Build Cat & Company issue PDFs from Markdown sources.",
        epilog="Examples:\n"
               "  python format_script.py              # Build all issues\n"
               "  python format_script.py --issue 1    # Build Issue 1 only\n"
               "  python format_script.py --issue 3-5  # Build Issues 3 through 5\n"
               "  python format_script.py --clean      # Remove all generated PDFs\n"
               "  python format_script.py --list       # List available issue files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--all", action="store_true", help="Build all discovered issues")
    group.add_argument("--issue", type=str, help="Build specific issue(s): '1' or range '3-5'")
    group.add_argument("--clean", action="store_true", help="Remove all generated PDFs")
    group.add_argument("--list", action="store_true", help="List available issue files")

    parser.add_argument("--output-dir", type=str, default=OUTPUT_DIR, help=f"Output directory for PDFs (default: {OUTPUT_DIR})")
    parser.add_argument("--source-dir", type=str, default=".", help="Directory to search for issue files (default: current directory)")
    parser.add_argument("--paper-size", type=str, default=None, help=f"Paper size for PDFs (default: a4). Examples: a4, letter, legal, a5, a3, b4, b5")

    args = parser.parse_args()

    # Apply CLI paper-size override
    if args.paper_size is not None:
        global PAPER_SIZE
        PAPER_SIZE = args.paper_size

    # Discover issue files
    issue_files = find_issue_files(args.source_dir)
    if not issue_files:
        print("No issue files found. Looking for files matching 'Issue-<N>.md' or 'Issue <N>.md'.")
        sys.exit(1)

    # Handle --list
    if args.list:
        list_issues(issue_files)
        return

    # Handle --clean
    if args.clean:
        clean_pdfs(issue_files, args.output_dir)
        return

    # Build operations
    if args.issue:
        success = build_specific(issue_files, args.issue, args.output_dir)
    elif args.all or not (args.issue or args.clean or args.list):
        success = build_all(issue_files, args.output_dir)
    else:
        parser.print_help()
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()