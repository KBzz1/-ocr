# 字段状态管理与确认

> 对应 PRD: PR-FE-004 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 字段状态管理与确认
  作为 医生
  我想要 清楚了解每个字段的人工审核状态和自动抽取风险
  以便 快速完成核验、修正和确认

  Scenario: 人工审核状态使用中文标签展示
    Given 审核页中有 unreviewed、confirmed、modified 状态的字段
    When 我查看字段列表
    Then 各字段应分别显示 "未审核"、"已确认"、"已修改"

  Scenario: 每个可审核字段都有确认入口
    Given 审核页中同时存在普通文本字段、判定字段和 "未提及" 字段
    When 我查看字段列表
    Then 每个字段都应该有独立的确认勾选框
    And 判定字段的确认勾选框应位于 "正常/异常/未提及" 判定框内部
    And 普通文本字段和 "未提及" 字段的确认勾选框应与字段值右侧对齐

  Scenario: 自动抽取风险作为字段元数据展示
    Given 后端返回字段 extraction_status、verification_status 和 quality_flags
    When 我查看字段列表
    Then 前端应展示未抽取、可疑、复核失败或质量风险提示
    And 这些提示不应替代人工审核状态

  Scenario: 修改字段后状态变为已修改
    Given 审核页中 "主诉" 字段状态为 unreviewed
    When 我修改该字段值并保存
    Then 字段状态应变为 modified
    And 自动抽取原值仍可追溯

  Scenario: 统一审核并完成时未修改字段变为已确认
    Given 审核页中有未修改的 unreviewed 字段
    When 我点击 "统一审核并完成"
    Then 未修改字段应提交为 confirmed
    And 已修改字段保持 modified
    And 任务状态应更新为 done

  Scenario: 保存 API 返回校验失败时展示具体问题
    Given 后端保存 API 返回 REVIEW_VALIDATION_FAILED
    And 返回的问题字段列表为 ["主诉不能为空"]
    When 我保存审核结果
    Then 我应该看到校验失败提示
    And 应该列出 "主诉不能为空"
```
