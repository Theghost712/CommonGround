from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Community(models.Model):
    PUBLIC = "public"
    PRIVATE = "private"
    RESTRICTED = "restricted"

    VISIBILITY_CHOICES = [
        (PUBLIC, "Public"),
        (PRIVATE, "Private"),
        (RESTRICTED, "Restricted"),
    ]

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"

    APPROVAL_STATUS_CHOICES = [
        (PENDING, "Pending Approval"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (SUSPENDED, "Suspended"),
    ]

    approval_status = models.CharField(
        max_length=12,
        choices=APPROVAL_STATUS_CHOICES,
        default=APPROVED,
        db_index=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_communities",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejection_reason = models.TextField(blank=True)

    suspension_reason = models.TextField(blank=True)

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(max_length=1000)
    category = models.CharField(max_length=60, default="General", db_index=True)
    visibility = models.CharField(max_length=12, choices=VISIBILITY_CHOICES, default=PUBLIC, db_index=True)
    logo_url = models.URLField(max_length=500, blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_communities",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["visibility", "created_at"]), models.Index(fields=["category"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:100] or "community"
            candidate = base
            suffix = 2
            while Community.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CommunityMembership(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    ROLE_CHOICES = [
        (OWNER, "Owner"),
        (ADMIN, "Administrator"),
        (MODERATOR, "Moderator"),
        (MEMBER, "Member"),
    ]

    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PENDING, "Pending approval"),
        (REJECTED, "Rejected"),
    ]

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_memberships")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default=MEMBER)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_community_memberships",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["community", "user"], name="unique_community_member")]
        ordering = ["joined_at"]
        indexes = [models.Index(fields=["community", "status", "joined_at"])]

    def approve(self, reviewer):
        self.status = self.ACTIVE
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewer
        self.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    def reject(self, reviewer):
        self.status = self.REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewer
        self.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    def __str__(self):
        return f"{self.user} — {self.community} ({self.status})"


class CommunityRule(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="rules")
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=1000)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return f"{self.community.name}: {self.title}"


class CommunityAnnouncement(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="announcements")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="community_announcements")
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=5000)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"{self.community.name}: {self.title}"
