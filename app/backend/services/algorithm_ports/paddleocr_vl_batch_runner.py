from argparse import ArgumentParser
import os
from pathlib import Path

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(Path.cwd() / "paddlex_cache"))
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from paddleocr import PaddleOCRVL


IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def collect_images(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def recognize_images(
    pipeline: PaddleOCRVL,
    image_paths: list[Path],
    max_new_tokens: int | None = None,
    max_pixels: int | None = None,
) -> list[tuple[Path, str]]:
    image_results = []
    for image_path in image_paths:
        predict_kwargs = {}
        if max_new_tokens is not None:
            predict_kwargs["max_new_tokens"] = max_new_tokens
        if max_pixels is not None:
            predict_kwargs["max_pixels"] = max_pixels
        output = pipeline.predict(input=str(image_path), **predict_kwargs)
        markdown_pages = [result.markdown for result in output]
        markdown_text = pipeline.concatenate_markdown_pages(markdown_pages)
        image_results.append((image_path, markdown_text))
    return image_results


def write_merged_markdown(image_results: list[tuple[Path, str]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as file:
        for image_path, markdown_text in image_results:
            file.write(f"# {image_path.name}\n\n")
            file.write(markdown_text.strip())
            file.write("\n\n---\n\n")


def parse_args():
    parser = ArgumentParser(description="批量识别目录中的图片，并合并输出为 Markdown 文件。")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--max-pixels", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)

    if not input_dir.exists():
        raise RuntimeError(f"输入目录不存在: {input_dir}")
    image_paths = collect_images(input_dir)
    if not image_paths:
        raise RuntimeError(f"输入目录中没有找到图片: {input_dir}")

    pipeline_kwargs = {}
    if args.device:
        pipeline_kwargs["device"] = args.device
    pipeline = PaddleOCRVL(**pipeline_kwargs)
    write_merged_markdown(
        recognize_images(
            pipeline,
            image_paths,
            max_new_tokens=args.max_new_tokens,
            max_pixels=args.max_pixels,
        ),
        output_file,
    )


if __name__ == "__main__":
    main()
