#!/usr/bin/env python3
"""
build_issues.py - Build Cat & Company issue PDFs from Markdown sources.

Cross-platform alternative to Makefile. Handles spaces in filenames,
auto-discovers Issue files, and works on Linux, macOS, and Windows.

Usage:
    python build_issues.py              # Build all issues
    python build_issues.py --all        # Build all issues (explicit)
    python build_issues.py --issue 1    # Build only Issue 1
    python build_issues.py --issue 3-5  # Build Issues 3, 4, 5
    python build_issues.py --clean      # Remove all generated PDFs
    python build_issues.py --list       # List available issue files

Requirements:
    - pandoc (https://pandoc.org/)
    - xelatex (TeX distribution: TeX Live, MiKTeX, or MacTeX)
    - Liberation Serif fonts (or set FONT_DIR and FONT_NAME options)
"""

import argparse
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Configuration Defaults ---
# These defaults can be overridden by a local config file.
# See CONFIG_FILES list below for supported filenames.
# Add your override file to .gitignore (e.g., ".build_config").

CONFIG_FILES = [
    ".build_config",       # Hidden file, naturally ignored by git
    "build_config.py",     # Explicit Python config module
    "build_config.json",   # JSON format (for simpler setups)
]

# Font configuration
FONT_DIR = None          # Path to Liberation font files (None = use font name lookup)
FONT_NAME = "Liberation Serif"
FONT_BOLD = "Liberation Serif"
FONT_ITALIC = "Liberation Serif"
FONT_BOLD_ITALIC = "Liberation Serif"

# Pandoc settings
PANDOC_INPUT_FORMAT = "commonmark_x"
PANDOC_PDF_ENGINE = "xelatex"
PANDOC_DOCUMENTCLASS = "report"
PANDOC_TOP_LEVEL_DIVISION = "section"  # Note: this is a pandoc CLI flag, NOT a -V latex variable

# Output directory for PDFs
OUTPUT_DIR = "pdf"

# Paper size (a4, letter, legal, executive, a5, a3, b4, b5, etc.)
PAPER_SIZE = "a4"

# Template directory for LaTeX templates
TEMPLATE_DIR = "templates"

# Title page template
TITLE_PAGE_TEMPLATE = os.path.join(TEMPLATE_DIR, "issue.tex")

# Issue metadata pattern - matches the first 6 lines of issue files
# Line 1: Series title (h1)
# Line 2: Issue number (- Issue N)
# Line 3: Page count (- NN pp[.])
# Line 4: Story title (- **Title** or - Title)
# Line 5: Author (- Author Name)
# Line 6: Copyright (- © year, ...)
ISSUE_METADATA_PATTERN = re.compile(
    r'^#\s+(.+)$\n'
    r'^-\s+Issue\s+(\d+)(?:\s*)$\n'
    r'^-\s+(\d+)\s+pp\.?\s*$\n'
    r'^-\s+\*\*(.+?)\*\*\s*$\n'
    r'^-\s+(.+?)$\n'
    r'^-\s+(\u00a9.+?)$',
    re.MULTILINE,
)

# --- Configuration Override Loading ---
def _load_config_file(filepath):
    """Load configuration overrides from a file.

    Supports three formats:
    1. Python module (.py): import as module, read attributes
    2. JSON (.json): parse JSON object, map keys to config vars
    3. Key=Value (.build_config or other): simple key=value pairs
    """
    if not os.path.isfile(filepath):
        return None

    config = {}
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".py":
        # Python module: import and read attributes
        spec = importlib.util.spec_from_file_location("_build_config", filepath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        config_keys = {
            "FONT_DIR", "FONT_NAME", "FONT_BOLD", "FONT_ITALIC",
            "FONT_BOLD_ITALIC", "PANDOC_INPUT_FORMAT", "PANDOC_PDF_ENGINE",
            "PANDOC_DOCUMENTCLASS", "PANDOC_TOP_LEVEL_DIVISION", "OUTPUT_DIR",
            "PAPER_SIZE",
        }
        for key in config_keys:
            if hasattr(mod, key):
                config[key] = getattr(mod, key)

    elif ext == ".json":
        # JSON format
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        config_keys = {
            "FONT_DIR", "FONT_NAME", "FONT_BOLD", "FONT_ITALIC",
            "FONT_BOLD_ITALIC", "PANDOC_INPUT_FORMAT", "PANDOC_PDF_ENGINE",
            "PANDOC_DOCUMENTCLASS", "PANDOC_TOP_LEVEL_DIVISION", "OUTPUT_DIR",
            "PAPER_SIZE",
        }
        for key in config_keys:
            if key in data:
                config[key] = data[key]

    else:
        # Key=Value format (simple text file)
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Remove surrounding quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    config_keys = {
                        "FONT_DIR", "FONT_NAME", "FONT_BOLD", "FONT_ITALIC",
                        "FONT_BOLD_ITALIC", "PANDOC_INPUT_FORMAT", "PANDOC_PDF_ENGINE",
                        "PANDOC_DOCUMENTCLASS", "PANDOC_TOP_LEVEL_DIVISION", "OUTPUT_DIR",
                        "PAPER_SIZE",
                    }
                    if key in config_keys:
                        config[key] = value

    return config


def _apply_config_overrides():
    """Load and apply configuration overrides from the first found config file."""
    import json  # needed for JSON config parsing

    for cfg_file in CONFIG_FILES:
        loaded = _load_config_file(cfg_file)
        if loaded is not None:
            print(f"Loading config from: {cfg_file}")
            for key, value in loaded.items():
                globals()[key] = value
            return

    # No config file found; use defaults (no output needed)

ISSUE_PATTERN = re.compile(r"^Issue\s+\d+\.md$", re.IGNORECASE)


def find_issue_files(directory="."):
    """Auto-discover Issue markdown files in the given directory."""
    issues = []
    for f in sorted(os.listdir(directory)):
        if ISSUE_PATTERN.match(f):
            # Extract issue number
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


def strip_issue_header(source_file):
    """Read the source file and return content with the first 6 lines removed.
    
    This removes the metadata header that will appear on the title page.
    """
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Skip the first 6 lines (metadata header)
    return "".join(lines[6:])


def get_pandoc_args():
    """Build the full list of pandoc command-line arguments."""
    args = [
        "-f", PANDOC_INPUT_FORMAT,
        "--pdf-engine", PANDOC_PDF_ENGINE,
        "-V", f"mainfont:{FONT_NAME}",
        "-V", f"mainfontoptions:BoldFont={FONT_BOLD}, ItalicFont={FONT_ITALIC}, BoldItalicFont={FONT_BOLD_ITALIC}",
        "-V", f"documentclass:{PANDOC_DOCUMENTCLASS}",
        "--top-level-division", PANDOC_TOP_LEVEL_DIVISION,
        "-V", f"papersize:{PAPER_SIZE}",
    ]

    if FONT_DIR:
        # Prepend font directory to mainfont paths
        args[2] = f"mainfont:{os.path.join(FONT_DIR, FONT_NAME)}"
        args[3] = (
            f"mainfontoptions:BoldFont={os.path.join(FONT_DIR, FONT_BOLD)}, "
            f"ItalicFont={os.path.join(FONT_DIR, FONT_ITALIC)}, "
            f"BoldItalicFont={os.path.join(FONT_DIR, FONT_BOLD_ITALIC)}"
        )

    return args


def build_issue(source_file, output_path):
    """Run pandoc to convert a single Markdown file to PDF with title page.
    
    This function:
    1. Parses metadata from the first 6 lines of the issue file
    2. Strips the metadata header from the content
    3. Creates a temporary file with clean content
    4. Runs pandoc with the custom LaTeX template and metadata variables
    """
    # Parse metadata
    metadata = parse_issue_metadata(source_file)
    print(metadata)
    if metadata is None:
        print(f"  WARNING: Could not parse metadata from {source_file}")
        print(f"  Falling back to standard build without title page.")
        # Fall back to standard build
        cmd = ["pandoc"] + get_pandoc_args() + [
            "-o", output_path,
            source_file,
        ]
        print(f"  Building: {source_file} -> {output_path}")
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR: pandoc failed for {source_file}")
                if result.stderr:
                    print(f"  stderr: {result.stderr[:500]}")
                return False
            return True
        except FileNotFoundError:
            print(f"  ERROR: 'pandoc' not found in PATH. Please install pandoc.")
            return False
    
    # Strip metadata header from content
    clean_content = strip_issue_header(source_file)
    
    # Create temporary file with clean content
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write(clean_content)
        tmp_path = tmp.name
    
    try:
        # Build pandoc command with template and metadata variables
        template_path = os.path.join(TEMPLATE_DIR, "issue.tex")
        if not os.path.exists(template_path):
            print(f"  ERROR: Template file not found: {template_path}")
            return False
        
        cmd = ["pandoc"] + get_pandoc_args() + [
            "-o", output_path,
            "--template", template_path,
            "-V", f"title={metadata['series_title']}",
            "-V", f"issueNumber={metadata['issue_number']}",
            "-V", f"pageCount={metadata['page_count']}",
            "-V", f"storyTitle={metadata['story_title']}",
            "-V", f"authorName={metadata['author']}",
            "-V", f"copyrightLine={metadata['copyright_line']}",
            tmp_path,
        ]
        
        print(f"  Building: {source_file} -> {output_path}")
        try:
            result = subprocess.run(
                cmd,
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
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
        source = os.path.join(".", filename)
        size = os.path.getsize(source)
        print(f"  Issue {num}: {filename} ({size:,} bytes)")


def main():
    # Load config overrides before anything else
    _apply_config_overrides()

    parser = argparse.ArgumentParser(
        description="Build Cat & Company issue PDFs from Markdown sources.",
        epilog="Examples:\n"
               "  python build_issues.py              # Build all issues\n"
               "  python build_issues.py --issue 1    # Build Issue 1 only\n"
               "  python build_issues.py --issue 3-5  # Build Issues 3 through 5\n"
               "  python build_issues.py --clean      # Remove all generated PDFs\n"
               "  python build_issues.py --list       # List available issue files",
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

    # Apply CLI paper-size override if provided
    if args.paper_size is not None:
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
        # Default: build all if no specific action given
        success = build_all(issue_files, args.output_dir)
    else:
        parser.print_help()
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()