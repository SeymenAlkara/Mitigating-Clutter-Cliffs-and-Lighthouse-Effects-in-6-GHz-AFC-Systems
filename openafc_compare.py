from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Iterable
import re
import difflib
from datetime import datetime


INTEREST_PATTERNS = [
	# path loss / propagation
	r"\bfspl\b", r"free[_\- ]?space", r"winner2", r"\bwinner\b", r"\bitm\b", r"longley", r"path[_\- ]?loss",
	# antenna / RPE
	r"\brpe\b", r"f\.?1245", r"f\.?699", r"antenna[_\- ]?pattern", r"boresight", r"azimuth", r"elevation",
	# ACIR / masks
	r"\bacir\b", r"\baclr\b", r"\bacs\b", r"adjacent[_\- ]?channel", r"mask",
	# noise / EIRP / PSD
	r"noise[_\- ]?figure", r"noise[_\- ]?power", r"\beirp\b", r"\bpsd\b",
	# aggregate / INR
	r"\binr\b", r"interference[_\- ]?to[_\- ]?noise", r"aggregate[_\- ]?interference",
]

OUR_TARGET_FILES = [
	"afc_new/propagation.py",
	"afc_new/itm.py",
	"afc_new/antenna.py",
	"afc_new/antenna_rpe.py",
	"afc_new/acir_masks.py",
	"afc_new/acir.py",
	"afc_new/aggregate.py",
	"afc_new/link_budget.py",
	"afc_new/grant_table.py",
	"afc_new/recipes.py",
]


def _read_text(p: Path) -> str:
	try:
		return p.read_text(encoding="utf-8", errors="replace")
	except Exception:
		return ""


def _collect_files(root: Path, exts: Iterable[str] = (".py", ".cpp", ".cc", ".cxx", ".hpp", ".h")) -> List[Path]:
	paths: List[Path] = []
	for ext in exts:
		paths.extend(root.rglob(f"*{ext}"))
	return paths


def _filter_interesting(files: List[Path], patterns: List[str]) -> Dict[Path, List[str]]:
	rxs = [re.compile(pat, flags=re.IGNORECASE) for pat in patterns]
	out: Dict[Path, List[str]] = {}
	for p in files:
		txt = _read_text(p)
		if not txt:
			continue
		for rx in rxs:
			if rx.search(txt):
				out[p] = txt.splitlines()
				break
	return out


def _diff_text(a_lines: List[str], b_lines: List[str], a_label: str, b_label: str) -> str:
	diff = difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label, lineterm="")
	return "\n".join(diff)


def _our_sources(project_root: Path) -> Dict[Path, List[str]]:
	srcs: Dict[Path, List[str]] = {}
	for rel in OUR_TARGET_FILES:
		p = project_root / rel
		if p.exists():
			srcs[p] = _read_text(p).splitlines()
	return srcs


def _best_match(openafc_file: Path, our_sources: Dict[Path, List[str]]) -> Tuple[Path | None, float]:
	# heuristic: match by keyword overlap
	open_txt = "\n".join(_read_text(openafc_file).splitlines())
	best = (None, 0.0)
	for p, lines in our_sources.items():
		txt = "\n".join(lines)
		seq = difflib.SequenceMatcher(a=open_txt, b=txt)
		ratio = seq.quick_ratio()
		if ratio > best[1]:
			best = (p, ratio)
	return best


def compare_codebases(openafc_root: Path, report_out: Path) -> Path:
	openafc_root = Path(openafc_root)
	report_out = Path(report_out)
	report_out.mkdir(parents=True, exist_ok=True)

	# Collect and filter openAFC sources
	engine_dir = openafc_root / "src" / "afc-engine"
	models_dir = openafc_root / "src" / "afc-packages" / "afcmodels" / "afcmodels"
	candidates = []
	if engine_dir.exists():
		candidates += _collect_files(engine_dir)
	if models_dir.exists():
		candidates += _collect_files(models_dir)

	open_hits = _filter_interesting(candidates, INTEREST_PATTERNS)

	# Our sources
	project_root = Path(__file__).resolve().parents[1]
	our_srcs = _our_sources(project_root)

	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	report = report_out / f"openafc_compare_{ts}.md"

	sections: List[str] = []
	sections.append(f"# openAFC vs afc_new comparison ({ts})")
	sections.append("")
	sections.append(f"- openAFC root: `{openafc_root}`")
	sections.append(f"- Engine dir exists: {engine_dir.exists()}")
	sections.append(f"- Models dir exists: {models_dir.exists()}")
	sections.append("")

	if not open_hits:
		sections.append("No interesting files found under the provided openAFC path. Check the path and try again.")
	else:
		sections.append(f"Found {len(open_hits)} openAFC files with relevant keywords.\n")

	for ofile, olines in sorted(open_hits.items()):
		best_p, ratio = _best_match(ofile, our_srcs)
		sections.append(f"## File: `{ofile}`")
		if best_p is None:
			sections.append(f"- No close match in our sources (similarity={ratio:.2f}).")
			continue
		sections.append(f"- Closest in our code: `{best_p}` (similarity={ratio:.2f})")
		sections.append("")
		sections.append("```diff")
		sections.append(_diff_text(olines, our_srcs[best_p], str(ofile), str(best_p)))
		sections.append("```")
		sections.append("")

	report.write_text("\n".join(sections), encoding="utf-8")
	return report


