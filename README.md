# 问卷星助手 (WJXHelper)

<p align="center">
  <img src="WJX.png" alt="WJXHelper Logo" width="150"/>
</p>

<p align="center">
  <strong>一款功能强大的、由 AI 驱动的问卷星自动化填写工具</strong>
</p>

<p align="center">
    <a href="https://github.com/XLinandWCH/WJXHelper/releases"><img src="https://img.shields.io/github/v/release/XLinandWCH/WJXHelper?style=for-the-badge&color=brightgreen" alt="Release"></a>
    <a href="https://github.com/XLinandWCH/WJXHelper/stargazers"><img src="https://img.shields.io/github/stars/XLinandWCH/WJXHelper?style=for-the-badge" alt="Stars"></a>
    <a href="https://github.com/XLinandWCH/WJXHelper/blob/main/LICENSE"><img src="https://img.shields.io/github/license/XLinandWCH/WJXHelper?style=for-the-badge&color=blue" alt="License"></a>
</p>

---

## 📝 项目简介

**问卷星助手 (WJXHelper)** 是一款智能、高效的自动化工具，旨在将您从繁琐的问卷填写任务中解放出来。它通过模拟真实用户行为，并深度集成了 **AI 智能配置** 功能，让问卷填写变得前所未有的简单和人性化。

无论您是需要处理大量重复问卷的研究人员，还是希望简化数据收集流程的普通用户，WJXHelper 都能为您节省宝贵的时间和精力。

## ✨ 核心功能

| 功能模块 | 特性描述 |
| :--- | :--- |
| **🚀 高效自动化** | 基于 `Selenium` 模拟真实操作，支持多线程并发与无头模式，大幅提升效率。 |
| **🧠 智能配置** | 支持权重随机、概率选择、多样化填空等多种策略，覆盖所有主流题型。 |
| **🤖 AI 驱动** | **(核心亮点)** 只需用自然语言描述您的要求（如“扮演一个满意的顾客”），AI 即可自动为您配置整个问卷的答案策略。支持 Gemini、OpenAI 等主流大语言模型。 |
| **⚙️ 灵活设置** | 支持 Edge, Chrome, Firefox 等主流浏览器，内置代理设置，并可自定义用户数据目录以实现环境隔离。 |
| **💾 配置管理** | 支持一键导入/导出复杂的答案配置文件 (JSON)，方便策略的复用与分享。 |
| **🎨 友好界面** | 直观的图形用户界面，实时监控填写进度与日志，并内置多款UI主题。 |

## 🛠️ 快速上手

### 1. 基础设置
- **首次运行**，请前往 **“程序设置”** 页面。
- **选择浏览器** 并 **指定驱动路径** (如果驱动不在系统环境变量中)。
- **配置 AI 服务** (可选，但强烈推荐)：填入您的 AI 服务商、API Key 和 Base URL。
- 根据需要调整 **并行线程数**、**目标份数**，并建议勾选 **“无头模式”** 以获得最佳性能。

### 2. 配置问卷
- 前往 **“问卷配置”** 页面，粘贴问卷链接并点击 **“加载问卷”**。
- **手动配置**：为每个题目设置权重、概率或填空内容。
- **AI 智能配置**：
    1. 在右侧 AI 助手中输入您的总体要求 (例如：“我是个大学生，消费观比较保守”)。
    2. 点击 **“发送”**，等待 AI 自动完成所有题目的配置。
    3. AI 配置完成后，您仍可手动微调。
- **保存配置**：强烈建议将配置保存为 JSON 文件，方便下次直接导入使用。

### 3. 开始运行
- 前往 **“开始运行”** 页面。
- 点击 **“开始全部填写”** 启动任务。
- 在界面中实时监控总体进度和每个线程的状态。

## 💡 技术栈

- **核心框架**: Python 3, Tkinter (Tkinter-Plus)
- **浏览器自动化**: Selenium
- **AI 服务**: OpenAI, Google Gemini API
- **打包**: PyInstaller

## ⚠️ 注意事项

- **合法合规**: 请在遵守问卷星平台用户协议和相关法律法规的前提下使用本工具。任何因滥用本工具产生的后果由使用者自行承担。
- **浏览器驱动**: 启动失败最常见的原因是浏览器驱动版本与浏览器版本不匹配。请确保二者严格对应。
- **人机验证**: 本工具对复杂的人机验证（如滑块、识图）处理能力有限。遇到频繁验证失败时，请尝试减少线程数或在非无头模式下观察。

---

感谢您的使用！如果觉得项目不错，请给一个 ⭐️ Star！