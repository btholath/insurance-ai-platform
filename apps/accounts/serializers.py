from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    """Read shape used for responses to every endpoint (never includes password)."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "date_joined"]
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(choices=Role.choices)

    class Meta:
        model = User
        fields = ["id", "email", "password", "first_name", "last_name", "role", "is_active", "date_joined"]
        read_only_fields = ["id", "is_active", "date_joined"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    """PATCH shape. Deliberately has no `password` field — password change is
    out of scope for this endpoint (contracts/users.md); any `password` key in
    the request body is silently ignored rather than applied.
    """

    role = serializers.ChoiceField(choices=Role.choices, required=False)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]
