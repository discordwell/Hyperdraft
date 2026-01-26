#!/usr/bin/env python3
"""
Upload Card Art to GitHub Releases

Zips each set's art folder and uploads to GitHub releases.
Requires `gh` CLI to be installed and authenticated.

Usage:
    python scripts/upload_card_art.py                    # Upload all sets
    python scripts/upload_card_art.py lorwyn_custom      # Upload specific set
    python scripts/upload_card_art.py --list             # List sets to upload
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ART_DIR = PROJECT_ROOT / "assets" / "card_art"
CUSTOM_ART_DIR = ART_DIR / "custom"
MTG_ART_DIR = ART_DIR / "mtg"
TEMP_DIR = PROJECT_ROOT / ".art_upload_temp"

RELEASE_TAG = "card-art-v1"
RELEASE_NAME = "Card Art Assets"


def get_all_sets() -> list[tuple[str, Path]]:
    """Get all sets with art available."""
    sets = []

    for category, dir_path in [("custom", CUSTOM_ART_DIR), ("mtg", MTG_ART_DIR)]:
        if dir_path.exists():
            for item in sorted(dir_path.iterdir()):
                if item.is_dir() and any(item.glob("*.png")):
                    sets.append((f"{category}/{item.name}", item))

    return sets


def get_set_size(path: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def zip_set(set_name: str, set_path: Path, output_dir: Path) -> Path | None:
    """Zip a set's art folder."""
    # Clean set name for filename
    safe_name = set_name.replace("/", "_")
    zip_path = output_dir / f"card_art_{safe_name}.zip"

    try:
        print(f"  Zipping {set_name}...")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in set_path.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(set_path.parent)
                    zf.write(file, arcname)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"    Created {zip_path.name} ({size_mb:.1f} MB)")
        return zip_path

    except Exception as e:
        print(f"    Error zipping: {e}")
        return None


def ensure_release_exists() -> bool:
    """Ensure the GitHub release exists, create if not."""
    # Check if release exists
    result = subprocess.run(
        ["gh", "release", "view", RELEASE_TAG],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"Release '{RELEASE_TAG}' exists")
        return True

    # Create release
    print(f"Creating release '{RELEASE_TAG}'...")
    result = subprocess.run(
        [
            "gh", "release", "create", RELEASE_TAG,
            "--title", RELEASE_NAME,
            "--notes", "Card art assets for Hyperdraft. Download individual sets as needed.",
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Failed to create release: {result.stderr}")
        return False

    print("Release created")
    return True


def upload_to_release(zip_path: Path) -> bool:
    """Upload a zip file to the GitHub release."""
    print(f"  Uploading {zip_path.name}...")

    result = subprocess.run(
        ["gh", "release", "upload", RELEASE_TAG, str(zip_path), "--clobber"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"    Upload failed: {result.stderr}")
        return False

    print(f"    Uploaded successfully")
    return True


def check_gh_cli() -> bool:
    """Check if gh CLI is available and authenticated."""
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: gh CLI not authenticated")
        print("Run: gh auth login")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload card art to GitHub releases")
    parser.add_argument("sets", nargs="*", help="Specific sets to upload")
    parser.add_argument("--list", action="store_true", help="List sets available to upload")
    parser.add_argument("--dry-run", action="store_true", help="Zip but don't upload")

    args = parser.parse_args()

    all_sets = get_all_sets()

    if args.list:
        print("Sets available to upload:")
        total_size = 0
        for name, path in all_sets:
            size = get_set_size(path)
            total_size += size
            print(f"  {name}: {size / (1024*1024):.1f} MB")
        print(f"\nTotal: {total_size / (1024*1024*1024):.2f} GB")
        return

    # Filter to specific sets if provided
    if args.sets:
        filtered = []
        for name, path in all_sets:
            short_name = name.split("/")[-1]
            if short_name in args.sets or name in args.sets:
                filtered.append((name, path))
        all_sets = filtered

        if not all_sets:
            print("No matching sets found")
            sys.exit(1)

    if not args.dry_run:
        if not check_gh_cli():
            sys.exit(1)

        if not ensure_release_exists():
            sys.exit(1)

    # Create temp directory
    TEMP_DIR.mkdir(exist_ok=True)

    try:
        success = 0
        failed = 0

        for name, path in all_sets:
            print(f"\nProcessing {name}...")

            zip_path = zip_set(name, path, TEMP_DIR)
            if not zip_path:
                failed += 1
                continue

            if args.dry_run:
                print(f"  [dry-run] Would upload {zip_path.name}")
                success += 1
            else:
                if upload_to_release(zip_path):
                    success += 1
                else:
                    failed += 1

            # Clean up zip after upload
            zip_path.unlink(missing_ok=True)

        print(f"\n{'='*40}")
        print(f"Completed: {success} succeeded, {failed} failed")

    finally:
        # Cleanup temp dir
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
