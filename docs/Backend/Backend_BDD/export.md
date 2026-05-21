# 导出服务

> 对应 PRD: PR-BE-009 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 导出服务
  作为 医生
  我想要 将审核后的结构化结果导出为 Excel 或 JSON
  以便 用于人工流转或后续系统集成

  Scenario: 导出前完整性检查
    Given 任务 T001 处于 review 或 done 状态
    When 我请求 GET /api/tasks/T001/export/check
    Then 应返回未审核字段、可疑字段、空值字段和无来源字段统计
    And 如存在风险字段，应返回 warning 标记但不阻断导出

  Scenario: 用户确认风险后导出 JSON 文件
    Given 任务 T001 处于 review 或 done 状态
    And 前端已展示完整性检查预警并由用户确认继续
    When 我请求 GET /api/tasks/T001/export/json
    Then 应返回 JSON 下载响应和正确的文件名
    And 字段值应来自人工审核的 final_value
    And 字段顺序应与 schema 定义一致

  Scenario: 用户确认风险后导出 Excel 文件
    Given 任务 T001 处于 review 或 done 状态
    And 前端已展示完整性检查预警并由用户确认继续
    When 我请求 GET /api/tasks/T001/export/excel
    Then 应返回 Excel 下载响应和正确的文件名
    And 字段值应来自人工审核结果而非自动抽取值

  Scenario: 导出文件保存到独立目录
    Given 任务 T001 已导出 JSON 和 Excel
    When 我检查文件系统
    Then 导出文件应保存在 T001 的 exports/ 目录中
    And 不应与其他任务的文件混合

  Scenario: 导出成功后记录导出信息
    Given 任务 T001 尚未导出
    When 导出成功完成
    Then 系统应记录导出时间、导出格式和文件路径
    And 不应引入独立 exported 任务状态

  Scenario: 导出失败不影响已审核数据
    Given 任务 T001 在导出过程中发生文件系统写入错误
    When 导出失败
    Then 系统应返回错误码 EXPORT_FAILED
    And 任务审核结果和任务状态不应被修改
```
