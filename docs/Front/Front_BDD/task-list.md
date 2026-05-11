# 任务列表

> 对应 PRD: PR-FE-003 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 任务列表
  作为 医生
  我想要 在电脑端查看所有病历任务的状态
  以便 了解处理进度并进入审核

  Scenario: 任务列表每一项展示核心字段
    Given 系统中存在多个不同状态的病历任务
    When 我访问工作台的任务列表区域
    Then 每个任务至少应显示：任务编号、创建时间、页数、处理状态、审核状态、导出状态

  Scenario: 各状态任务使用对应的中文标签展示
    Given 系统中存在 created、uploading、uploaded、processing、ready_for_review、confirmed、exported、failed 状态的任务
    When 我查看任务列表
    Then 每个状态应显示对应的中文标签："已创建"、"上传中"、"上传完成"、"处理中"、"待审核"、"已确认"、"已导出"、"失败"

  Scenario: 手机端完成采集后任务列表自动新增
    Given 任务列表当前有 2 个任务
    And 手机端完成了一次新的采集
    When 任务列表轮询或收到推送
    Then 任务列表应该自动新增一条记录
    And 新任务的初始状态应为 "上传完成" 或 "处理中"

  Scenario: 任务从上传完成到待审核的状态变化过程可见
    Given 一个任务当前状态为 "上传完成"
    When 后端开始处理该任务
    Then 任务状态应该更新为 "处理中"
    When 后端处理完成
    Then 任务状态应该更新为 "待审核"
    And 每次状态变化应在列表中有视觉反馈

  Scenario: 算法模块未配置时任务显示失败而非降级路径
    Given 后端算法模块未配置
    And 一个任务处理时触发了 ALGORITHM_MODULE_NOT_CONFIGURED
    When 我查看任务列表
    Then 该任务状态应该显示为 "失败"
    And 应该显示错误摘要 "算法模块未配置"
    And 应该显示 "重新处理" 按钮
    And 不应该出现 "人工补录后继续确认" 的降级入口

  Scenario: 点击失败任务可查看完整错误原因
    Given 任务列表中有一个失败任务
    When 我点击该任务的错误信息展开按钮
    Then 我应该看到完整的错误原因说明
    And 错误信息不应包含堆栈信息

  Scenario: 失败任务重新处理后状态更新
    Given 任务列表中有一个失败任务
    When 我点击该任务的 "重新处理" 按钮
    Then 系统应该调用 POST /api/tasks/{taskId}/retry
    And 任务状态应该更新为 "处理中"

  Scenario: 筛选待审核任务时只展示对应状态
    Given 系统中有 3 个待审核任务和 2 个已确认任务
    When 我选择筛选条件 "待审核"
    Then 列表只应显示 3 个待审核任务
    And 已确认任务不应出现
```
