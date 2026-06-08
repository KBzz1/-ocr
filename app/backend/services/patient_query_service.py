"""患者中心查询服务。

聚合 PatientService 和 TaskService:
- list_patients(query):返回每个未删除患者的任务计数和最近记录时间
- get_detail(patient_id):返回患者基本信息和按记录类型分组、按时间倒序的任务时间轴

不复制审核字段契约,审核字段按需通过审核接口获取。
"""
from typing import Iterable


class PatientQueryService:
    def __init__(self, patient_service, task_service):
        self._patient_service = patient_service
        self._task_service = task_service

    def list_patients(self, query: str | None = None) -> list[dict]:
        patients = self._patient_service.list(query)
        result = []
        for record in patients:
            public = self._patient_service.to_public(record)
            tasks = self._task_service.list_for_patient(record["patient_id"])
            public["task_count"] = len(tasks)
            public["latest_record_at"] = self._compute_latest_record_at(tasks)
            result.append(public)
        return result

    def get_detail(self, patient_id: str) -> dict:
        record = self._patient_service.get(patient_id)
        patient_public = self._patient_service.to_public(record)
        tasks = self._task_service.list_for_patient(patient_id)
        return {
            "patient": patient_public,
            "record_groups": self._group_tasks(tasks),
        }

    def _group_tasks(self, tasks: Iterable[dict]) -> list[dict]:
        groups: dict[str, dict] = {}
        for task in tasks:
            doc_type = task.get("document_type") or ""
            doc_label = task.get("document_type_label") or doc_type
            group = groups.setdefault(
                doc_type,
                {"document_type": doc_type, "document_type_label": doc_label, "tasks": []},
            )
            group["tasks"].append(task)

        # 同一组内排序:按 record_date 倒序;同一天有时间记录在仅日期记录之前;
        # record_date/record_time 相同则用 task_id 做稳定 tie-breaker。
        for group in groups.values():
            group["tasks"].sort(key=self._task_sort_key, reverse=True)

        # 组之间排序:按该组最近记录时间倒序
        ordered = sorted(
            groups.values(),
            key=lambda g: self._task_sort_key(g["tasks"][0]) if g["tasks"] else ("", "", ""),
            reverse=True,
        )
        return ordered

    @staticmethod
    def _task_sort_key(task: dict) -> tuple[str, str, int | str]:
        # 时间字段缺失时使用空字符串,空字符串小于任意 "HH:mm",
        # 倒序排时仅日期记录排在带时间记录之后,满足 spec。
        task_id = str(task.get("task_id") or "")
        task_id_key: int | str = int(task_id) if task_id.isdigit() else task_id
        return (task.get("record_date") or "", task.get("record_time") or "", task_id_key)

    @staticmethod
    def _compute_latest_record_at(tasks: list[dict]) -> str | None:
        if not tasks:
            return None
        latest = max(tasks, key=PatientQueryService._task_sort_key)
        date = latest.get("record_date")
        if not date:
            return None
        time = latest.get("record_time")
        if time:
            return f"{date}T{time}"
        return date
