import sys
import subprocess
import textwrap
import time

import pytest

from app.backend.services.algorithm_ports import local_paddleocr
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
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
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


def test_local_paddleocr_port_emits_runner_diagnostic_events(tmp_path):
    events = []
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
            args = parser.parse_args()

            first = sorted(Path(args.input_dir).iterdir())[0]
            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(f"# {first.name}\\n\\nOCR text", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    port.parse(
        {
            "task_id": "task_001",
            "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
        }
    )

    event_names = [event for event, _ in events]
    assert event_names == ["ocr_runner_started", "ocr_runner_finished"]
    assert events[0][1]["task_id"] == "task_001"
    assert events[0][1]["page_count"] == 1
    assert events[0][1]["python_executable"] == sys.executable
    assert events[0][1]["script_path"] == str(runner)
    assert events[0][1]["max_new_tokens"] == 1024
    assert events[0][1]["max_pixels"] == 501760
    assert events[0][1]["input_files"][0]["filename"] == "001_page_a.jpg"
    assert events[0][1]["input_files"][0]["bytes"] == 7
    assert events[1][1]["exit_code"] == 0
    assert events[1][1]["output_exists"] is True


def test_local_paddleocr_port_scales_timeout_by_page_count(tmp_path, monkeypatch):
    events = []
    observed_timeout = None
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text("raise SystemExit('should be monkeypatched')", encoding="utf-8")
    sources = []
    for page_no in range(1, 4):
        source = tmp_path / f"source-{page_no}.jpg"
        source.write_bytes(f"image-{page_no}".encode("utf-8"))
        sources.append(source)

    def fake_run(command, cwd, env, timeout, is_cancelled):
        nonlocal observed_timeout
        observed_timeout = timeout
        output = tmp_path / "ocr-runs" / "task_001" / "output" / "all_results.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "\n\n---\n\n".join(
                f"# {page_no:03d}_page_{page_no}.jpg\n\nOCR text {page_no}"
                for page_no in range(1, 4)
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(local_paddleocr, "_run_with_process_group_timeout", fake_run)
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    port.parse(
        {
            "task_id": "task_001",
            "pages": [
                {"page_id": f"page_{page_no}", "page_no": page_no, "processed_path": str(source)}
                for page_no, source in enumerate(sources, start=1)
            ],
        }
    )

    assert observed_timeout == 30
    assert events[0][1]["timeout_seconds"] == 30


def test_local_paddleocr_port_emits_failure_diagnostic_event_on_nonzero_exit(tmp_path):
    events = []
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import sys

            print("runner stdout before failure")
            print("runner stderr before failure", file=sys.stderr)
            raise SystemExit(7)
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=10,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    with pytest.raises(RuntimeError, match="exit_code=7"):
        port.parse(
            {
                "task_id": "task_001",
                "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
            }
        )

    event_names = [event for event, _ in events]
    assert event_names == ["ocr_runner_started", "ocr_runner_finished", "ocr_runner_failed"]
    assert events[2][1]["exit_code"] == 7
    assert "runner stdout before failure" in events[2][1]["stdout_tail"]
    assert "runner stderr before failure" in events[2][1]["stderr_tail"]


def test_local_paddleocr_port_timeout_kills_child_process_group(tmp_path):
    marker = tmp_path / "child-survived.txt"
    runner = tmp_path / "spawns_child_then_hangs.py"
    runner.write_text(
        textwrap.dedent(
            f"""
            import subprocess
            import sys
            import time

            subprocess.Popen([
                sys.executable,
                "-c",
                "import pathlib,time; time.sleep(1.2); pathlib.Path({str(marker)!r}).write_text('alive')",
            ])
            time.sleep(10)
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=1,
    )

    with pytest.raises(RuntimeError, match="执行超时"):
        port.parse(
            {
                "task_id": "task_001",
                "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
            }
        )

    time.sleep(1.5)
    assert not marker.exists()


def test_local_paddleocr_port_does_not_block_when_runner_writes_large_stderr(tmp_path):
    runner = tmp_path / "writes_large_stderr.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            import sys
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
            args = parser.parse_args()

            sys.stderr.write("x" * (1024 * 1024 * 2))
            sys.stderr.flush()
            first = sorted(Path(args.input_dir).iterdir())[0]
            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(f"# {first.name}\\n\\nOCR text", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    events = []
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        timeout_seconds=3,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
        }
    )

    assert result["pages"][0]["text"] == "OCR text"
    assert events[-1][0] == "ocr_runner_finished"
    assert events[-1][1]["stderr_tail"].endswith("x" * 100)


def test_local_paddleocr_port_passes_cache_home_to_runner(tmp_path):
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            import os
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
            args = parser.parse_args()

            cache_home = os.environ["PADDLE_PDX_CACHE_HOME"]
            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            first = sorted(Path(args.input_dir).iterdir())[0]
            output.write_text(f"# {first.name}\\n\\n{cache_home}", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    cache_dir = tmp_path / "shared-cache"
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        cache_dir=str(cache_dir),
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
        }
    )

    assert result["pages"][0]["text"] == str(cache_dir)


def test_local_paddleocr_port_passes_device_to_runner(tmp_path):
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
            parser.add_argument("--device")
            args = parser.parse_args()

            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            first = sorted(Path(args.input_dir).iterdir())[0]
            output.write_text(f"# {first.name}\\n\\n{args.device}", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        device="gpu:0",
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
        }
    )

    assert result["pages"][0]["text"] == "gpu:0"


def test_local_paddleocr_port_passes_generation_limits_to_runner(tmp_path):
    runner = tmp_path / "fake_ocr_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--input-dir")
            parser.add_argument("--output-file")
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
            args = parser.parse_args()

            output = Path(args.output_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            first = sorted(Path(args.input_dir).iterdir())[0]
            output.write_text(
                f"# {first.name}\\n\\n{args.max_new_tokens}/{args.max_pixels}",
                encoding="utf-8",
            )
            """
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source-a.jpg"
    source.write_bytes(b"image-a")
    port = LocalPaddleOCRDocumentPort(
        python_executable=sys.executable,
        script_path=str(runner),
        work_root=str(tmp_path / "ocr-runs"),
        max_new_tokens=512,
        max_pixels=100000,
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task_001",
            "pages": [{"page_id": "page_a", "page_no": 1, "processed_path": str(source)}],
        }
    )

    assert result["pages"][0]["text"] == "512/100000"


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
            parser.add_argument("--max-new-tokens")
            parser.add_argument("--max-pixels")
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


def test_local_paddleocr_port_default_max_new_tokens_is_1024():
    port = LocalPaddleOCRDocumentPort(
        python_executable="python",
        script_path="runner.py",
        work_root="/tmp",
    )
    assert port._max_new_tokens == 1024
    assert port._max_pixels == 501760
    assert port._timeout_seconds == 180
