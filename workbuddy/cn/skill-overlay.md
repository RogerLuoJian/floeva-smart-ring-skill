---
name: floeva-smart-ring
display_name: Floeva
display_name_en: Floeva
description: Query authorized Floeva ring, band, and wearable health data through the packaged Floeva CLI. Use for health overviews, Flow, sleep, heart rate, HRV, activity, product help, dashboards, charts, and troubleshooting.
description_zh: 通过 Floeva CLI 查询已授权的戒指、腕带和可穿戴健康数据、Flow、趋势与产品帮助。
description_en: Query authorized Floeva ring, band, and wearable health data, Flow, trends, and product help through the packaged CLI.
allowed-tools: Bash
version: 0.2.1
author: Floeva
---

# Floeva

Use only the packaged `scripts/floeva-auth.py` CLI through Bash. The CLI owns authentication, reads its private credential store, restricts Floeva hosts and operations, and emits business JSON. Never read local credential files, construct HTTP requests, or ask the user to paste a password or token. If authorization is missing or expired, ask the user to reconnect the Floeva connector in WorkBuddy.

Before presenting a successful health result, read @references/data-presentation.md completely and follow its units, missing-value, coverage, comparison, and non-diagnostic rules. Answer in the user's language and lead with the most useful grounded finding.

## Commands

- Run `python3 scripts/floeva-auth.py overview --client floeva-workbuddy-cn` for a broad latest overview. On Windows use `python` instead of `python3`.
- Run `python3 scripts/floeva-auth.py tools --client floeva-workbuddy-cn` before a focused query. Select only a returned tool and follow its parameter schema.
- Run a selected tool as `python3 scripts/floeva-auth.py call --client floeva-workbuddy-cn --tool <name> --arguments '<JSON object>'`. Use one shell argument for the JSON and do not interpolate shell syntax from user text.
- Use `get_flow_score_detail` whenever the user asks about Flow. Never infer Flow from overview metrics.
- Use `get_help` for setup, charging, waterproofing, warranty, FAQ, or troubleshooting questions.
- If a requested capability is absent from `tools`, explain that it is unavailable. Do not guess a tool name or arguments.

Pass the user's requested date range and IANA timezone only when the selected tool schema supports them. Do not add undeclared arguments. Treat the result as Floeva wearable data: a wearable may be a ring, band, or another supported device, and health measurements do not identify its hardware model.

## Visual requests

For dashboard, chart, graph, or visual-report requests, provide the compact Markdown tables and accessible sparklines from @references/data-presentation.md. This connector version does not expose a browser-opening Canvas command, so do not claim that a page was opened or a private report was created.

## Errors

- Authorization required: ask the user to reconnect this connector; do not inspect local files.
- Daily limit reached: explain the limit and retry later; do not reauthorize.
- Timeout or service unavailable: offer a retry without inventing results.
- Missing data: keep it missing rather than converting it to zero.

Floeva provides consumer wellness context, not diagnosis or emergency monitoring. If the user reports concerning symptoms, prioritize appropriate professional or emergency guidance.
