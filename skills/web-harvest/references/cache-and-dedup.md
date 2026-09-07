# 跨任务缓存与去重

缓存数据库默认位于 `~/.cache/web-harvest/harvest.sqlite3`。它是执行状态，不属于skill源码，也不进入Obsidian。

## 默认边界

- 普通公开页面默认只保存URL、标题、时间、来源等级、正文指纹、使用工具和Obsidian路径，不保存正文。
- 只有显式传入 `--store-body` 才保存正文。
- 登录态页面传入 `--authenticated` 后默认跳过；只有用户明确允许时才可配合 `--allow-private-metadata` 保存非正文元数据。
- 密码、Cookie、Token、验证码、未公开商业秘密和个人隐私不得写入缓存。
- 同一URL通过规范化查询参数去重；不同URL的相同正文通过SHA-256指纹识别。

## 时效

| kind | 默认有效期 |
|---|---:|
| `t0` | 10分钟 |
| `news` | 6小时 |
| `page` | 24小时 |
| `query` | 6小时 |
| `static` | 3650天 |

缓存命中只表示“已有可复用结果”，不表示内容仍然正确。T0必须按实时数据纪律刷新；用户明确要求最新信息时，应检查发布时间和缓存年龄。

## 常用命令

```bash
python3 scripts/cache.py stats
python3 scripts/cache.py lookup-url "https://example.com/page?utm_source=x"
python3 scripts/cache.py put-document "https://example.com/page" \
  --title "Example" --content-file /tmp/page.md --kind static \
  --source-tier P1 --tool anysearch --obsidian-path "投研笔记知识库/00_Inbox/Example.md"
python3 scripts/cache.py lookup-content --content-file /tmp/page.md
python3 scripts/cache.py lookup-query "latest HBM4 news" --kind news
python3 scripts/cache.py put-query "latest HBM4 news" --route general_search --kind news
```

所有命令均输出JSON，便于其他脚本或agent继续处理。
