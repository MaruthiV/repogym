import ast
import re
import subprocess
from collections import Counter
from pathlib import Path

CHARS_PER_TOKEN = 4
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist"}
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".go", ".md", ".toml", ".cfg", ".yaml", ".yml"}
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "in", "on", "of", "to", "and", "or", "not",
    "it", "this", "that", "with", "for", "when", "should", "fix", "bug", "issue",
    "error", "fails", "failing", "works", "instead", "please", "using",
}


def repo_files(root: Path) -> list[Path]:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in SOURCE_EXTS \
                and not any(part in SKIP_DIRS for part in p.parts):
            files.append(p)
    return files


def prompt_keywords(prompt: str, top: int = 12) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", prompt)
    # split camelCase and snake_case into extra terms
    expanded = list(words)
    for w in words:
        expanded += re.findall(r"[A-Z]?[a-z]+", w)
    counts = Counter(w.lower() for w in expanded if w.lower() not in STOPWORDS)
    return [w for w, _ in counts.most_common(top)]


def render(files: list[tuple[Path, str]], budget_tokens: int) -> str:
    budget = budget_tokens * CHARS_PER_TOKEN
    parts, used = [], 0
    for path, text in files:
        block = f"### {path}\n```\n{text}\n```\n"
        if used + len(block) > budget:
            remaining = budget - used - 200
            if remaining > 500:
                parts.append(f"### {path} (truncated)\n```\n{text[:remaining]}\n```\n")
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


class FullContext:
    name = "full"

    def build(self, root: Path, prompt: str, budget_tokens: int) -> str:
        # smallest files first so more of the repo fits
        files = sorted(repo_files(root), key=lambda p: p.stat().st_size)
        return render([(p.relative_to(root), p.read_text(errors="replace")) for p in files],
                      budget_tokens)


class BM25Context:
    name = "bm25"
    k1 = 1.5
    b = 0.75

    def build(self, root: Path, prompt: str, budget_tokens: int) -> str:
        terms = prompt_keywords(prompt)
        docs = []
        for p in repo_files(root):
            text = p.read_text(errors="replace")
            docs.append((p, text, Counter(re.findall(r"[a-z0-9_]+", text.lower()))))
        n = len(docs) or 1
        avgdl = sum(sum(c.values()) for _, _, c in docs) / n
        scored = []
        for p, text, counts in docs:
            dl = sum(counts.values()) or 1
            score = 0.0
            for t in terms:
                tf = counts.get(t, 0)
                if not tf:
                    continue
                df = sum(1 for _, _, c in docs if t in c)
                idf = max(0.01, (n - df + 0.5) / (df + 0.5))
                import math
                score += math.log(1 + idf) * tf * (self.k1 + 1) / \
                    (tf + self.k1 * (1 - self.b + self.b * dl / avgdl))
            scored.append((score, p, text))
        scored.sort(key=lambda x: -x[0])
        return render([(p.relative_to(root), text) for s, p, text in scored if s > 0],
                      budget_tokens)


class GraphContext:
    name = "graph"

    def build(self, root: Path, prompt: str, budget_tokens: int) -> str:
        # seed with bm25 top hits, expand one hop along python imports
        files = [p for p in repo_files(root) if p.suffix == ".py"]
        modmap = {}
        for p in files:
            mod = ".".join(p.relative_to(root).with_suffix("").parts)
            modmap[mod] = p
            if mod.endswith(".__init__"):
                modmap[mod.removesuffix(".__init__")] = p

        def imports_of(p: Path) -> set[Path]:
            out = set()
            try:
                tree = ast.parse(p.read_text(errors="replace"))
            except SyntaxError:
                return out
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    for mod, path in modmap.items():
                        if mod == name or mod.endswith("." + name) or name.endswith(mod):
                            out.add(path)
            return out

        terms = set(prompt_keywords(prompt))
        seeds = []
        for p in files:
            text = p.read_text(errors="replace").lower()
            hits = sum(text.count(t) for t in terms)
            if hits:
                seeds.append((hits, p))
        seeds.sort(key=lambda x: -x[0])
        picked: list[Path] = []
        seen = set()
        for _, p in seeds[:5]:
            if p not in seen:
                picked.append(p)
                seen.add(p)
            for dep in imports_of(p):
                if dep not in seen:
                    picked.append(dep)
                    seen.add(dep)
        return render([(p.relative_to(root), p.read_text(errors="replace")) for p in picked],
                      budget_tokens)


class GrepContext:
    name = "grep"

    def build(self, root: Path, prompt: str, budget_tokens: int) -> str:
        terms = prompt_keywords(prompt, top=6)
        hits: Counter = Counter()
        for t in terms:
            r = subprocess.run(["rg", "-l", "-i", t], cwd=root, capture_output=True, text=True)
            for line in r.stdout.splitlines():
                hits[line] += 1
        ranked = [root / f for f, _ in hits.most_common() if (root / f).suffix in SOURCE_EXTS]
        return render([(p.relative_to(root), p.read_text(errors="replace")) for p in ranked],
                      budget_tokens)


PROVIDERS = {c.name: c for c in [FullContext(), BM25Context(), GraphContext(), GrepContext()]}
