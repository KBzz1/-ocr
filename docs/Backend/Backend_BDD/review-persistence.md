# 人工审核结果保存

> 对应 PRD: PR-BE-008 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 人工审核结果保存
  作为 医生
  我想要 在电脑端审核结构化字段并保存修改
  以便 修改痕迹被完整保留，且自动抽取原值不被覆盖

  Scenario: 首次获取审核结果时生成初始记录
    Given 任务 T001 已完成处理，字段候选已生成
    When 电脑端请求 GET /api/tasks/T001/review
    Then 系统应基于外部模块的字段候选生成初始审核记录
    And 每个字段的审核状态应为 unreviewed
    And 每个字段的 final_value 应等于 original_value

  Scenario: 修改字段值并保存
    Given 任务 T001 的字段 "主诉" 原值为 "头痛3天"
    When 医生修改为 "头痛3天加重1天" 并保存
    Then 系统应保存 final_value 为 "头痛3天加重1天"
    And original_value 应保留为 "头痛3天"
    And 该字段状态应变更为 modified

  Scenario: 确认字段
    Given 任务 T001 的字段 "主诉" 处于 unreviewed 状态
    When 医生点击确认该字段
    Then 该字段状态应变更为 confirmed

  Scenario: 标记字段存疑
    Given 任务 T001 的字段 "初步诊断" 抽取值不确定
    When 医生标记该字段为存疑
    Then 该字段状态应变更为 suspicious

  Scenario: 清空字段
    Given 任务 T001 的字段 "辅助检查" 原值为空或不可信
    When 医生清空该字段值
    Then 该字段状态应变更为 empty
    And final_value 应为空

  Scenario: 多次修改保留历史
    Given 任务 T001 的字段 "主诉" 已被修改 3 次
    When 我查询该字段的修改历史
    Then 应返回每次修改前后的值、修改时间和操作人

  Scenario: 再次打开任务显示人工结果
    Given 任务 T001 的字段已被医生修改并保存
    When 重新打开任务并请求审核结果
    Then 应优先返回人工 final_value 而非自动抽取 original_value

  Scenario: 审核结果与自动结果分开存储
    Given 任务 T001 的字段已被人工修改
    When 我查询自动抽取结果
    Then 仍应能获取到原始的自动抽取候选值
    And 人工审核结果不应覆盖自动抽取结果文件

  Scenario: 确认任务前进行完整性校验
    Given 任务 T001 仍有 2 个字段为 unreviewed，1 个字段为 suspicious
    When 医生尝试确认任务 POST /api/tasks/T001/confirm
    Then 系统应返回 400 和错误码 REVIEW_VALIDATION_FAILED
    And 响应应列出所有未审核、存疑和空值字段

  Scenario: 完整性校验通过后确认任务
    Given 任务 T001 所有字段均已确认（confirmed、modified 或确认可接受的 empty）
    When 医生确认任务
    Then 任务状态应变更为 confirmed
    And 确认时间应被记录

  Scenario: 失败任务不可确认
    Given 任务 T001 处于 failed 状态
    When 医生尝试确认任务
    Then 系统应返回错误，指示任务处理失败不可审核
```
