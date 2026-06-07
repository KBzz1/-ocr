# 患者中心记录归档（后端 BDD）

> 对应 PRD: BE-PAT-01 | 依赖: `docs/Shared/terminology.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 患者档案与任务归属
  作为 医生
  我想要 把多个病历任务归集到同一个患者档案
  以便 在患者维度集中阅览历次结构化结果并支持改绑

  Scenario: 创建带患者归属的任务
    Given 存在一个未删除的患者档案
    When 我提交患者、记录类型和记录日期（可选时间）
    Then 系统应创建 uploading 任务并返回手机上传二维码
    And 任务应包含 patient_id、patient_snapshot、document_type、record_date、record_time

  Scenario: 缺少患者或记录类型时拒绝创建
    Given 后端服务已正常启动
    When 我提交缺少患者或记录类型的创建请求
    Then 接口应返回 INVALID_REQUEST_PARAMS
    And 任务不应被创建

  Scenario: 已删除患者不能用于创建或改绑
    Given 患者 P001 处于已逻辑删除状态
    When 我提交使用 P001 的创建或改绑请求
    Then 接口应返回 PATIENT_DELETED

  Scenario: 不存在或已删除患者返回标准错误
    Given 系统中没有患者 P-NOT-EXIST
    When 我请求 GET /api/patients/P-NOT-EXIST
    Then 接口应返回 PATIENT_NOT_FOUND
    And 当患者被逻辑删除后再次查询也返回 PATIENT_NOT_FOUND

  Scenario: 活跃 processing 任务拒绝修改归属元数据
    Given 任务 T001 处于 processing 状态
    When 我请求 PATCH /api/tasks/T001/metadata
    Then 接口应返回 INVALID_TASK_TRANSITION
    And 任务状态、患者和记录时间应保持不变

  Scenario: 处理后修改记录类型会重新抽取字段
    Given 任务 T001 处于 review 状态且已有 OCR 文本
    When 我请求 PATCH /api/tasks/T001/metadata 并修改 document_type
    Then 任务应重新进入 processing
    And 后端应只重新执行字段抽取，不重新跑 OCR 或文档解析
    And 旧 Schema 下的审核字段不应再被展示或导出

  Scenario: 缺少成功 OCR 文本时拒绝更正记录类型
    Given 任务 T001 处于 review 状态但缺少 document_result.json
    When 我请求 PATCH /api/tasks/T001/metadata 并修改 document_type
    Then 接口应返回 REEXTRACTION_VALIDATION_FAILED
    And 任务和原审核结果应保持不变

  Scenario: 重抽取进行中时拒绝修改记录类型
    Given 任务 T001 存在正在运行的 OCR 文本重新抽取
    When 我请求 PATCH /api/tasks/T001/metadata 并修改 document_type
    Then 接口应返回 INVALID_TASK_TRANSITION
    And 任务状态、审核结果应保持不变

  Scenario: 任务改绑不修改 OCR、审核结果和状态
    Given 任务 T001 处于 review 状态
    When 我请求 PATCH /api/tasks/T001/metadata 并改绑到另一患者
    Then 任务应绑定到新患者
    And OCR 文本、审核结果和状态应保持不变
    And 原患者详情页不应再显示该任务

  Scenario: 仅删除患者时任务保留并标记患者已删除
    Given 任务 T001 属于患者 P001
    When 我请求 DELETE /api/patients/P001?delete_tasks=false
    Then 患者应进入逻辑删除状态
    And 任务 T001 应保留
    And 任务列表应继续展示 T001 并标记患者已删除
    And 患者 JSON、任务 JSON 和结果文件应仍存在

  Scenario: 同时删除患者及关联任务时任务默认不可见
    Given 任务 T001 属于患者 P001
    When 我请求 DELETE /api/patients/P001?delete_tasks=true
    Then 患者和任务 T001 都应进入逻辑删除
    And 任务列表默认查询不应再返回 T001
    And 任务 JSON 和结果文件应仍存在

  Scenario: 含 processing 任务时拒绝同时删除
    Given 患者 P001 存在 processing 任务
    When 我请求 DELETE /api/patients/P001?delete_tasks=true
    Then 接口应返回 INVALID_TASK_TRANSITION
    And 患者和任务应保持不变

  Scenario: 普通用户删除任务不会物理清理文件
    Given 任务 T001 处于 review 状态
    When 我请求 DELETE /api/tasks/T001
    Then 任务 JSON 应保留且标记 deleted_at
    And 任务 pages/results 目录应保留
    And 后续 GET /api/tasks/T001 应返回 TASK_NOT_FOUND

  Scenario: 导出包含患者和记录元数据
    Given 任务 T001 处于 review 状态
    When 我请求导出 JSON/Excel
    Then 导出文件应包含 patient_id、当前患者姓名、记录类型、记录日期、记录时间、任务编号
    And 姓名修改后再次导出应使用当前姓名

  Scenario: 患者已删除但任务保留时导出使用姓名快照
    Given 任务 T001 属于已删除患者 P001
    When 我请求导出该任务
    Then 导出文件应使用 patient_snapshot.name 并标记 patient.deleted=true

  Scenario: 已删除任务不能导出
    Given 任务 T001 处于已逻辑删除状态
    When 我请求导出该任务
    Then 接口应返回 EXPORT_VALIDATION_FAILED
```
