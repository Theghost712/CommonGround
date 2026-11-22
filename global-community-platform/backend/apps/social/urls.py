from django.urls import path, re_path

from . import views

urlpatterns = [
    path("people/", views.PeopleSearchView.as_view(), name="people_search"),
    path("people/suggestions/", views.SuggestionsView.as_view(), name="people_suggestions"),
    path("people/discover/", views.DiscoverView.as_view(), name="people_discover"),
    path("people/stories/", views.StoriesView.as_view(), name="people_stories"),
    path("people/contacts/match/", views.ContactMatchView.as_view(), name="people_contact_match"),
    path("people/requests/", views.FollowRequestsView.as_view(), name="follow_requests"),
    re_path(r"^people/requests/(?P<username>[^/]+)/(?P<action>approve|decline)/$", views.FollowRequestsView.as_view(), name="follow_request_action"),
    path("people/<str:username>/", views.PersonDetailView.as_view(), name="person_detail"),
    path("people/<str:username>/follow/", views.FollowView.as_view(), name="person_follow"),
    path("people/<str:username>/followers/", views.FollowersView.as_view(), name="person_followers"),
    path("people/<str:username>/following/", views.FollowingView.as_view(), name="person_following"),
    path("people/<str:username>/label/", views.LabelView.as_view(), name="person_label"),
]
