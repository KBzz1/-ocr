# 图片上传与文件管理

> 对应 PRD: PR-BE-003 | 依赖: `docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 图片上传与文件管理
  作为 手机端上传用户
  我想要 将病历原图上传到指定任务
  以便 后续进行 OCR、文档解析和慢阻肺字段抽取

  Scenario: 上传图片到指定任务
    Given 任务 T001 处于 uploading 状态
    And 手机上传请求携带有效上传令牌
    When 手机端上传一张 JPEG 图片到 POST /api/mobile-upload/T001/images
    Then 系统应返回上传成功响应
    And 图片应保存到 T001 的独立目录中
    And 页面记录应包含 page_no、原图路径、预览路径和上传时间

  Scenario: 多图页序按上传成功顺序确定
    Given 任务 T001 处于 uploading 状态
    When 手机端依次成功上传 3 张图片
    Then 三张图片的 page_no 应分别为 1、2、3
    And 页序不依赖文件名、拍摄时间或前端传入排序

  Scenario: 上传请求不接收框选坐标
    Given 任务 T001 处于 uploading 状态
    When 手机端上传一张图片
    Then 系统应只保存原图和上传元数据
    And 不应保存 quad_points、裁剪图或透视矫正结果

  Scenario: 非 uploading 任务拒绝继续上传
    Given 任务 T001 状态为 processing
    When 手机端继续上传图片
    Then 系统应返回 409 和错误码 TASK_UPLOAD_CLOSED

  Scenario: 拒绝非图片文件
    Given 任务 T001 处于 uploading 状态
    When 上传一个 PDF 文件
    Then 系统应返回 400 和错误码 UNSUPPORTED_FILE_TYPE

  Scenario: 拒绝超大文件
    Given 任务 T001 处于 uploading 状态
    When 上传的图片超过配置的文件大小阈值
    Then 系统应返回 400 和错误码 FILE_TOO_LARGE

  Scenario: 完成上传时无图片返回错误
    Given 任务 T001 处于 uploading 状态
    And 任务没有任何已上传图片
    When 手机端调用 POST /api/mobile-upload/T001/finish
    Then 系统应返回 400 和错误码 TASK_EMPTY
    And 任务状态仍为 uploading

  Scenario: 完成上传后任务进入 processing
    Given 任务 T001 处于 uploading 状态
    And 任务已有 3 张已上传图片
    When 手机端调用 POST /api/mobile-upload/T001/finish
    Then 任务状态应变为 processing
    And 系统应触发后续 OCR、文档解析和字段抽取流程

  Scenario: 上传阶段不调用算法子系统
    Given 任务 T001 处于 uploading 状态
    When 手机端上传一张图片
    Then 系统仅保存原图和上传元数据
    And 不应在此时调用 OCR、文档解析或字段抽取模块

  Scenario: 删除任务时清理对应文件
    Given 任务 T001 已有上传图片和中间文件
    When 用户删除任务 T001
    Then 系统应清理 T001 的独立目录
    And 不应影响其他任务的文件
```
