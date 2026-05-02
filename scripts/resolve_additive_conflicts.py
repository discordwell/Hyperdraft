"""Resolve git merge conflicts that are purely additive — both sides
appended different content to the same region. Keep both sides in order.

For each conflict block:
    <<<<<<< HEAD
    ...HEAD content...
    =======
    ...other content...
    >>>>>>> branch
The output is HEAD content followed by other content (no markers).

Usage: python scripts/resolve_additive_conflicts.py <file> [<file>...]
"""
import sys
from pathlib import Path

def resolve(path: Path) -> int:
    text = path.read_text()
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    resolved = 0
    while i < n:
        line = lines[i]
        if line.startswith("<<<<<<<"):
            # Find ======= and >>>>>>> markers
            sep = None
            end = None
            for j in range(i + 1, n):
                if lines[j].startswith("=======") and sep is None:
                    sep = j
                elif lines[j].startswith(">>>>>>>"):
                    end = j
                    break
            if sep is None or end is None:
                # Malformed, give up
                return -1
            # HEAD content: i+1 .. sep-1
            # OTHER content: sep+1 .. end-1
            out.extend(lines[i+1:sep])
            out.extend(lines[sep+1:end])
            i = end + 1
            resolved += 1
            continue
        out.append(line)
        i += 1
    if resolved:
        path.write_text("\n".join(out))
    return resolved

def main():
    total = 0
    for p in sys.argv[1:]:
        path = Path(p)
        n = resolve(path)
        if n < 0:
            print(f"  {p}: MALFORMED")
        else:
            print(f"  {p}: resolved {n} conflict block(s)")
            total += n
    print(f"Total: {total}")

if __name__ == "__main__":
    main()
