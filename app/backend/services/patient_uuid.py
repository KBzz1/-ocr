"""患者编号 UUID helper。

把 uuid4 包装在一个独立小模块里,便于测试 monkeypatch 替换。
"""
from uuid import uuid4 as _uuid4


def uuid4():
    return _uuid4()
