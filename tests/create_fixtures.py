"""Create tiny simulated files for logic tests only."""
from pathlib import Path

NAMES = ["IMG_001.jpg", "IMG_002.jpg", "Screenshot_20260928.png", "final.psd", "final2.psd", "最终版3.psd", "报告.pdf", "报告副本.pdf", "project.zip", "setup.exe", "model.skp", "model2.skp"]


def create(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        data = ("test fixture: " + name).encode("utf-8")
        if name == "报告.pdf":
            data = b"%PDF-1.1\n1 0 obj<</Title (Project Report)>>endobj\n"
        elif name == "报告副本.pdf":
            data = b"%PDF-1.1\n1 0 obj<</Title (Project Report)>>endobj\n"
        elif name == "Screenshot_20260928.png":
            data = bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001")
        (root / name).write_bytes(data)


if __name__ == "__main__":
    create(Path(__file__).resolve().parent.parent / "test_files")
