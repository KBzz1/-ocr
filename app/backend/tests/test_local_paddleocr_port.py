import os
import sys
import textwrap

import pytest

from app.backend.services.algorithm_ports.local_paddleocr import (
    LocalPaddleOCRDocumentPort,
    parse_paddleocr_markdown,
)


def test_parse_paddleocr_markdown_splits_pages_by_filename():
    markdown = """
# 001_page-a.jpg

第一页 OCR 文本

---

# 002_page-b.png

第二页 OCR 文本
"""

    parsed = parse_paddleocr_markdown(markdown)

    assert parsed == {
        "001_page-a.jpg": "第一页 OCR 文本",
        "002_page-b.png": "第二页 OCR 文本",
    }


def test_parse_paddleocr_markdown_ignores_non_page_preamble():
    markdown = "识别完成\n\n# 001_page-a.jpg\n\n正文\n\n---\n"

    assert parse_paddleocr_markdown(markdown) == {"001_page-a.jpg": "正文"}


def test_parse_paddleocr_markdown_keeps_body_headings_when_expected_names_are_given():
    markdown = "# 001_page-a.jpg\n\n# 入院记录\n\n正文\n\n---\n"

    parsed = parse_paddleocr_markdown(markdown, expected_names={"001_page-a.jpg"})

    assert parsed == {"001_page-a.jpg": "# 入院记录\n\n正文"}


def test_local_paddleocr_port_runs_script_and_returns_document_result(tmp_path):
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            args = parser.parse_args()

            images = sorted(Path(args.input_dir).iterdir())
            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                "\\n\\n---\\n\\n".join(
                    f"# {image.name}\\n\\nOCR text for {image.name}" for image in images
                ),
                encoding="utf-8",
            )
            """
        ),
        encoding="utf-8",
    )
    source_1 = tmp_path / "source-a.jpg"
    source_2 = tmp_path / "source-b.png"
    source_1.write_bytes(b"image-a")
    source_2.write_bytes(b"image-b")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [
                {"page_id": "page_b", "page_no": 2, "processed_path": str(source_2)},
                {"page_id": "page_a", "page_no": 1, "processed_path": str(source_1)},
            ],
        }
    )

    assert result["merged_text"] == "OCR text for 001_page_a.jpg\n\nOCR text for 002_page_b.png"
    assert result["pages"] == [
        {
            "page_id": "page_a",
            "page_no": 1,
            "status": "success",
            "text": "OCR text for 001_page_a.jpg",
            "blocks": [],
            "tables": [],
            "source": "local_paddleocr_vl",
        },
        {
            "page_id": "page_b",
            "page_no": 2,
            "status": "success",
            "text": "OCR text for 002_page_b.png",
            "blocks": [],
            "tables": [],
            "source": "local_paddleocr_vl",
        },
    ]


def test_local_paddleocr_port_marks_missing_page_output_failed(tmp_path):
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            args = parser.parse_args()

            first = sorted(Path(args.input_dir).iterdir())[0]
            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(f"# {first.name}\\n\\nOnly first page", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    source_1 = tmp_path / "source-a.jpg"
    source_2 = tmp_path / "source-b.png"
    source_1.write_bytes(b"image-a")
    source_2.write_bytes(b"image-b")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [
                {"page_id": "page_a", "page_no": 1, "processed_path": str(source_1)},
                {"page_id": "page_b", "page_no": 2, "processed_path": str(source_2)},
            ],
        }
    )

    assert result["pages"][0]["status"] == "success"
    assert result["pages"][1]["status"] == "failed"
    assert result["pages"][1]["error_message"] == "OCR 输出缺少该页结果"


def test_local_paddleocr_port_rejects_missing_script(tmp_path):
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(tmp_path / "missing.py"),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
    )

    with pytest.raises(RuntimeError, match="OCR runner 不存在"):
        port.parse({"task_id": "task_001", "pages": []})
