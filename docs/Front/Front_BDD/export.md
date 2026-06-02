# 导出功能

> 对应 PRD: PR-FE-005 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 导出功能
  作为 医生
  我想要 导出审核后的结构化结果
  以便 用于人工流转或后续处理

  Scenario: review 和 done 任务展示 Excel 和 JSON 导出入口
    Given 任务状态为 review 或 done
    When 我进入该任务的详情或审核页
    Then 我应该看到 "导出 Excel" 按钮
    And 我应该看到 "导出 JSON" 按钮

  Scenario: 导出 JSON 触发下载
    Given 任务状态为 review 或 done
    When 我点击 "导出 JSON"
    Then 系统应该调用 GET /api/tasks/{taskId}/export/json
    And 浏览器触发文件下载

  Scenario: 导出 Excel 触发下载
    Given 任务状态为 review 或 done
    When 我点击 "导出 Excel"
    Then 系统应该调用 GET /api/tasks/{taskId}/export/excel
    And 浏览器触发文件下载

  Scenario: 导出失败不影响已审核数据
    Given 导出 API 返回 500 错误
    When 我点击导出
    Then 我应该看到导出失败提示
    And 已保存的字段数据不应丢失
    And 我可以再次尝试导出

  Scenario: 批量 JSON zip 下载
    Given 我在任务管理页选择多个 review 或 done 任务
    When 我点击批量导出
    Then 系统应该调用 POST /api/tasks/export/batch-zip
    And 浏览器触发 zip 文件下载
    And 当前 MVP 不提供批量 Excel 下载

  Scenario: 导出成功不改变任务状态
    Given 任务状态为 done
    When 我导出 JSON 或 Excel 成功
    Then 任务状态仍应为 done
    And 页面可展示最近导出时间和格式
```
