# 手机端文档采集

> 对应 PRD: PR-FE-002 | 依赖: `docs/Shared/terminology.md`, `docs/Shared/state-enums.md`

```gherkin
Feature: 手机端文档采集
  作为 采集人
  我想要 用手机拍摄病历文书页面并上传到工作站
  以便 在电脑端进行结构化审核

  Scenario: 通过有效会话链接进入采集页
    Given 存在一个有效的采集会话 "sess_001"
    When 我通过 URL "http://192.168.1.100:{port}/capture?session=sess_001" 访问采集页
    Then 我应该看到采集页面
    And 我应该看到 "已采集 0 页" 的提示
    And 我应该看到 "拍照" 和 "选择已有图片" 按钮

  Scenario: 会话不存在时禁用采集功能
    Given 会话 "sess_invalid" 不存在
    When 我通过 URL 访问 "?session=sess_invalid"
    Then 我应该看到 "无效的采集链接，请重新扫描二维码"
    And "拍照" 按钮应该处于禁用状态
    And "选择已有图片" 按钮应该处于禁用状态

  Scenario: 会话过期后禁止新增内容
    Given 采集会话 "sess_001" 已过期
    When 我访问该会话的采集页
    Then 我应该看到 "采集会话已过期" 的提示
    And 所有拍摄、选择、上传、删除、排序按钮都应该处于禁用状态

  Scenario: 已锁定的会话禁止编辑
    Given 采集会话 "sess_001" 状态为 locked
    When 我访问该会话的采集页
    Then 我应该看到 "采集已完成，请在电脑端查看" 的提示
    And 拍照、删除、排序、补拍入口均不可用

  Scenario: 拍照后显示本地预览
    Given 我在采集页且会话有效
    When 我点击 "拍照" 按钮
    Then 应该触发设备的相机或文件选择
    When 我选取一张图片
    Then 我应该看到该图片的本地预览
    And 我应该看到四边形框选 overlay 叠加在图片上

  Scenario: 选择相册中的图片作为病历页面
    Given 我在采集页且会话有效
    When 我点击 "选择已有图片"
    And 我选择一张 jpg 图片
    Then 我应该看到该图片的预览
    And 我应该看到四边形框选 overlay

  Scenario: 选择 PDF 文件时前端直接拦截
    Given 我在采集页且会话有效
    When 我点击 "选择已有图片" 并选择一个 pdf 文件
    Then 我应该看到 "不支持的文件类型" 的错误提示
    And 不应该调用上传 API

  Scenario: 选择超过 20MB 的图片时前端拦截
    Given 我在采集页且会话有效
    When 我选择一张超过 20MB 的图片
    Then 我应该看到 "图片过大（最大 20MB）" 的提示
    And 不应该调用上传 API

  Scenario: 上传过程中显示加载状态并阻止重复点击
    Given 我在采集页已选择一张图片并确认框选
    When 我点击 "确认上传"
    Then 该页面应该显示上传中的 loading 状态
    And 我再次点击 "确认上传" 时不应该产生第二个上传请求

  Scenario: 单页上传失败后只重试失败页
    Given 我已成功上传第 1 页
    And 第 2 页上传时网络异常导致失败
    When 我查看页面列表
    Then 第 2 页应该显示 "上传失败，请重试" 和重试按钮
    And 第 1 页不应该被重复上传
    When 我点击第 2 页的重试按钮
    Then 应该只重新上传第 2 页

  Scenario: 零页时不允许完成采集
    Given 我在采集页且未上传任何页面
    When 我点击 "完成采集" 按钮
    Then 我应该看到 "请至少采集一页病历" 的提示
    And 不应该调用 finish API

  Scenario: 完成采集后锁定会话并提示到电脑端查看
    Given 我已成功上传 3 页病历图片
    When 我点击 "完成采集" 按钮
    Then 系统应该调用 POST /api/mobile/sess_001/finish
    And 页面应该切换为只读完成态
    And 我应该看到 "采集完成，请在电脑端继续审核" 的提示

  Scenario: 移动端视口下按钮和交互区域不遮挡
    Given 我使用 iPhone 12 尺寸的移动设备 (390x844)
    When 我访问采集页
    Then 所有主要操作按钮应该在可视区域内
    And 按钮不应该相互遮挡
    And 四边形角点手柄应该可以单手拖动
```
