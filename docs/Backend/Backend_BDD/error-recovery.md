# 错误处理与可恢复性

> 依赖: `docs/Shared/error-codes.md`

```gherkin
Feature: 错误处理与可恢复性
  作为 用户
  我想要 在任何流程失败时看到明确的错误信息
  以便 了解发生了什么并能重新尝试

  Scenario: 统一错误响应格式
    Given 任何后端接口返回错误
    Then 响应应使用统一结构：
      {
        "error": {
          "code": "ERROR_CODE",
          "message": "人类可读的中文错误描述",
          "details": {}
        }
      }

  Scenario: 不存在的资源返回 404
    Given 系统中不存在 session_id 为 "NONEXISTENT" 的会话
    When 我请求 GET /api/capture-sessions/NONEXISTENT
    Then 应返回 404 和错误码 SESSION_NOT_FOUND
    And 不应返回调用堆栈

  Scenario: 上传失败的页面可重试
    Given 手机端上传图片时网络中断
    When 网络恢复后重新上传
    Then 系统应正常接收并保存

  Scenario: 任务处理失败可重新处理
    Given 任务 T001 因算法模块异常而失败
    When 算法模块恢复后重试任务
    Then 任务应重新进入 processing 流程
    And 应使用最新的算法模块版本

  Scenario: 服务无响应时的容错
    Given 后端服务在处理请求时崩溃重启
    When 服务重新启动
    Then 未完成的处理任务应保持原状态
    And 已持久化的数据和审核结果不应丢失
```
