# 字段状态管理与确认校验

> 对应 PRD: PR-FE-006 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 字段状态管理与确认校验
  作为 医生
  我想要 清楚了解每个字段的审核状态
  以便 确保所有字段都经过审核后再确认

  Scenario: 所有字段状态使用中文标签展示
    Given 审核页中有 unreviewed、confirmed、modified、suspicious、empty、confirmed_empty 状态的字段
    When 我查看字段列表
    Then 各字段应分别显示 "未审核"、"已确认"、"已修改"、"存疑"、"为空"、"空值已确认"

  Scenario: 统计栏实时展示各类状态的字段数量
    Given 审核页中含有：
      | 状态     | 数量 |
      | 未审核   | 3    |
      | 存疑     | 1    |
      | 为空     | 2    |
      | 已确认   | 5    |
    When 我查看统计栏
    Then 应该显示 "未审核: 3"、"存疑: 1"、"为空: 2"、"已确认: 5"

  Scenario: 所有字段为已确认或已修改时直接提交
    Given 审核页中所有字段状态均为 confirmed 或 modified
    When 我点击 "确认审核"
    Then 应该直接调用 POST /api/tasks/{taskId}/review/confirm
    And 不应弹出提示弹窗

  Scenario: 有未审核字段时确认前弹出预警提示
    Given 审核页中有 2 个未审核字段
    When 我点击 "确认审核"
    Then 应该弹出预警窗，显示 "还有 2 个字段未审核，是否继续？"
    And 弹窗应有 "继续确认" 和 "取消" 按钮

  Scenario: 有存疑字段时确认前弹出预警提示
    Given 审核页中有 1 个存疑字段
    When 我点击 "确认审核"
    Then 应该弹出预警窗，显示 "还有 1 个字段标记为存疑，是否继续？"

  Scenario: 取消确认弹窗后不调用 confirm API
    Given 审核页中有未审核字段
    When 我点击 "确认审核"
    And 在弹窗中点击 "取消"
    Then 不应该调用 confirm API
    And 审核页保持可编辑状态

  Scenario: 在提示弹窗中选择继续后提交确认
    Given 审核页中有未审核字段
    When 我点击 "确认审核"
    And 在弹窗中点击 "继续确认"
    Then 应该调用 POST /api/tasks/{taskId}/review/confirm
    And 任务状态应更新为 "已确认"

  Scenario: 为空字段可显式确认为空值可接受
    Given 审核页中 "婚育史" 字段状态为 "为空"
    When 我点击该字段旁的 "确认空值" 操作
    Then 系统应该调用字段保存 API 并标记空值已确认
    And 字段状态应变为 "空值已确认"
    And 该字段不再被记入确认阻断项

  Scenario: 空值已确认字段在导出时不阻断
    Given 审核页中所有未审核字段已确认
    And 有 1 个 "空值已确认" 字段
    When 我点击 "确认审核"
    Then 不应该因空值字段阻断确认
    And 确认审核应该正常完成

  Scenario: confirm API 返回校验失败时展示具体问题
    Given 后端 confirm API 返回 REVIEW_VALIDATION_FAILED
    And 返回的问题字段列表为 ["主诉不能为空", "初步诊断未审核"]
    When 我点击 "确认审核"
    Then 我应该看到校验失败提示
    And 应该列出 "主诉不能为空" 和 "初步诊断未审核"
```
