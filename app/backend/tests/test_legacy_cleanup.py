"""Task 11 清理旧版小字段抽取路径的契约测试。

这些测试在 Task 1-10 完成后的清理阶段必须通过；任何旧版小字段路径
（copd_admission_record.v1.yaml、build_extraction_prompt、build_section_group_
extraction_prompt、build_source_hint_regeneration_prompt、STRATEGY_SECTION_GROUPS、
SECTION_GROUPS、section_splitter、COPDFieldExtractor / COPDFieldPort / _LazyCOPD
FieldPort、legacy 小字段 key）都不应再出现在活动抽取代码与配置中。
"""

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCHEMA_PATH = (
    REPO_ROOT
    / "app"
    / "config"
    / "schemas"
    / "copd_admission_record.v1.yaml"
)
LEGACY_FIELD_KEYS = (
    "copd_history_years",
    "blood_gas_pao2",
    "blood_gas_paco2",
    "ct_features",
    "positive_signs",
    "maintenance_therapy",
    "dyspnea_grade_mMRC",
)


def test_legacy_small_field_schema_file_removed():
    """旧 copd_admission_record.v1.yaml 文件必须已删除。"""
    assert not LEGACY_SCHEMA_PATH.exists(), (
        f"旧版小字段 schema 仍存在: {LEGACY_SCHEMA_PATH}；Task 11 要求删除。"
    )


def _scan_active_files() -> list[Path]:
    """枚举活动代码与配置扫描范围。"""
    backend_root = REPO_ROOT / "app" / "backend"
    config_root = REPO_ROOT / "app" / "config"
    scanned: list[Path] = []
    for subdir in ("services/copd_extraction", "services/algorithm_ports"):
        root = backend_root / subdir
        if root.is_dir():
            for path in root.rglob("*.py"):
                if path.is_file():
                    scanned.append(path)
    init_path = backend_root / "__init__.py"
    if init_path.is_file():
        scanned.append(init_path)
    if config_root.is_dir():
        for path in config_root.rglob("*"):
            if path.is_file():
                scanned.append(path)
    return scanned


def test_active_code_no_longer_mentions_old_small_field_keys():
    """活动代码与配置不应再出现旧版小字段 key。"""
    offenders: list[tuple[Path, str, str]] = []
    this_file = Path(__file__).resolve()
    for path in _scan_active_files():
        if path.resolve() == this_file:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for legacy_key in LEGACY_FIELD_KEYS:
            if legacy_key in text:
                offenders.append((path, legacy_key, "active_code_match"))
    assert not offenders, (
        "以下活动代码或配置仍包含旧版小字段 key:\n"
        + "\n".join(
            f"  {path}: 旧 key={legacy_key}"
            for path, legacy_key, _ in offenders
        )
    )


def test_active_prompt_module_no_longer_exports_legacy_free_key_builders():
    """新 prompts.py 不应再导出旧版自由 key builder，但必须保留新 builder。"""
    from app.backend.services.copd_extraction import prompts

    forbidden = (
        "build_extraction_prompt",
        "build_section_group_extraction_prompt",
        "build_source_hint_regeneration_prompt",
    )
    for name in forbidden:
        assert not hasattr(prompts, name), (
            f"prompts 模块仍导出旧版 builder {name}；Task 11 要求删除。"
        )

    assert hasattr(prompts, "build_admission_structured_fields_prompt"), (
        "prompts 模块必须保留新固定字段 builder build_admission_structured_fields_prompt。"
    )
    assert hasattr(prompts, "ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION"), (
        "prompts 模块必须保留新固定字段版本常量 ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION。"
    )


def test_active_extraction_port_does_not_reference_section_group_strategy():
    """port.py 与 extractor.py 必须不再引用 SECTION_GROUPS 策略或 source_hint 旧元数据。"""
    active_files = [
        REPO_ROOT / "app" / "backend" / "services" / "copd_extraction" / "port.py",
        REPO_ROOT / "app" / "backend" / "services" / "copd_extraction" / "extractor.py",
    ]
    forbidden_substrings = (
        "STRATEGY_SECTION_GROUPS",
        "SECTION_GROUPS",
        "source_hint",
        "evidence_phrase",
    )
    offenders: list[tuple[Path, str]] = []
    for path in active_files:
        text = path.read_text(encoding="utf-8")
        for substr in forbidden_substrings:
            if substr in text:
                offenders.append((path, substr))
    assert not offenders, (
        "port.py / extractor.py 仍引用旧版 SECTION_GROUPS 策略或旧元数据：\n"
        + "\n".join(f"  {path}: 含 {substr}" for path, substr in offenders)
    )


def test_legacy_section_splitter_module_removed():
    """section_splitter.py 必须已删除：活动路径按 schema + evidence units 抽取。"""
    splitter_path = (
        REPO_ROOT
        / "app"
        / "backend"
        / "services"
        / "copd_extraction"
        / "section_splitter.py"
    )
    assert not splitter_path.exists(), (
        f"旧 section_splitter.py 仍存在: {splitter_path}；Task 11 要求删除。"
    )
