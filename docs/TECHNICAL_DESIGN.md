# ha-uhomecp 技术设计文档

> Home Assistant 集成：U管家（uhomecp.com）社区门禁系统

## 1. 项目概述

将 uhomecp.com（四格互联"寻常生活"物业管理平台）的社区门禁功能接入 Home Assistant，实现：
- 在 HA 中查看所有门禁
- 每个门禁映射为一个 switch 实体（开 = 触发开门）
- 支持手机+密码登录（RSA 加密）

## 2. 平台分析

### 2.1 平台信息

| 项目 | 值 |
|------|-----|
| 平台 | 四格互联（SEGI）"寻常生活" |
| 域名 | www.uhomecp.com |
| 前端 | Vue.js SPA + JSEncrypt RSA 加密 |
| 认证 | 手机号+密码（RSA加密）/ 微信 OAuth / 短信验证码 |

### 2.2 已验证的 API 接口

| 功能 | 方法 | 路径 | 认证 |
|------|------|------|------|
| 密码登录 | POST | `/authc-restapi/v1/user/auth/login` | 无 |
| 获取门列表 | GET | `/door-restapi/v1/userapp/doorList` | Cookie |
| 开门 | POST | `/uhomecp-app/v1/userapp/opendoor/submit.json` | Cookie |
| 微信门列表 | GET | `/door-restapi/v1/userapp/doorListForWeChat` | Cookie |
| 生成门禁二维码 | GET | `/door-restapi/v1/userapp/generateQRCodeForDoorH5` | Cookie |
| 获取用户信息 | GET | `/enterprise-app/user/selectByDetails` | Cookie |
| 查询小区列表 | GET | `/uhomecp-sso/v1/community/findMyCommunity` | Cookie |

### 2.3 登录请求格式

```
POST /authc-restapi/v1/user/auth/login
Content-Type: application/x-www-form-urlencoded

loginType=1
password=<RSA加密后的密码>
tel=<手机号>
clientId=wx
md5Flag=true
```

登录成功响应：
```json
{
  "code": "0",
  "data": {
    "userId": "12345",
    "custId": "67890",
    "communityId": "111"
  }
}
```

认证通过 Cookie 中的 `JSESSIONID` 维持会话。

### 2.4 开门请求格式

```
POST /uhomecp-app/v1/userapp/opendoor/submit.json
Content-Type: application/x-www-form-urlencoded

custId=<用户ID>
userId=<用户ID>
doorId=<门禁ID>
communityId=<小区ID>
doorIdStr=<门禁字符串ID>
appVersion=2.3
appType=2
```

开门成功响应（根据逆向推测）：
```json
{
  "code": "0",
  "message": "门已开"
}
```

### 2.5 门列表响应格式（根据逆向推测）

```json
{
  "code": "0",
  "data": [
    {
      "doorId": 123,
      "doorIdStr": "abc123",
      "name": "小区正门",
      "doorType": 1,
      "deviceType": 1
    }
  ]
}
```

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

### 3.3 Python 实现方案

```python
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
import base64

def encrypt_password(password: str, public_key_pem: str) -> str:
    """加密密码：Base64编码 → RSA加密 → base64输出"""
    # 1. Base64 编码密码
    pwd_b64 = base64.b64encode(password.encode()).decode()
    
    # 2. 加载 RSA 公钥
    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    
    # 3. RSA 加密（PKCS1v15）
    encrypted = public_key.encrypt(pwd_b64.encode(), padding.PKCS1v15())
    
    # 4. 返回 base64 编码的密文
    return base64.b64encode(encrypted).decode()
```

> **注意**：经验证，此加密方式与前端 sg-rsa.js 输出格式一致（均为 172 字符 base64）。服务器接受请求格式并尝试验证（返回"账号或密码错误"而非"参数错误"）。

### 3.4 加密验证状态

| 验证项 | 状态 |
|--------|------|
| sg-rsa.js 从服务器获取 | ✅ |
| Python 加密输出格式正确（172字符 base64） | ✅ |
| 服务器接受请求并尝试验证 | ✅ |
| 密码登录成功 | ⏳ 待账号解锁后验证 |

> 账号因多次测试被锁定，需等待解锁后做最终验证。用户已确认密码在其他设备上可正常登录。

## 4. 架构设计

### 4.1 整体架构

```
Home Assistant
├── custom_components/
│   └── uhomecp/
│       ├── __init__.py        # 集成入口（setup/unload）
│       ├── manifest.json      # 集成元数据
│       ├── config_flow.py     # UI 配置流程
│       ├── const.py           # 常量定义
│       ├── api.py             # API 客户端
│       ├── switch.py          # 门禁 switch 实体
│       └── translations/
│           └── zh.json        # 中文翻译
├── hacs.json                  # HACS 集成元数据
├── README.md
└── LICENSE
```

### 4.2 组件职责

| 组件 | 职责 |
|------|------|
| `api.py` | UHomeCPClient 类：登录、获取门列表、开门、会话管理 |
| `config_flow.py` | HA UI 配置：输入手机号+密码 → 验证登录 → 选择小区 → 完成 |
| `switch.py` | 每个门禁创建一个 switch 实体，turn_on 触发开门 |
| `__init__.py` | 协调各组件初始化和卸载 |
| `const.py` | API 地址、默认值、域名常量 |

### 4.3 API 客户端设计（api.py）

```python
class UHomeCPClient:
    """U管家 API 客户端"""
    
    BASE_URL = "https://www.uhomecp.com"
    
    def __init__(self, phone: str, password: str):
        self.phone = phone
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
        self.user_info = {}      # userId, custId, communityId
        self.doors = []          # 门禁列表
    
    async def login(self) -> bool:
        """登录：RSA加密密码 → POST登录接口 → 保存Cookie"""
        
    async def get_doors(self) -> list[dict]:
        """获取门禁列表"""
        
    async def open_door(self, door_id: str, door_id_str: str) -> bool:
        """开门"""
```

### 4.4 Switch 实体设计

每个门禁映射为一个 `SwitchEntity`：

| 属性 | 值 |
|------|-----|
| `unique_id` | `uhomecp_{door_id}` |
| `name` | 门禁名称（如"小区正门"） |
| `is_on` | `False`（开门后自动复位） |
| `turn_on()` | 调用开门 API，成功后1秒自动设为 off |

> 门禁本质上是一个"按钮"而非"开关"，但用 switch 实体可以在 HA 的仪表盘上直接点击操作。开门后自动复位为 off 状态。

### 4.5 Config Flow 设计

```
Step 1: 输入手机号 + 密码
        ↓ 验证登录
Step 2: 完成
```

## 5. 数据流

### 5.1 开门流程

```
用户点击 switch "开"
  → switch.turn_on()
    → client.ensure_logged_in()  # 检查/刷新登录
    → client.open_door(door_id, door_id_str)
      → POST /uhomecp-app/v1/userapp/opendoor/submit.json
      → 返回结果
    → 成功：switch.is_on = True → 1秒后 → switch.is_on = False
    → 失败：记录错误日志
```

### 5.2 定时刷新

```
每 30 分钟：
  → client.get_doors()
  → 更新实体列表（新增/移除门禁）
```

## 6. 待验证事项

| # | 事项 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | 密码登录 API 调通 | P0 | ⏳ 待账号解锁 |
| 2 | 门列表 API 响应格式 | P0 | ⏳ 待登录后验证 |
| 3 | 开门 API 响应格式 | P0 | ⏳ 待登录后验证 |
| 4 | 会话过期时间和刷新策略 | P1 | ⏳ 待实测 |
| 5 | HTTPS 证书验证 | P2 | ✅ 默认验证 |

## 7. 依赖

| 包 | 用途 |
|-----|------|
| `cryptography` | RSA 加密（PKCS1v15） |
| `requests` | HTTP 客户端（HA 自带） |
| `homeassistant` | HA 框架 |

## 8. 已知限制

1. **账号锁定**：连续密码错误会导致账号锁定（30分钟~数小时），需做好重试策略
2. **RSA 公钥可能更换**：公钥内嵌在前端，平台方可能随时更换。需要支持从服务器动态获取公钥
3. **会话有效期未知**：Cookie 会话的有效期未实测，需要定时刷新
4. **开门是单次动作**：switch 实体的"开"状态是临时的，开门后自动复位

## 9. 逆向来源

- 前端源码：`https://www.uhomecp.com/h5/wechat-platform-h5/js/app.95d73209.js`
- 门禁组件：`https://www.uhomecp.com/h5/wechat-platform-h5/js/chunk-58b2ccbc.55899fce.js`
- RSA 加密：`https://www.uhomecp.com/h5/wechat-platform-h5/static/common/sg-rsa.js`
- 配置文件：`https://www.uhomecp.com/configs.js`
- V2EX 原帖：`https://www.v2ex.com/t/1228153`
