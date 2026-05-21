# 任务生命周期管理

> 对应 PRD: PR-BE-004 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 任务生命周期管理
  作为 医生
  我想要 追踪每个病历任务从上传到导出的完整流程
  以便 了解处理进度并及时处理异常

  Scenario: 新建任务后进入上传中
    Given 后端服务已正常启动
    When 电脑端发起 "新建任务"
    Then 系统应创建新的病历任务
    And 任务初始状态为 uploading
    And 系统应返回手机上传入口

  Scenario: 任务正常处理流程
    Given 任务 T001 处于 uploading 状态且已有图片
    When 手机端点击 "完成上传"
    Then 任务状态应进入 processing
    When 后端完成 OCR/文档解析和慢阻肺专病字段抽取
    Then 任务状态应进入 review
    And 结构化字段结果应对电脑端可见

  Scenario: 按状态筛选任务列表
    Given 系统中有多个不同状态的任务
    When 我请求 GET /api/tasks?status=review
    Then 应仅返回状态为 review 的任务

  Scenario: 处理失败时保留错误信息
    Given 任务 T001 在处理过程中因外部模块异常或字段结果整体不可用而失败
    Then 任务状态应变为 failed
    And 应保存 error_code、error_message 和 failed_at

  Scenario: 单字段可疑不阻断审核
    Given 任务 T001 的字段结果中存在 evidence 可疑或 OCR 风险标记
    When 处理流程完成
    Then 任务状态应进入 review
    And 可疑字段应提示人工重点核验

  Scenario: 失败任务可重试
    Given 任务 T001 处于 failed 状态
    When 我请求 POST /api/tasks/T001/retry
    Then 任务状态应回到 processing
    And 系统应重新触发处理流程

  Scenario: 待审核任务可重新处理
    Given 任务 T001 处于 review 状态
    When 我请求 POST /api/tasks/T001/reprocess
    Then 任务状态应回到 processing
    And 系统应重新触发处理流程
```
