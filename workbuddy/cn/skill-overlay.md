---
name: floeva-smart-ring
display_name: Floeva 健康
display_name_en: Floeva Health
description: Query authorized Floeva ring, band, and wearable health data through the Floeva MCP tools. Use for health overviews, Flow, sleep, heart rate, HRV, activity, product help, dashboards, charts, and troubleshooting.
description_zh: 通过 Floeva MCP 工具查询已授权的戒指、腕带和可穿戴健康数据、Flow、趋势与产品帮助。
description_en: Query authorized Floeva ring, band, and wearable health data, Flow, trends, and product help through MCP.
allowed-tools: get_health_overview,get_blood_oxygen_data,get_daily_health_summary,get_flow_score_detail,get_heart_rate_data,get_help,get_hrv_data,get_pressure_data,get_sleep_data,get_steps_data,get_temperature_data,get_user_baseline,get_workout_data
version: 0.1.0
author: Floeva
---

# Floeva Health

Use only the Floeva MCP tools exposed by this connector. Never read local credential files, run an authentication script, construct HTTP requests, or ask the user to paste a password or token. If authorization is missing or expired, ask the user to reconnect the Floeva connector in WorkBuddy.

Before presenting a successful health result, read @references/data-presentation.md completely and follow its units, missing-value, coverage, comparison, and non-diagnostic rules. Answer in the user's language and lead with the most useful grounded finding.

## Choose tools

- Use `get_health_overview` for a broad latest overview. It includes recent sleep, heart, activity, and baseline context when available.
- Use the matching discovered metric tool for sleep, heart rate, HRV, steps, blood oxygen, temperature, pressure, workout, or daily-summary requests.
- Use `get_flow_score_detail` whenever the user asks about Flow. Never infer Flow from overview metrics.
- Use `get_help` for setup, charging, waterproofing, warranty, FAQ, or troubleshooting questions.
- If a requested capability is unfamiliar, inspect the connector's available MCP tools and their schemas. Do not guess a tool name or arguments.

Pass the user's requested date range and IANA timezone only when the selected tool schema supports them. Do not add undeclared arguments. Treat the result as Floeva wearable data: a wearable may be a ring, band, or another supported device, and health measurements do not identify its hardware model.

## Visual requests

For dashboard, chart, graph, or visual-report requests, provide the compact Markdown tables and accessible sparklines from @references/data-presentation.md. This connector version does not expose a browser-opening Canvas tool, so do not claim that a page was opened or a private report was created.

## Errors

- Authorization required: ask the user to reconnect this connector; do not inspect local files.
- Daily limit reached: explain the limit and retry later; do not reauthorize.
- Timeout or service unavailable: offer a retry without inventing results.
- Missing data: keep it missing rather than converting it to zero.

Floeva provides consumer wellness context, not diagnosis or emergency monitoring. If the user reports concerning symptoms, prioritize appropriate professional or emergency guidance.
