"""Audit utilities: run manifest, environment capture, and hashing.

This module helps produce a reproducible "paper trail" for each simulation run:
- capture Python/environment/package versions
- compute hashes for inputs (files or in-memory JSON)
- write a manifest.json alongside outputs
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import hashlib
import json
import os
import platform
import subprocess
import sys


def _sha256_bytes(data: bytes) -> str:
	"""Compute SHA-256 for raw bytes (hex)."""
	h = hashlib.sha256()
	h.update(data)
	return h.hexdigest()


def sha256_file(path: str | Path) -> Optional[str]:
	"""Compute SHA-256 for a file, if it exists; else None."""
	p = Path(path)
	if not p.exists() or not p.is_file():
		return None
	h = hashlib.sha256()
	with p.open("rb") as f:
		for chunk in iter(lambda: f.read(8192), b""):
			h.update(chunk)
	return h.hexdigest()


def sha256_json(obj: Any) -> str:
	"""Compute SHA-256 for a JSON-serializable object (stable ordering)."""
	data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
	return _sha256_bytes(data)


def get_git_commit(root: str | Path | None = None) -> Optional[str]:
	"""Return current Git commit SHA if available, else None."""
	try:
		res = subprocess.run(
			["git", "rev-parse", "HEAD"],
			cwd=str(root or Path(__file__).resolve().parents[1]),
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
			text=True,
			check=True,
		)
		sha = res.stdout.strip()
		return sha if sha else None
	except Exception:
		return None


def capture_env_info(extra_packages: Iterable[str] = ("numpy", "pandas", "streamlit")) -> Dict[str, Any]:
	"""Capture environment versions (Python, platform, selected packages)."""
	info: Dict[str, Any] = {
		"python": {
			"version": sys.version,
			"executable": sys.executable,
		},
		"platform": {
			"system": platform.system(),
			"release": platform.release(),
			"version": platform.version(),
			"machine": platform.machine(),
			"processor": platform.processor(),
		},
		"packages": {},
	}
	# Try to capture afc_new version if any
	try:
		import importlib.metadata as md  # py3.8+
		for name in ["afc_new", *extra_packages]:
			try:
				info["packages"][name] = md.version(name)  # type: ignore
			except Exception:
				# Fall back to import and getattr __version__ if present
				try:
					mod = __import__(name)
					v = getattr(mod, "__version__", None)
					info["packages"][name] = (v if v is not None else "unknown")
				except Exception:
					info["packages"][name] = "unknown"
	except Exception:
		pass
	return info


def make_run_manifest(
	*,
	run_tag: str,
	spec_path: str | Path | None = None,
	incumbents_path: str | Path | None = None,
	incumbents_data_digest: str | None = None,
	args: Dict[str, Any],
	outputs: Dict[str, str] | None = None,
	notes: str | None = None,
) -> Dict[str, Any]:
	"""Build a manifest dictionary describing a simulation run."""
	manifest: Dict[str, Any] = {
		"run_tag": run_tag,
		"git_commit": get_git_commit(),
		"environment": capture_env_info(),
		"inputs": {
			"spec_path": str(spec_path) if spec_path else None,
			"spec_sha256": sha256_file(spec_path) if spec_path else None,
			"incumbents_path": str(incumbents_path) if incumbents_path else None,
			"incumbents_sha256": sha256_file(incumbents_path) if incumbents_path else None,
			"incumbents_data_digest": incumbents_data_digest,
		},
		"arguments": args,
		"outputs": outputs or {},
		"notes": notes or "",
	}
	return manifest


def write_manifest(out_dir: str | Path, manifest: Dict[str, Any], filename: str) -> Path:
	"""Write manifest JSON to out_dir/filename, return path."""
	out = Path(out_dir)
	out.mkdir(parents=True, exist_ok=True)
	p = out / filename
	with p.open("w", encoding="utf-8") as f:
		json.dump(manifest, f, indent=2, ensure_ascii=False)
	return p


def verify_files_exist(paths: Iterable[str | Path]) -> Dict[str, bool]:
	"""Return a map of path -> exists flag for quick integrity checks."""
	result: Dict[str, bool] = {}
	for p in paths:
		pp = Path(p)
		result[str(pp)] = pp.exists() and pp.is_file() and (pp.stat().st_size > 0)
	return result


