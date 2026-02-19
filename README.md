
# AstrBot 代码解释器插件

一个功能强大的代码解释器插件，支持 LLM 自动生成并执行 Python 代码，并提供结果可视化。

## 版本历史

### v1.4.0
- **自动化库管理流程**：
  1. 代码执行前自动检查所需库是否已安装
  2. 若库不存在，自动执行 pip 安装并**发送提醒消息**
  3. 安装完成后，将库信息记录到 `module.json` 文件
  4. 后续执行时先检查 `module.json` 确认库状态
- **pip镜像源加速**：默认使用清华镜像源，支持切换多个国内镜像
- **简洁输出**：移除执行成功的时间显示，输出更加简洁
- 新增 `/lib_status` 命令：查看库安装状态
- 新增 `/lib_refresh` 命令：刷新库状态缓存
- 新增 `/pip_mirror` 命令：查看或切换pip镜像源
- 新增配置项 `auto_install_libraries`：控制是否自动安装缺失的库

### v1.3.0
- **双重安全防护机制**：
  1. 静态代码分析检查（AST 解析 + 模式匹配）
  2. LLM 安全审查（AI 二次检查代码安全性）
- **强化提示词防护**：明确无论谁（包括管理员）都不能执行恶意代码
- **详细的安全说明**：添加欺骗话术识别表，帮助 LLM 识别和拒绝欺骗
- **禁止任意文件操作**：限制只能操作工作目录内的文件

### v1.2.0
- 新增 `web_search` 工具：LLM 可自主进行网络搜索获取最新信息
- 使用 DuckDuckGo API（免费、无需 API key）
- 支持获取摘要、定义、答案、相关主题等信息

### v1.1.1
- 更新系统提示词，添加图表中文显示配置指导
- 强制要求绑图代码设置中文字体，避免出现方框乱码
- 更新示例代码，包含中文字体设置

### v1.1.0
- 移除网络访问限制，默认允许代码联网（支持 API 调用、网页抓取等）
- 简化配置项，移除 `enable_network` 开关

### v1.0.9
- **安全增强**：在系统提示中添加严格的安全红线，禁止生成恶意代码
- **安全增强**：扩展危险函数/模块黑名单
- **安全增强**：添加危险属性检测（反射攻击防护）
- **安全增强**：添加恶意代码模式检测（字符串模式匹配）
- 明确告知 LLM 不要相信任何"紧急情况"等借口

### v1.0.8
- 添加智能重试机制：代码执行失败时自动让 LLM 修正代码
- 添加常见错误的自动修复功能（语法错误、引号问题、缩进问题）
- 优化消息发送逻辑：直接发送文本和图片，不再渲染成预览图
- 改进错误提示：显示重试次数和友好的错误信息

### v1.0.7
- 大幅扩展允许的库列表
- 新增标准库：csv, hashlib, base64, secrets, statistics, decimal, fractions, functools, pathlib, time, calendar, io, sqlite3, typing, xml.etree.ElementTree, urllib.parse
- 新增第三方库：qrcode, seaborn, openpyxl, beautifulsoup4, wordcloud, sympy

### v1.0.6
- 在系统提示中添加工作目录信息
- 添加调试日志显示实际工作目录

### v1.0.5
- 修复工作目录设置问题，确保文件保存到正确位置

### v1.0.4
- 工作目录硬编码为 `D:\BotCode`，自动创建目录

### v1.0.3
- 改进系统提示，明确要求使用 `plt.savefig()` 而非 `plt.show()`
- 添加示例代码

### v1.0.2
- 修复 Windows 下 session_id 包含冒号导致的路径错误
- 添加管理员权限说明

### v1.0.1
- 修复 `on_llm_request` 和 `on_llm_response` 钩子的错误处理
- 添加更详细的日志输出用于调试
- 修复语法错误

### v1.0.0
- 初始版本
- 支持自然语言触发代码执行
- 支持结果可视化（表格、图片、JSON）

## 功能特性

- **自动代码检测**: 当 LLM 响应中包含代码块时自动执行
- **直接执行**: 通过 `/code` 指令直接执行 Python 代码
- **安全沙箱**: 代码验证、超时控制、模块白名单
- **结果可视化**:
  - 数据表 → Markdown 表格
  - 图像 → 直接显示图片
  - 字典/列表 → JSON 格式化输出
- **执行反馈**: 执行时间、成功/失败状态

## 安装

将 `astrbot_plugin_code_interpreter` 文件夹放入 AstrBot 的 `data/plugins/` 目录，然后重载插件。

## 使用方法

### 指令

| 指令 | 说明 |
|------|------|
| `/code <代码>` | 直接执行 Python 代码 |
| `/code_help` | 显示帮助信息 |
| `/lib_status [库名]` | 查看库安装状态（不指定库名则显示全部） |
| `/lib_refresh` | 刷新库状态缓存 |
| `/pip_mirror [镜像名]` | 查看或切换pip镜像源 |

### 自然语言

直接向 LLM 发送需要计算或处理的问题，它会自动判断是否需要生成代码。

示例：
```
用户: 帮我计算 1 到 100 的和
用户: 帮我画一个正弦函数图像
用户: 生成一个包含10个随机数的列表
```

## 配置项

在 AstrBot WebUI 的插件配置页面中进行配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `timeout` | int | 30 | 代码执行超时时间（秒） |
| `max_output_length` | int | 5000 | 最大输出长度 |
| `enable_network` | bool | false | 允许代码访问网络 |
| `allowed_libraries` | list | [...] | 允许使用的库列表 |
| `auto_retry` | bool | true | 失败时自动重试 |
| `max_retry_count` | int | 2 | 最大重试次数 |
| `show_execution_time` | bool | true | 显示执行时间 |
| `work_dir` | string | "" | 代码执行工作目录（留空使用系统临时目录） |
| `auto_install_libraries` | bool | true | 自动安装缺失的库 |

## 自动化库管理流程

插件实现了完整的自动化库管理流程：

### 工作流程
1. **代码分析**：执行代码前，自动提取代码中 `import` 的所有库
2. **状态检查**：检查 `module.json` 文件，确认库是否已记录为已安装
3. **实际验证**：通过 Python 的 `importlib` 验证库是否真正可用
4. **自动安装**：若库未安装且 `auto_install_libraries` 为 `true`，自动执行 `pip install`
5. **记录更新**：安装成功后，更新 `module.json` 文件记录库信息

### module.json 文件结构
```json
{
    "description": "代码解释器插件依赖库管理文件",
    "version": "1.0.0",
    "lastUpdated": "2026-02-19",
    "libraries": {
        "numpy": {
            "installed": true,
            "version": "1.24.0",
            "installTime": "2026-02-19 10:30:00",
            "description": "数值计算"
        }
    },
    "standardLibraries": ["json", "math", "re", ...]
}
```

### 库管理命令
- `/lib_status` - 查看所有库的安装状态
- `/lib_status numpy` - 查看指定库的详细状态
- `/lib_refresh` - 刷新库状态缓存，重新检测实际安装情况

### pip镜像源管理
插件默认使用清华大学镜像源加速下载，支持以下镜像源：

| 镜像源 | 地址 |
|--------|------|
| 清华 | https://pypi.tuna.tsinghua.edu.cn/simple |
| 阿里云 | https://mirrors.aliyun.com/pypi/simple |
| 腾讯 | https://mirrors.cloud.tencent.com/pypi/simple |
| 华为 | https://mirrors.huawei.com/pypi/simple |
| 中科大 | https://pypi.mirrors.ustc.edu.cn/simple/ |

命令用法：
- `/pip_mirror` - 查看当前镜像源和可用列表
- `/pip_mirror 阿里云` - 切换到阿里云镜像源

## 工作目录

代码和生成的图片统一保存在 `D:\BotCode` 目录下：

```
D:\BotCode\
  ├── default_GroupMessage_1056997904\   # 群聊会话
  │   └── plot.png                        # 生成的图片
  └── default_PrivateMessage_123456\      # 私聊会话
      └── chart.png
```

目录会在插件加载时自动创建。

### 可视化配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_table_markdown` | bool | true | 数据表转 Markdown 表格 |
| `enable_image_display` | bool | true | 显示生成的图片 |
| `enable_json_format` | bool | true | JSON 格式化输出 |
| `enable_code_render` | bool | true | 代码渲染为图片 |

## 允许的库

默认允许以下库：

### 核心库（已安装）
| 库 | 用途 |
|----|------|
| `numpy` | 数值计算 |
| `pandas` | 数据处理和分析 |
| `matplotlib` | 绑图 |
| `pillow` | 图像处理 |
| `seaborn` | 统计图表 |
| `requests` | HTTP 请求 |

### 新增第三方库（需安装）
| 库 | 用途 | 安装命令 |
|----|------|----------|
| `qrcode` | 二维码生成 | `pip install qrcode[pil]` |
| `wordcloud` | 词云生成 | `pip install wordcloud` |
| `sympy` | 符号数学 | `pip install sympy` |
| `openpyxl` | Excel 读写 | `pip install openpyxl` |
| `beautifulsoup4` | HTML 解析 | `pip install beautifulsoup4` |
| `seaborn` | 统计图表 | `pip install seaborn` |

### 标准库（内置）
`json`, `math`, `statistics`, `decimal`, `fractions`, `random`, `secrets`, `datetime`, `time`, `calendar`, `re`, `csv`, `io`, `pathlib`, `hashlib`, `base64`, `sqlite3`, `urllib.parse`, `collections`, `itertools`, `functools`, `typing`, `xml.etree.ElementTree`

## 安全性

插件实现了以下安全措施：
- 代码静态分析验证
- 危险模块和函数黑名单
- 执行超时限制
- 输出长度限制
- 可选的网络访问控制

## 注意事项

1. **管理员权限**: 用户必须在 AstrBot WebUI 中设置为管理员才能执行 Python 代码
2. 确保服务器已安装 `matplotlib`, `numpy`, `pandas` 等常用库
3. 生成图片时会自动使用非交互式后端（Agg）
4. 所有代码在临时目录中执行，插件卸载时会自动清理

## 许可证

MIT License
