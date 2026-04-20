# 抓包操作指南

本文档指导你如何通过抓包获取"鸿鹄智充"公众号菜单背后的真实 URL、API 接口和认证信息。

---

## 准备工作

### 工具选择（任选其一）

| 工具 | 平台 | 费用 | 推荐度 |
|------|------|------|--------|
| **Charles** | macOS / Windows | 付费（30天试用） | ⭐⭐⭐⭐⭐ |
| **Fiddler Classic** | Windows | 免费 | ⭐⭐⭐⭐ |
| **BurpSuite Community** | 全平台 | 免费 | ⭐⭐⭐ |

### 必备辅助工具

- **Proxifier**（Windows/macOS）：强制微信走代理
  - 下载：https://www.proxifier.com/
  - 微信 PC 版默认**不走**系统代理，必须用 Proxifier 强制代理

---

## 方案一：Charles + Proxifier（推荐）

### Step 1：安装并启动 Charles

1. 下载安装 Charles：https://www.charlesproxy.com/download/
2. 启动 Charles，首次运行会提示安装根证书 → 点击"Install"
3. 在 Charles 菜单中：`Proxy` → `SSL Proxying Settings`
   - 勾选 `Enable SSL Proxying`
   - 在 Include 列表中添加：`*:*`（或只添加 `*.weixin.qq.com:*` 和目标域名）
4. 记下 Charles 的代理端口（默认 `8888`）

### Step 2：配置 Proxifier

1. 安装 Proxifier
2. 打开 `Profile` → `Proxy Servers` → `Add`
   - Address: `127.0.0.1`
   - Port: `8888`（Charles 端口）
   - Protocol: `HTTPS`
3. 打开 `Profile` → `Proxification Rules` → `Add`
   - Applications: 选择 `WeChat.exe`（微信进程）
   - Target hosts: `Any`
   - Action: 选择你刚添加的 Charles 代理

### Step 3：抓取菜单跳转

1. 确保 Charles 和 Proxifier 都在运行
2. 打开 PC 微信 → 进入"鸿鹄智充"公众号
3. 在 Charles 中点击 `Proxy` → `Stop Recording`（暂停记录）
4. 清空 Charles 中的所有请求记录
5. 点击 `Proxy` → `Start Recording`（恢复记录）
6. **点击公众号底部的"扫码充电"菜单**
7. 等待 H5 页面完全加载

### Step 4：分析抓包结果

在 Charles 中你会看到一系列请求，重点关注：

#### 4.1 找到菜单跳转 URL
- 在 Filter 中输入 `mp.weixin.qq.com`
- 找到返回 **302 Redirect** 的请求
- 右键 → `Follow` 查看完整的重定向链
- **记录最终的跳转目标 URL** → 这就是 H5 页面的真实地址

#### 4.2 找到数据 API
- 在 Filter 中输入目标域名（如 `honghu` 或 `charge` 等关键词）
- 找到返回 **JSON 数据** 的请求（Response 类型为 `application/json`）
- 这些就是你需要复制的 API 接口

#### 4.3 提取认证信息
- 选中一个 API 请求
- 查看 `Request` 标签页中的：
  - **Headers** → 特别是 `Cookie`、`Authorization`、`User-Agent`
  - **URL** → 完整的请求地址和参数
- 查看 `Response` 标签页中的 JSON 数据结构

---

## 方案二：Fiddler + Proxifier（Windows 用户）

### Step 1：安装 Fiddler Classic

1. 下载：https://www.telerik.com/fiddler/fiddler-classic
2. 启动后，`Tools` → `Options` → `HTTPS`
   - 勾选 `Capture HTTPS CONNECTs`
   - 勾选 `Decrypt HTTPS traffic`
   - 安装证书时点击"是"

### Step 2：配置 Proxifier

与 Charles 方案相同，代理地址改为 `127.0.0.1`，端口改为 `8888`（Fiddler 默认端口）

### Step 3：抓包操作

1. 打开 PC 微信 → 进入"鸿鹄智充"公众号
2. 在 Fiddler 中按 `Ctrl+X` 清空所有会话
3. 点击"扫码充电"菜单
4. 在左侧会话列表中：
   - 找到 `mp.weixin.qq.com` 域名的 302 重定向请求
   - 找到返回 JSON 的 API 请求

### Step 4：提取信息

- 选中请求 → 右侧 `Inspectors` → `Headers`（查看请求头）
- `Inspectors` → `Raw`（查看完整的原始请求）
- `Inspectors` → `JSON`（查看响应数据结构）

---

## 需要记录的信息清单

完成抓包后，请将以下信息填入 `config.yaml`：

### 1. API 接口信息
```
- API 完整 URL: https://xxx.com/api/v1/charge/status
- 请求方法: GET 或 POST
- 请求参数: ?order_id=xxx&token=yyy
```

### 2. 认证信息
```
- Cookie: 完整的 Cookie 字符串
- Authorization: Bearer xxx（如果有）
- User-Agent: 完整的 UA 字符串
- Referer: 来源页面地址
```

### 3. 响应数据结构
```
- 找到功率值在 JSON 中的路径
  例如响应为 {"code":0,"data":{"power":1500,"voltage":220}}
  则功率路径为: data.power
```

### 4. 页面信息（Playwright 模式需要）
```
- H5 页面完整 URL
- 充电功率数字的 CSS 选择器
  （在浏览器中右键功率数字 → 检查元素 → 复制选择器）
```

---

## 常见问题

### Q: Charles/Fiddler 中看不到微信的请求？
**A:** 微信 PC 版不走系统代理，必须使用 Proxifier 强制代理。确保 Proxifier 规则正确配置，并且微信进程名是 `WeChat.exe`。

### Q: HTTPS 请求显示为乱码？
**A:** 需要安装并信任 Charles/Fiddler 的根证书。在 Charles 中：`Help` → `SSL Proxying` → `Install Charles Root Certificate`。

### Q: 抓到的请求很多，如何快速找到目标？
**A:** 使用 Filter 功能，按域名筛选。先找 `mp.weixin.qq.com`（微信域名），再找目标业务域名。关注返回 JSON 格式的请求。

### Q: Token/Cookie 多久会过期？
**A:** 这取决于"鸿鹄智充"平台的服务端设置。通常 OAuth Token 有效期为 2 小时到 7 天不等。建议先测试，记录过期时间，然后在脚本中设置定时刷新。

### Q: 抓包后发现页面没有独立的 API 接口，数据直接渲染在 HTML 中？
**A:** 这种情况下使用 Playwright 模式。在浏览器开发者工具中找到功率数字的 CSS 选择器，填入 `config.yaml` 的 `playwright.power_selector` 配置项。
