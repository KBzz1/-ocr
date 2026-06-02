# 手机端任务上传

> 对应 PRD: PR-FE-002 | 依赖: `docs/Shared/terminology.md`, `docs/Shared/state-enums.md`

```gherkin
Feature: 手机端任务上传
  作为 医生或病案整理人员
  我想要 用手机扫码后把多张病历图片上传到同一个任务
  以便 在电脑端继续 OCR 处理、人工审核和导出

  Scenario: 通过有效任务上传链接进入手机上传页
    Given 电脑端已创建一个状态为 uploading 的任务
    And 二维码链接包含该任务 ID 和上传令牌
    When 我用手机访问该上传链接
    Then 我应该看到该任务的手机上传页
    And 页面应显示任务编号、已上传图片数量和 "拍照/选择图片" 入口
    And 页面不应显示采集会话状态、剩余时间、锁定或过期信息

  Scenario: 上传链接无效时禁止上传
    Given 任务不存在或上传令牌无效
    When 我访问手机上传页
    Then 我应该看到 "无效的上传链接，请重新扫描二维码" 的提示
    And "拍照/选择图片" 入口应该不可用
    And 不应该调用图片上传 API

  Scenario: 非 uploading 任务只读展示并禁止继续上传
    Given 任务状态不是 uploading
    When 我访问该任务的手机上传页
    Then 页面应提示该任务已结束上传，请回到电脑端查看
    And "拍照/选择图片" 和 "完成上传" 入口应该不可用

  Scenario: 上传多张图片后按成功上传顺序展示页序
    Given 我在有效任务上传页
    When 我依次拍照或选择 3 张图片并上传成功
    Then 已上传列表应显示第 1 页、第 2 页、第 3 页
    And 页序应按上传成功顺序确定
    And 每页应显示上传成功状态、缩略图或文件名

  Scenario: 选择不支持文件时前端直接拦截
    Given 我在有效任务上传页
    When 我选择一个 pdf 文件
    Then 我应该看到 "不支持的文件类型" 的错误提示
    And 不应该调用上传 API

  Scenario: 选择超过大小限制的图片时前端拦截
    Given 我在有效任务上传页
    When 我选择一张超过大小限制的图片
    Then 我应该看到图片过大的错误提示
    And 不应该调用上传 API

  Scenario: 单张图片上传失败后允许重试
    Given 我已成功上传第 1 页
    And 第 2 页上传时网络异常导致失败
    When 我查看已上传列表
    Then 第 2 页应显示 "上传失败，请重试"
    And 第 1 页不应该被重复上传
    When 我点击第 2 页的重试入口
    Then 系统应只重新上传第 2 页

  Scenario: 零页时不允许完成上传
    Given 当前任务还没有任何已上传图片
    When 我点击 "完成上传"
    Then 我应该看到 "请至少上传一张病历图片" 的提示
    And 不应该调用完成上传 API

  Scenario: 完成上传后提示回到电脑端
    Given 我已成功上传 3 张病历图片
    When 我点击 "完成上传"
    Then 系统应该调用 POST /api/mobile-upload/{task_id}/finish
    And 页面应该提示 "上传完成，请回到电脑端查看处理结果"
    And 页面不应提供修订采集、补拍替换、重新框选或拖拽排序入口
```
