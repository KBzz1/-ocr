import json
import os
import tempfile


class JsonStore:
    """基于本地目录的 JSON 文件读写工具。

    - 路径安全：relative_path 校验，拒绝 ../ 越权和绝对路径
    - 原子写入：先写 .tmp 临时文件，再 os.replace
    - 目录自动创建
    """

    def __init__(self, base_dir: str):
        self._base_dir = os.path.abspath(base_dir)
        os.makedirs(self._base_dir, exist_ok=True)

    def _resolve(self, relative_path: str) -> str:
        """校验并返回安全的绝对路径。"""
        if os.path.isabs(relative_path):
            raise ValueError(f"路径越权: 不允许绝对路径 {relative_path}")

        resolved = os.path.normpath(os.path.join(self._base_dir, relative_path))
        if not resolved.startswith(self._base_dir + os.sep) and resolved != self._base_dir:
            raise ValueError(f"路径越权: {relative_path}")

        return resolved

    def read(self, relative_path: str, default=None):
        filepath = self._resolve(relative_path)
        if not os.path.isfile(filepath):
            return default
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def write(self, relative_path: str, data):
        filepath = self._resolve(relative_path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=os.path.dirname(filepath),
                prefix=f".{os.path.basename(filepath)}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_file = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, filepath)
        finally:
            if tmp_file and os.path.exists(tmp_file):
                os.remove(tmp_file)

    def delete(self, relative_path: str):
        filepath = self._resolve(relative_path)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass

    def exists(self, relative_path: str) -> bool:
        filepath = self._resolve(relative_path)
        return os.path.isfile(filepath)

    def list_json(self, relative_dir: str):
        directory = self._resolve(relative_dir)
        if not os.path.isdir(directory):
            return []

        items = []
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(relative_dir, name)
            items.append(self.read(path))
        return items
