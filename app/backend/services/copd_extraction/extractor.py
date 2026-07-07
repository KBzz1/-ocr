import threading

from ...errors import AppError, ErrorCode


def _raise_if_cancelled(token) -> None:
    """批次之间检查取消 token;若 set 则抛 REEXTRACTION_CANCELLED。

    Token 是任意带 ``is_set()`` 的对象(实际是 threading.Event)。单次 in-flight
    LLM 调用本身不可中断,这里只能让链路在下一个批次边界停下。
    """
    if token is None:
        return
    if getattr(token, "is_set", lambda: False)():
            raise AppError(
                ErrorCode.REEXTRACTION_CANCELLED,
                message="用户取消重新处理",
                details={"reason": "user_cancelled"},
            )
