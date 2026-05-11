# 本地服务启动与离线运行

> 对应 PRD: PR-BE-001 | 依赖: `docs/Shared/terminology.md`, `docs/Shared/error-codes.md`

```gherkin
Feature: 本地服务启动与离线运行
  作为 系统维护者
  我想要 在断网环境下启动本地工作站
  以便 在院内环境中为医生提供可靠的服务

  Scenario: 正常启动并返回运行状态
    Given 系统依赖的静态文件和配置均已就位
    When 我执行启动脚本
    Then 后端服务应在 5 秒内完成启动
    And GET /api/system/status 应返回 200 和 status "running"
    And 响应应包含 version、started_at 和 lan_addresses 字段
    And 前端静态页面应可在 "http://127.0.0.1:{port}" 访问

  Scenario: 断网环境下系统正常启动
    Given 电脑处于完全断网状态
    When 我执行启动脚本
    Then 系统应正常启动，不因网络不可用而崩溃
    And 启动过程中不应有任何对外部网络（包括 CDN、模型下载地址）的请求
    And GET /api/system/status 应返回 200

  Scenario: 展示局域网访问地址
    Given 电脑已连接局域网且获取到 IP
    When 我查询系统状态
    Then lan_addresses 应包含局域网 IP 地址
    And 不应将 127.0.0.1 作为手机端可用的默认地址

  Scenario: 手动指定局域网地址
    Given 系统自动识别的局域网地址不可用
    When 用户通过接口手动指定可访问的局域网地址
    Then 系统应使用用户指定的地址重新生成采集二维码
    And 二维码中的 URL 应指向用户指定的地址

  Scenario: 配置文件缺失时安全降级
    Given 配置文件不存在
    When 我执行启动脚本
    Then 系统应使用安全默认值启动
    And 日志应记录 "配置文件缺失，使用默认配置" 的 warning
    And GET /api/system/status 仍应返回 200

  Scenario: 算法模块未配置时系统仍可启动
    Given 外部算法模块文件未放置在预期目录
    When 我执行启动脚本
    Then 系统应正常启动
    And GET /api/system/status 应返回 200
    And 日志应记录 "算法模块未配置" 的提示
    But 后续触发任务处理时应进入 failed 状态
```
