# 导出服务

> 对应 PRD: PR-BE-009 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 导出服务
  作为 医生
  我想要 将审核确认后的结构化结果导出为 Excel 或 JSON
  以便 用于人工流转或后续系统集成

  Scenario: 导出前完整性检查
    Given 任务 T001 处于 confirmed 状态
    When 我请求 GET /api/tasks/T001/export/check
    Then 应返回未审核字段数、存疑字段数、空值字段数和无来源字段数

  Scenario: 未确认任务拒绝导出
    Given 任务 T001 处于 ready_for_review 状态
    When 我请求导出
    Then 系统应返回 400 和错误码 EXPORT_VALIDATION_FAILED
    And 错误信息应提示 "任务尚未确认"

  Scenario: 导出 JSON 文件
    Given 任务 T001 处于 confirmed 状态且导出检查通过
    When 我请求 GET /api/tasks/T001/export/json
    Then 应返回 JSON 下载响应和正确的文件名
    And JSON 结构应包含任务编号、导出时间、schema 版本
    And 字段值应来自人工审核的 final_value
    And 每个字段应包含审核状态标记
    And 字段顺序应与 schema 定义一致

  Scenario: 导出 Excel 文件
    Given 任务 T001 处于 confirmed 状态且导出检查通过
    When 我请求 GET /api/tasks/T001/export/excel
    Then 应返回 Excel 下载响应和正确的文件名
    And Excel 应按字段组分 sheet 组织
    And 每个字段应包含字段名、final_value、审核状态
    And 字段值应来自人工审核结果而非自动抽取值

  Scenario: 导出文件保存到独立目录
    Given 任务 T001 已导出 JSON 和 Excel
    When 我检查文件系统
    Then 导出文件应保存在 T001 的 exports/ 目录中
    And 不应与其他任务的文件混合

  Scenario: 导出成功后更新任务状态
    Given 任务 T001 尚未导出
    When 导出成功完成
    Then 任务状态应变为 exported
    And 导出记录应包含导出时间、导出格式和文件路径

  Scenario: 导出失败不影响已审核数据
    Given 任务 T001 在导出过程中发生文件系统写入错误
    When 导出失败
    Then 系统应返回错误码 EXPORT_FAILED
    And 任务审核结果和 confirmed 状态不应被修改
```
