# Router Reference

## Decision Rules

Use the cheapest reliable path first, then escalate.

## Default Tool Ownership

- `web-harvest` owns routing only. It decides which channel to use and should not duplicate work that a narrower tool can do better.
- `AnySearch MCP` owns search discovery, vertical search, batch search, and URL Markdown extraction when `mcp__anysearch__*` tools are exposed in the current Codex thread.
- `AnySearch CLI` is the fallback for the same AnySearch functions when MCP tools are not hot-loaded, unavailable, rate-limited, or failing.
- `web-access` owns real browser work: login state, clicks, scrolling, screenshots, uploads, account-scoped pages, and pages where human browser state matters.
- `Scrapling` owns production crawling: repeated pages, pagination, JSON/CSV exports, retry/checkpointed runs, dynamic public pages at scale, and adaptive selectors.
- `Agent Reach` owns platform-native routing and health checks for YouTube, Bilibili, RSS, V2EX, GitHub, and optional authenticated social channels. Its Exa backend supplements English technical/code semantic search; it does not replace AnySearch for general discovery.
- `stock-data` owns structured financial data: quotes, K-lines, financial statements, valuation, funds flow, announcements, research reports, indices, and ETFs. Search tools only supplement sources and context.
- Built-in web tools are lightweight fallback or verification tools, especially for official docs and single-page checks.

Conflict rule: prefer the owner above. When two tools can do the same thing, choose the cheaper/narrower one first: AnySearch MCP over CLI, AnySearch before Exa for generic search, Agent Reach for platform-native content, single-page extraction over browser, `web-access` over Scrapling for login/interaction, Scrapling over browser for repeatable bulk crawling, and `stock-data` over generic web or Xueqiu search for structured finance.

1. Unknown source or search problem:
   - Use AnySearch MCP `search` for general discovery; fall back to AnySearch CLI.
   - Use AnySearch MCP `get_sub_domains` then vertical search for domain-specific topics; fall back to CLI.
   - Use AnySearch MCP `batch_search` for multiple independent leads or hybrid general+vertical coverage; fall back to CLI.
   - If anonymous AnySearch returns daily quota exhaustion, fall back to Agent Reach Exa or built-in search for the current task. Do not describe this as a broken/expired key unless a key was actually supplied and the response is 401/403.
2. Static public page:
   - Use built-in web tools, Jina, curl, or Scrapling `Fetcher`.
   - Use AnySearch MCP/CLI `extract` when Markdown content is enough.
3. Dynamic public page:
   - Use Scrapling `DynamicFetcher`.
   - If layout/interaction matters more than scale, use `web-access`.
4. Login-aware page:
   - Use `web-access` with the user's real browser session.
   - Do not extract or persist sensitive cookies unless explicitly authorized and necessary.
5. Anti-bot or challenge page:
   - Check whether the task is authorized and necessary.
   - For occasional user-authorized access, prefer `web-access`.
   - For repeatable public-data collection, consider Scrapling `StealthyFetcher` with rate limits and proxies.
6. Large crawl:
   - Use Scrapling `Spider` with concurrency limits, checkpointing, exports, and retry logic.
7. Platform-native content:
   - Load `<your-skills-root>/agent-reach/SKILL.md`.
   - Run `agent-reach doctor --json` and use only a healthy `active_backend`.
   - Use Exa only as a complementary semantic/code search path when AnySearch recall is insufficient.
   - Never auto-import browser cookies or configure account credentials without explicit user authorization.

## Risk Levels

Green:
- Public pages, documentation, official announcements, pages with permissive robots or APIs.

Yellow:
- Logged-in pages owned by the user or organization, social platforms, heavy dynamic pages, frequent requests.

Red:
- Paywalls, private data, account abuse, CAPTCHA farms, credential extraction, bypassing explicit access controls.

Refuse red tasks or ask for a compliant alternative.

## Probing Checklist

- Does the first response contain target data in HTML?
- Is the source URL unknown, requiring AnySearch discovery first?
- Does the topic belong to a vertical domain where AnySearch `get_sub_domains` can improve recall?
- Does the page require JavaScript rendering?
- Is login required?
- Is there a stable API endpoint visible through browser behavior?
- Does pagination use URL params, cursor tokens, infinite scroll, or POST bodies?
- Are there rate limits or challenge pages?
- What output fields are required?

## Combining web-access and Scrapling

Use AnySearch as the discovery layer:

- Find official pages, source URLs, article pages, documents, code docs, company pages, or domain-specific records.
- Run batch or hybrid queries when one query formulation is too narrow.
- Extract candidate HTML pages to Markdown for quick triage.
- Prefer MCP when exposed in the active thread; use the CLI fallback for the same calls when MCP is absent.

Use `web-access` as the browser reconnaissance layer:

- Open the page with the real browser.
- Inspect DOM and network-observable behavior.
- Discover natural links and cursor patterns.
- Validate selectors and sample fields.

Then use Scrapling as the production layer:

- Encode selectors and pagination.
- Add checkpointing and retries.
- Export structured JSONL/CSV.
- Keep request rate conservative.
