# LLM Platform 边界说明

## 目标

明确 `core platform`、`agent-pack`、`tool-pack` 三层的责任边界，避免后续拆分后再次耦合回主仓库。

## 1. Core Platform

平台层负责所有通用底座能力。

### 平台必须负责

- 用户认证与 session 识别
- ACL 与策略控制
- `Tool Registry`
- `Agent Registry`
- Runtime 编排
- Trace 与审计
- File Service
- Schema 校验
- Draft / Register / Publish 生命周期

### 平台禁止负责

- 直接持有业务型 tool 定义
- 直接持有业务型 agent prompt
- 在运行时里写死某个业务能力的 UI 或输入输出结构

## 2. Tool Pack

`tool-pack` 是能力定义包，不是平台运行时。

### tool-pack 负责

- `Tool Manifest`
- tool 的说明、样例、UI schema
- 可选 executor 配置

### tool-pack 不负责

- 鉴权
- ACL
- Trace Store
- Session 获取
- 直接访问平台内部 service

## 3. Agent Pack

`agent-pack` 是 agent 定义包，不是运行时框架。

### agent-pack 负责

- `Agent Spec`
- system prompt
- 模板与默认配置

### agent-pack 不负责

- 直接实现 tool 调用链
- 绕过 runtime 执行
- 直接写 trace store
- 直接访问文件系统

## 4. 唯一入口原则

以下入口必须唯一：

- tool 调用入口：`ToolRegistry.execute`
- agent 运行入口：`OtieRuntime.run`
- 文件访问入口：`FileService` + ACL
- trace 写入入口：平台 trace service

任何子模块都不应绕过这些入口。

## 5. 数据边界

### 平台层持有

- registry 数据
- trace 数据
- ACL 数据
- files metadata
- runtime state

### 子模块持有

- manifest/spec 文件
- prompt/template
- 样例与 UI 描述

## 6. 发布边界

LLM 只能生成草案，不能直接发布：

1. draft
2. validate
3. register
4. publish

发布动作必须发生在平台层。

## 7. 后续实现要求

- 新增 tool 时优先放到 `tool-pack`
- 新增 agent 时优先放到 `agent-pack`
- 平台只新增 loader、validator、registry、runtime
- 如果出现平台层直接 import 某个业务 tool/agent 实现，应视为耦合回退
