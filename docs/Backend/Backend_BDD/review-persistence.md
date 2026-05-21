# 人工审核结果保存

> 对应 PRD: PR-BE-008 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 人工审核结果保存
  作为 医生
  我想要 在电脑端审核结构化字段并保存修改
  以便 修改痕迹被完整保留，且自动抽取原值不被覆盖

  Scenario: 首次获取审核结果时生成初始记录
    Given 任务 T001 已进入 review 状态
    When 电脑端请求 GET /api/tasks/T001/review
    Then 系统应基于字段结果生成初始审核记录
    And 每个字段的人工审核状态应为 unreviewed
    And 每个字段的 final_value 应等于自动抽取值或空值

  Scenario: 字段级风险元数据随审核结果展示
    Given 字段结果包含未抽取、可疑、复核失败或 OCR 纠偏信息
    When 电脑端请求审核结果
    Then 审核页应能展示这些风险提示
    And 风险提示不应覆盖人工 final_value

  Scenario: 修改字段值并保存
    Given 任务 T001 的某字段已有自动抽取值
    When 医生修改该字段并保存
    Then 系统应保存人工 final_value
    And 自动抽取原值和证据信息应保留
    And 该字段人工审核状态应变更为 modified

  Scenario: 确认字段
    Given 任务 T001 的字段处于 unreviewed 状态
    When 医生点击确认该字段
    Then 该字段人工审核状态应变更为 confirmed

  Scenario: 多次修改保留历史
    Given 任务 T001 的字段已被修改多次
    When 我查询该字段的修改历史
    Then 应返回每次修改前后的值和修改时间

  Scenario: 审核完成后任务进入 done
    Given 任务 T001 处于 review 状态
    When 医生确认审核完成
    Then 任务状态应变更为 done

  Scenario: 失败任务不可确认
    Given 任务 T001 处于 failed 状态
    When 医生尝试确认任务
    Then 系统应返回错误，指示任务处理失败不可审核
```
