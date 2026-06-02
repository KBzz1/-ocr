# 端到端业务流程

> 包含当前 MVP 成功流、失败流和离线验证流

```gherkin
Feature: 端到端业务流程
  作为 医生
  我想要 完成从手机上传图片到审核导出的完整病历处理流程
  以便 将纸质病历转化为结构化数据

  Scenario: 完整流程 — 上传三页病历并审核导出
    Given 工作站已启动且运行正常
    When 我打开工作台
    Then 显示本地服务可用且任务列表为空

    When 我点击 "新建任务"
    Then 弹窗生成手机上传二维码
    And 任务列表新增一条 uploading 任务

    When 我用手机扫描二维码进入上传页
    Then 显示手机上传页面，可以点击 "拍照/选择图片"

    When 我依次拍摄或选择 3 张病历图片并上传成功
    Then 页面列表显示 3 页已上传，页序为 1、2、3

    When 我点击 "完成上传"
    Then 手机端提示回到电脑端查看
    And 任务状态变为 processing

    When 后端处理完成
    Then 任务状态变为 review

    When 我进入审核页
    Then 可以看到原图、OCR 文本和结构化字段
    When 我修改字段并保存
    Then 字段状态变为 modified
    When 我统一审核并完成任务
    Then 未修改字段提交为 confirmed
    And 任务状态变为 done

    When 我点击 "导出 JSON"
    Then 触发 JSON 文件下载
    When 我点击 "导出 Excel"
    Then 触发 Excel 文件下载
    And 任务状态仍为 done

  Scenario: 算法模块未配置时任务失败且无降级路径
    Given 后端算法模块未配置
    When 手机端完成上传后任务进入处理阶段
    Then 任务状态应该显示为 failed
    And 错误原因为 "算法模块未配置，无法生成结构化字段"
    And 审核入口不可用或只显示失败态
    And 页面不应该出现 "人工补录后继续确认/导出" 的降级路径

  Scenario: 离线环境完整流程验证
    Given 电脑处于完全断网状态
    And 工作站以离线模式启动
    When 我访问工作台
    Then 页面正常加载，无外部资源加载失败

    When 我用手机连接电脑热点并访问上传页
    Then 手机上传页正常加载

    When 我完成上传、审核和导出
    Then 所有操作正常完成
    And 整个过程中不应有任何外部域名请求
```
