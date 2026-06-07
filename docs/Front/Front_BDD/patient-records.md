# 患者中心记录归档（前端 BDD）

> 对应 PRD: FE-PAT-01 | 依赖: `docs/Shared/terminology.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 患者中心
  作为 医生
  我想要 把多个病历任务归集到同一个患者档案
  以便 在患者维度集中阅览历次结构化结果并支持改绑

  Scenario: 新建任务弹窗统一填写患者、记录类型、记录日期
    Given 电脑端已登录工作台
    When 我点击 "新建任务" 按钮
    Then 弹窗应同时展示患者选择、记录类型、记录日期和可选时间
    And 我填写完成后点击 "创建任务"
    And 系统应创建 uploading 任务并弹出二维码
    And 二维码内容来自后端 mobile_upload_url

  Scenario: 创建失败时弹窗内不显示二维码
    Given 后端 POST /api/tasks 返回 INVALID_REQUEST_PARAMS
    When 我在弹窗内提交创建请求
    Then 弹窗内不应出现二维码
    And 我应看到后端返回的中文错误提示

  Scenario: 新建患者时同名提示
    Given 后端 GET /api/patients?query=测试用例 返回两个患者
    When 我在弹窗内输入 "测试用例" 并尝试创建
    Then 弹窗应展示两个已有患者编号和 "仍然新建" 入口
    And 我点击 "仍然新建" 后才调用 POST /api/patients

  Scenario: 手机端不再修改记录类型
    Given 我已扫码进入手机上传页
    When 我查看上传页
    Then 页面应只读展示 document_type_label
    And 页面不应提供记录类型切换或文书模板选择器

  Scenario: 患者管理页支持搜索
    Given 后端存在多个患者档案
    When 我在搜索框输入姓名或患者编号
    Then 列表应只展示匹配的患者
    And 搜索期间按钮应禁用避免并发请求

  Scenario: 患者列表展示姓名/编号/任务数/最近记录时间
    Given 后端 GET /api/patients 返回患者列表
    When 我查看患者管理页
    Then 每一行应展示患者姓名、患者编号、未删除任务数和最近记录时间
    And 已删除患者不应出现在默认列表

  Scenario: 患者详情按记录类型导航和时间轴
    Given 患者 P001 有多个不同记录类型和时间的任务
    When 我进入患者详情页
    Then 左侧应展示按 document_type 分组的导航及每组任务数
    And 右侧应展示当前记录类型按记录时间倒序排列的任务列表
    And 列表应包含 uploading/processing/review/done/failed 全部未删除任务

  Scenario: review/done 任务可展开字段摘要
    Given 任务 T001 处于 review 状态
    When 我点击该记录行
    Then 详情页应按需调用审核接口加载结构化字段
    And 字段应按 Schema 分组展示全部字段，包括空值
    And 状态字段不展示结构化字段

  Scenario: 患者详情不复制审核契约
    Given 任务 T001 处于 uploading 状态
    When 我查看患者详情页
    Then 详情页响应不包含结构化字段，只展示任务摘要
    And 只在用户展开 review/done 记录时才调用审核接口

  Scenario: 从患者详情进入审核页
    Given 任务 T001 处于 review 状态
    When 我点击 "进入审核/查看结果"
    Then 页面应跳转到现有审核页
    And 审核页应展示患者姓名、患者编号、记录类型、记录时间

  Scenario: 任务管理显示患者和记录信息
    Given 任务管理页存在多个任务
    When 我查看任务列表
    Then 每一行应展示患者姓名/编号、记录类型、记录日期和可选时间
    And 患者已删除时该列应展示 "患者已删除" 标记

  Scenario: 改绑患者
    Given 任务 T001 处于 uploading 或 review 状态
    When 我点击 "改绑患者" 并选择另一个患者
    Then 后端应调用 PATCH /api/tasks/T001/metadata
    And 任务管理列表应展示新的患者姓名
    And 患者已删除时改绑按钮应被禁用

  Scenario: processing 任务禁用改绑
    Given 任务 T001 处于 processing 状态
    When 我查看任务管理列表
    Then 改绑按钮应被禁用
    And 鼠标悬停或提示应解释需等待处理完成

  Scenario: 仅删除患者
    Given 患者详情页存在关联任务
    When 我点击 "仅删除患者"
    Then 后端应调用 DELETE /api/patients/{id}?delete_tasks=false
    And 任务管理应继续展示该任务并标记 "患者已删除"
    And 我应能将该任务改绑到其他患者

  Scenario: 同时删除患者及关联任务
    Given 患者详情页存在可删除任务
    When 我点击 "同时删除患者及关联任务"
    Then 后端应调用 DELETE /api/patients/{id}?delete_tasks=true
    And 任务应从任务管理默认列表中消失
    And 患者和任务文件应仍存在（不出现 "文件已被物理删除" 提示）

  Scenario: 同时删除被后端拒绝时页面不刷数据
    Given 患者 P001 存在 processing 任务
    When 我点击 "同时删除患者及关联任务"
    Then 后端返回 INVALID_TASK_TRANSITION
    And 页面应展示统一错误消息
    And 不应刷新或重置当前患者数据

  Scenario: 已删除患者的保留任务显示 "患者已删除" 标记
    Given 任务 T001 属于已删除患者 P001
    When 我在任务管理查看 T001
    Then 任务行应展示 "患者已删除" 标记
    And 改绑按钮仍可用
```

## 前端控制台隐私约束

- 前端源码不得调用 `console.log/debug/info/warn/error` 输出患者姓名、OCR 原文、结构化字段值或包含这些内容的对象
- 测试断言可以引用 mock 中的患者姓名，但不通过 `console.*` 输出
- 错误提示统一走 `normalizeApiError`，不暴露后端原始 `message`
