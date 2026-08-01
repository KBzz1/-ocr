"""金标提炼辅助工具（一次性）：OCR 差异清单 + 章节切分。

用法:
    python scripts/maintenance/extract_golden_helpers.py --case 1 --action diff
    python scripts/maintenance/extract_golden_helpers.py --case 1 --action sections
"""
import argparse
import difflib
import re
from pathlib import Path

GROUND_TRUTH_DIR = Path("data/text_data/ground_truth")
OCR_RESULTS_DIR = Path("data/text_data/ocr_results")

SECTION_TITLES = [
    "主诉", "现病史", "既往史", "个人史", "婚育史", "月经史", "家族史",
    "体温", "辅助检查", "初步诊断", "最后诊断",
]


def load_pair(case: int) -> tuple[str, str]:
    gt = (GROUND_TRUTH_DIR / f"{case}.txt").read_text(encoding="utf-8")
    ocr = (OCR_RESULTS_DIR / f"{case}.txt").read_text(encoding="utf-8")
    return gt, ocr


def print_diff(case: int) -> None:
    gt, ocr = load_pair(case)
    matcher = difflib.SequenceMatcher(None, gt, ocr, autojunk=False)
    print(f"=== case_{case} OCR 差异清单（金标原文 → OCR 读成） ===")
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        left = gt[i1:i2].replace("\n", "⏎")
        right = ocr[j1:j2].replace("\n", "⏎")
        print(f"- 原文「{left[:60]}」 → OCR「{right[:60]}」")


def print_sections(case: int) -> None:
    gt, _ = load_pair(case)
    lines = gt.splitlines()
    print(f"=== case_{case} 章节切分 ===")
    for title in SECTION_TITLES:
        for i, line in enumerate(lines):
            if re.match(rf"^{re.escape(title)}[:：]", line):
                print(f"\n## {title}\n")
                print(line)
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="金标提炼辅助工具")
    parser.add_argument("--case", type=int, required=True, help="病历编号 1..6")
    parser.add_argument("--action", choices=["diff", "sections"], required=True)
    args = parser.parse_args()
    if args.action == "diff":
        print_diff(args.case)
    else:
        print_sections(args.case)


if __name__ == "__main__":
    main()
