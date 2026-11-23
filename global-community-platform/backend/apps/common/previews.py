"""Link previews: when someone shares a CommonGround link on WhatsApp, Facebook, X or
in an SMS app, the app's crawler reads Open Graph tags from the page. The site is a
single-page app, so the server fills those tags into index.html per URL:

- /discussions/<id>  post text and its first photo or video cover
- /u/<username>      name, bio, followers
- /communities/<id>  name, description, members
- /tags/<name>       hashtag and post count
- anything else      the site name and logo

Only things anyone could see without signing in are described (public posts and
communities, non-private profiles); everything else gets the generic preview.
Preview images are served as JPEG (/og-image/<attachment id>.jpg), which every
messaging app accepts, unlike WebP.
"""

import re
from html import escape
from io import BytesIO

from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

SITE_NAME = "CommonGround"
DEFAULT_TITLE = "CommonGround — Ideas build communities"
DEFAULT_DESCRIPTION = "A global space for meaningful conversations and communities. Share photos, videos and stories, chat and call friends, and join communities."
OG_IMAGE_SIZE = (1200, 1200)


def _clip(text, length=180):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _public_post(post_id):
    from apps.discussions.views import visible_discussions

    return visible_discussions(AnonymousUser()).select_related("author", "author__profile", "community").filter(pk=post_id).first()


def describe(request, path):
    """(title, description, image_url, type) for a path, or None for the default."""
    match = re.match(r"^/discussions/(\d+)/?$", path)
    if match:
        post = _public_post(int(match.group(1)))
        if post is None:
            return None
        author = post.author.get_full_name() or post.author.username
        cover = post.attachments.filter(thumbnail__gt="").order_by("created_at").first()
        is_video = post.attachments.filter(content_type__startswith="video/").exists()
        text = post.body or post.title or ("a video" if is_video else "a photo")
        title = f"{author} on {SITE_NAME}" if not post.title else f"{post.title} · {author}"
        image = request.build_absolute_uri(f"/og-image/{cover.pk}.jpg") if cover else ""
        return title, _clip(text), image, "video.other" if is_video else "article"

    match = re.match(r"^/u/([\w.@+-]+)/?$", path)
    if match:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(username=match.group(1), is_active=True).select_related("profile").first()
        profile = getattr(user, "profile", None) if user else None
        if user is None or getattr(profile, "is_private", False):
            return None
        name = user.get_full_name() or user.username
        followers = user.follower_links.count() if hasattr(user, "follower_links") else 0
        bio = getattr(profile, "bio", "") or ""
        avatar = getattr(profile, "avatar_url", "") or ""
        description = _clip(bio) or f"{followers} followers · See {name}'s photos, videos and stories."
        return f"{name} (@{user.username}) · {SITE_NAME}", description, avatar if avatar.startswith("https://") else "", "profile"

    match = re.match(r"^/communities/(\d+)/?$", path)
    if match:
        from apps.communities.models import Community, CommunityMembership

        community = Community.objects.filter(pk=match.group(1), approval_status=Community.APPROVED, visibility=Community.PUBLIC).first()
        if community is None:
            return None
        members = CommunityMembership.objects.filter(community=community, status=CommunityMembership.ACTIVE).count()
        description = _clip(community.description) or f"Join {members} members on {SITE_NAME}."
        image = community.cover_url or community.logo_url or ""
        return f"{community.name} · {SITE_NAME} community", f"{members} members · {description}", image if image.startswith("https://") else "", "website"

    match = re.match(r"^/tags/([\w-]+)/?$", path)
    if match:
        from apps.discussions.models import Hashtag

        tag = Hashtag.objects.filter(name=match.group(1).lower()).first()
        if tag is None:
            return None
        count = tag.discussions.count()
        return f"#{tag.name} on {SITE_NAME}", f"{count} {'post' if count == 1 else 'posts'} tagged #{tag.name}.", "", "website"
    return None


def render_index(request, html):
    """Put the right title, description and Open Graph tags into index.html."""
    try:
        described = describe(request, request.path)
    except Exception:  # a broken preview must never break the page
        described = None
    title, description, image, kind = described or (DEFAULT_TITLE, DEFAULT_DESCRIPTION, "", "website")
    image = image or request.build_absolute_uri("/icons/icon-512.png")
    url = request.build_absolute_uri(request.path)
    tags = "\n".join([
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        f'<meta property="og:type" content="{escape(kind)}" />',
        f'<meta property="og:title" content="{escape(title)}" />',
        f'<meta property="og:description" content="{escape(description)}" />',
        f'<meta property="og:url" content="{escape(url)}" />',
        f'<meta property="og:image" content="{escape(image)}" />',
        f'<meta name="twitter:card" content="{"summary_large_image" if "/og-image/" in image else "summary"}" />',
        f'<meta name="twitter:title" content="{escape(title)}" />',
        f'<meta name="twitter:description" content="{escape(description)}" />',
        f'<meta name="twitter:image" content="{escape(image)}" />',
        f'<link rel="canonical" href="{escape(url)}" />',
    ])
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.S)
    html = re.sub(r'<meta name="description" content="[^"]*"\s*/?>', f'<meta name="description" content="{escape(description)}" />', html, count=1)
    return html.replace("</head>", f"{tags}\n</head>", 1)


@require_GET
def og_image(request, attachment_id):
    """JPEG preview of a public post's first photo (or video cover), max 1200 px."""
    from PIL import Image

    from apps.discussions.models import DiscussionAttachment

    attachment = DiscussionAttachment.objects.filter(pk=attachment_id).select_related("discussion").first()
    if attachment is None or _public_post(attachment.discussion_id) is None:
        raise Http404
    field = attachment.display or attachment.thumbnail
    if not field:
        raise Http404
    with field.open("rb") as handle:
        image = Image.open(BytesIO(handle.read()))
        image.load()
    image = image.convert("RGB")
    image.thumbnail(OG_IMAGE_SIZE)
    out = BytesIO()
    image.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    response = HttpResponse(out.getvalue(), content_type="image/jpeg")
    # Crawlers and the CDN may keep it for a day; it only exists for public posts.
    response["Cache-Control"] = "public, max-age=86400, s-maxage=86400"
    return response
