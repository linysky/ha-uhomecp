# HA 集成验证码识别方案调研

> 调研时间：2026-08-01

## 调研项目

| 项目 | Stars | 验证码类型 | 方案 | Docker/Alpine 兼容 |
|------|-------|-----------|------|-------------------|
| [sgcc_electricity_new](https://github.com/ARC-MX/sgcc_electricity_new) | 1774 | 腾讯滑块+点选 | ONNX 离线模型 + 大模型 API 兜底 | ✅ 自带 Docker 镜像 |
| [ha-95598](https://github.com/renxiaoyaoo/ha-95598) | 37 | 腾讯点选 | 纯图片算法（Pillow）+ Selenium 截图 | ✅ 自带 Docker 镜像 |
| [erovinieta](https://github.com/emanuelbesliu/homeassistant-erovinieta) | 5 | 简单文字（4位字母） | Pillow 模板匹配，零外部依赖 | ✅ 纯 Python |

## 方案详解

### 方案 A：Pillow 模板匹配（erovinieta 项目）⭐ 最推荐

**原理：** 预先用 ddddocr 标注 200 张验证码样本，提取每个字母的二值化像素模板（20×28），内嵌到代码中。运行时对验证码图片做字符分割 + 模板匹配。

**优点：**
- **零外部依赖** — 只用 Pillow（HA 自带）
- **94% 单字符准确率，99.9% 整体成功率**（含 5 次重试）
- **在任何环境都能跑** — 不需要 onnxruntime、tesseract 等
- 代码量约 400 行，模板数据压缩后约 10KB
- 有 i/l 模糊消歧的启发式算法

**缺点：**
- 需要针对特定验证码字体预训练模板
- 只适合简单文字验证码，不适合滑块/点选/扭曲验证码

**适配 uhomecp：**
- uhomecp 是 4 位字母/数字混合验证码，和 erovinieta 类似
- 需要收集 uhomecp 验证码样本，用 ddddocr 标注后生成模板
- 在 glibc 环境先用 ddddocr 标注 → 提取模板 → 内嵌代码 → musllinux 直接跑

**代码：** `captcha_ocr.py` 约 400 行，模板用 zlib 压缩 + base64 编码

### 方案 B：ONNX 离线模型（sgcc_electricity_new）

**原理：** 训练一个轻量 CNN 模型，导出为 ONNX 格式，用 onnxruntime 推理。

**优点：**
- 准确率高（接近 100%）
- 不依赖网络
- 支持复杂验证码

**缺点：**
- **onnxruntime 在 musllinux 上没有预编译 wheel** — 需要自己编译
- 模型文件较大（几 MB）
- 需要训练数据和训练流程

**适用场景：** 如果 onnxruntime 能在目标环境跑（glibc Linux），这是最佳方案。但对我们 musllinux 环境不适用。

### 方案 C：大模型 API（sgcc_electricity_new 新版）

**原理：** 把验证码图片发给大模型（火山引擎豆包等），让 LLM 识别文字。

**优点：**
- 准确率极高（LLM 理解能力）
- 不需要本地模型/依赖
- 适应各种验证码变形

**缺点：**
- 需要网络 + API Key
- 有成本（每次识别调 API）
- 增加延迟

**适用场景：** 作为兜底方案，当本地方案失败时使用。

### 方案 D：Selenium + 浏览器自动化（ha-95598）

**原理：** 用 Selenium 控制 Chrome 浏览器，截图后用图片算法识别。

**优点：**
- 能处理复杂的交互式验证码（点选、滑块）
- 最贴近真实用户行为

**缺点：**
- 需要 Chrome + chromedriver + Xvfb
- 资源占用大（几百 MB 镜像）
- 在 HA 插件中不现实（HA 不自带浏览器）

## 对 uhomecp 的建议

### 短期：方案 A（Pillow 模板匹配）

1. 在 glibc 环境用 ddddocr 批量识别 uhomecp 验证码，收集标注
2. 提取每个字符的二值化像素模板
3. 压缩内嵌到代码中
4. 代码用 Pillow 做字符分割 + 模板匹配
5. 在 musllinux 上直接跑，零依赖

**预估工作量：** 1-2 天
**预估准确率：** 90-95%（单次），99%+（含重试）

### 中期：方案 C（大模型 API 兜底）

当本地 OCR 失败时，可选调用大模型 API 识别。用户自行配置 API Key。

### 不推荐

- ❌ onnxruntime — musllinux 无 wheel，编译复杂
- ❌ tesseract — 已验证准确率仅 40%
- ❌ ddddocr — musllinux 装不上 onnxruntime
- ❌ Selenium — HA 插件中不现实
