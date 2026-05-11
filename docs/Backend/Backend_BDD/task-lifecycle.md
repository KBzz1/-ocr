# 任务生命周期管理

> 对应 PRD: PR-BE-004 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 任务生命周期管理
  作为 医生
  我想要 追踪每个病历任务从上传到导出的完整流程
  以便 了解处理进度并及时处理异常

  Scenario: 采集完成后自动创建任务
    Given 会话 S001 处于 active 状态且已有图片
    When 采集人点击 "完成采集"
    Then 系统应创建新的病历任务
    And 任务初始状态为 created
    And 任务应记录创建时间、页数和来源会话

  Scenario: 任务正常处理流程
    Given 任务 T001 处于 uploaded 状态
    When 后端触发文档解析和字段抽取处理
    Then 任务状态应依次流经 uploading → uploaded → processing
    And 处理成功后任务进入 ready_for_review 状态
    And 结构化的字段候选结果应对电脑端可见

  Scenario: 按状态筛选任务列表
    Given 系统中有多个不同状态的任务
    When 我请求 GET /api/tasks?status=ready_for_review
    Then 应仅返回状态为 ready_for_review 的任务

  Scenario: 查看任务详情
    Given 任务 T001 已完成处理
    When 我请求 GET /api/tasks/T001
    Then 应返回任务基本信息、页面列表、文档解析摘要和审核状态

  Scenario: 非法状态转换被拒绝
    Given 任务 T001 处于 uploaded 状态
    When 尝试直接将任务状态改为 confirmed
    Then 系统应返回 400 和错误码 INVALID_TASK_TRANSITION

  Scenario: 处理失败时保留错误信息
    Given 任务 T001 在处理过程中因算法模块异常而失败
    Then 任务状态应变为 failed
    And 应保存 error_code、error_message 和 failed_at
    And 已成功处理的中间结果应保留用于排查

  Scenario: 失败任务可重试
    Given 任务 T001 处于 failed 状态
    When 我请求 POST /api/tasks/T001/retry
    Then 任务状态应回到 processing
    And 系统应重新触发处理流程

  Scenario: 状态变更记录历史
    Given 任务 T001 经历了多次状态变更
    When 我查询任务详情
    Then 每次状态变更应记录时间、变更前状态和变更后状态
```
