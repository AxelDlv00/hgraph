"""Small lexical scanner for source statistics and display, not elaboration.

Masks preserve offsets and newlines. Nested comments, doc comments, strings,
raw strings, character literals and quoted identifiers are distinguished so
comment text cannot become a declaration or an admission.
"""

from dataclasses import dataclass
import re


@dataclass
class LeanSource:
    code: str
    without_comments: str
    without_docstrings: str
    docs: list[tuple[int, int]]


def scan_lean(text: str) -> LeanSource:
    code = list(text)
    comments = list(text)
    docstrings = list(text)
    docs = []

    def mask(buf, start, end):
        buf[start:end] = ["\n" if c == "\n" else " " for c in text[start:end]]

    i = 0
    while i < len(text):
        start = i
        if text.startswith("--", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            mask(code, start, i)
            mask(comments, start, i)
        elif text.startswith("/-", i):
            is_doc = text.startswith(("/--", "/-!"), i)
            depth = 1
            i += 2
            while i < len(text) and depth:
                if text.startswith("/-", i):
                    depth += 1
                    i += 2
                elif text.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            mask(code, start, i)
            mask(comments, start, i)
            if is_doc:
                mask(docstrings, start, i)
                docs.append((start, i))
        elif text[i] == '"' or (text[i] == 'r' and re.match(r'r#+"|r"', text[i:i + 64])):
            raw = re.match(r'r(#+|)"', text[i:]) if text[i] == 'r' else None
            if raw:
                ending = '"' + raw.group(1)
                end = text.find(ending, i + raw.end())
                i = len(text) if end < 0 else end + len(ending)
            else:
                i += 1
                while i < len(text):
                    if text[i] == '\\':
                        i += 2
                    elif text[i] == '"':
                        i += 1
                        break
                    else:
                        i += 1
            mask(code, start, min(i, len(text)))
        elif text[i] == '«':
            end = text.find('»', i + 1)
            i = len(text) if end < 0 else end + 1
            mask(code, start, i)
        elif text[i] == "'" and (char := re.match(r"'(?:\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)|[^'\\\n])'", text[i:])):
            i += char.end()
            mask(code, start, i)
        else:
            i += 1
    return LeanSource("".join(code), "".join(comments), "".join(docstrings), docs)


def keyword_count(code: str, keyword: str) -> int:
    return len(re.findall(r"(?<![\w.'])" + re.escape(keyword) + r"(?![\w'.])", code))


def statement_prefix(body: str, kind: str) -> str:
    """Hide theorem proofs while retaining definition and structure bodies."""
    if kind not in {"theorem", "lemma"}:
        return body
    code = scan_lean(body).code
    depth = 0
    for i, char in enumerate(code):
        if char in "([{⦃":
            depth += 1
        elif char in ")]}⦄":
            depth = max(0, depth - 1)
        elif depth == 0 and (code.startswith(":=", i) or char == "|"):
            return body[:i].rstrip()
    return body
