"""Search engines and link previews.

The React app renders in the browser, so a crawler (Google, WhatsApp, Facebook, X)
fetching /discussions/12 would see an empty page called "CommonGround". For public
discussions and communities, the page shell is filled in on the server with:

- a real <title>, description and canonical link,
- Open Graph / Twitter tags, so shared links show a card with a title and picture,
- schema.org JSON-LD, which Google uses for forum results,
- the text itself inside #root, which React replaces once it loads.

Only content anyone may see signed out is described. Posts in public communities
are offered to search engines (sitemap, index); posts on members' own profiles get
link previews but ask search engines not to index them.
"""
import json
import re

import bleach
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

SITE_NAME = "CommonGround"
DEFAULT_DESCRIPTION = "A global space for meaningful conversations and communities."
SITEMAP_LIMIT = 5000
# Private parts of the app that have nothing for a search engine.
DISALLOWED = ["/api/", "/admin/", "/messages", "/notifications", "/settings/", "/bookmarks", "/moderation", "/earnings", "/pay/", "/profile", "/people/requests"]

_DISCUSSION = re.compile(r"^/discussions/(\d+)/?$")
_COMMUNITY = re.compile(r"^/communities/(\d+)/?$")


def site_url():
    return settings.FRONTEND_URL.rstrip("/")


def _text(value, limit, html=False):
    """Plain text on one line, cut at a word. `html` content has its tags removed first."""
    if html:
        value = bleach.clean(value or "", tags=[], strip=True).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _absolute(url):
    if not url:
        return ""
    return url if url.startswith(("http://", "https://")) else site_url() + url


def public_discussions():
    from apps.discussions.views import visible_discussions

    return visible_discussions(None)


def indexable_discussions():
    from apps.communities.models import Community

    return public_discussions().filter(community__visibility=Community.PUBLIC)


def public_communities():
    from apps.communities.models import Community

    return Community.objects.filter(visibility=Community.PUBLIC, approval_status=Community.APPROVED)


def _discussion_page(pk):
    from apps.discussions.images import image_url

    discussion = public_discussions().select_related("author", "community").prefetch_related("attachments").filter(pk=pk).first()
    if discussion is None:
        return None
    author = discussion.author.get_full_name() or discussion.author.username
    body = _text(discussion.content_html, 5000, html=True) if discussion.content_html else _text(discussion.body, 5000)
    title = discussion.title or _text(body, 70) or f"Post by {author}"
    where = f" in {discussion.community.name}" if discussion.community else ""
    description = _text(body, 200) or f"A post by {author}{where} on {SITE_NAME}."
    image = next((image_url(a, "display") for a in discussion.attachments.all() if a.is_image), "")
    url = f"{site_url()}/discussions/{discussion.pk}"
    comments = discussion.comments.count()
    structured = {
        "@context": "https://schema.org", "@type": "DiscussionForumPosting",
        "headline": title[:110], "text": body[:5000], "url": url,
        "datePublished": discussion.created_at.isoformat(), "dateModified": discussion.updated_at.isoformat(),
        "author": {"@type": "Person", "name": author, "url": f"{site_url()}/u/{discussion.author.username}"},
        "interactionStatistic": {"@type": "InteractionCounter", "interactionType": "https://schema.org/CommentAction", "userInteractionCount": comments},
    }
    if image:
        structured["image"] = _absolute(image)
    snapshot = (
        f"<article><p><a href=\"/u/{escape(discussion.author.username)}\">{escape(author)}</a>"
        + (f" · <a href=\"/communities/{discussion.community_id}\">{escape(discussion.community.name)}</a>" if discussion.community else "")
        + f" · {discussion.created_at:%d %b %Y}</p><h1>{escape(title)}</h1><p>{escape(body)}</p>"
        f"<p>{comments} comment{'s' if comments != 1 else ''}. <a href=\"/register\">Join {SITE_NAME}</a> to take part.</p></article>"
    )
    return {
        "title": f"{title} · {SITE_NAME}", "description": description, "url": url, "image": image, "type": "article",
        "structured": structured, "snapshot": snapshot, "index": discussion.community_id is not None and discussion.community.visibility == "public",
    }


def _community_page(pk):
    community = public_communities().filter(pk=pk).first()
    if community is None:
        return None
    url = f"{site_url()}/communities/{community.pk}"
    description = _text(community.description, 200) or f"Join the {community.name} community on {SITE_NAME}."
    recent = indexable_discussions().filter(community=community).only("pk", "title", "body")[:20]
    links = "".join(f"<li><a href=\"/discussions/{d.pk}\">{escape(d.title or _text(d.body, 80) or 'Post')}</a></li>" for d in recent)
    structured = {"@context": "https://schema.org", "@type": "Organization", "name": community.name, "description": description, "url": url}
    if community.logo_url:
        structured["logo"] = community.logo_url
    return {
        "title": f"{community.name} · {SITE_NAME}", "description": description, "url": url,
        "image": community.cover_url or community.logo_url, "type": "website", "structured": structured,
        "snapshot": f"<main><h1>{escape(community.name)}</h1><p>{escape(_text(community.description, 1000))}</p><ul>{links}</ul></main>",
        "index": True,
    }


def page_for_path(path):
    """Metadata for a public page, or None for everything else."""
    match = _DISCUSSION.match(path)
    if match:
        return _discussion_page(int(match.group(1)))
    match = _COMMUNITY.match(path)
    if match:
        return _community_page(int(match.group(1)))
    return None


def render_shell(html, page):
    """Fill the app shell (dist/index.html) with a page's metadata and text."""
    image = _absolute(page.get("image")) or f"{site_url()}/icons/icon-512.png"
    structured = json.dumps(page["structured"], ensure_ascii=False).replace("<", "\\u003c")
    tags = [
        f'<link rel="canonical" href="{escape(page["url"])}" />',
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        f'<meta property="og:type" content="{page["type"]}" />',
        f'<meta property="og:title" content="{escape(page["title"])}" />',
        f'<meta property="og:description" content="{escape(page["description"])}" />',
        f'<meta property="og:url" content="{escape(page["url"])}" />',
        f'<meta property="og:image" content="{escape(image)}" />',
        f'<meta name="twitter:card" content="{"summary_large_image" if page.get("image") else "summary"}" />',
        f'<meta name="twitter:title" content="{escape(page["title"])}" />',
        f'<meta name="twitter:description" content="{escape(page["description"])}" />',
        f'<meta name="twitter:image" content="{escape(image)}" />',
        f'<script type="application/ld+json">{structured}</script>',
    ]
    if not page.get("index"):
        tags.append('<meta name="robots" content="noindex" />')
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{escape(page['title'])}</title>", html, count=1, flags=re.S)
    html = re.sub(r'<meta name="description" content="[^"]*"\s*/?>', lambda _: f'<meta name="description" content="{escape(page["description"])}" />', html, count=1)
    html = html.replace("</head>", "\n    ".join(["", *tags]) + "\n  </head>", 1)
    return html.replace('<div id="root"></div>', f'<div id="root"><div class="seo-snapshot">{page["snapshot"]}</div></div>', 1)


@require_GET
def robots_txt(request):
    lines = ["User-agent: *", *[f"Disallow: {path}" for path in DISALLOWED], "", f"Sitemap: {site_url()}{reverse('sitemap')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


@require_GET
@cache_page(60 * 60)
def sitemap_xml(request):
    base = site_url()
    urls = [f"<url><loc>{escape(base)}/register</loc><changefreq>monthly</changefreq></url>"]
    for community in public_communities().only("pk", "updated_at").order_by("-updated_at")[:1000]:
        urls.append(f"<url><loc>{escape(base)}/communities/{community.pk}</loc><lastmod>{community.updated_at:%Y-%m-%d}</lastmod><changefreq>daily</changefreq></url>")
    for discussion in indexable_discussions().only("pk", "updated_at").order_by("-updated_at")[:SITEMAP_LIMIT]:
        urls.append(f"<url><loc>{escape(base)}/discussions/{discussion.pk}</loc><lastmod>{discussion.updated_at:%Y-%m-%d}</lastmod></url>")
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    return HttpResponse(body, content_type="application/xml; charset=utf-8")
