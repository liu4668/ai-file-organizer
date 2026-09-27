"""Preview-first, reversible file organizer. Python standard library only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

KINDS = {
    "Images": "jpg jpeg png webp gif tif tiff bmp svg",
    "Design": "psd ai indd fig xd sketch",
    "CAD": "rvt dwg dxf",
    "3D": "skp blend fbx obj 3ds max 3dm",
    "Documents": "pdf doc docx txt md rtf",
    "Spreadsheets": "xls xlsx csv",
    "Presentations": "ppt pptx",
    "Archives": "zip rar 7z",
    "Software": "exe msi dmg pkg",
    "Video": "mp4 mov avi mkv webm",
    "Audio": "mp3 wav aac flac",
    "Code": "py js ts html css json yaml yml rb java cpp c cs",
}
EXT_KIND = {ext: kind for kind, extensions in KINDS.items() for ext in extensions.split()}
PROJECT_SUBDIRS = {"CAD": "Drawings", "3D": "Models", "Images": "References", "Documents": "Documents", "Spreadsheets": "Documents", "Presentations": "Deliverables", "Design": "Deliverables"}
TYPE_WORDS = {"Images": "Image", "Documents": "Document", "Spreadsheets": "Spreadsheet", "Presentations": "Presentation", "Design": "Design", "CAD": "Drawing", "3D": "Model", "Video": "Video", "Audio": "Audio", "Code": "Code", "Archives": "Archive", "Software": "Installer", "Review": "Review"}
KEYWORDS = {"render": "Render", "效果图": "Render", "screenshot": "Screenshot", "截图": "Screenshot", "report": "Report", "报告": "Report", "contract": "Contract", "合同": "Contract", "论文": "Paper", "drawing": "Drawing", "图纸": "Drawing", "model": "Model", "模型": "Model", "cover": "Cover", "封面": "Cover"}
VERSION_RE = re.compile(r"(?:^|[\s_.-])v0*(\d+)(?:$|[\s_.-])|(?:final|最终版|修改版|new|copy|副本)\s*0*(\d*)(?:$|[\s_.-])", re.I)
STOP_WORDS = {"final", "new", "copy", "report", "render", "model", "image", "document", "screenshot", "img", "最终版", "修改版", "副本", "报告", "图纸", "模型", "效果图"}


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    config.setdefault("output_folder", "Organized")
    config.setdefault("rename_files", True)
    config.setdefault("detect_duplicates", True)
    config.setdefault("analyze_content", True)
    config.setdefault("recognize_versions", True)
    config.setdefault("dry_run_first", True)
    config.setdefault("ignore_directories", [".git", "node_modules", ".ai-file-organizer"])
    config.setdefault("ignore_extensions", [])
    config.setdefault("category_rules", {})
    config.setdefault("naming_rule", "{project}_{type}_{date}_{version}")
    if not config["dry_run_first"]:
        raise ValueError("dry_run_first must remain true")
    out = Path(config["output_folder"])
    if out.is_absolute() or ".." in out.parts or str(out) in ("", "."):
        raise ValueError("output_folder must be a relative child path")
    return config


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"[\s.]+", "_", value).strip("_ ")
    return value[:80] or "Unknown"


def content_hint(path: Path, kind: str) -> str:
    try:
        if kind == "Documents" and path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as z:
                data = z.read("word/document.xml")[:150000]
            root = ElementTree.fromstring(data)
            text = " ".join(e.text or "" for e in root.iter() if e.tag.endswith("}t"))
            return text[:3000]
        if kind == "Documents" and path.suffix.lower() == ".pdf":
            data = path.read_bytes()[:150000]
            if not data.startswith(b"%PDF"):
                return ""
            chunks = re.findall(rb"\(([^)]{3,120})\)\s*Tj", data)
            titles = re.findall(rb"/Title\s*\(([^)]{3,120})\)", data)
            return " ".join(c.decode("latin1", "ignore") for c in titles + chunks)[:3000]
        if kind in ("Documents", "Code", "Spreadsheets") and path.suffix.lower() in (".txt", ".md", ".rtf", ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".rb", ".java", ".cpp", ".c", ".cs", ".csv"):
            return path.read_bytes()[:12000].decode("utf-8-sig", "ignore")[:3000]
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        pass
    return ""


def image_dimensions(path: Path) -> str:
    try:
        with path.open("rb") as f:
            head = f.read(32)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "%dx%d" % struct.unpack(">II", head[16:24])
        if head[:3] == b"GIF":
            return "%dx%d" % struct.unpack("<HH", head[6:10])
        if head[:2] == b"\xff\xd8":
            with path.open("rb") as f:
                f.read(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2:
                        break
                    if marker[0] != 0xFF:
                        break
                    if marker[1] in (0xD8, 0xD9, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                        continue
                    raw = f.read(2)
                    if len(raw) < 2:
                        break
                    length = struct.unpack(">H", raw)[0]
                    if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3):
                        dimensions = f.read(5)
                        if len(dimensions) == 5:
                            height, width = struct.unpack(">HH", dimensions[1:])
                            return f"{width}x{height}"
                    f.seek(length - 2, 1)
    except (OSError, struct.error):
        pass
    return ""


def version(stem: str) -> str:
    match = VERSION_RE.search(stem)
    if not match:
        return ""
    num = match.group(1) or match.group(2) or "1"
    return f"V{int(num):02d}"


def project_name(rel: Path, stem: str, mode: str, configured: str = "") -> str:
    if configured:
        return slug(configured)
    if mode == "project" and len(rel.parts) > 1:
        return slug(rel.parts[0])
    parts = re.split(r"[_\s.-]+", stem)
    candidate = parts[0] if parts else ""
    if candidate and candidate.lower() not in STOP_WORDS and not re.fullmatch(r"(?:IMG|DSC|PXL)?\d+|V\d+|final\d*|new\d*|copy\d*", candidate, re.I) and len(candidate) > 2:
        return slug(candidate)
    return ""


def file_type(path: Path, kind: str, hint: str) -> str:
    source = path.stem + " " + hint[:500]
    for key, label in KEYWORDS.items():
        if key.lower() in source.lower():
            return label
    return TYPE_WORDS.get(kind, "Review")


def scan(root: Path, config: dict) -> list[Path]:
    files = []
    ignored = set(config["ignore_directories"]) | {".ai-file-organizer", Path(config["output_folder"]).parts[0]}
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ignored and not (Path(current) / d).is_symlink())
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file() or path.suffix.lower().lstrip(".") in config["ignore_extensions"]:
                continue
            files.append(path)
    return files


def reserve(target: Path, used: set[str]) -> Path:
    candidate = target
    i = 2
    while str(candidate).casefold() in used or candidate.exists():
        candidate = target.with_name(f"{target.stem}_{i:03d}{target.suffix}")
        i += 1
    used.add(str(candidate).casefold())
    return candidate


def build_plan(root: Path, config: dict, mode: str) -> dict:
    files = scan(root, config)
    hashes = {}
    by_size = defaultdict(list)
    for path in files:
        by_size[path.stat().st_size].append(path)
    if config["detect_duplicates"]:
        for group in by_size.values():
            if len(group) > 1:
                for path in group:
                    hashes[path] = digest(path)
    exact = {}
    seen_hash = {}
    for path in files:
        h = hashes.get(path)
        if h and h in seen_hash:
            exact[path] = seen_hash[h]
        elif h:
            seen_hash[h] = path
    possible = []
    by_stem = defaultdict(list)
    for path in files:
        normalized = VERSION_RE.sub("", path.stem).casefold().strip(" _.-")
        normalized = re.sub(r"(?:[ _.-]*(?:副本|copy)[ _.-]*\d*)$", "", normalized, flags=re.I)
        if not normalized and version(path.stem):
            normalized = "version_only"
        if normalized:
            by_stem[(normalized, path.suffix.casefold())].append(path)
    for group in by_stem.values():
        if len(group) > 1:
            for path in group[1:]:
                if path not in exact:
                    possible.append({"file": str(path.relative_to(root)), "similar_to": str(group[0].relative_to(root)), "reason": "same base name or version family; manual review"})
    entries = []
    used = set()
    counts = Counter()
    for path in files:
        rel = path.relative_to(root)
        ext = path.suffix.lower().lstrip(".")
        kind = config["category_rules"].get(ext, EXT_KIND.get(ext, "Review"))
        if not isinstance(kind, str) or not re.fullmatch(r"[\w -]{1,60}", kind):
            kind = "Review"
        hint = content_hint(path, kind) if config["analyze_content"] and mode != "quick" else ""
        typ = file_type(path, kind, hint) if mode != "quick" else TYPE_WORDS.get(kind, "Review")
        project = project_name(rel, path.stem, mode, config.get("project_name", "")) if mode != "quick" else ""
        if not project and hint:
            match = re.search(r"(?:project(?: name)?|项目名称|项目名)\s*[:：]\s*([\w\u4e00-\u9fff-]{3,50})", hint, re.I)
            if match:
                project = slug(match.group(1))
        if mode == "project" and not project:
            project = slug(root.name)
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")
        ver = version(path.stem) if config["recognize_versions"] else ""
        if mode == "duplicates":
            target = path
        else:
            if mode == "rename":
                folder = path.parent
            elif path in exact:
                folder = root / config["output_folder"] / "Duplicates" / "Exact"
            elif mode == "project":
                sub = PROJECT_SUBDIRS.get(kind, kind)
                if kind == "Images" and typ == "Render":
                    sub = "Renders"
                elif kind == "CAD":
                    sub = "Drawings"
                folder = root / config["output_folder"] / (project or "Review") / sub
            else:
                folder = root / config["output_folder"] / kind
            if config["rename_files"]:
                counts[(typ, date)] += 1
                fallback = f"{slug(typ)}_{date}_{counts[(typ, date)]:03d}"
                fields = {"project": project, "type": slug(typ), "date": date, "version": ver, "sequence": f"{counts[(typ, date)]:03d}"}
                try:
                    pattern = config["naming_rule"].format(**fields)
                except (KeyError, ValueError) as e:
                    raise ValueError(f"invalid naming_rule: {e}") from e
                stem = slug(re.sub(r"_+", "_", pattern.strip("_ "))) if project or config["naming_rule"] != "{project}_{type}_{date}_{version}" else fallback
                if ver and not project and config["naming_rule"] == "{project}_{type}_{date}_{version}":
                    stem += "_" + ver
                name = stem + path.suffix.lower()
            else:
                name = path.name
            target = path if folder / name == path else reserve(folder / name, used)
        entries.append({"old_path": str(path), "new_path": str(target), "old_name": path.name, "new_name": target.name, "size": path.stat().st_size, "sha256": hashes.get(path) or digest(path), "kind": kind, "type": typ, "project": project, "version": ver, "image_dimensions": image_dimensions(path) if kind == "Images" else "", "content_excerpt": hint[:160], "exact_duplicate_of": str(exact[path].relative_to(root)) if path in exact else ""})
    return {"schema": 1, "root": str(root), "mode": mode, "created_at": datetime.now().isoformat(timespec="seconds"), "entries": entries, "possible_duplicates": possible}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def duplicate_report(plan: dict) -> str:
    lines = ["# Duplicate report", "", "Exact matches use file size and SHA-256. Possible matches need human review. No files are deleted.", "", "## Exact", "", "| Original | Duplicate | Bytes | SHA-256 | Reason |", "|---|---|---:|---|---|"]
    for e in plan["entries"]:
        if e["exact_duplicate_of"]:
            lines.append(f'| {e["exact_duplicate_of"]} | {Path(e["old_path"]).relative_to(plan["root"])} | {e["size"]} | `{e["sha256"]}` | identical bytes |')
    lines += ["", "## Possible", "", "| Original | Possible duplicate | Reason |", "|---|---|---|"]
    for item in plan["possible_duplicates"]:
        lines.append(f'| {item["similar_to"]} | {item["file"]} | {item["reason"]} |')
    return "\n".join(lines) + "\n"


def report(plan: dict, stage: str) -> str:
    entries = plan["entries"]
    kinds = Counter(e["kind"] for e in entries)
    moved = [e for e in entries if e["old_path"] != e["new_path"]]
    renamed = sum(e["old_name"] != e["new_name"] for e in moved)
    exact = sum(bool(e["exact_duplicate_of"]) for e in entries)
    lines = [f"# Organizer {stage}", "", f'Mode: {plan["mode"]}', f'Files scanned: {len(entries)}', f'Planned or completed moves: {len(moved)}', f'Renamed: {renamed}', f'Exact duplicates: {exact}', f'Possible duplicates: {len(plan["possible_duplicates"])}', f'Review: {kinds["Review"]}', "", "## Categories", ""]
    lines += [f"- {key}: {value}" for key, value in sorted(kinds.items())]
    lines += ["", "## Before → After", ""]
    lines += [f'- `{Path(e["old_path"]).relative_to(plan["root"])}` → `{Path(e["new_path"]).relative_to(plan["root"])}`' for e in entries[:100]]
    if len(entries) > 100:
        lines.append(f"- ... {len(entries)-100} more; see plan.json")
    return "\n".join(lines) + "\n"


def preview(root: Path, config: dict, mode: str) -> dict:
    state = root / ".ai-file-organizer"
    plan = build_plan(root, config, mode)
    write_json(state / "plan.json", plan)
    (state / "organize_report.md").write_text(report(plan, "preview"), encoding="utf-8")
    (state / "duplicate_report.md").write_text(duplicate_report(plan), encoding="utf-8")
    return plan


def apply(root: Path, config: dict) -> dict:
    state = root / ".ai-file-organizer"
    plan = json.loads((state / "plan.json").read_text(encoding="utf-8"))
    if Path(plan["root"]).resolve() != root or plan["mode"] == "duplicates":
        raise ValueError("plan does not allow moves for this root")
    logpath = state / "organize_log.json"
    if logpath.exists() and json.loads(logpath.read_text(encoding="utf-8")).get("status") != "undone":
        raise ValueError("undo the prior run before applying another plan")
    moves = [e for e in plan["entries"] if e["old_path"] != e["new_path"]]
    for e in moves:
        old, new = Path(e["old_path"]), Path(e["new_path"])
        if not old.is_file() or old.is_symlink() or digest(old) != e["sha256"] or new.exists():
            raise ValueError(f"plan is stale or destination occupied: {old}")
        if root not in old.parents or root not in new.parents:
            raise ValueError("path escapes selected root")
        ancestor = new.parent
        while not ancestor.exists() and ancestor != root:
            ancestor = ancestor.parent
        if ancestor.is_symlink() or root not in ancestor.resolve().parents and ancestor.resolve() != root:
            raise ValueError(f"destination parent escapes selected root: {new}")
    log = {"schema": 1, "root": str(root), "status": "in_progress", "started_at": datetime.now().isoformat(timespec="seconds"), "entries": []}
    write_json(logpath, log)
    for e in moves:
        old, new = Path(e["old_path"]), Path(e["new_path"])
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            raise ValueError(f"destination became occupied: {new}")
        shutil.move(str(old), str(new))
        log["entries"].append({"old_path": str(old), "new_path": str(new), "old_name": old.name, "new_name": new.name, "sha256": e["sha256"], "action": "move_rename", "operated_at": datetime.now().isoformat(timespec="seconds")})
        write_json(logpath, log)
    log["status"] = "complete"
    write_json(logpath, log)
    (state / "organize_report.md").write_text(report(plan, "complete"), encoding="utf-8")
    return log


def undo(root: Path) -> dict:
    path = root / ".ai-file-organizer" / "organize_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    if Path(log["root"]).resolve() != root or log["status"] == "undone":
        raise ValueError("no active run to undo")
    failures = []
    for e in reversed(log["entries"]):
        if "undone_at" in e:
            continue
        old, new = Path(e["old_path"]), Path(e["new_path"])
        if old.exists():
            failures.append(f"original path occupied: {old}")
            continue
        if not new.is_file() or digest(new) != e["sha256"]:
            failures.append(f"moved file missing or changed: {new}")
            continue
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(new), str(old))
        e["undone_at"] = datetime.now().isoformat(timespec="seconds")
        write_json(path, log)
    log["status"] = "partial_undo" if failures else "undone"
    log["undo_failures"] = failures
    write_json(path, log)
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview-first file organizer")
    parser.add_argument("command", choices=["preview", "apply", "undo"])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--mode", choices=["quick", "smart", "project", "duplicates", "rename"], default="smart")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    root = args.folder.resolve()
    if not root.is_dir():
        parser.error(f"folder does not exist: {root}")
    try:
        config = read_config(args.config or Path(__file__).resolve().parent.parent / "organizer_config.json")
        if args.command == "preview":
            plan = preview(root, config, args.mode)
            kinds = Counter(e["kind"] for e in plan["entries"])
            print(f"整理预览：扫描 {len(plan['entries'])} 个文件；分类 {dict(kinds)}；计划重命名 {sum(e['old_name'] != e['new_name'] for e in plan['entries'])}；完全重复 {sum(bool(e['exact_duplicate_of']) for e in plan['entries'])}；疑似重复 {len(plan['possible_duplicates'])}。")
            print(f"预览：{root / '.ai-file-organizer' / 'organize_report.md'}")
            print("确认后运行 apply --confirm 确认执行整理")
        elif args.command == "apply":
            if args.confirm != "确认执行整理":
                raise ValueError("apply requires --confirm 确认执行整理")
            log = apply(root, config)
            print(f"整理完成：处理 {len(log['entries'])} 个文件。日志：{root / '.ai-file-organizer' / 'organize_log.json'}")
        else:
            log = undo(root)
            print(f"撤销结果：{log['status']}；恢复 {sum('undone_at' in e for e in log['entries'])} 个；失败 {len(log['undo_failures'])} 个。")
            for failure in log["undo_failures"]:
                print(failure)
            return 1 if log["undo_failures"] else 0
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
