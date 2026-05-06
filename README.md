# 智能查询数据 Agent

这是一个本地可运行的数据查询 agent，支持自然语言查 `JSON/CSV`，并提供聊天式 Web 界面、图表展示和结果导出。

## 当前能力

- 中文自然语言查询
- 本地规则解析
- 可选 OpenAI 增强解析
- 摘要卡片、结果表格、柱状图
- 导出 `CSV/JSON`

## 快速开始

命令行版本：

```bash
python agent.py --data data/sample_sales.json --query "按地区统计销售额"
```

Web 版本：

```bash
python webapp.py --data data/sample_sales.json --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 启用 OpenAI

设置环境变量：

```powershell
$env:OPENAI_API_KEY="你的 OpenAI API Key"
$env:OPENAI_MODEL="gpt-5-mini"
python webapp.py --data data/sample_sales.json
```

如果没有设置 `OPENAI_API_KEY`，系统会自动回退到本地规则模式。

## 示例问题
<img width="1916" height="1450" alt="image" src="https://github.com/user-attachments/assets/b9001055-2800-42da-a972-a3a8e3443246" />

- `华东地区销售额总和`
- `状态为已完成的订单有多少条`
- `按地区统计销售额`
- `销售额最高的是哪条记录`
- `利润平均值是多少`

## 说明

当前 OpenAI 集成使用的是官方 `Responses API`，用于把自然语言转换成结构化查询计划；真正的数据执行仍然发生在本地。
