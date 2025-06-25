import uuid
from rest_framework import serializers
from .models import AnonymousUser, SecurityEvent, SecurityQuestion
from django.contrib.auth.hashers import make_password

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model  = AnonymousUser
        fields = [
            'exchange_code', 'password',
            'trust_score', 'last_active',
            'created_at', 'client_token'
        ]
        extra_kwargs = {
            'exchange_code': {'read_only': True},
            'client_token':  {'read_only': True},
        }

    def create(self, validated_data):
        raw_password = validated_data.pop('password')

        user = AnonymousUser(**validated_data)

        user.set_password(raw_password)

        user.save()

        return user

class SecurityQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityQuestion
        fields = ['id', 'question_enc', 'created_at']
        read_only_fields = fields

class SetupSecurityQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=255, write_only=True)
    answer = serializers.CharField(max_length=255, write_only=True)

    def validate(self, attrs):
        if len(attrs['question']) < 10:
            raise serializers.ValidationError("Question must be at least 10 characters")
        if len(attrs['answer']) < 3:
            raise serializers.ValidationError("Answer must be at least 3 characters")
        return attrs

class AnswerSecurityQuestionSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    answer = serializers.CharField(max_length=255)

class SecurityEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityEvent
        fields = ['event_type', 'created_at']
        read_only_fields = fields

class LoginSerializer(serializers.Serializer):
    exchange_code = serializers.CharField(max_length=8)
    password      = serializers.CharField(write_only=True)

    def validate(self, attrs):
        exchange_code = attrs.get("exchange_code")
        password      = attrs.get("password")

        try:
            user = AnonymousUser.objects.get(exchange_code=exchange_code)
        except AnonymousUser.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")

        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials")

        # rotate salt => new client_token
        user.rotate_session_salt()

        attrs["user"] = user
        return attrs
    
class PasswordResetSerializer(serializers.Serializer):
    exchange_code = serializers.CharField(max_length=8)
    new_password = serializers.CharField(write_only=True, required=False)
    
    def validate(self, attrs):
        try:
            user = AnonymousUser.objects.get(exchange_code=attrs['exchange_code'])
        except AnonymousUser.DoesNotExist:
            raise serializers.ValidationError("Invalid exchange code")
        
        attrs['user'] = user
        return attrs
    
    
class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnonymousUser
        fields = ['username', 'email', 'phone', 'location', 'bio']  # Add fields you want to update
        extra_kwargs = {
            'email': {'required': False},
            'phone': {'required': False},
            # Add other fields as needed
        }
    
    def validate_username(self, value):
        if value and len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long")
        return value


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnonymousUser
        fields = [
            'username', 'email', 'phone', 'location', 'bio', 
            'avatar_url', 'trust_score', 'total_trades', 'success_rate',
            'exchange_code', 'created_at'
        ]
        read_only_fields = [
            'exchange_code', 'trust_score', 'total_trades', 
            'success_rate', 'created_at'
        ]

    def validate_username(self, value):
        if value and len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long")
        return value

    def validate_email(self, value):
        if value and not value.strip():
            return None
        return value

class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})
        
        if len(attrs['new_password']) < 6:
            raise serializers.ValidationError({"new_password": "Password must be at least 6 characters long"})
        
        return attrs