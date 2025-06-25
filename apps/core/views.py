import uuid
from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
import random
from rest_framework.views import APIView
from rest_framework import generics, permissions, status
from rest_framework.throttling import ScopedRateThrottle
from .models import SecurityQuestion, AnonymousUser, SecurityEvent
from .serializers import (
    SecurityQuestionSerializer,
    SetupSecurityQuestionSerializer,
    AnswerSecurityQuestionSerializer, 
    UserSerializer, 
    SecurityEventSerializer, 
    LoginSerializer,
    UpdateProfileSerializer,
    PasswordResetSerializer,
    PasswordChangeSerializer,
    ProfileSerializer
)


class UserCreateView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Creates an anonymous user
    """
    queryset = AnonymousUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'registration'

    @staticmethod
    def _generate_exchange_code() -> str:
        prefix = settings.XUSDT_SETTINGS["EXCHANGE_CODE_PREFIX"] 
        total = settings.XUSDT_SETTINGS["EXCHANGE_CODE_LENGTH"] 

        if total <= len(prefix):
            raise ValueError(
                "EXCHANGE_CODE_LENGTH must be greater than the length of "
                "EXCHANGE_CODE_PREFIX"
            )

        random_len = total - len(prefix)
        digits = "".join(random.choices("0123456789", k=random_len))
        return f"{prefix}{digits}"

    def perform_create(self, serializer):
        max_attempts = 5
        for _ in range(max_attempts):
            code = self._generate_exchange_code()
            if not AnonymousUser.objects.filter(exchange_code=code).exists():
                break
        else:
            raise RuntimeError("Could not generate a unique exchange_code")

        user: AnonymousUser = serializer.save(exchange_code=code)

        SecurityEvent.log_event(
            event_type=1, 
            actor_token=user.client_token,
            ip_address=self.request.META.get("REMOTE_ADDR", ""),
            details={"action": "user_created"},
        )


class UserDetailView(generics.RetrieveAPIView):
    """
    GET /api/auth/me/
    Returns current user details
    """
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class SecurityEventListView(generics.ListAPIView):
    """
    GET /api/security-events/
    Lists security events for admin or current user
    """
    serializer_class = SecurityEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return SecurityEvent.objects.all()
        return SecurityEvent.objects.filter(actor_token=self.request.user.client_token)


class LoginView(generics.GenericAPIView):
    """
    POST /api/auth/login/
    Authenticates a user and returns tokens
    """
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        SecurityEvent.log_event(
            event_type=1,
            actor_token=user.client_token,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "login"},
        )

        return Response(
            {
                "exchange_code": user.exchange_code,
                "client_token": user.client_token,
                "trust_score": user.trust_score,
            },
            status=status.HTTP_200_OK,
        )


class SecurityQuestionListView(generics.ListAPIView):
    """
    GET /api/auth/security-questions/
    Lists security questions for current user
    """
    serializer_class = SecurityQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecurityQuestion.objects.filter(user=self.request.user)


class SetupSecurityQuestionView(generics.CreateAPIView):
    """
    POST /api/auth/setup-security-question/
    Creates a new security question for current user
    """
    serializer_class = SetupSecurityQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'security_questions'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if SecurityQuestion.objects.filter(user=request.user).count() >= 3:
            return Response(
                {"detail": "Maximum of 3 security questions allowed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        question = SecurityQuestion.objects.create(user=request.user)
        question.set_question_answer(
            serializer.validated_data['question'],
            serializer.validated_data['answer']
        )

        SecurityEvent.log_event(
            event_type=4,
            actor_token=request.user.client_token,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "security_question_added"},
        )

        return Response(
            SecurityQuestionSerializer(question).data,
            status=status.HTTP_201_CREATED
        )


class VerifySecurityQuestionView(generics.GenericAPIView):
    """
    POST /api/auth/verify-security-question/
    Verifies answer to a security question
    """
    serializer_class = AnswerSecurityQuestionSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'verify_questions'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            question = SecurityQuestion.objects.get(
                id=serializer.validated_data['question_id']
            )
        except SecurityQuestion.DoesNotExist:
            return Response(
                {"detail": "Invalid security question"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if question.verify_answer(serializer.validated_data['answer']):
            question.last_used = timezone.now()
            question.save()
            return Response({"verified": True}, status=status.HTTP_200_OK)
        
        SecurityEvent.log_event(
            event_type=3,
            actor_token=question.user.client_token if question.user else None,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "failed_question_attempt", "question_id": str(question.id)},
        )
        
        return Response({"verified": False}, status=status.HTTP_400_BAD_REQUEST)


class RecoveryQuestionsView(generics.GenericAPIView):
    """
    GET /api/auth/recovery/questions/<exchange_code>/
    Returns security questions for password recovery
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'recovery'

    def get(self, request, exchange_code, *args, **kwargs):
        try:
            user = AnonymousUser.objects.get(exchange_code=exchange_code)
        except AnonymousUser.DoesNotExist:
            return Response(
                {"detail": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        questions = SecurityQuestion.objects.filter(user=user)
        return Response(
            SecurityQuestionSerializer(questions, many=True).data,
            status=status.HTTP_200_OK
        )


class InitiatePasswordResetView(generics.GenericAPIView):
    """
    POST /api/auth/recovery/initiate/
    Initiates password reset process
    """
    serializer_class = PasswordResetSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        questions = SecurityQuestion.objects.filter(user=user)
        
        SecurityEvent.log_event(
            event_type=3,
            actor_token=user.client_token,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "password_reset_initiated"},
        )
        
        return Response(
            SecurityQuestionSerializer(questions, many=True).data,
            status=status.HTTP_200_OK
        )


class CompletePasswordResetView(generics.GenericAPIView):
    """
    POST /api/auth/recovery/complete/
    Completes password reset process
    """
    serializer_class = PasswordResetSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        new_password = serializer.validated_data['new_password']
        
        user.set_password(new_password)
        user.save()
        
        SecurityEvent.log_event(
            event_type=3,
            actor_token=user.client_token,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "password_reset_completed"},
        )
        
        return Response(
            {"detail": "Password successfully reset"},
            status=status.HTTP_200_OK
        )
    
class UpdateProfileView(generics.UpdateAPIView):
    """
    PATCH /api/auth/update-profile/
    Updates user profile information
    """
    serializer_class = UpdateProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = serializer.save()
        
        SecurityEvent.log_event(
            event_type=4,
            actor_token=user.client_token,
            ip_address=self.request.META.get("REMOTE_ADDR", ""),
            details={"action": "profile_updated"},
        )

class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET, PATCH /api/auth/profile/
    Retrieve or update user profile
    """
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'profile'

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = serializer.save()
        
        SecurityEvent.log_event(
            event_type=4,
            actor_token=user.client_token,
            ip_address=self.request.META.get("REMOTE_ADDR", ""),
            details={"action": "profile_updated"},
        )

class ChangePasswordView(generics.GenericAPIView):
    """
    POST /api/auth/change-password/
    Change user password
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_change'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']
        
        if not user.check_password(current_password):
            return Response(
                {"current_password": "Current password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(new_password)
        user.save()
        
        SecurityEvent.log_event(
            event_type=3,
            actor_token=user.client_token,
            ip_address=request.META.get("REMOTE_ADDR", ""),
            details={"action": "password_changed"},
        )
        
        return Response(
            {"detail": "Password has been changed successfully"},
            status=status.HTTP_200_OK
        )
    
class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        avatar = request.FILES.get('avatar')

        if not avatar:
            return Response(
                {"error": "No avatar file provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file size (example: limit to 2MB)
        max_size = 2 * 1024 * 1024  # 2MB
        if avatar.size > max_size:
            return Response(
                {"error": "File size too large. Maximum 2MB allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type (example: only images)
        valid_types = ['image/jpeg', 'image/png', 'image/gif']
        if avatar.content_type not in valid_types:
            return Response(
                {"error": "Invalid file type. Only JPEG, PNG, and GIF are allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # In a real implementation, you would:
            # 1. Save the file to your storage (S3, local filesystem, etc.)
            # 2. Generate a URL for the file
            # 3. Store that URL in the avatar_url field
            
            # For this example, we'll just store the file name
            # In production, use something like:
            # from django.core.files.storage import default_storage
            # file_path = default_storage.save(f'avatars/{user.id}/{avatar.name}', avatar)
            # avatar_url = default_storage.url(file_path)
            
            # For now, we'll just store a placeholder
            avatar_url = f"/media/avatars/user_{user.id}/{avatar.name}"
            user.avatar_url = avatar_url
            user.save()
            
            SecurityEvent.log_event(
                event_type=4,
                actor_token=user.client_token,
                ip_address=request.META.get("REMOTE_ADDR", ""),
                details={"action": "avatar_updated"},
            )
            
            return Response(
                {
                    "message": "Avatar uploaded successfully.",
                    "avatar_url": user.avatar_url
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )