# 任务列表

> 对应 PRD: PR-FE-003 | 依赖: `docs/Shared/state-enums.md`

```gherkin
Feature: 任务列表
  作为 医生或病案整理人员
  我想要 在电脑端查看所有病历任务的状态
  以便 了解上传、处理、审核和导出进度

  Scenario: 任务列表每一项展示核心字段
    Given 系统中存在多个病历任务
    When 我进入任务管理页
    Then 每个任务至少应显示任务编号、创建时间、图片数量、当前状态和主要操作
    And 失败任务应显示可理解的错误原因

  Scenario: 各 MVP 状态任务使用对应中文标签展示
    Given 系统中存在 uploading、processing、review、done、failed 状态的任务
    When 我查看任务列表
    Then 每个状态应显示对应中文标签："上传中"、"处理中"、"待审核"、"已完成"、"失败"
    And 不应显示 "采集中"、"上传完成"、"已确认" 或 "已导出" 等旧状态

  Scenario: 新建任务后列表新增上传中任务
    Given 任务列表当前有 2 个任务
    When 电脑端点击 "新建任务"
    Then 任务列表应该新增一条记录
    And 新任务的初始状态应为 uploading
    And 操作区应提供查看二维码入口

  Scenario: 手机端完成上传后任务进入处理中
    Given 一个任务当前状态为 uploading
    When 手机端完成上传
    Then 任务状态应该更新为 processing
    And 列表应提示回到电脑端等待处理结果

  Scenario: 处理成功后任务进入待审核
    Given 一个任务当前状态为 processing
    When 后端 OCR/文档解析和慢阻肺字段抽取完成
    Then 任务状态应该更新为 review
    And 操作区应提供进入审核入口

  Scenario: 审核完成后任务进入已完成
    Given 一个任务当前状态为 review
    When 我在审核页完成审核
    Then 任务状态应该更新为 done
    And 操作区仍应提供查看结果和导出入口

  Scenario: 算法模块未配置时任务显示失败而非降级路径
    Given 后端算法模块未配置
    And 一个任务处理时触发 ALGORITHM_MODULE_NOT_CONFIGURED
    When 我查看任务列表
    Then 该任务状态应该显示为 "失败"
    And 应该显示错误摘要 "算法模块未配置"
    And 应该显示 "重新处理" 按钮
    And 不应该出现 "人工补录后继续确认" 的降级入口

  Scenario: 失败任务重新处理后状态更新
    Given 任务列表中有一个 failed 任务
    When 我点击该任务的 "重新处理" 按钮
    Then 系统应该调用重新处理 API
    And 任务状态应该更新为 processing

  Scenario: 筛选待审核任务时只展示 review 状态
    Given 系统中有 3 个 review 任务和 2 个 done 任务
    When 我选择筛选条件 "待审核"
    Then 列表只应显示 3 个 review 任务
    And done 任务不应出现

  Scenario: 任务列表不提供旧采集会话操作
    Given 我查看任意任务行
    Then 操作区不应显示修订采集、取消会话、解锁、重新框选、拖拽排序或补拍替换入口
```
