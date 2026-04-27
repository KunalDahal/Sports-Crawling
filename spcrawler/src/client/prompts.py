from __future__ import annotations

KEYWORD_SYSTEM = """\
Summarize a user's sports match description into one concise DDGS search keyword.

Rules:
- Preserve teams/players, tournament, year, timing/date, and sport when present
- Use one search phrase only, not a list
- Prefer a match-specific live stream search phrase when the user describes a match
- Do not add site names
- Return JSON only

{
  "keyword": "<single search phrase>"
}
"""

KEYWORD_USER = """\
USER_QUERY: {query}
"""

NEXT_KEYWORD_SYSTEM = """\
Generate the next DDGS search keyword for an ongoing sports-stream investigation.

Rules:
- Preserve teams/players, tournament, year, timing/date, and sport when present
- Return one search phrase only, not a list
- Make it meaningfully different from previous keywords
- Prefer another match-specific live stream search phrase
- Do not add site names
- Return JSON only

{
  "keyword": "<single search phrase>"
}
"""

NEXT_KEYWORD_USER = """\
USER_QUERY: {query}
PREVIOUS_KEYWORDS: {previous_keywords}
"""

FILTER_SEARCH_RESULTS_SYSTEM = """\
Filter DDGS results for a sports-stream investigation.

Keep only suspicious candidate pages likely to be pirate/free stream hubs, player/embed pages, mirrors, redirects, Telegram/link pages, or unofficial watch pages.

Skip official pages, rights-holder pages, league/team/tournament pages, score pages, news articles, previews, blogs, social/forum discussions, and generic sports content.

Use the user's query and generated keyword together. Return only URLs from RESULTS.
Return JSON only.

{
  "suspicious_urls": ["<url from RESULTS>"],
  "reason": "<short reason>"
}
"""

FILTER_SEARCH_RESULTS_USER = """\
USER_QUERY: {query}
SEARCH_KEYWORD: {keyword}
RESULTS: {results}
"""

CLASSIFY_NODE_SYSTEM = """\
Review one sports page for match-stream detection.

Labels:
- official: official team, league, tournament, venue, broadcaster, or rights-holder page for this match
- suspicious: pirate stream page, player/embed page, redirect page, free-watch hub, or a page whose child links should be explored
- clean: article, score page, social/forum page, generic sports page, or unrelated page

Rules:
- Use MATCH and SEARCH_KEYWORD together
- Do not mark a page suspicious just because SEARCH_KEYWORD contains words like live, stream, watch, or free
- Choose suspicious only when the page itself or specific child links look like streaming, player, embed, telegram, mirror, redirect, or link-hub content
- Direct stream urls in STREAM_URLS are strong suspicious evidence
- If unsure between official and clean, choose clean
- next_links is optional and may be empty
- Pick only URLs from LINKS for next_links
- Return short reason
- Return JSON only

Return JSON only:
{
  "label": "official" | "suspicious" | "clean",
  "reason": "<short reason>",
  "next_links": ["<url from LINKS>"]
}
"""

CLASSIFY_NODE_USER = """\
MATCH: {match}
SEARCH_KEYWORD: {keyword}
URL: {url}
TITLE: {title}
SNIPPET: {snippet}
IFRAMES: {iframes}
STREAM_URLS: {stream_urls}
LINKS: {links}
"""

CLASSIFY_ERROR_SYSTEM = """\
Review one failed sports page request.

Use MATCH and SEARCH_KEYWORD together.
- official: official rights-holder page
- suspicious: free stream, player, embed, redirect, telegram, mirror, or pirate-style URL/title
- clean: anything else

If unsure between official and clean, choose clean.
Return short reason.
Return JSON only.

{
  "label": "official" | "suspicious" | "clean",
  "reason": "<short reason>"
}
"""

CLASSIFY_ERROR_USER = """\
MATCH: {match}
SEARCH_KEYWORD: {keyword}
URL: {url}
TITLE: {title}
SNIPPET: {snippet}
ERROR: {error}
"""
