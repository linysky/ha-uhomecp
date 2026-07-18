# ha-uhomecp 技术设计文档

> Home Assistant 集成：[uhomecp.com](https://www.uhomecp.com) 社区门禁系统
> 验证状态：✅ 已在深圳豪方天际花园小区验证通过

## 1. 项目概述

将 uhomecp.com（四格互联 SEGI 物业管理平台）的社区门禁功能接入 Home Assistant，实现：
- 在 HA 中查看所有门禁
- 每个门禁映射为一个 switch 实体（开 = 触发开门，1.5秒防抖）
- 支持手机号+密码登录（RSA 加密 + 验证码）
- 实体按小区分组显示

## 2. 平台分析

### 2.1 平台信息

| 项目 | 值 |
|------|-----|
| 平台 | 四格互联（SEGI）物业管理平台 |
| 域名 | www.uhomecp.com |
| 前端 | Vue.js SPA + JSEncrypt RSA 加密 |
| 认证 | 手机号+密码（RSA加密）/ 微信 OAuth / 短信验证码 |

### 2.2 已验证的 API 接口

| 功能 | 方法 | 路径 | Content-Type | 状态 |
|------|------|------|--------------|------|
| 密码登录 | POST | `/authc-restapi/v1/user/auth/login` | form-urlencoded | ✅ |
| 获取验证码 | GET | `/authc-restapi/v1/auth/code/getImgCode` | - | ✅ |
| 查询小区列表 | GET | `/uhomecp-sso/v1/community/findMyCommunity` | - | ✅ |
| 获取门列表 | GET | `/door-restapi/v1/userapp/doorList` | - | ✅ |
| 开门 | POST | `/uhomecp-app/v1/userapp/opendoor/submit.json` | **application/json** | ✅ |

> **重要**：开门接口使用 `application/json`，不是 `application/x-www-form-urlencoded`。用错会返回 415。

### 2.3 登录流程（完整）

```
Step 1: POST /authc-restapi/v1/user/auth/login
        ├── 参数: tel, password(RSA加密), loginType=1, clientId=wx, md5Flag=true
        ├── 响应 code="0" → 登录成功
        └── 响应 code="20010" → 需要验证码，进入 Step 2

Step 2: GET /authc-restapi/v1/auth/code/getImgCode
        ├── 响应: {data: {imgCode: "base64图片", randomToken: "uuid"}}
        └── POST /authc-restapi/v1/user/auth/login（带 imgCode + randomToken）
            └── 响应 code="0" → 登录成功
```

### 2.4 关键发现（踩坑记录）

#### r_ua Cookie 问题

**现象**：Python requests 登录返回"密码错误"，但浏览器同样密码可以登录

**原因**：服务器要求请求携带 `r_ua` Cookie。没有此 Cookie 时，无论密码是否正确都返回"密码错误"

**解决**：登录前先发一个预热请求（任意参数的 POST 到登录接口），服务器会在 Set-Cookie 中返回 `r_ua`，后续请求携带此 Cookie 即可

#### 自定义请求头

**现象**：即使有 `r_ua` Cookie，仍可能返回"密码错误"

**原因**：服务器检查 `sec-ch-ua`、`versionCode`、`source`、`platform` 等自定义请求头

**必须携带的请求头**：
```python
{
    "sec-ch-ua-platform": '"Android"',
    "sec-ch-ua": '"Chromium";v="90", "Google Chrome";v="90"',
    "sec-ch-ua-mobile": "?1",
    "versionCode": "60",
    "source": "6",
    "platform": "null",
}
```

#### 验证码

验证码是 4 位字母/数字混合，每次登录都可能出现。在 HA 集成中，首次配置时需要用户手动输入验证码。验证码图片通过 HTML `<img>` 标签嵌入配置流程描述中。

## 3. 密码加密方案

### 3.1 加密流程

```
原始密码 → Base64编码 → RSA公钥加密(PKCS1v15) → 密文(base64)
```

### 3.2 RSA 公钥

```
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC03KMpYBkJ51nCrWUsMr1E3T5/q
8ETu/UbeJnbyjYD4u3F/4iEECLbUxe9k49gQcb4rR2zciI0Oy8R3x1Irndjc81f9w9
g2fTqNnsM00siVsqh6VGEV9XBkWOUoyg601WNbR3HiIa3GyLvo79oND0mdFBP0QqQc
2h7IMqaR71hEwIDAQAB
```

- 1024-bit RSA 公钥
- 使用 PKCS#1 v1.5 padding（非 OAEP）
- 密钥内嵌在前端 sg-rsa.js 中（JSEncrypt 3.0.0-rc.1）
- Python 实现中公钥在模块级缓存，避免每次调用都重新加载

### 3.3 验证状态

| 验证项 | 状态 |
|--------|------|
| sg-rsa.js 从服务器获取 | ✅ |
| Python 加密输出格式正确（172字符 base64） | ✅ |
| 服务器接受请求并尝试验证 | ✅ |
| 密码登录成功（含验证码） | ✅ |

## 4. 架构设计

### 4.1 项目结构

```
custom_components/uhomecp/
├── __init__.py        # 集成入口 + DataUpdateCoordinator
├── api.py             # API 客户端（登录、门列表、开门）
├── button.py          # 门禁 button 实体
├── config_flow.py     # UI 配置流程（账号→验证码→小区选择）
├── const.py           # 常量（URL、RSA 公钥、请求头）
├── icon.png           # 品牌图标（uhomecp.com logo）
├── manifest.json      # HA 元数据
├── sensor.py          # 小区名称传感器 + device_info
├── strings.json       # 中文字符串（默认语言）
└── translations/
    └── zh-Hans.json   # 简体中文翻译
```

### 4.2 核心组件

| 组件 | 职责 |
|------|------|
| `api.py` | UHomeCPClient：登录（含验证码+预热）、获取门列表、开门、会话持久化 |
| `config_flow.py` | 三步配置：手机号+密码 → 验证码 → 小区选择 |
| `button.py` | 每个门禁一个 button 实体，press = 开门，1.5秒防抖 |
| `sensor.py` | 小区名称传感器 + `get_device_info()` 供实体分组 |
| `__init__.py` | 协调初始化，恢复 session cookies 避免重复登录 |

### 4.3 Config Flow

```
Step 1: 输入手机号 + 密码
        ↓ 尝试登录（含预热获取 r_ua Cookie）
        ├── code="0" → 登录成功 → Step 3
        └── code="20010" → 需要验证码 → Step 2

Step 2: 显示验证码图片（HTML img 标签）+ 输入验证码
        ↓ 带验证码登录
        └── code="0" → 登录成功 → Step 3

Step 3: 选择小区（多个活跃小区时显示选择框，单个自动选择）
        ↓ 保存配置（含 session cookies + user_info）
        完成
```

唯一 ID 格式：`{手机号}_{小区ID}`（支持同一账号管理多个小区）

### 4.4 Session 持久化

配置完成后，session cookies 和 user_info 保存到 config entry data。HA 重启时：
1. 恢复 cookies + user_info
2. 尝试获取门列表验证 session 是否有效
3. 失败则重新登录（可能触发验证码，需重新配置）

## 5. 依赖

| 包 | 用途 |
|-----|------|
| `cryptography` | RSA 加密（PKCS1v15） |
| `requests` | HTTP 客户端（HA 自带） |

## 6. 已知限制

1. **验证码**：每次登录可能需要验证码，首次配置需用户手动输入
2. **RSA 公钥可能更换**：公钥内嵌在前端，平台方可能随时更换
3. **会话有效期较短**：Cookie 会话有效期未实测，集成会自动处理过期重新登录
4. **巴法云兼容**：使用 Switch 实体（非 Button），兼容巴法云同步到米家

## 7. 逆向来源

- 前端源码：`https://www.uhomecp.com/h5/wechat-platform-h5/js/app.95d73209.js`
- 门禁组件：`https://www.uhomecp.com/h5/wechat-platform-h5/js/chunk-58b2ccbc.55899fce.js`
- RSA 加密：`https://www.uhomecp.com/h5/wechat-platform-h5/static/common/sg-rsa.js`
- 配置文件：`https://www.uhomecp.com/configs.js`
- 品牌图标：`https://pic.uhomecp.com/logo/uhome_new.png`
