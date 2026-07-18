# ha-uhomecp

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz/)

Home Assistant 集成：[uhomecp.com](https://www.uhomecp.com) 社区门禁系统

## 验证状态

✅ 已在 **深圳豪方天际花园** 小区验证通过（四格互联"寻常生活"平台）

## 功能

- 🔐 手机号 + 密码登录（RSA 加密）
- 🚪 每个门禁映射为一个 switch 实体，点击开门后自动复位
- 🏘️ 多小区支持，配置时选择
- 🔄 自动刷新门禁列表（每 5 分钟）
- 🔁 会话过期自动重新登录
- 🇨🇳 中文 UI

## 安装

### HACS（推荐）

1. 在 HACS 中添加自定义仓库：`linysky/ha-uhomecp`
2. 搜索 "uhomecp" 并安装
3. 重启 Home Assistant

### 手动安装

1. 将 `custom_components/uhomecp` 目录复制到你的 HA 的 `custom_components/` 目录下
2. 重启 Home Assistant
3. 在 设置 → 设备与服务 → 添加集成 中搜索 "uhomecp"

## 配置

1. 在 HA 中添加集成
2. 输入你的 uhomecp 手机号和密码
3. 如果服务器要求验证码，输入图片中的验证码
4. 选择你要管理的小区（如果只有一个则自动选择）
5. 完成！门禁会自动出现在设备列表中

> 每个小区会创建独立的集成条目，支持同一账号管理多个小区。

## 实体

每个门禁表现为一个开关实体：

- **开（press）** = 触发开门，1 秒后自动复位为关
- 可以添加到仪表盘直接点击开门
- 支持自动化：`switch.turn_on` 服务调用

所有实体按小区名称分组显示。

## 平台信息

- 平台：四格互联"寻常生活"物业管理系统
- 域名：www.uhomecp.com
- 认证：手机号 + 密码（RSA PKCS1v15 加密）

## 注意事项

- 连续密码错误会导致账号锁定（30 分钟~数小时），请确保密码正确
- RSA 公钥内嵌在前端，平台方可能更换。如果登录失败，可能需要更新公钥
- 会话有效期较短，集成会自动处理过期重新登录
- 如果会话过期且需要验证码，集成会标记为不可用，需要重新配置

## 免责声明

本集成通过逆向分析 uhomecp.com H5 页面实现，仅供个人使用。平台方可能随时更改 API 或加强安全措施，导致集成失效。使用本集成产生的任何风险由用户自行承担。

## License

MIT
