# ha-uhomecp

Home Assistant 集成：[U管家（uhomecp.com）](https://www.uhomecp.com) 社区门禁系统

## 功能

- 🔐 手机号 + 密码登录（RSA 加密）
- 🚪 每个门禁映射为一个 switch 实体，点击开门后自动复位
- 🏘️ 多小区支持，配置时选择
- 📊 传感器：小区名称、门禁数量
- 🔄 自动刷新门禁列表（每 5 分钟）
- 🔁 会话过期自动重新登录
- 🇨🇳 中文 UI

## 安装

### HACS（推荐）

1. 在 HACS 中添加自定义仓库：`linysky/ha-uhomecp`
2. 搜索 "U管家门禁" 并安装
3. 重启 Home Assistant

### 手动安装

1. 将 `custom_components/uhomecp` 目录复制到你的 HA 的 `custom_components/` 目录下
2. 重启 Home Assistant
3. 在 设置 → 设备与服务 → 添加集成 中搜索 "U管家门禁"

## 配置

1. 在 HA 中添加集成
2. 输入你的 U管家手机号和密码
3. 如果服务器要求验证码，输入图片中的验证码
4. 选择你要管理的小区（如果只有一个则自动选择）
5. 完成！门禁会自动出现在设备列表中

> 每个小区会创建独立的集成条目，支持同一账号管理多个小区。

## 实体

### Switch（开关）

每个门禁表现为一个开关实体：

- **开（turn_on）** = 触发开门，1 秒后自动复位为关
- 可以添加到仪表盘直接点击开门
- 支持自动化：`switch.turn_on` 服务调用

### Sensor（传感器）

| 实体 | 说明 | 示例 |
|------|------|------|
| 小区 | 当前小区名称 | 豪方天际花园 |
| 门禁数量 | 可用门禁总数 | 12 |

## 平台信息

- 平台：四格互联（SEGI）"寻常生活"物业管理系统
- 域名：www.uhomecp.com
- 认证：手机号 + 密码（RSA PKCS1v15 加密）

## 注意事项

- 连续密码错误会导致账号锁定（30 分钟~数小时），请确保密码正确
- RSA 公钥内嵌在前端，平台方可能更换。如果登录失败，可能需要更新公钥
- 会话有效期较短，集成会自动处理过期重新登录
- 如果会话过期且需要验证码，集成会标记为不可用，需要重新配置

## 开发

项目结构：

```
custom_components/uhomecp/
├── __init__.py        # 集成入口 + DataUpdateCoordinator
├── api.py             # API 客户端（登录、开门等）
├── config_flow.py     # UI 配置流程（账号密码→验证码→小区选择）
├── const.py           # 常量（URL、RSA 公钥）
├── manifest.json      # HA 元数据
├── sensor.py          # 传感器（小区名称、门禁数量）
├── switch.py          # 门禁开关实体
├── strings.json       # 英文字符串（源文件）
└── translations/
    ├── en.json        # 英文翻译
    └── zh.json        # 中文翻译
```

## License

MIT
