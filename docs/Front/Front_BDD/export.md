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

  Scenario: 未确认任务不可导出
    Given 任务状态为 "待审核"
    When 我查看导出按钮
    Then "导出 Excel" 按钮应该处于禁用状态
    And "导出 JSON" 按钮应该处于禁用状态
    And 悬停在按钮上应显示 tooltip "请先确认审核"

  Scenario: 后端策略允许未确认导出时展示预警面板
    Given 后端配置允许未确认任务导出但返回 warning
    When 我查看导出区域
    Then 应该展示完整性检查面板
    And 面板中显示未审核、存疑、为空、未定位来源字段的数量

  Scenario: 点击导出 Excel 触发下载
    Given 任务已确认
    When 我点击 "导出 Excel" 按钮
    Then 系统应该调用 GET /api/tasks/{taskId}/export/excel
    And 浏览器应该触发文件下载
    And 下载的文件名应该包含任务编号

  Scenario: 点击导出 JSON 触发下载
    Given 任务已确认
    When 我点击 "导出 JSON" 按钮
    Then 系统应该调用 GET /api/tasks/{taskId}/export/json
    And 浏览器应该触发文件下载
    And 下载的文件名应该包含任务编号

  Scenario: 导出操作前展示字段完整性检查结果
    Given 审核结果中有 2 个未审核字段、1 个存疑字段
    When 我进入导出流程
    Then 我应该看到导出前的完整性统计：
      | 统计项           | 数量 |
      | 未审核字段       | 2    |
      | 存疑字段         | 1    |
      | 为空字段         | 0    |
      | 未定位来源字段   | 1    |

  Scenario: 导出失败不影响已审核数据
    Given 导出 API 返回 500 错误
    When 我点击 "导出 Excel"
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
