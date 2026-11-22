from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Community, CommunityMembership
from apps.discussions.models import Discussion
from apps.events.models import CommunityEvent

User = get_user_model()


class CommunityManagementAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="StrongPass123!")
        self.applicant = User.objects.create_user(username="applicant", password="StrongPass123!")
        self.admin = User.objects.create_user(username="admin", password="StrongPass123!")
        self.community = Community.objects.create(
            name="Global Ideas",
            description="A place for useful conversations.",
            category="General",
            visibility=Community.RESTRICTED,
            created_by=self.owner,
        )
        CommunityMembership.objects.create(
            community=self.community, user=self.owner,
            role=CommunityMembership.OWNER, status=CommunityMembership.ACTIVE,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_restricted_join_creates_pending_request(self):
        self.authenticate(self.applicant)
        response = self.client.post(f"/api/v1/communities/{self.community.id}/join/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], CommunityMembership.PENDING)

    def test_owner_can_approve_membership_request(self):
        membership = CommunityMembership.objects.create(
            community=self.community, user=self.applicant,
            status=CommunityMembership.PENDING,
        )
        self.authenticate(self.owner)
        response = self.client.post(
            f"/api/v1/communities/{self.community.id}/approve-request/",
            {"membership_id": membership.id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.status, CommunityMembership.ACTIVE)
        self.assertEqual(membership.reviewed_by, self.owner)

    def test_regular_member_cannot_approve_membership_request(self):
        CommunityMembership.objects.create(
            community=self.community, user=self.admin,
            role=CommunityMembership.MEMBER, status=CommunityMembership.ACTIVE,
        )
        target = CommunityMembership.objects.create(
            community=self.community, user=self.applicant,
            status=CommunityMembership.PENDING,
        )
        self.authenticate(self.admin)
        response = self.client.post(
            f"/api/v1/communities/{self.community.id}/approve-request/",
            {"membership_id": target.id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        target.refresh_from_db()
        self.assertEqual(target.status, CommunityMembership.PENDING)

    def test_private_community_is_hidden_from_non_members(self):
        self.community.visibility = Community.PRIVATE
        self.community.save(update_fields=["visibility"])
        self.authenticate(self.applicant)
        response = self.client.get(f"/api/v1/communities/{self.community.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_creator_cannot_set_community_approval_status(self):
        self.community.approval_status = Community.APPROVED
        self.community.save(update_fields=["approval_status"])
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/v1/communities/{self.community.id}/",
            {"approval_status": Community.SUSPENDED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.APPROVED)

    def test_owner_cannot_manage_community_before_platform_approval(self):
        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/v1/communities/{self.community.id}/",
            {"name": "Pending edit"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.community.refresh_from_db()
        self.assertEqual(self.community.name, "Global Ideas")

    def test_non_staff_cannot_open_platform_approval_admin(self):
        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        self.client.force_authenticate(user=None)
        self.client.force_login(self.owner)

        response = self.client.post(
            "/admin/communities/community/",
            {"action": "approve_communities", "_selected_action": [self.community.id]},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.PENDING)

    def test_platform_change_permission_can_approve_and_reject_communities(self):
        platform_user = User.objects.create_user(username="community_platform", password="StrongPass123!")
        platform_user.is_staff = True
        platform_user.save(update_fields=["is_staff"])
        permission = Permission.objects.get(
            content_type__app_label="communities", codename="change_community"
        )
        platform_user.user_permissions.add(permission)
        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        self.client.force_login(platform_user)

        approved = self.client.post(
            "/admin/communities/community/",
            {"action": "approve_communities", "_selected_action": [self.community.id]},
        )
        self.assertEqual(approved.status_code, status.HTTP_302_FOUND)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.APPROVED)

        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        rejected = self.client.post(
            "/admin/communities/community/",
            {"action": "reject_communities", "_selected_action": [self.community.id]},
        )
        self.assertEqual(rejected.status_code, status.HTTP_302_FOUND)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.REJECTED)

        self.community.approval_status = Community.APPROVED
        self.community.save(update_fields=["approval_status"])
        suspended = self.client.post(
            "/admin/communities/community/",
            {"action": "suspend_communities", "_selected_action": [self.community.id]},
        )
        self.assertEqual(suspended.status_code, status.HTTP_302_FOUND)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.SUSPENDED)

        restored = self.client.post(
            "/admin/communities/community/",
            {"action": "restore_communities", "_selected_action": [self.community.id]},
        )
        self.assertEqual(restored.status_code, status.HTTP_302_FOUND)
        self.community.refresh_from_db()
        self.assertEqual(self.community.approval_status, Community.APPROVED)

    def add_membership(self, user, role):
        return CommunityMembership.objects.create(
            community=self.community, user=user, role=role,
            status=CommunityMembership.ACTIVE,
        )

    def test_owner_can_assign_and_remove_moderators(self):
        self.add_membership(self.applicant, CommunityMembership.MEMBER)
        self.authenticate(self.owner)

        promote = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": CommunityMembership.objects.get(user=self.applicant).id, "role": CommunityMembership.MODERATOR},
            format="json",
        )
        self.assertEqual(promote.status_code, status.HTTP_200_OK)
        self.assertEqual(promote.data["role"], CommunityMembership.MODERATOR)

        demote = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": promote.data["id"], "role": CommunityMembership.MEMBER},
            format="json",
        )
        self.assertEqual(demote.status_code, status.HTTP_200_OK)
        self.assertEqual(demote.data["role"], CommunityMembership.MEMBER)

    def test_community_admin_can_assign_moderator_but_not_platform_privileges(self):
        self.add_membership(self.admin, CommunityMembership.ADMIN)
        target = self.add_membership(self.applicant, CommunityMembership.MEMBER)
        self.authenticate(self.admin)

        promote = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": target.id, "role": CommunityMembership.MODERATOR},
            format="json",
        )
        self.assertEqual(promote.status_code, status.HTTP_200_OK)

        assign_admin = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": target.id, "role": CommunityMembership.ADMIN},
            format="json",
        )
        self.assertEqual(assign_admin.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.delete(f"/api/v1/communities/{self.community.id}/?confirm_id={self.community.id}").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_moderator_can_moderate_members_but_cannot_administer_roles_or_community(self):
        self.add_membership(self.admin, CommunityMembership.MODERATOR)
        target = self.add_membership(self.applicant, CommunityMembership.MEMBER)
        self.authenticate(self.admin)

        remove = self.client.post(
            f"/api/v1/communities/{self.community.id}/remove-member/",
            {"membership_id": target.id}, format="json",
        )
        self.assertEqual(remove.status_code, status.HTTP_200_OK)

        change_role = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": target.id, "role": CommunityMembership.MODERATOR},
            format="json",
        )
        self.assertEqual(change_role.status_code, status.HTTP_403_FORBIDDEN)

        edit = self.client.patch(
            f"/api/v1/communities/{self.community.id}/",
            {"name": "Unauthorized rename"}, format="json",
        )
        self.assertEqual(edit.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_manage_rules_and_announcements(self):
        self.add_membership(self.admin, CommunityMembership.MODERATOR)
        self.authenticate(self.admin)

        rule = self.client.post(
            f"/api/v1/communities/{self.community.id}/rules/",
            {"title": "Be kind", "description": "Treat members respectfully."},
            format="json",
        )
        announcement = self.client.post(
            f"/api/v1/communities/{self.community.id}/announcements/",
            {"title": "Welcome", "body": "Welcome to the community."},
            format="json",
        )
        self.assertEqual(rule.status_code, status.HTTP_201_CREATED)
        self.assertEqual(announcement.status_code, status.HTTP_201_CREATED)

    def test_ordinary_member_cannot_use_community_admin_operations(self):
        self.add_membership(self.admin, CommunityMembership.MEMBER)
        target = self.add_membership(self.applicant, CommunityMembership.MEMBER)
        self.authenticate(self.admin)

        role_response = self.client.patch(
            f"/api/v1/communities/{self.community.id}/update-member-role/",
            {"membership_id": target.id, "role": CommunityMembership.MODERATOR},
            format="json",
        )
        remove_response = self.client.post(
            f"/api/v1/communities/{self.community.id}/remove-member/",
            {"membership_id": target.id}, format="json",
        )
        self.assertEqual(role_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(remove_response.status_code, status.HTTP_403_FORBIDDEN)

        rule_response = self.client.post(
            f"/api/v1/communities/{self.community.id}/rules/",
            {"title": "No", "description": "Members cannot administer rules."},
            format="json",
        )
        self.assertEqual(rule_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_delete_requires_permission_confirmation_and_unused_community(self):
        platform_user = User.objects.create_user(username="platform", password="StrongPass123!")
        platform_user.is_staff = True
        platform_user.save(update_fields=["is_staff"])
        delete_permission = Permission.objects.get(
            content_type__app_label="communities", codename="delete_community"
        )
        platform_user.user_permissions.add(delete_permission)
        self.client.force_authenticate(platform_user)

        missing_confirmation = self.client.delete(f"/api/v1/communities/{self.community.id}/")
        self.assertEqual(missing_confirmation.status_code, status.HTTP_400_BAD_REQUEST)

        used = Discussion.objects.create(
            community=self.community, author=self.owner,
            title="Existing content", body="This community is in use.",
        )
        blocked_delete = self.client.delete(
            f"/api/v1/communities/{self.community.id}/?confirm_id={self.community.id}"
        )
        self.assertEqual(blocked_delete.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Community.objects.filter(pk=self.community.id).exists())
        self.assertTrue(Discussion.objects.filter(pk=used.pk).exists())

        used.delete()
        self.community.rules.create(title="Rule", description="Community rule")
        blocked_by_rule = self.client.delete(
            f"/api/v1/communities/{self.community.id}/?confirm_id={self.community.id}"
        )
        self.assertEqual(blocked_by_rule.status_code, status.HTTP_400_BAD_REQUEST)
        self.community.rules.all().delete()
        deleted = self.client.delete(
            f"/api/v1/communities/{self.community.id}/?confirm_id={self.community.id}"
        )
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Community.objects.filter(pk=self.community.id).exists())

    def test_platform_staff_without_model_permission_cannot_delete(self):
        platform_user = User.objects.create_user(username="staff_only", password="StrongPass123!")
        platform_user.is_staff = True
        platform_user.save(update_fields=["is_staff"])
        self.client.force_authenticate(platform_user)

        response = self.client.delete(
            f"/api/v1/communities/{self.community.id}/?confirm_id={self.community.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Community.objects.filter(pk=self.community.id).exists())
