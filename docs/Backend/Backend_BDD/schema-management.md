# 字段 Schema 管理

> 对应 PRD: PR-BE-007 | 依赖: `docs/Shared/terminology.md`

```gherkin
Feature: 字段 Schema 管理
  作为 系统
  我想要 根据预定义的 schema 配置抽取字段范围
  以便 不同文书类型可以使用不同的字段模板，且历史任务不受影响

  Scenario: 读取当前生效的 schema
    Given schema 配置文件存在且格式合法
    When 前端请求 GET /api/schema/current
    Then 应返回 schema 的 version、document_type 和字段组定义
    And 字段组应按配置文件顺序排列

  Scenario: Schema 缺少必要字段时加载失败
    Given schema 配置文件缺少 version 字段
    When 系统尝试加载 schema
    Then 应记录错误日志
    And 依赖于 schema 的接口应返回明确的配置错误

  Scenario: Schema 包含重复 field_key 时拒绝加载
    Given schema 配置文件中存在两个相同的 field_key
    When 系统尝试加载 schema
    Then 应拒绝加载并记录错误

  Scenario: 修改 schema 后新任务使用新版本
    Given 当前 schema 版本为 1.0.0
    When 维护者更新 schema 文件至 1.1.0 并重启系统
    Then 新创建的任务应记录 schema_version 为 1.1.0
    And 前端应展示 1.1.0 版本的字段组

  Scenario: 历史任务保留旧 schema 版本
    Given 任务 T001 使用 schema 版本 1.0.0 创建
    When schema 文件已更新至 1.1.0
    Then 任务 T001 仍应使用 1.0.0 版本的字段定义
    And 任务 T001 的字段展示不应受新 schema 影响

  Scenario: 不同文书类型可选择不同 schema
    Given 存在 copd_admission_record 和 general_medical_record 两种 schema
    When 创建任务时指定 document_type 为 copd_admission_record
    Then 系统应使用 copd_admission_record 对应的 schema 配置
    And 当前版本默认使用慢阻肺专病 schema

  Scenario: 后端不得用 schema 兜底抽取字段
    Given 外部字段抽取模块返回整体无效/全空/无法解析的输出
    When 系统处理字段结果
    Then 不得基于 schema 的 field_key 生成空值字段
    And 任务必须进入 failed 状态

  Scenario: 单字段为空或不确定时保留元数据进入审核
    Given 外部字段抽取模块返回的字段中存在 extraction_status 为 not_found 或 uncertain 的字段
    When 系统处理字段结果
    Then 任务应进入 review 状态
    And 每个字段应保留 extraction_status、verification_status 和 quality_flags
    And 前端应展示风险字段供人工核验
```
