# 四边形框选交互

> 对应 PRD: PR-FE-009 | 本节只测前端交互和坐标契约，不测自动识别边界、裁剪、透视矫正等图像处理效果

```gherkin
Feature: 四边形框选交互
  作为 采集人
  我想要 在拍摄或选择图片后调整四边形框选范围
  以便 排除屏幕背景、工具栏等非病历内容

  Scenario: 拍摄或选择图片后默认显示四边形 overlay
    Given 我已完成拍摄或选择图片并看到预览
    Then 图片上应该叠加一个四边形 overlay
    And 四边形的四个角点应该显示可拖动手柄
    And 默认角点应大约覆盖图片中心 80% 区域
    And 页面不应该展示 X/Y 像素值输入框、坐标数值面板或滑块

  Scenario: 拖动左上角点后坐标和 overlay 同步更新
    Given 图片预览上显示了四边形 overlay
    When 我拖动左上角点向图片中心移动
    Then 状态中的 quad_points.tl 应该更新为新坐标
    And overlay 形状应该相应重绘

  Scenario: 任一角点拖动不得超出图片边界
    Given 图片预览上显示了四边形 overlay
    When 我尝试将角点拖到图片边界之外
    Then 角点应该被限制在图片边界内
    And 坐标值不应包含负数或超出图片尺寸的值

  Scenario: 形成自相交四边形时阻止上传
    Given 我拖动角点导致四边形自相交
    When 我尝试点击 "确认上传"
    Then 上传应该被阻止
    And 我应该看到 "框选区域无效，请重新调整" 的提示

  Scenario: 不做任何调整直接确认上传使用默认范围
    Given 拍摄或选择图片后显示了默认四边形 overlay
    And 我没有拖动任何角点
    When 我直接点击 "确认上传"
    Then 上传请求体应该包含默认的 quad_points
    And 图片应该被成功上传

  Scenario: 已上传页面可重新框选并保存新坐标
    Given 我已成功上传第 1 页
    When 我在页面列表中点击第 1 页的 "重新框选"
    Then 我应该进入 "调整识别范围" 页面
    And 图片上应该显示该页当前保存的四边形 overlay
    When 我拖动角点后点击 "确认上传"
    Then 系统应该调用 PUT /api/mobile/sess_001/pages/page_001/quad
    And 请求体应该包含我调整后的 quad_points
    And 页面列表中第 1 页仍保持原页序

  Scenario: 锁定后不可重新框选
    Given 采集会话 "sess_001" 状态为 locked
    When 我查看已上传页面列表
    Then "重新框选" 按钮应该不可见或禁用

  Scenario: 手动调整后提交的坐标以手动值为准
    Given 外部模块返回了自动识别的边界坐标
    And 前端展示了该自动边界
    When 我手动拖动角点调整范围
    And 我点击 "确认上传"
    Then 上传请求体中的 quad_points 应该是我手动调整后的坐标
    And 不应使用外部模块返回的自动坐标

  Scenario: 外部图像处理模块未配置时不伪造预览
    Given 外部图像处理模块未配置
    When 我调整四边形后点击 "预览裁剪结果"
    Then 我应该看到 "裁剪预览暂不可用" 的提示
    And 不应该展示伪造的矫正后图片
    And "确认上传" 按钮仍然可用

  Scenario: 四边形 overlay 渲染出错时提供重新拍摄入口
    Given 图片预览页面加载时 overlay 组件渲染异常
    Then 错误边界应该接管并展示错误提示
    And 我应该看到 "重新拍摄" 的入口按钮
    And 不应该生成假的处理后的图片
```
