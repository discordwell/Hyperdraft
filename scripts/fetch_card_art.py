#!/usr/bin/env python3
"""
Fetch Card Art

Downloads and extracts card art for sets from GitHub releases.
Art is stored locally in assets/card_art/ and only downloaded once.

Usage:
    python scripts/fetch_card_art.py <set_name>
    python scripts/fetch_card_art.py lorwyn_custom
    python scripts/fetch_card_art.py --list
    python scripts/fetch_card_art.py --all
"""

import argparse
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# GitHub repo info
REPO_OWNER = "discordwell"
REPO_NAME = "Hyperdraft"
RELEASES_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"

# Local paths
PROJECT_ROOT = Path(__file__).parent.parent
ART_DIR = PROJECT_ROOT / "assets" / "card_art"
CUSTOM_ART_DIR = ART_DIR / "custom"
MTG_ART_DIR = ART_DIR / "mtg"


def get_releases() -> list[dict]:
    """Fetch release info from GitHub API."""
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching releases: {e}")
        return []


def find_art_asset(releases: list[dict], set_name: str) -> tuple[str, str] | None:
    """
    Find the download URL for a set's art zip.

    Looks for assets named like:
    - card_art_<set_name>.zip
    - <set_name>_art.zip
    - <set_name>.zip
    """
    patterns = [
        f"card_art_{set_name}.zip",
        f"{set_name}_art.zip",
        f"{set_name}.zip",
    ]

    for release in releases:
        for asset in release.get("assets", []):
            asset_name = asset["name"].lower()
            for pattern in patterns:
                if asset_name == pattern.lower():
                    return asset["browser_download_url"], asset["name"]

    return None


def get_local_art_path(set_name: str) -> Path:
    """Determine local path for a set's art."""
    # Check if it's a custom set or MTG set
    custom_path = CUSTOM_ART_DIR / set_name
    mtg_path = MTG_ART_DIR / set_name

    if custom_path.exists():
        return custom_path
    if mtg_path.exists():
        return mtg_path

    # Default to custom for new sets
    return custom_path


def is_art_available(set_name: str) -> bool:
    """Check if art is already downloaded for a set."""
    custom_path = CUSTOM_ART_DIR / set_name
    mtg_path = MTG_ART_DIR / set_name

    # Consider available if folder exists and has files
    for path in [custom_path, mtg_path]:
        if path.exists() and any(path.iterdir()):
            return True

    return False


def download_file(url: str, dest: Path) -> bool:
    """Download a file with progress indication."""
    try:
        print(f"Downloading from {url}...")

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total:
                        pct = (downloaded / total) * 100
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        print(f"\r  {mb:.1f}/{total_mb:.1f} MB ({pct:.0f}%)", end="", flush=True)

            print()  # Newline after progress

        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """Extract a zip file to destination."""
    try:
        print(f"Extracting to {dest_dir}...")

        # Create destination if needed
        dest_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Check structure - might have a root folder or not
            names = zf.namelist()

            # If all files share a common prefix folder, strip it
            if names:
                first_part = names[0].split("/")[0]
                all_same_root = all(n.startswith(first_part + "/") or n == first_part for n in names)

                if all_same_root and first_part:
                    # Extract to temp, then move contents
                    temp_dir = dest_dir.parent / f".temp_{dest_dir.name}"
                    zf.extractall(temp_dir)

                    # Move contents from nested folder
                    nested = temp_dir / first_part
                    if nested.exists():
                        for item in nested.iterdir():
                            shutil.move(str(item), str(dest_dir / item.name))
                        shutil.rmtree(temp_dir)
                    else:
                        # No nesting, move everything
                        for item in temp_dir.iterdir():
                            shutil.move(str(item), str(dest_dir / item.name))
                        shutil.rmtree(temp_dir)
                else:
                    # No common root, extract directly
                    zf.extractall(dest_dir)

        print(f"  Extracted {len(names)} files")
        return True
    except Exception as e:
        print(f"Extraction failed: {e}")
        return False


def fetch_set_art(set_name: str, force: bool = False) -> bool:
    """
    Fetch art for a set if not already available.

    Returns True if art is available (either already existed or downloaded).
    """
    set_name = set_name.lower().replace("-", "_").replace(" ", "_")

    # Check if already have it
    if not force and is_art_available(set_name):
        print(f"Art for '{set_name}' already available locally")
        return True

    # Fetch release info
    print(f"Looking for art package for '{set_name}'...")
    releases = get_releases()

    if not releases:
        print("Could not fetch releases from GitHub")
        return False

    # Find the asset
    result = find_art_asset(releases, set_name)
    if not result:
        print(f"No art package found for '{set_name}'")
        print("Available sets can be listed with: python scripts/fetch_card_art.py --list")
        return False

    url, asset_name = result

    # Download to temp location
    temp_zip = ART_DIR / f".download_{set_name}.zip"
    if not download_file(url, temp_zip):
        return False

    # Determine destination
    # Check asset name for hints about location
    if "mtg" in asset_name.lower() or set_name in ["woe", "lci", "mkm", "otj", "blb", "dsk", "fdn"]:
        dest_dir = MTG_ART_DIR / set_name
    else:
        dest_dir = CUSTOM_ART_DIR / set_name

    # Extract
    if not extract_zip(temp_zip, dest_dir):
        temp_zip.unlink(missing_ok=True)
        return False

    # Cleanup
    temp_zip.unlink(missing_ok=True)

    print(f"Successfully installed art for '{set_name}'")
    return True


def list_available_sets(releases: list[dict]) -> list[str]:
    """List all sets with art available for download."""
    sets = []

    for release in releases:
        for asset in release.get("assets", []):
            name = asset["name"].lower()
            if name.endswith(".zip"):
                # Extract set name from filename
                set_name = name.replace("card_art_", "").replace("_art", "").replace(".zip", "")
                sets.append(set_name)

    return sorted(set(sets))


def list_local_sets() -> list[str]:
    """List sets with art available locally."""
    sets = []

    for dir_path in [CUSTOM_ART_DIR, MTG_ART_DIR]:
        if dir_path.exists():
            for item in dir_path.iterdir():
                if item.is_dir() and any(item.iterdir()):
                    sets.append(item.name)

    return sorted(sets)


def main():
    parser = argparse.ArgumentParser(description="Fetch card art from GitHub releases")
    parser.add_argument("set_name", nargs="?", help="Set name to fetch art for")
    parser.add_argument("--list", action="store_true", help="List available sets")
    parser.add_argument("--local", action="store_true", help="List locally available sets")
    parser.add_argument("--all", action="store_true", help="Download all available sets")
    parser.add_argument("--force", action="store_true", help="Re-download even if exists")

    args = parser.parse_args()

    if args.local:
        print("Locally available sets:")
        for s in list_local_sets():
            print(f"  {s}")
        return

    if args.list:
        print("Fetching release info...")
        releases = get_releases()
        sets = list_available_sets(releases)

        if sets:
            print("Available for download:")
            for s in sets:
                local = "✓" if is_art_available(s) else " "
                print(f"  [{local}] {s}")
        else:
            print("No art packages found in releases")
        return

    if args.all:
        print("Fetching all available sets...")
        releases = get_releases()
        sets = list_available_sets(releases)

        for s in sets:
            fetch_set_art(s, force=args.force)
        return

    if not args.set_name:
        parser.print_help()
        sys.exit(1)

    success = fetch_set_art(args.set_name, force=args.force)
    sys.exit(0 if success else 1)


# Convenience function for importing from other modules
def ensure_art_available(set_name: str) -> bool:
    """
    Ensure art is available for a set, downloading if needed.

    Call this when loading a set to lazily fetch art.
    Returns True if art is available.
    """
    return fetch_set_art(set_name, force=False)


if __name__ == "__main__":
    main()
