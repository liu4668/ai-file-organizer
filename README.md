# AI 文件整理工作流

入口：`scripts/organizer.py`。需要 Python 3.10+；Windows 推荐 `py -3`，macOS/Linux 用 `python3`。Codex 可按 `SKILL.md` 理解自然语言并选择模式；脚本也可直接运行。

```powershell
py -3 scripts/organizer.py preview test_files --mode smart
py -3 scripts/organizer.py apply test_files --confirm 确认执行整理
py -3 scripts/organizer.py undo test_files
py -3 scripts/organizer.py preview test_files --mode duplicates
py -3 scripts/organizer.py preview test_files --mode project
```

`preview` 在目标目录的 `.ai-file-organizer/` 写入 `plan.json`、`organize_report.md` 和 `duplicate_report.md`。检查后才能执行 `apply`。执行生成 `organize_log.json`；如日志仍代表未撤销的整理，先撤销才能执行另一计划。`undo` 只恢复日志记录且哈希未变化的文件；被修改、丢失或原路径已被占用的文件会明确列出。

配置见 `organizer_config.json`。可通过 `--config` 传入自定义 JSON。`category_rules` 以不带点的扩展名映射到分类名；`naming_rule` 可用 `{project}`、`{type}`、`{date}`、`{version}`、`{sequence}`。`project_name` 可显式指定项目。`quick` 只按格式分类；`smart` 加入文件名和可读取内容；`project` 建立项目下的 Drawings、Models、Renders、References、Documents、Deliverables 等目录；`duplicates` 只输出报告；`rename` 保持目录结构。

内容分析是保守的：PDF 只尝试提取简单文本和标题，DOCX 读取 XML，文本和代码读取前段内容，PNG/GIF/JPEG 读取尺寸。无法可靠识别的内容不会被强行推断；未知格式进入 Review。疑似重复基于文件名及版本族，视觉相似度需另行人工或视觉工具判断。完全重复使用大小和 SHA-256。原文件内容不修改，也不执行删除。
