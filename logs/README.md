# logs

日志目录。真实运行日志文件不提交；排查本机问题时按需查看热日志、冷日志和结构化事件。

## 日志结构

```
logs/
├── backend.log           # 热: WARNING+ERROR，当前会话关键信息，文件小
├── backend-events.jsonl  # 热: 结构化业务事件（任务流转、OCR、导出）
├── access.log            # 冷: HTTP 请求日志（Werkzeug）
├── debug.log             # 冷: DEBUG+INFO，含 LLM 原始返回等诊断细节
├── boot.log              # 冷: 进程 stdout/stderr 兜底输出
├── backend.pid           # 进程 PID 文件
├── frontend.log          # 热: 前端构建日志
└── archive/              # 冷: 归档的历史日志
    └── YYYY-MM/          # 按月归档
        └── backend.YYYYMMDD-HHmmss.log
```

### 热日志

`backend.log` 仅记录 WARNING 及以上级别，用于快速定位当前问题：
- 算法模块异常、契约违规
- 字段抽取结构校验失败
- 服务启动警告

文件上限 512 KB，保留 3 个滚动备份。

### 冷日志

- `access.log`: HTTP 请求详情，前端轮询噪音隔离在此
- `debug.log`: 完整诊断信息，包括 LLM 原始返回、字段规范化详情
- `boot.log`: 进程 stdout/stderr 兜底，Flask/Werkzeug 启动输出
