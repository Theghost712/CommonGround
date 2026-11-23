from django.urls import path

from . import views

urlpatterns = [
    path("stories/", views.StoryCreateView.as_view(), name="story_create"),
    path("stories/tray/", views.StoryTrayView.as_view(), name="story_tray"),
    path("stories/mine/", views.MyRecentStoriesView.as_view(), name="story_mine"),
    path("stories/highlights/", views.HighlightsView.as_view(), name="story_highlights_create"),
    path("stories/highlights/user/<str:username>/", views.HighlightsView.as_view(), name="story_highlights_user"),
    path("stories/highlights/<int:pk>/", views.HighlightDetailView.as_view(), name="story_highlight_detail"),
    path("stories/close-friends/", views.CloseFriendsView.as_view(), name="story_close_friends"),
    path("stories/close-friends/<str:username>/", views.CloseFriendsView.as_view(), name="story_close_friend"),
    path("stories/hidden-from/", views.HiddenFromView.as_view(), name="story_hidden_from"),
    path("stories/hidden-from/<str:username>/", views.HiddenFromView.as_view(), name="story_hidden_from_user"),
    path("stories/user/<str:username>/", views.StoryUserView.as_view(), name="story_user"),
    path("stories/<int:pk>/", views.StoryDetailView.as_view(), name="story_detail"),
    path("stories/<int:pk>/media/", views.StoryMediaView.as_view(), name="story_media"),
    path("stories/<int:pk>/view/", views.StoryViewedView.as_view(), name="story_viewed"),
    path("stories/<int:pk>/viewers/", views.StoryViewersView.as_view(), name="story_viewers"),
    path("stories/<int:pk>/reply/", views.StoryReplyView.as_view(), name="story_reply"),
]
