# LLM Platform 定义生命周期

## 目标

统一 `tool` 与 `agent` 的定义生命周期，确保所有草案、注册、发布动作都使用同一套状态机，而不是在不同模块里各自实现。

适用对象：

- `Tool Manifest`
- `Agent Spec`

## 1. 状态列表

平台定义以下生命周期状态：

- `draft`
- `validated`
- `validation_failed`
- `registered`
- `publish_pending`
- `published`
- `publish_rejected`
- `disabled`
- `deprecated`

## 2. 状态语义

### `draft`

定义刚创建，可能来自：

- 人工创建
- LLM 生成草案
- 外部导入

特点：

- 允许编辑
- 不允许被正式调用
- 必须先通过校验

### `validated`

定义已通过 schema 与平台规则校验。

特点：

- 结构合法
- 可进入 register
- 不代表已经可用

### `validation_failed`

定义校验失败。

特点：

- 必须保留失败原因
- 允许修正后重新校验
- 不允许 register 或 publish

### `registered`

定义已写入 registry，但尚未发布。

特点：

- 可被平台发现
- 默认不对普通运行流开放
- 可以进入 publish 流程

### `publish_pending`

定义已提交发布申请，等待人工或策略审批。

特点：

- 不可调用
- 必须记录审批状态

### `published`

定义已正式发布，可被平台正常加载和调用。

特点：

- 可被 agent/runtime 使用
- 允许查询与执行

### `publish_rejected`

定义发布申请被拒绝。

特点：

- 必须保留拒绝原因
- 可修改后重新进入校验或发布流程

### `disabled`

定义暂时下线。

特点：

- 保留历史记录
- 不允许运行时调用
- 可以重新启用并恢复发布状态

### `deprecated`

定义已废弃，但保留兼容与历史查询。

特点：

- 不建议新接入使用
- 可以保留只读查询

## 3. 合法流转

标准流转如下：

1. `draft -> validated`
2. `draft -> validation_failed`
3. `validation_failed -> draft`
4. `validated -> registered`
5. `registered -> publish_pending`
6. `publish_pending -> published`
7. `publish_pending -> publish_rejected`
8. `publish_rejected -> draft`
9. `published -> disabled`
10. `disabled -> published`
11. `published -> deprecated`
12. `disabled -> deprecated`

## 4. 非法流转

以下流转应被平台拒绝：

- `draft -> published`
- `validation_failed -> published`
- `draft -> registered`，如果未先做 validate
- `deprecated -> published`
- `publish_rejected -> published`，如果未重新校验或重新申请发布

## 5. 校验要求

每次进入 `validated` 之前，平台必须至少执行：

1. Schema 校验
2. 必填字段校验
3. id/version 合法性校验
4. policy 字段合法性校验
5. 平台约束校验

示例：

- `tool.kind=http` 时必须提供 `endpoint`
- `agent.availableTools` 中的 tool id 必须符合命名规范
- 风险级别不允许缺失时必须报错

## 6. 审批要求

每次进入 `published` 之前，平台必须确认：

1. 当前状态已经是 `registered` 或 `publish_pending`
2. 校验已经通过
3. 如果定义来自 LLM draft，需要经过 review
4. 如果策略要求审批，需要留下审批人和审批时间

## 7. 审计要求

每次状态流转都必须记录 trace 或审计事件，至少包括：

- `entityType`
- `entityId`
- `version`
- `fromState`
- `toState`
- `operator`
- `timestamp`
- `reason`

推荐事件类型：

- `draft_created`
- `definition_validated`
- `definition_validation_failed`
- `definition_registered`
- `definition_publish_requested`
- `definition_published`
- `definition_publish_rejected`
- `definition_disabled`
- `definition_deprecated`

## 8. 存储建议

建议平台至少保存两部分数据：

### 定义文件

- tool manifest
- agent spec

### 生命周期记录

- 当前状态
- 校验结果
- 审批结果
- 审计记录

建议存储位置：

- `data/registry/tools/`
- `data/registry/agents/`
- `data/drafts/tools/`
- `data/drafts/agents/`

## 9. 与 API 的关系

生命周期对应 API：

- `POST /v1/tools/draft`
- `POST /v1/tools/register`
- `POST /v1/tools/{id}/publish`
- `POST /v1/agents/draft`
- `POST /v1/agents/register`
- `POST /v1/agents/{id}/publish`

这些 API 的实现必须遵守本文定义的状态流转规则。
