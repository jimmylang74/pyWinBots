# 微信 (WeChat) 自动化插件

## 概述
该插件提供对 Windows 微信客户端的自动化控制能力。支持应用的启动管理、联系人查找以及消息发送。

## 使用流程

### 1. 启动微信
调用 `weixin_launch` 启动微信客户端。首次启动后需要用户扫码登录。

### 2. 搜索联系人
搜索前确保微信主窗口处于激活状态。调用 `weixin_search_contact(name="联系人名称")`。
该操作会聚焦到微信的搜索框，输入联系人名称并点击搜索结果。

### 3. 发送消息
调用 `weixin_send_message(contact="联系人名称", message="消息内容")` 发送消息。
函数内部会先自动搜索联系人并进入聊天窗口，然后输入消息并发送。

## 可用工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `weixin_launch` | 启动微信 | 无 |
| `weixin_search_contact` | 搜索联系人 | `name`: 联系人名称 |
| `weixin_send_message` | 发送消息 | `contact`: 联系人, `message`: 消息内容 |
| `weixin_get_main_window` | 获取窗口信息 | 无 |

## 注意事项

- 微信 Windows 客户端使用 CEF (Chromium Embedded Framework) 渲染，部分 UI 元素可能使用自定义控件
- 启动后的扫码登录环节必须人工完成
- 如果微信已经在运行，`weixin_launch` 会自动连接到现有进程
- 发送消息时，建议先确认消息内容无误，因为该操作不可撤销
- 确保 Windows 系统的缩放设置不影响 UI 定位（推荐 100%）
