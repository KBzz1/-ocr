# app/config

应用配置命名空间。允许提交安全默认模板（如 `default.yaml`），但不得提交真实运行配置。

| 说明文件 | 配置范围 |
|----------|----------|
| `application.README.md` | 应用名称、版本、启动模式等全局设置 |
| `network.README.md` | 本地端口、局域网地址选择、二维码访问地址 |
| `storage.README.md` | 上传、结果、导出、日志目录策略 |
| `schema.README.md` | 当前 schema 版本、文书类型选择策略 |
| `algorithm-modules.README.md` | 外部算法模块路径、启用状态、契约版本 |
| `export.README.md` | Excel、JSON 导出策略 |
| `logging.README.md` | 本地日志级别、脱敏和轮转策略 |

## 约束

- 不提交本机私有路径、患者数据、密钥、模型权重或真实部署参数。
- 算法配置缺失时，任务处理应失败并返回明确错误，不做降级处理。
