---
name: ai-file-organizer
description: Preview, classify, rename, check duplicates, and reversibly organize a local folder from natural-language instructions or a JSON config. Use when the user asks to organize files, inspect duplicates, or undo this workflow's last run.
---

# AI 文件整理工作流

Use `scripts/organizer.py` to scan local files. Translate the user's natural language into one of five modes: `quick` (format only), `smart` (name, format, readable content), `project` (project folders), `duplicates` (report only), or `rename` (keep directory structure). Adapt a copy of `organizer_config.json` for user supplied categories, naming, output folder, ignored paths, and project name.

1. Identify the exact target folder. If it is ambiguous, ask the user. Never assume their Downloads or current project path.
2. Run `py -3 scripts/organizer.py preview <folder> --mode <mode> [--config <config>]`. Read `.ai-file-organizer/organize_report.md`, `.ai-file-organizer/duplicate_report.md`, and `plan.json`. Improve uncertain project or content labels in config and regenerate the preview when evidence supports it. Never invent content facts.
3. Show counts and representative old → new paths. Ask for the exact confirmation **“确认执行整理”** before changing real files. A prior request to create or test this skill is not confirmation to organize a separate real folder.
4. On confirmation, run `py -3 scripts/organizer.py apply <folder> --confirm 确认执行整理`. Report the concise result and the report/log locations.
5. For “撤销上一次整理”, run `py -3 scripts/organizer.py undo <folder>`. Report any file that could not be restored and why.

The script never deletes or overwrites. Exact duplicates are moved to `Duplicates/Exact` only during an approved organizing run; possible duplicates stay in their category and are listed for review. `duplicates` mode creates only reports. Unknown extensions use `Review`. The standard library reads text, basic PDF text, DOCX text, and PNG/GIF/JPEG dimensions; visual similarity and deep proprietary format analysis require separate available tools and should be described as unavailable when absent. The agent may inspect files with available visual/document tools to refine a preview, but must not claim the script itself made those judgments.

See `README.md` for CLI and configuration details.
