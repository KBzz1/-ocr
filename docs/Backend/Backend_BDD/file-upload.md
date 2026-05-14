# 图片上传与文件管理

> 对应 PRD: PR-BE-003, PR-BE-011 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 图片上传与文件管理
  作为 采集人（医生）
  我想要 将拍摄的病历页面和框选元数据上传到电脑
  以便 后续进行文档解析和字段抽取

  Scenario: 上传图片到指定会话
    Given 会话 S001 处于 active 状态
    When 手机端上传一张 JPEG 图片到 POST /api/mobile/S001/pages
    Then 系统应返回 201 和 page_id
    And 图片应保存到该会话对应任务的独立目录中
    And 页面记录应包含 page_no 和上传时间

  Scenario: 上传带框选元数据的页面
    Given 会话 S001 处于 active 状态
    When 上传请求包含原图、quad_points、图片尺寸
    Then 系统应保存原始图像
    And 系统应保存四个角点坐标、图片尺寸和上传时间
    And 系统不应在前端或后端自行执行裁剪或透视矫正

  Scenario: 更新已上传页面的框选元数据
    Given 会话 S001 处于 active 状态
    And 页面 P001 已成功上传
    When 手机端调用 PUT /api/mobile/S001/pages/P001/quad
    And 请求体包含新的 quad_points
    Then 系统应更新页面 P001 的四个角点坐标和更新时间
    And 系统不应要求重新上传原图
    And 页面 P001 的 page_no 不应变化

  Scenario: 拒绝锁定会话的框选坐标更新
    Given 会话 S001 已锁定
    And 页面 P001 已成功上传
    When 手机端调用 PUT /api/mobile/S001/pages/P001/quad
    Then 系统应返回 409 和错误码 SESSION_LOCKED

  Scenario: 缺少框选坐标时不阻断上传
    Given 会话 S001 处于 active 状态
    When 上传请求不包含 quad_points
    Then 系统应正常接收并返回 201
    And quad_points 字段保存为 null

  Scenario: 拒绝非图片文件
    Given 会话 S001 处于 active 状态
    When 上传一个 PDF 文件
    Then 系统应返回 400 和错误码 UNSUPPORTED_FILE_TYPE

  Scenario: 拒绝超大文件
    Given 会话 S001 处于 active 状态
    When 上传的图片超过配置的文件大小阈值
    Then 系统应返回 400 和错误码 FILE_TOO_LARGE

  Scenario: 拒绝非法框选坐标
    Given 会话 S001 处于 active 状态
    When 上传请求的 quad_points 缺角点、包含非数字值、或坐标自相交
    Then 系统应返回 400 和错误码 INVALID_QUAD_POINTS

  Scenario: 更新框选坐标时拒绝非法坐标
    Given 会话 S001 处于 active 状态
    And 页面 P001 已成功上传
    When PUT /api/mobile/S001/pages/P001/quad 的请求体包含缺角点、非数字值、越界或自相交的 quad_points
    Then 系统应返回 400 和错误码 INVALID_QUAD_POINTS

  Scenario: 文件存储按任务隔离
    Given 存在任务 T001 和 T002
    When 分别上传图片到两个任务
    Then T001 的文件应保存在 T001 独立目录中
    And T002 的文件应保存在 T002 独立目录中
    And 两个任务的文件不应混淆

  Scenario: 上传阶段不调用算法模块
    Given 会话 S001 处于 active 状态
    When 手机端上传一张图片
    Then 系统仅保存原图和元数据
    And 不应在此时调用图像处理或 OCR 模块

  Scenario: 删除任务时清理对应文件
    Given 任务 T001 已有上传图片和中间文件
    When 用户删除任务 T001
    Then 系统应清理 T001 的独立目录
    And 不应影响其他任务的文件
```
