# 采集会话管理

> 对应 PRD: PR-BE-002 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 采集会话管理
  作为 采集人（医生）
  我想要 通过手机扫码进入采集会话，完成多页病历拍摄并锁定
  以便 将完整的病历页面按正确顺序归入一个任务

  Scenario: 创建采集会话并生成二维码
    Given 后端服务已正常启动
    When 电脑端发起 "新建采集" 请求 POST /api/capture-sessions
    Then 系统应返回 201 和唯一的 session_id
    And 响应应包含二维码 URL
    And 会话默认状态为 active
    And 会话应记录 created_at 和 expires_at

  Scenario: 查询会话信息
    Given 已存在一个 active 会话 S001
    When 我查询 GET /api/capture-sessions/S001
    Then 应返回会话的当前页数、状态、创建时间和过期时间

  Scenario: 会话过期后拒绝上传
    Given 会话 S001 已超过 expires_at
    When 手机端尝试上传图片到该会话
    Then 系统应返回 409 和错误码 SESSION_EXPIRED
    And 错误信息应包含 "采集会话已过期"

  Scenario: 采集完成前允许编辑页面列表
    Given 会话 S001 处于 active 状态，已有 3 页图片
    When 采集人删除第 2 页
    Then 系统应从会话中移除该页
    And 剩余页面应保持原有顺序
    When 采集人将第 3 页调整为第 1 页
    Then 系统应更新页序
    When 采集人补拍第 1 页并上传新图片
    Then 系统应替换第 1 页的图片和框选元数据，页序保持不变
    When 采集人重新框选第 1 页
    Then 系统应更新第 1 页的 quad_points，且不重新上传原图

  Scenario: 完成采集后会话锁定
    Given 会话 S001 处于 active 状态，已有顺序固化的 5 页图片
    When 采集人点击 "完成采集" POST /api/mobile/S001/finish
    Then 会话状态应变更为 locked
    And 当前页面列表顺序应被固化为任务处理顺序
    And 当前页面的框选元数据应被固化为任务处理输入
    And 系统应根据页面列表创建或更新对应的病历任务

  Scenario: 锁定后禁止编辑
    Given 会话 S001 已锁定
    When 尝试新增、删除、调整页面顺序、补拍或重新框选
    Then 系统应返回 409 和错误码 SESSION_LOCKED
    And 错误信息应包含 "采集已完成，不可编辑"

  Scenario: 重复完成采集幂等
    Given 会话 S001 已锁定且任务已创建
    When 再次调用 POST /api/mobile/S001/finish
    Then 系统应幂等返回当前 locked 状态
    And 不应重复创建任务

  Scenario: 会话过期后不可完成采集
    Given 会话 S001 已过期
    When 调用 POST /api/mobile/S001/finish
    Then 系统应返回 409 和错误码 SESSION_EXPIRED

  Scenario: 无已上传页面时不可完成采集
    Given 会话 S001 处于 active 状态
    And 会话 S001 还没有任何已成功上传并写回 upload_ref 的页面
    When 调用 POST /api/mobile/S001/finish
    Then 系统应返回 400 和错误码 SESSION_EMPTY
    And 不应创建病历任务
```
