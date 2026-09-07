# AnySearch Reference

AnySearch is the discovery layer for `web-harvest`. It is not a crawler runtime like Scrapling and does not operate the user's browser like `web-access`. Use it to find candidate sources, run vertical searches, batch independent queries, and extract HTML page content as Markdown.

Default priority: use the registered AnySearch MCP tools first when the current Codex thread exposes them (`search`, `batch_search`, `extract`, `get_sub_domains`). Use the local CLI below as the fallback when MCP tools are not hot-loaded, fail, or need command-line recovery.

## Installed Path

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py doc
```

Fast path command:

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py
```

Anonymous access is allowed with lower limits. API key priority is `--api_key` flag, `.env`, environment variable, then anonymous.

## Search

Use for source discovery and current information.

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py search "query" --max_results 5
```

## Vertical Search

For domain-specific topics, call `get_sub_domains` first.

Supported top-level domains include:

- `finance`
- `academic`
- `travel`
- `health`
- `code`
- `legal`
- `gaming`
- `film`
- `business`
- `security`
- `ip`
- `energy`
- `environment`
- `agriculture`
- `resource`
- `social_media`

Example:

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py get_sub_domains --domain finance
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py search "AAPL" --domain finance --sub_domain finance.quote --sdp type=stock,symbol=AAPL,cn_code= --max_results 5
```

If `get_sub_domains` marks a parameter as required, include it in `--sdp`. If no value applies, pass it as an empty value, for example `cn_code=`.

## Batch Search

Use for multiple independent source-finding queries. Maximum 5 queries per call.

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py batch_search --query "q1" --query "q2"
```

Hybrid search when unsure:

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py batch_search --queries '[{"query":"quantum computing"},{"query":"QBTS","domain":"finance","sub_domain":"finance.quote","sub_domain_params":"type=stock,symbol=QBTS,cn_code="}]'
```

## Extract

Use when search snippets are insufficient and the URL is an HTML page.

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py extract "https://example.com/page"
```

The output is already Markdown. Do not pass `--format markdown`, `--format json`, or `--markdown`.

## When to Escalate Beyond AnySearch

- If search returns candidate URLs but data fields must be collected from many pages, use Scrapling.
- If extract fails on a dynamic, login-only, or anti-bot page, use `web-access` or Scrapling `DynamicFetcher`/`StealthyFetcher`.
- If the target is sensitive or private, avoid AnySearch because queries and URLs are sent to `https://api.anysearch.com`.
