# 任务管理表格规整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆开任务管理复合栏位，并统一整张表的宽度、对齐、行高和操作按钮网格。

**Architecture:** 保持任务数据和交互不变，只调整 `TaskList` 的表格语义结构及其局部 CSS。组件测试锁定独立表头和单元格归属，Playwright 在真实页面中核对宽屏对齐与窄屏横向滚动。

**Tech Stack:** React 18、TypeScript、CSS、Vitest、Testing Library、Playwright

---

### Task 1: 锁定拆列行为

**Files:**
- Modify: `app/frontend/src/pages/tasks/TasksPage.test.tsx`

- [x] **Step 1: 修改患者与记录测试，断言四个独立表头**

将原“患者与记录”表头断言改为：

```ts
expect(headerCells).toContain('患者姓名');
expect(headerCells).toContain('患者编号');
expect(headerCells).toContain('记录类型');
expect(headerCells).toContain('记录时间');
expect(headerCells).not.toContain('患者与记录');
```

并断言患者姓名、患者编号、记录类型和记录时间分别位于对应列索引的单元格内。

- [x] **Step 2: 运行目标测试并确认因旧表头失败**

Run: `npm --prefix app/frontend run test -- --run src/pages/tasks/TasksPage.test.tsx`

Expected: FAIL，失败原因包含找不到“患者姓名”等新表头或仍存在“患者与记录”。

### Task 2: 拆分栏位并统一表格规则

**Files:**
- Modify: `app/frontend/src/components/tasks/TaskList.tsx`
- Modify: `app/frontend/src/components/tasks/tasks.css`

- [x] **Step 1: 将复合栏位拆为四个表头和四个单元格**

在 `TaskList.tsx` 中为所有列添加 `task-list-col--*` class，并分别渲染患者姓名、患者编号、记录类型和记录时间。患者已删除标记保留在患者姓名单元格。

- [x] **Step 2: 添加明确列宽和对齐规则**

在 `tasks.css` 中提高表格最小宽度，按列 class 设定宽度。选择、页数和状态列居中，其余列左对齐；普通文本单行，失败原因最多两行。

- [x] **Step 3: 将操作区改为固定网格**

操作区使用固定列宽的 CSS grid，按钮保持现有业务顺序，删除图标占固定末位，表头与按钮区左边界一致。

- [x] **Step 4: 运行目标测试并确认通过**

Run: `npm --prefix app/frontend run test -- --run src/pages/tasks/TasksPage.test.tsx`

Expected: PASS。

### Task 3: 静态验证与端到端视觉核对

**Files:**
- Verify: `app/frontend/src/components/tasks/TaskList.tsx`
- Verify: `app/frontend/src/components/tasks/tasks.css`
- Create: `app/frontend/output/playwright/task-table-alignment-wide.png`
- Create: `app/frontend/output/playwright/task-table-alignment-narrow.png`

- [x] **Step 1: 运行类型检查和构建**

Run: `npm --prefix app/frontend run typecheck`

Expected: PASS。

Run: `npm --prefix app/frontend run build`

Expected: PASS。

- [x] **Step 2: 运行任务管理 E2E**

Run: `npm --prefix app/frontend run test:e2e -- tests/e2e/current-workflows.spec.ts`

Expected: PASS。

- [x] **Step 3: 启动真实页面并截图**

启动本地前端，使用 Playwright 打开 `/tasks`，在宽屏和窄屏尺寸下截图到 `app/frontend/output/playwright/`。

- [x] **Step 4: 视觉核对**

检查表头与内容同轴、四个患者记录栏位独立、状态列居中、操作按钮左起规则排列、窄屏出现横向滚动且栏位不挤压。发现问题则修正后重复测试和截图。
