# 导出功能

> 对应 PRD: PR-FE-007 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 导出功能
  作为 医生
  我想要 导出审核后的结构化结果
  以便 用于人工流转或系统集成

  Scenario: 已确认任务展示 Excel 和 JSON 导出入口
    Given 任务状态为 "已确认"
    When 我进入该任务的详情或审核页
    Then 我应该看到 "导出 Excel" 按钮
    And 我应该看到 "导出 JSON" 按钮

  Scenario: 导出前展示完整性检查预警面板
    Given 审核结果中有 2 个未审核字段、1 个存疑字段、1 个为空字段、1 个未定位来源字段
    When 我点击 "导出 Excel" 按钮
    Then 系统应该调用导出完整性检查 API
    And 前端展示预警面板：
      | 统计项           | 数量 |
      | 未审核字段       | 2    |
      | 存疑字段         | 1    |
      | 为空字段         | 1    |
      | 未定位来源字段   | 1    |
      | 空值已确认字段   | 0    |
    And 面板应显示 "存在未审核或存疑字段，导出结果可能不完整"
    And 面板应提供 "继续导出" 和 "返回审核" 按钮

  Scenario: 所有字段已确认时直接触发下载
    Given 任务已确认且所有字段状态为 confirmed、modified 或 confirmed_empty
    When 我点击 "导出 Excel"
    Then 完整性检查返回零预警项
    And 系统直接调用 GET /api/tasks/{taskId}/export/excel
    And 浏览器触发文件下载

  Scenario: 用户在预警面板中选择继续导出
    Given 完整性检查面板显示有未审核和存疑字段
    When 我点击 "继续导出"
    Then 系统应该调用 GET /api/tasks/{taskId}/export/excel
    And 浏览器应该触发文件下载
    And 下载的文件名应该包含任务编号

  Scenario: 用户在预警面板中选择返回审核
    Given 完整性检查面板显示有未审核字段
    When 我点击 "返回审核"
    Then 不应该调用导出 API
    And 页面应保持在审核页可编辑状态

  Scenario: 点击导出 JSON 同样展示预警面板
    Given 审核结果中有未审核字段
    When 我点击 "导出 JSON" 按钮
    Then 同样展示完整性检查预警面板

  Scenario: 导出失败不影响已审核数据
    Given 导出 API 返回 500 错误
    When 我点击 "继续导出"
    Then 我应该看到 "导出失败：服务器内部错误"
    And 已审核的字段数据不应丢失
    And 我可以再次尝试导出

  Scenario: 导出成功后显示导出时间和格式
    Given 导出 API 返回成功
    When 我导出 Excel 后
    Then 任务详情应该显示最近导出时间
    And 应该显示导出格式为 "Excel"
    And 任务状态应更新为 "已导出"
```
