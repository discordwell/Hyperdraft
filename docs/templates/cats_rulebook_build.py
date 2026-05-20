"""Convert the cats_rulebook.md to styled HTML for Chrome-headless PDF rendering.

Writes ``docs/cats_rulebook.html`` from ``docs/cats_rulebook.md``.

Hand-rolled (no markdown library required). Supports the small subset of
markdown the rulebook uses: ATX headings, paragraphs, blockquotes, ordered
and unordered lists, tables (pipe-delimited with hyphen separator row),
bold/italic, inline code, and fenced code blocks.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

DOCS = Path("/Users/discordwell/Projects/HYPERDRAFT/docs")
MD = DOCS / "cats_rulebook.md"
HTML_OUT = DOCS / "cats_rulebook.html"


# Cream + butterscotch palette (matches the Cats frontend vibe).
CSS = r"""
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --cream-pg:     #FBF1DC;   /* page background */
  --cream-card:   #F5E5C0;   /* boxed callouts */
  --butterscotch: #C68B3A;   /* primary accent */
  --burnt:        #8C4A1F;   /* heading color */
  --cocoa:        #3B2412;   /* body text */
  --tabby:        #6E4220;   /* sub-headings */
  --mauve:        #7E5A6C;   /* italic / muted */
  --whisker:      #E8D8B0;   /* table row alt */
  --paw:          #B07A35;   /* dividers */
  --shadow:       rgba(120, 76, 30, 0.18);
}

html { font-size: 11.5pt; }

body {
  background: var(--cream-pg);
  color: var(--cocoa);
  font-family: 'EB Garamond', 'Garamond', 'Georgia', serif;
  line-height: 1.55;
}

/* ─── Print ─── */
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
  @bottom-left { content: "Cats — a day in the life"; font-family: 'Inter','sans-serif'; font-size: 8pt; color: #8C4A1F; }
  @bottom-right { content: counter(page); font-family: 'Inter','sans-serif'; font-size: 8pt; color: #8C4A1F; }
}
@media print {
  body { background: #FBF1DC; }
  .page-break { page-break-before: always; }
  h1, h2, h3, h4 { page-break-after: avoid; }
  table, blockquote { page-break-inside: avoid; }
  .cover { page-break-after: always; }
  .quickref { page-break-before: always; }
}

/* ─── Typography ─── */
h1, h2, h3, h4 { font-family: 'Fraunces', 'Playfair Display', 'Garamond', serif; font-weight: 700; }
h1 { font-size: 3.4rem; color: var(--burnt); letter-spacing: -0.01em; line-height: 1.05; }
h2 { font-size: 1.85rem; color: var(--burnt); margin-top: 1.8rem; margin-bottom: 0.6rem; border-bottom: 2px solid var(--paw); padding-bottom: 6px; }
h3 { font-size: 1.35rem; color: var(--tabby); margin-top: 1.2rem; margin-bottom: 0.35rem; }
h4 { font-size: 1.1rem; color: var(--butterscotch); margin-top: 0.9rem; margin-bottom: 0.25rem; font-style: italic; }
p  { margin: 0.55rem 0; }

em { color: var(--mauve); font-style: italic; }
strong { color: var(--burnt); font-weight: 700; }
code { font-family: 'JetBrains Mono', 'Menlo', monospace; font-size: 0.85em; background: var(--cream-card); padding: 0.05em 0.3em; border-radius: 3px; }

/* ─── Layout ─── */
.wrapper { max-width: 780px; margin: 0 auto; padding: 0 0.5rem; }
.section { margin-bottom: 2.4rem; }

/* ─── Cover Page ─── */
.cover {
  text-align: center;
  padding: 4.5rem 1.5rem 3rem;
  background: var(--cream-card);
  border: 3px double var(--butterscotch);
  border-radius: 8px;
  box-shadow: 0 4px 16px var(--shadow);
  margin: 0.5rem 0 2.5rem 0;
  position: relative;
  overflow: hidden;
}
.cover::before {
  content: "";
  position: absolute; inset: 14px;
  border: 1px solid var(--butterscotch);
  border-radius: 4px;
  pointer-events: none;
}
.cover h1 {
  font-size: 4.6rem;
  margin-bottom: 0.4rem;
}
.cover-subtitle {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-size: 1.45rem;
  color: var(--tabby);
  margin-bottom: 2.2rem;
  letter-spacing: 0.01em;
}
.cover-paws {
  font-size: 2.2rem;
  letter-spacing: 1rem;
  color: var(--butterscotch);
  margin: 1.5rem 0;
  padding-left: 1rem;
}
.cover-hook {
  font-family: 'EB Garamond', serif;
  font-style: italic;
  color: var(--cocoa);
  font-size: 1.1rem;
  max-width: 520px;
  margin: 1.6rem auto 1.2rem;
  line-height: 1.55;
}
.cover-meta {
  display: inline-block;
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--burnt);
  background: var(--cream-pg);
  border: 1px solid var(--paw);
  padding: 0.5rem 1.2rem;
  border-radius: 2px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-top: 0.6rem;
}

/* ─── Section dividers ─── */
.paws-divider {
  text-align: center;
  font-size: 1.6rem;
  color: var(--paw);
  letter-spacing: 0.9rem;
  margin: 2rem 0 1.5rem 0;
  padding-left: 0.9rem;
  opacity: 0.55;
}

/* ─── Blockquote ─── */
blockquote {
  border-left: 4px solid var(--butterscotch);
  background: var(--cream-card);
  padding: 0.8rem 1.2rem;
  margin: 1rem 0;
  font-style: italic;
  color: var(--tabby);
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0.2rem 0; }

/* ─── Lists ─── */
ul, ol {
  margin: 0.4rem 0 0.8rem 0;
  padding-left: 1.6rem;
}
ul li, ol li {
  margin-bottom: 0.3rem;
}
ul li::marker { color: var(--butterscotch); }
ol li::marker { color: var(--butterscotch); font-weight: 700; }

/* ─── Tables ─── */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.9rem 0 1.2rem 0;
  font-size: 0.95em;
  background: var(--cream-pg);
}
thead { background: var(--butterscotch); color: var(--cream-pg); }
thead th { padding: 0.55rem 0.7rem; text-align: left; font-family: 'Fraunces', serif; font-size: 0.92em; letter-spacing: 0.02em; }
tbody td { padding: 0.45rem 0.7rem; border-bottom: 1px solid var(--whisker); vertical-align: top; }
tbody tr:nth-child(even) { background: var(--cream-card); }
tbody tr:last-child td { border-bottom: 1px solid var(--paw); }

/* ─── Pre / code blocks (table-layout ascii) ─── */
pre {
  background: var(--cream-card);
  border: 1px solid var(--paw);
  padding: 0.8rem;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Menlo', monospace;
  font-size: 0.82em;
  line-height: 1.35;
  margin: 0.8rem 0;
  white-space: pre;
  overflow-x: hidden;
  color: var(--cocoa);
}
pre code { background: transparent; padding: 0; font-size: 1em; }

/* ─── Quick-reference page ─── */
.quickref {
  background: var(--cream-card);
  border: 2px solid var(--butterscotch);
  border-radius: 6px;
  padding: 1.2rem 1.4rem;
  margin-top: 2rem;
}
.quickref h2 {
  margin-top: 0;
  border-bottom: 2px solid var(--butterscotch);
}
.quickref h3 {
  color: var(--burnt);
  font-size: 1.15rem;
  margin-top: 1rem;
}

/* ─── Credits ─── */
.credits {
  text-align: center;
  font-family: 'EB Garamond', serif;
  font-style: italic;
  color: var(--tabby);
  margin-top: 2.5rem;
  padding: 1.5rem;
  border-top: 1px solid var(--paw);
  border-bottom: 1px solid var(--paw);
}
.credits strong { color: var(--burnt); font-style: normal; }

/* Inline emoji-cat sizing */
.paw-inline { color: var(--butterscotch); font-weight: bold; }
hr { border: 0; height: 1px; background: linear-gradient(to right, transparent, var(--paw), transparent); margin: 1.5rem 0; }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


# Inline formatting: bold, italic, inline code. Order matters.
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    """Apply inline markdown after escaping."""
    text = _esc(text)
    # Code first so we don't process ** or * inside it.
    parts: list[tuple[str, str]] = []  # (kind, content)

    def stash_code(m: re.Match) -> str:
        parts.append(("code", m.group(1)))
        return f"\x00C{len(parts)-1}\x00"

    text = _CODE.sub(stash_code, text)
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    text = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)

    def restore_code(m: re.Match) -> str:
        idx = int(m.group(1))
        return f"<code>{parts[idx][1]}</code>"

    text = re.sub(r"\x00C(\d+)\x00", restore_code, text)
    return text


def convert_markdown(md_text: str) -> str:
    """Convert our subset markdown to HTML body."""
    lines = md_text.split("\n")
    out: list[str] = []
    i = 0
    in_list: str | None = None  # 'ul' | 'ol' | None
    in_blockquote = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    def close_blockquote() -> None:
        nonlocal in_blockquote
        if in_blockquote:
            out.append("</blockquote>")
            in_blockquote = False

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            close_list()
            close_blockquote()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            out.append("<pre><code>" + _esc("\n".join(buf)) + "</code></pre>")
            continue

        # Table — must have a header row then a separator row of |---|
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", lines[i + 1]):
            close_list()
            close_blockquote()
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip header + separator
            out.append("<table>")
            out.append("<thead><tr>")
            for c in header_cells:
                out.append(f"<th>{_inline(c)}</th>")
            out.append("</tr></thead>")
            out.append("<tbody>")
            while i < len(lines) and "|" in lines[i]:
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>")
                for c in row_cells:
                    out.append(f"<td>{_inline(c)}</td>")
                out.append("</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        # Heading
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            close_list()
            close_blockquote()
            level = len(m.group(1))
            text = _inline(m.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Horizontal rule (--- or ***)
        if re.match(r"^\s*(---|\*\*\*|___)\s*$", line):
            close_list()
            close_blockquote()
            out.append('<div class="paws-divider">&#x1F43E; &#x1F43E; &#x1F43E;</div>')
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            close_list()
            if not in_blockquote:
                out.append("<blockquote>")
                in_blockquote = True
            content = re.sub(r"^>\s?", "", line)
            if content.strip():
                out.append(f"<p>{_inline(content)}</p>")
            i += 1
            continue
        else:
            if in_blockquote and line.strip() == "":
                close_blockquote()

        # Unordered list (- ...) or task list (- [ ] ... / - [x] ...)
        m = re.match(r"^(\s*)-\s+(\[[ xX]\]\s+)?(.*)$", line)
        if m:
            close_blockquote()
            if in_list != "ul":
                close_list()
                out.append("<ul>")
                in_list = "ul"
            content = m.group(3)
            if m.group(2):  # task list marker
                checked = "x" in m.group(2).lower()
                box = (
                    '<span style="font-family:Menlo,monospace; color:var(--butterscotch); margin-right:6px;">'
                    + ("[x]" if checked else "[ ]")
                    + "</span>"
                )
                out.append(f"<li>{box}{_inline(content)}</li>")
            else:
                out.append(f"<li>{_inline(content)}</li>")
            i += 1
            continue

        # Ordered list (1. ...)
        m = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if m:
            close_blockquote()
            if in_list != "ol":
                close_list()
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        # Blank line
        if line.strip() == "":
            close_list()
            close_blockquote()
            i += 1
            continue

        # Plain paragraph: accumulate consecutive non-empty, non-list, non-heading lines
        close_list()
        close_blockquote()
        para = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip() != ""
            and not lines[i].startswith("#")
            and not lines[i].startswith(">")
            and not lines[i].startswith("```")
            and not re.match(r"^\s*-\s+", lines[i])
            and not re.match(r"^\s*\d+\.\s+", lines[i])
            and not re.match(r"^\s*(---|\*\*\*|___)\s*$", lines[i])
            and not (
                "|" in lines[i]
                and i + 1 < len(lines)
                and re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", lines[i + 1])
            )
        ):
            para.append(lines[i])
            i += 1
        joined = " ".join(p.strip() for p in para)
        out.append(f"<p>{_inline(joined)}</p>")

    close_list()
    close_blockquote()
    return "\n".join(out)


def cover_block(meta: str) -> str:
    return f"""<div class="cover">
  <h1>Cats</h1>
  <div class="cover-subtitle">A Day in the Life</div>
  <div class="cover-paws">&#x1F43E; &#x1F43E; &#x1F43E;</div>
  <p class="cover-hook">A trick-taking, pile-building card game about household cats and the four things they actually care about: territory, naps, snacks, and attention. Nine rounds. One day. One small, dignified disaster.</p>
  <div class="cover-meta">{meta}</div>
</div>"""


def build() -> str:
    src = MD.read_text(encoding="utf-8")

    # Strip the first H1 + hook paragraph from the body — we use them in the cover block.
    # The H1 is "# Cats: A Day in the Life"; the cover_block has its own.
    lines = src.split("\n")
    # find first "## 2." or "## " line — keep everything from there.
    start_idx = 0
    for idx, ln in enumerate(lines):
        if ln.startswith("## 2."):
            start_idx = idx
            break

    body_md = "\n".join(lines[start_idx:])
    body_html = convert_markdown(body_md)

    # Wrap §13 (quickref) in a special box. We detect it by the heading text and re-inject.
    # Look for "<h2>13. Quick Reference …</h2>" and add page-break + box.
    body_html = re.sub(
        r"(<h2>13\.[^<]*</h2>)",
        r'<div class="page-break"></div><div class="quickref">\1',
        body_html,
        count=1,
    )
    # Close the box just before the §14 Credits heading.
    body_html = re.sub(
        r"(<h2>14\.[^<]*</h2>)",
        r'</div><div class="page-break"></div>\1',
        body_html,
        count=1,
    )

    # Wrap §14 contents in a credits div: from <h2>14. Credits</h2> to end of file.
    body_html = re.sub(
        r"(<h2>14\.[^<]*</h2>)(.*)$",
        lambda m: '<div class="credits">' + m.group(1) + m.group(2) + "</div>",
        body_html,
        count=1,
        flags=re.DOTALL,
    )

    # Add page-breaks before §3, §6, §9, §10, §11 to spread content across the print page count.
    for section in ("3.", "6.", "9.", "10.", "11."):
        body_html = re.sub(
            rf"(<h2>{re.escape(section)}[^<]*</h2>)",
            r'<div class="page-break"></div>\1',
            body_html,
            count=1,
        )

    cover = cover_block("For 2 players &nbsp;·&nbsp; ~15 minutes &nbsp;·&nbsp; Ages 8+")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Cats — A Day in the Life</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,700;1,400&family=Fraunces:ital,wght@0,400;0,500;0,700;1,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>
<div class="wrapper">
{cover}
{body_html}
</div>
</body>
</html>
"""
    return doc


def main() -> None:
    html_doc = build()
    HTML_OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {HTML_OUT} ({len(html_doc)} bytes)")


if __name__ == "__main__":
    main()
