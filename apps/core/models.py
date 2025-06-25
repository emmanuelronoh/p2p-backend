import uuid
import hashlib
import hmac
import json
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


# ---------------------------------------------------------------------------
# AnonymousUser
# ---------------------------------------------------------------------------

class AnonymousUserManager(BaseUserManager):
    def create_user(self, exchange_code, password, **extra_fields):
        if not exchange_code:
            raise ValueError("The Exchange Code must be set")

        user = self.model(exchange_code=exchange_code, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, exchange_code, password, **extra_fields):
        extra_fields.setdefault("trust_score", 100)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(exchange_code, password, **extra_fields)

class AnonymousUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Public identifier – e.g. EX-123456
    exchange_code = models.CharField(max_length=8, unique=True, editable=False)

    # Store Django’s hashed password so we can combine it with the salt
    password_hash = models.CharField(max_length=128, editable=False)

    session_salt = models.CharField(max_length=32, editable=False)
    client_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="SHA3-256(salt + password_hash)",
    )

    username = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)
    total_trades = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    last_active = models.DateTimeField(null=True, blank=True)

    trust_score = models.SmallIntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0-100 reputation score",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "exchange_code"
    REQUIRED_FIELDS = []

    objects = AnonymousUserManager()

    # --------------------------------------------------------------------- #
    # Helpers                                                               #
    # --------------------------------------------------------------------- #

    def __str__(self):
        return f"User {self.exchange_code}"

    def set_password(self, raw_password):
        """
        Override to (a) capture Django’s hashed password in `password_hash`
        and (b) generate a session salt + client-token combo.
        """
        super().set_password(raw_password)                     # sets .password
        self.password_hash = self.password                     # keep a copy

        # fresh salt
        self.session_salt = hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]

        # client token = SHA3-256(salt + password_hash)
        blob = f"{self.session_salt}{self.password_hash}".encode()
        self.client_token = hashlib.sha3_256(blob).hexdigest()

        self.last_active = timezone.now()

    def rotate_session_salt(self):
        """Rotate salt on login so the client token can be refreshed."""
        self.session_salt = hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]
        blob = f"{self.session_salt}{self.password_hash}".encode()
        self.client_token = hashlib.sha3_256(blob).hexdigest()
        self.save(update_fields=["session_salt", "client_token"])

    class Meta:
        indexes = [
            models.Index(fields=["exchange_code"], name="idx_user_exchange_code"),
            models.Index(fields=["client_token"], name="idx_user_client_token"),
        ]


# ---------------------------------------------------------------------------
# SecurityEvent
# ---------------------------------------------------------------------------

class SecurityEvent(models.Model):
    anonymous_user = models.ForeignKey(
    'core.AnonymousUser',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='security_events'  # <-- This is key
)

    EVENT_TYPES = (
        (1, "Login"),
        (2, "Trade"),
        (3, "Dispute"),
        (4, "Admin"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.SmallIntegerField(choices=EVENT_TYPES)

    actor_token = models.CharField(
        max_length=64, blank=True, help_text="HMAC-SHA256(actor_identity)"
    )
    ip_hmac = models.CharField(
        max_length=64, blank=True, help_text="HMAC-SHA256(ip_address)"
    )
    details_enc = models.TextField(blank=True, help_text="AEAD-encrypted JSON")
    created_at = models.DateTimeField(auto_now_add=True)

    # --------------------------- helper ---------------------------------- #

    @classmethod
    def log_event(
        cls,
        *,
        event_type: int,
        actor_token: str | None = None,
        ip_address: str | None = None,
        details: dict | None = None,
    ):
        """
        Convenience wrapper that:
          • HMAC-hashes the IP with `SECURITY_EVENT_HMAC_KEY`
          • JSON-encodes the details
        """
        key = settings.SECURITY_EVENT_HMAC_KEY.encode()
        ip_hmac = (
            hmac.new(key, ip_address.encode(), hashlib.sha256).hexdigest()
            if ip_address
            else ""
        )

        return cls.objects.create(
            event_type=event_type,
            actor_token=actor_token or "",
            ip_hmac=ip_hmac,
            details_enc=json.dumps(details or {}),
        )

    # --------------------------------------------------------------------- #

    def __str__(self):
        return f"{self.get_event_type_display()} @ {self.created_at}"

    class Meta:
        indexes = [
            models.Index(fields=["event_type"], name="idx_event_type"),
            models.Index(fields=["actor_token"], name="idx_event_actor"),
            models.Index(fields=["created_at"], name="idx_event_timestamp"),
        ]


class SecurityQuestion(models.Model):
    user = models.ForeignKey(AnonymousUser, on_delete=models.CASCADE, related_name='security_questions')
    question_enc = models.TextField(help_text="Encrypted security question")
    answer_enc = models.TextField(help_text="Encrypted answer")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)

    @classmethod
    def encrypt_data(cls, data: str) -> str:
        fernet = Fernet(settings.SECURITY_QUESTION_ENCRYPTION_KEY)
        return fernet.encrypt(data.encode()).decode()

    @classmethod
    def decrypt_data(cls, encrypted_data: str) -> str:
        fernet = Fernet(settings.SECURITY_QUESTION_ENCRYPTION_KEY)
        return fernet.decrypt(encrypted_data.encode()).decode()

    def set_question_answer(self, question: str, answer: str):
        self.question_enc = self.encrypt_data(question)
        self.answer_enc = self.encrypt_data(answer.lower().strip())  # Normalize answer
        self.save()

    def verify_answer(self, answer: str) -> bool:
        try:
            stored_answer = self.decrypt_data(self.answer_enc)
            return stored_answer == answer.lower().strip()
        except:
            return False

    def __str__(self):
        return f"Security Question for {self.user.exchange_code}"