# 外部算法模块集成

> 对应 PRD: PR-BE-005, PR-BE-006 | 依赖: `docs/Shared/error-codes.md`

```gherkin
Feature: 外部算法模块集成
  作为 系统
  我想要 调用外部交付的图像处理、OCR 和 LLM 字段抽取模块
  以便 获得文档解析结果和结构化字段候选，同时正确处理模块失败

  Scenario: 算法模块未配置时任务处理失败
    Given 外部算法模块文件未放置在预期目录
    When 系统触发任务 T001 的处理流程
    Then 任务状态应变为 failed
    And error_code 应为 ALGORITHM_MODULE_NOT_CONFIGURED
    And error_message 应包含 "算法模块未配置"
    And 任务不应进入 ready_for_review 或任何可审核状态

  Scenario: 图像处理模块返回处理后图像路径
    Given 外部图像处理模块已正确配置
    When 系统调用图像处理模块传入原图和框选坐标
    Then 模块返回的 processed 图像路径应被持久化
    And 该路径应传递给后续的文档解析模块

  Scenario: 图像处理模块异常时任务失败
    Given 外部图像处理模块可被调用但抛出异常
    When 系统触发任务处理
    Then 任务状态应变为 failed
    And error_code 应为 ALGORITHM_MODULE_FAILED
    And 原始图像和 quad_points 应被保留用于排查
    And 系统不应崩溃或返回 500

  Scenario: 文档解析成功并原样保存结果
    Given 外部文档解析模块已正确配置
    When 系统调用文档解析模块传入处理后图像列表
    Then 模块返回的 pages、blocks、tables、merged_text 应被原样持久化
    And 系统不应修改或改写模块返回的任何字段值

  Scenario: 部分页面解析失败时整体任务失败
    Given 外部文档解析模块返回 5 页结果，其中第 3 页状态为 failed
    When 系统接收该解析结果
    Then 每页的 success/failed 标记应被保留
    And 任务整体状态应变为 failed
    And 成功页面的结果应被保留用于排查

  Scenario: 空解析结果视为失败
    Given 外部文档解析模块返回空的 pages 数组
    When 系统接收该结果
    Then 任务状态应变为 failed
    And 不应将空结果暴露为可审核的文档结果

  Scenario: 字段抽取成功并原样保存候选
    Given 外部字段抽取模块已正确配置
    When 系统调用字段抽取模块传入文档解析结果和 schema
    Then 模块返回的 field_key、original_value、evidence、confidence 应被原样持久化
    And 每个字段应标记为 unreviewed 初始状态

  Scenario: 字段抽取返回空候选时任务失败
    Given 外部字段抽取模块返回空的字段候选数组
    When 系统接收该结果
    Then 任务状态应变为 failed
    And 系统不得基于 schema 生成空字段作为替代
    And 任务不应进入 ready_for_review 状态

  Scenario: 字段抽取返回 schema 外字段时任务失败
    Given 外部字段抽取模块返回的字段中包含 schema 未定义的 field_key
    When 系统校验字段候选
    Then 任务状态应变为 failed
    And error_code 应为 ALGORITHM_CONTRACT_INVALID

  Scenario: 字段抽取返回非法字段结构时任务失败
    Given 外部字段抽取模块返回的字段缺少 field_key 或 original_value
    When 系统校验字段结构
    Then 任务状态应变为 failed
    And error_code 应为 ALGORITHM_CONTRACT_INVALID
    And 非法字段不应被保存

  Scenario: 失败任务不可进入审核
    Given 任务 T001 处于 failed 状态
    When 尝试获取该任务的审核结果或确认该任务
    Then 系统应返回错误，指示任务处理失败
```
