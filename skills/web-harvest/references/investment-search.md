# Investment Search Reference

Use this reference when `web-harvest` is called for investment research, AI supply-chain research, company mapping, rumor verification, source tracing, order/customer clues, or knowledge-base evidence collection.

The goal is not to maximize search result count. The goal is to turn messy web information into an auditable evidence map.

## Evidence Ladder

Classify each source before using it in a conclusion:

| Level | Source type | How to use |
| --- | --- | --- |
| P0 | Company filings, exchange/regulator disclosures, official company pages, official product pages, official technical blogs, customer/supplier official announcements | Fact base |
| P1 | Reputable factual news, industry media with named sources, standards bodies, conference papers, official event transcripts, credible buy-side style research | Verification and context |
| P2 | Sell-side reports, expert calls, BRM report summaries, target prices, forecast models, industry maps | Clues and assumptions; label as sell-side |
| P3 | KOL posts, social screenshots, self-media, anonymous "small essays", forum posts, unsourced supply-chain claims | Leads only; never final facts without P0/P1/P2 cross-check |

If a conclusion relies mainly on P2/P3, say so and downgrade confidence.

## Default Investment Search Playbooks

### 1. Small-Essay / Rumor Verification

Use for: "小作文", "传闻", "全网在传", "微信群说", "市场说", "有没有这类文章".

Search in this order:

1. Exact phrase and key entities in Chinese.
2. Same claim translated into English/Korean/Japanese when the chain is global.
3. Official company/source pages for each named party.
4. Reputable industry media.
5. Social/KOL sources only after the source ladder is built.

Output:

- Original claim decomposed into atomic claims.
- Source table with source level, URL, date, and whether it supports/contradicts/does not address each claim.
- Verdict: confirmed / partially supported / unsupported / contradicted / too early.
- Investment implication and failure condition.

### 2. Source Tracing

Use for: "找到原文", "源头链接", "这个观点从哪来", "访谈/播客/博客全文".

Search pattern:

- Title/entity + quoted phrase.
- Speaker/company + topic + date.
- Podcast/video/article title + transcript.
- Search official, then transcript mirrors, then media summaries.

Output:

- Best original source URL.
- If original source is audio/video, include transcript/source quality and timestamp if available.
- If only derivative sources exist, label them derivative and avoid treating paraphrases as direct quotes.

### 3. Supply-Chain / Order / Customer Verification

Use for: "谁供货", "是否进入大厂供应链", "审厂", "定点", "订单真实不真实", "受益公司".

Search pattern:

- Customer official announcements, supplier pages, procurement pages, conference presentations.
- Filings and earnings-call transcripts for revenue/customer wording.
- Industry media for supplier checks.
- BRM/sell-side only as P2 clues after official/news sources.

Output:

- Customer evidence: named order, qualification, design-in, audit, shipment, or only inference.
- Supplier evidence: revenue exposure, product match, certification, capacity, and timing.
- Alternative suppliers and substitution risk.
- Confidence rating by evidence level.

### 4. Technology Route / Replacement Claims

Use for: "替代 HBM", "新技术降低成本", "谁会被替代", "技术路线变了".

Search pattern:

- Official architecture pages and technical blogs.
- Standards/OCP/JEDEC/IEEE/conference materials.
- Product specifications and roadmaps.
- Industry teardown or technical analysis.

Output:

- What is replaced, what is supplemented, and what remains core.
- Time horizon: shipping now / announced / sampling / roadmap / concept.
- Workload boundary: training, inference prefill, inference decode, KV cache, storage, networking, packaging.
- Winners and losers by layer, with evidence level.

### 5. Company Universe Discovery

Use for: "还有哪些公司", "第六家", "谁最正宗", "A股映射".

Search pattern:

- Official market-share or shipment sources.
- Company product pages and filings.
- Industry rankings and customer ecosystem pages.
- Local-language searches for Japan/Korea/Taiwan/China supply chains.

Output:

- Core companies, second-line companies, and false positives.
- Product purity and revenue exposure.
- Customer validation.
- Capacity/technology bottleneck.
- Investability and listed ticker mapping if relevant.

## Query Design

Use batch search when the topic has multiple angles:

- Official angle: company + product/architecture + official.
- Industry angle: product + supplier + market share.
- Local-language angle: Chinese/Korean/Japanese/Taiwan media terms.
- Counterclaim angle: "delayed", "cancelled", "reverted", "no order", "not qualified".
- Company mapping angle: product + suppliers + customers.

Prefer 3-5 targeted queries over one broad query.

## Output Checklist

For investment-search tasks, return or save:

- Search channel used: MCP, CLI, extract, web-access, Scrapling, stock-data, or fallback.
- Source table: title, URL, date, source level, claim relevance.
- Claim matrix when there is a rumor or small essay.
- Contradictory evidence and uncertainty.
- What needs follow-up in stock-data, BRM, filings, or the knowledge base.

If writing into Obsidian, preserve URLs, source dates, evidence levels, and whether the item is fact, third-party view, estimate, or scenario.
