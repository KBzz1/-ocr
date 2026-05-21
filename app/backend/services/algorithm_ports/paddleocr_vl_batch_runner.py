from argparse import ArgumentParser
from pathlib import Path

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


def recognize_images(pipeline: PaddleOCRVL, image_paths: list[Path]) -> list[tuple[Path, str]]:
    image_results = []
    for image_path in image_paths:
        output = pipeline.predict(input=str(image_path))
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

    pipeline = PaddleOCRVL()
    write_merged_markdown(recognize_images(pipeline, image_paths), output_file)


if __name__ == "__main__":
    main()
