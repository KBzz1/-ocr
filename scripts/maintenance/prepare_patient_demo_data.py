#!/usr/bin/env python3
"""一次性开发数据整理脚本: 把现有测试任务收敛到一个可见任务,绑定到"测试用例"患者。

仅在开发环境使用,运行要求:
- 必须显式传 --storage-dir 和 --keep-task-id
- 必须传 --confirm-dev-data 才允许 --apply
- 默认 dry-run;只有 --apply 才修改文件
- 输出只显示任务 ID、患者 ID、计数;不输出病历内容
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def _ensure_repo_root():
    """把仓库根加入 sys.path,使 'app' 模块可导入。"""
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


_ensure_repo_root()

from app.backend.storage.json_store import JsonStore  # noqa: E402

DEV_BANNER = "DEV TOOL ONLY"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _iter_task_ids(store):
    return [item.get("task_id") for item in store.list_json("tasks") if isinstance(item, dict)]


def _read_patient(store, patient_id):
    return store.read(f"patients/{patient_id}.json")


def _write_patient(store, patient_id, record):
    store.write(f"patients/{patient_id}.json", record)


def prepare_demo_data(
    *,
    storage_dir,
    keep_task_id,
    record_date,
    apply=False,
    patient_name="测试用例",
    now_provider=None,
):
    """整理开发数据;返回变更摘要 dict。

    - keep_task_id 必填且必须存在
    - 其他任务设置 deleted_at (逻辑删除),文件保留
    - 保留任务补充 document_type="copd_admission_record" 和 record_date
    - 创建"测试用例"患者并把保留任务的 patient_id 指向该患者
    - 重复运行幂等
    """
    store = JsonStore(storage_dir)
    now_provider = now_provider or _now_iso
    if not store.exists(f"tasks/{keep_task_id}.json"):
        raise SystemExit(f"保留任务不存在: tasks/{keep_task_id}.json")

    tasks = _iter_task_ids(store)
    if not tasks:
        raise SystemExit("存储目录中没有任何任务")

    hidden_count = 0
    kept = None
    for tid in tasks:
        path = f"tasks/{tid}.json"
        record = store.read(path)
        if not isinstance(record, dict):
            continue
        if str(record.get("task_id")) == str(keep_task_id):
            kept = record
            continue
        if record.get("deleted_at"):
            continue
        if apply:
            record["deleted_at"] = now_provider()
            record["updated_at"] = record["deleted_at"]
            store.write(path, record)
        hidden_count += 1

    if kept is None:
        raise SystemExit(f"保留任务读取失败: {keep_task_id}")

    # 找到或创建"测试用例"患者
    patient = None
    for record in [store.read(p) for p in [item for item in []] if False]:  # placeholder
        pass
    # 实际查询:扫 patients 目录
    for item in store.list_json("patients"):
        if isinstance(item, dict) and item.get("name") == patient_name and not item.get("deleted_at"):
            patient = item
            break

    if patient is None:
        from app.backend.services.patient_service import PatientService

        if apply:
            service = PatientService(store, now=now_provider)
            patient = service.create(patient_name)
        else:
            patient = {"patient_id": "P-XXXXXXXX", "name": patient_name}

    # 补全保留任务的归属和元数据
    if apply:
        kept["patient_id"] = patient["patient_id"]
        kept["patient_snapshot"] = {
            "patient_id": patient["patient_id"],
            "name": patient.get("name"),
        }
        if not kept.get("document_type"):
            kept["document_type"] = "copd_admission_record"
        if not kept.get("document_type_label"):
            kept["document_type_label"] = "入院记录"
        kept["record_date"] = record_date
        if not kept.get("record_time"):
            kept["record_time"] = None
        if not kept.get("deleted_at"):
            kept["deleted_at"] = None
        kept["updated_at"] = now_provider()
        store.write(f"tasks/{keep_task_id}.json", kept)

    return {
        "kept_task_id": keep_task_id,
        "patient_id": patient.get("patient_id"),
        "hidden_task_count": hidden_count,
        "applied": apply,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=DEV_BANNER)
    parser.add_argument("--storage-dir", required=True)
    parser.add_argument("--keep-task-id", required=True)
    parser.add_argument("--record-date", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-dev-data", action="store_true")
    args = parser.parse_args(argv)

    print(DEV_BANNER, file=sys.stderr)
    if args.apply and not args.confirm_dev_data:
        parser.error("--apply 必须配合 --confirm-dev-data 才允许写入")

    summary = prepare_demo_data(
        storage_dir=args.storage_dir,
        keep_task_id=args.keep_task_id,
        record_date=args.record_date,
        apply=args.apply,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
