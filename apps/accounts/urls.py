# urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserViewSet,UserStatsAPIView,TeamMembersAPIView

# Map ViewSet actions manually
user_list = UserViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

user_detail = UserViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'put': 'update',
    'delete': 'destroy'
})

# Authentication URLs
login = UserViewSet.as_view({'post': 'login'})
logout = UserViewSet.as_view({'post': 'logout'})
me = UserViewSet.as_view({'get': 'me'})
change_password = UserViewSet.as_view({'post': 'change_password'})
refresh_token = UserViewSet.as_view({'post': 'refresh_token'})  # Added

# OTP Password Reset URLs
forgot_password = UserViewSet.as_view({'post': 'forgot_password'})
verify_otp = UserViewSet.as_view({'post': 'verify_otp'})
reset_password = UserViewSet.as_view({'post': 'reset_password'})

urlpatterns = [
    # 🔐 Authentication APIs
    path('auth/login/', login, name='login'),
    path('auth/logout/', logout, name='logout'),
    path('auth/me/', me, name='me'),
    path('auth/change-password/', change_password, name='change-password'),
    path('auth/refresh-token/', refresh_token, name='refresh-token'),  # Added
    # OR use built-in view: path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # 🔑 Password Reset (OTP) APIs
    path('auth/forgot-password/', forgot_password, name='forgot-password'),
    path('auth/verify-otp/', verify_otp, name='verify-otp'),
    path('auth/reset-password/', reset_password, name='reset-password'),

    # 👤 User Management APIs
    path('users/', user_list, name='user-list'),
    path('users/<int:pk>/', user_detail, name='user-detail'),
     path('users/stats/', UserStatsAPIView.as_view(), name='user-stats'),
      path("team-members/", TeamMembersAPIView.as_view(), name="team-members"),
]