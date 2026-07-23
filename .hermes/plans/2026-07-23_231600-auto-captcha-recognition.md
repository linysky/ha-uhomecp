# 自动验证码识别 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 添加 ddddocr 自动验证码识别，session 过期时自动获取验证码→自动识别→自动登录，无需用户手动输入。

**Architecture:** 新增 `captcha.py` 模块封装 ddddocr OCR 逻辑，修改 `config_flow.py` 和 `__init__.py` 在 reauth 流程中集成自动识别。OCR 识别失败时回退到手动输入。

**Tech Stack:** ddddocr (onnxruntime), Python 3.11+, Docker HA 环境

---

## 当前上下文

- 项目：ha-uhomecp (Home Assistant 集成：uhomecp.com 社区门禁)
- 当前版本：v1.1.1
- 分支：beta
- 验证码格式：4 位字母/数字，带干扰线
- 已有 reauth 流程：session 过期 → 显示验证码表单 → 用户手动输入

## 目标流程

```
session 过期
  → 自动获取验证码图片
  → ddddocr 自动识别
  → 自动登录
  ├── 成功 → 更新 session，继续工作
  └── 失败 → 回退到手动输入验证码
```

---

### Task 1: 添加 ddddocr 依赖

**Objective:** 在 manifest.json 中添加 ddddocr 依赖

**Files:**
- Modify: `custom_components/uhomecp/manifest.json:10`

**Step 1: 修改 manifest.json**

```json
"requirements": ["cryptography>=41.0.0", "ddddocr>=1.4.0"],
```

**Step 2: 验证依赖可安装**

```bash
cd /home/linooy/OxShrimp/ha-uhomecp
pip install ddddocr --dry-run
```

Expected: 显示安装计划，无错误

**Step 3: Commit**

```bash
git add custom_components/uhomecp/manifest.json
git commit -m "feat: add ddddocr dependency for captcha OCR"
```

---

### Task 2: 创建 captcha.py OCR 模块

**Objective:** 封装 ddddocr 识别逻辑，提供简洁的识别接口

**Files:**
- Create: `custom_components/uhomecp/captcha.py`

**Step 1: 创建 captcha.py**

```python
"""Captcha OCR recognition using ddddocr."""

import base64
import logging
from io import BytesIO

from PIL import Image

_LOGGER = logging.getLogger(__name__)

# Lazy-load ddddocr to avoid import errors if not installed
_ocr_instance = None


def _get_ocr():
    """Get or create ddddocr instance (lazy load)."""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            import ddddocr
            _ocr_instance = ddddocr.DdddOcr(show_ad=False)
            _LOGGER.info("ddddocr initialized successfully")
        except ImportError:
            _LOGGER.warning("ddddocr not installed, captcha auto-recognition disabled")
            return None
        except Exception as err:
            _LOGGER.error("Failed to initialize ddddocr: %s", err)
            return None
    return _ocr_instance


def recognize_captcha(img_base64: str) -> str | None:
    """Recognize captcha from base64 encoded image.

    Args:
        img_base64: Base64 encoded captcha image (JPEG/PNG)

    Returns:
        Recognized text (4 chars) or None if recognition failed
    """
    ocr = _get_ocr()
    if ocr is None:
        return None

    try:
        img_bytes = base64.b64decode(img_base64)
        result = ocr.classification(img_bytes)

        # Validate: should be 4 alphanumeric chars
        if result and len(result) == 4 and result.isalnum():
            _LOGGER.info("Captcha recognized: %s", result)
            return result

        _LOGGER.warning("Captcha recognition invalid: %s (length=%d)", result, len(result) if result else 0)
        return None
    except Exception as err:
        _LOGGER.error("Captcha recognition failed: %s", err)
        return None


def is_available() -> bool:
    """Check if captcha OCR is available."""
    return _get_ocr() is not None
```

**Step 2: Commit**

```bash
git add custom_components/uhomecp/captcha.py
git commit -m "feat: add captcha OCR module with ddddocr"
```

---

### Task 3: 修改 config_flow.py - 首次登录自动识别验证码

**Objective:** 在首次登录的验证码步骤中，自动尝试识别验证码

**Files:**
- Modify: `custom_components/uhomecp/config_flow.py:109-168`

**Step 1: 添加 import**

在 config_flow.py 顶部添加：

```python
from .captcha import recognize_captcha, is_available
```

**Step 2: 修改 async_step_captcha 方法**

在获取验证码后，自动尝试识别：

```python
async def async_step_captcha(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle the captcha step."""
    errors: dict[str, str] = {}

    # Build captcha image HTML
    captcha_html = f'<img src="data:image/jpeg;base64,{self._img_code}" style="width:200px;">'

    if user_input is not None:
        captcha = user_input["captcha"]

        # Empty captcha = refresh
        if not captcha.strip():
            try:
                self._img_code, self._random_token = (
                    await self._client.async_get_captcha()
                )
            except Exception:
                _LOGGER.exception("Failed to refresh captcha")
                errors["base"] = "unknown"
            captcha_html = f'<img src="data:image/jpeg;base64,{self._img_code}" style="width:200px;">'
            return self.async_show_form(
                step_id="captcha",
                data_schema=STEP_CAPTCHA_DATA_SCHEMA,
                errors=errors,
                description_placeholders={"tip": captcha_html},
            )

        try:
            await self._client.async_login_with_captcha(
                captcha, self._random_token
            )
        except AccountLocked as err:
            _LOGGER.error("Account locked: %s", err)
            errors["base"] = "account_locked"
        except LoginError as err:
            _LOGGER.error("Login with captcha failed: %s", err)
            errors["base"] = "invalid_captcha"
            # Get a fresh captcha
            try:
                self._img_code, self._random_token = (
                    await self._client.async_get_captcha()
                )
            except Exception:
                _LOGGER.exception("Failed to refresh captcha")
                errors["base"] = "unknown"
        except Exception as err:
            _LOGGER.exception("Unexpected error during captcha login: %s", err)
            errors["base"] = "unknown"
        else:
            return await self._after_login()

    # Auto-try OCR if available
    auto_result = await self.hass.async_add_executor_job(
        recognize_captcha, self._img_code
    )
    if auto_result:
        _LOGGER.info("Auto-recognized captcha: %s, trying login", auto_result)
        try:
            await self._client.async_login_with_captcha(
                auto_result, self._random_token
            )
        except (LoginError, Exception) as err:
            _LOGGER.warning("Auto-login with captcha '%s' failed: %s", auto_result, err)
            # Fall through to show manual form
        except AccountLocked as err:
            _LOGGER.error("Account locked during auto-login: %s", err)
            errors["base"] = "account_locked"
        else:
            return await self._after_login()

    return self.async_show_form(
        step_id="captcha",
        data_schema=STEP_CAPTCHA_DATA_SCHEMA,
        errors=errors,
        description_placeholders={"tip": captcha_html},
    )
```

**Step 3: Commit**

```bash
git add custom_components/uhomecp/config_flow.py
git commit -m "feat: auto-recognize captcha on first login"
```

---

### Task 4: 修改 config_flow.py - reauth 流程自动识别验证码

**Objective:** 在 reauth 的验证码步骤中，自动尝试识别验证码

**Files:**
- Modify: `custom_components/uhomecp/config_flow.py:88-139`

**Step 1: 修改 async_step_reauth_captcha 方法**

```python
async def async_step_reauth_captcha(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle captcha step during reauth."""
    errors: dict[str, str] = {}
    captcha_html = f'<img src="data:image/jpeg;base64,{self._img_code}" style="width:200px;">'

    if user_input is not None:
        captcha = user_input["captcha"]

        if not captcha.strip():
            try:
                self._img_code, self._random_token = (
                    await self._client.async_get_captcha()
                )
            except Exception:
                _LOGGER.exception("Failed to refresh captcha")
                errors["base"] = "unknown"
            captcha_html = f'<img src="data:image/jpeg;base64,{self._img_code}" style="width:200px;">'
            return self.async_show_form(
                step_id="reauth_captcha",
                data_schema=STEP_CAPTCHA_DATA_SCHEMA,
                errors=errors,
                description_placeholders={"tip": captcha_html},
            )

        try:
            await self._client.async_login_with_captcha(
                captcha, self._random_token
            )
        except LoginError as err:
            _LOGGER.error("Reauth captcha failed: %s", err)
            errors["base"] = "invalid_captcha"
            try:
                self._img_code, self._random_token = (
                    await self._client.async_get_captcha()
                )
            except Exception:
                _LOGGER.exception("Failed to refresh captcha")
                errors["base"] = "unknown"
        except Exception as err:
            _LOGGER.exception("Unexpected error during reauth: %s", err)
            errors["base"] = "unknown"
        else:
            return await self._after_reauth()

    # Auto-try OCR if available
    auto_result = await self.hass.async_add_executor_job(
        recognize_captcha, self._img_code
    )
    if auto_result:
        _LOGGER.info("Auto-recognized captcha for reauth: %s", auto_result)
        try:
            await self._client.async_login_with_captcha(
                auto_result, self._random_token
            )
        except (LoginError, Exception) as err:
            _LOGGER.warning("Auto-reauth with captcha '%s' failed: %s", auto_result, err)
        except AccountLocked as err:
            _LOGGER.error("Account locked during auto-reauth: %s", err)
            errors["base"] = "account_locked"
        else:
            return await self._after_reauth()

    return self.async_show_form(
        step_id="reauth_captcha",
        data_schema=STEP_CAPTCHA_DATA_SCHEMA,
        errors=errors,
        description_placeholders={"tip": captcha_html},
    )
```

**Step 2: Commit**

```bash
git add custom_components/uhomecp/config_flow.py
git commit -m "feat: auto-recognize captcha during reauth flow"
```

---

### Task 5: 修改 __init__.py - setup 时自动识别验证码

**Objective:** 在 async_setup_entry 中，当 session 过期需要验证码时，自动尝试 OCR 识别

**Files:**
- Modify: `custom_components/uhomecp/__init__.py:44-49`

**Step 1: 添加 import**

```python
from .captcha import recognize_captcha
```

**Step 2: 修改 setup 中的 CaptchaRequired 处理**

```python
    # Restore saved session if available, otherwise fresh login
    saved_cookies = entry.data.get("_cookies")
    saved_user_info = entry.data.get("_user_info")
    if saved_cookies and saved_user_info:
        client.set_session_cookies(saved_cookies)
        client.set_user_info(saved_user_info)
        _LOGGER.info("Restored saved session for %s", phone)
    else:
        try:
            await client.async_login()
        except CaptchaRequired as err:
            # Try auto OCR recognition
            auto_result = await hass.async_add_executor_job(
                recognize_captcha, err.img_code
            )
            if auto_result:
                _LOGGER.info("Auto-recognized captcha during setup: %s", auto_result)
                try:
                    await client.async_login_with_captcha(
                        auto_result, err.random_token
                    )
                except Exception:
                    raise ConfigEntryAuthFailed(
                        "Auto-login failed - please reconfigure"
                    )
            else:
                raise ConfigEntryAuthFailed(
                    "Captcha required - please reconfigure the integration"
                )
        except UHomeCPApiError as err:
            _LOGGER.error("Failed to login: %s", err)
            return False
```

**Step 3: 修改 re-login 中的 CaptchaRequired 处理**

```python
    # Verify session by fetching doors
    try:
        await client.async_get_doors()
    except Exception:
        _LOGGER.info("Saved session invalid, re-logging in")
        try:
            await client.async_login()
        except CaptchaRequired as err:
            # Try auto OCR recognition
            auto_result = await hass.async_add_executor_job(
                recognize_captcha, err.img_code
            )
            if auto_result:
                _LOGGER.info("Auto-recognized captcha during re-login: %s", auto_result)
                try:
                    await client.async_login_with_captcha(
                        auto_result, err.random_token
                    )
                except Exception:
                    raise ConfigEntryAuthFailed(
                        "Auto-login failed - please reconfigure"
                    )
            else:
                raise ConfigEntryAuthFailed(
                    "Captcha required - please reconfigure the integration"
                )
        except UHomeCPApiError as err:
            _LOGGER.error("Failed to login: %s", err)
            return False
```

**Step 4: Commit**

```bash
git add custom_components/uhomecp/__init__.py
git commit -m "feat: auto-recognize captcha during setup and re-login"
```

---

### Task 6: 添加 OCR 可用性状态传感器

**Objective:** 添加一个 binary_sensor 显示 OCR 是否可用，方便用户知道自动识别是否生效

**Files:**
- Modify: `custom_components/uhomecp/sensor.py`

**Step 1: 在 sensor.py 中添加**

```python
from .captcha import is_available

# 在 async_setup_entry 中添加
async_add_entities([
    UHomeCPCommunitySensor(...),
    UHomeCPOcrStatusSensor(...),  # 新增
])
```

```python
class UHomeCPOcrStatusSensor(SensorEntity):
    """Sensor showing if captcha OCR is available."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:text-recognition"
    _attr_name = "验证码识别"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_ocr_status"
        self._attr_device_info = get_device_info(entry)

    @property
    def native_value(self) -> str:
        return "可用" if is_available() else "不可用"
```

**Step 2: Commit**

```bash
git add custom_components/uhomecp/sensor.py
git commit -m "feat: add OCR status sensor"
```

---

### Task 7: 更新翻译文件

**Objective:** 添加新的翻译字符串

**Files:**
- Modify: `custom_components/uhomecp/strings.json`
- Modify: `custom_components/uhomecp/translations/zh-Hans.json`

**Step 1: 更新 strings.json**

在 error 部分添加：

```json
"auto_login_failed": "自动登录失败，请手动输入验证码"
```

**Step 2: 更新 zh-Hans.json**

同样添加：

```json
"auto_login_failed": "自动登录失败，请手动输入验证码"
```

**Step 3: Commit**

```bash
git add custom_components/uhomecp/strings.json custom_components/uhomecp/translations/zh-Hans.json
git commit -m "feat: add auto-login translation strings"
```

---

### Task 8: 测试和验证

**Objective:** 端到端测试自动验证码识别流程

**Step 1: 安装 ddddocr**

```bash
cd /home/linooy/OxShrimp/ha-uhomecp
pip install ddddocr
```

**Step 2: 单独测试 OCR 模块**

```python
python3 -c "
from custom_components.uhomecp.captcha import recognize_captcha, is_available
print('OCR available:', is_available())
# 测试一个真实验证码图片（需要从 API 获取）
"
```

**Step 3: 在 HA 中测试**

1. 删除现有集成
2. 重新添加集成
3. 观察是否自动识别验证码
4. 检查日志确认自动识别流程

**Step 4: 测试 reauth 流程**

1. 等待 session 过期（或手动清除 cookies）
2. 观察是否自动 reauth
3. 检查日志确认自动识别流程

**Step 5: 更新版本号**

```json
// manifest.json
"version": "1.2.0"

// const.py
VERSION = "1.2.0"
```

**Step 6: 发版**

```bash
git add -A
git commit -m "release: v1.2.0 - auto captcha recognition"
git push
```

---

## 风险和注意事项

1. **ddddocr 准确率**：简单验证码 ~85-95%，复杂验证码可能不够。回退机制确保用户体验不受影响。
2. **依赖大小**：ddddocr ~50MB，onnxruntime ~50MB，总计 ~100MB。在 Docker 环境可接受。
3. **首次加载延迟**：ddddocr 首次加载需要几秒，后续使用缓存。
4. **Python 版本**：ddddocr 支持 Python 3.8-3.12，HA Docker 环境通常使用 Python 3.11/3.12，兼容。
5. **账号锁定风险**：自动识别错误可能触发多次登录尝试，导致账号锁定。建议限制重试次数（最多 3 次）。

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `manifest.json` | 修改 | 添加 ddddocr 依赖 |
| `captcha.py` | 新增 | OCR 识别模块 |
| `config_flow.py` | 修改 | 集成自动识别 |
| `__init__.py` | 修改 | setup 时自动识别 |
| `sensor.py` | 修改 | 添加 OCR 状态传感器 |
| `strings.json` | 修改 | 添加翻译 |
| `translations/zh-Hans.json` | 修改 | 添加翻译 |
| `const.py` | 修改 | 更新版本号 |
