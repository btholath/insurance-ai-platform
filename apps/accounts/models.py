from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class Role(models.TextChoices):
    FRAUD_ANALYST = "fraud_analyst", "Fraud Analyst"
    CLAIMS_ADJUSTER = "claims_adjuster", "Claims Adjuster"
    CUSTOMER_SERVICE = "customer_service", "Customer Service"
    UNDERWRITER = "underwriter", "Underwriter"
    COMPLIANCE_OFFICER = "compliance_officer", "Compliance Officer"
    RISK_MANAGER = "risk_manager", "Risk Manager"
    PRODUCT_MANAGER = "product_manager", "Product Manager"
    EXECUTIVE_LEADERSHIP = "executive_leadership", "Executive Leadership"
    SYSTEM_ADMINISTRATOR = "system_administrator", "System Administrator"


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="user_role_valid",
                check=models.Q(role__in=Role.values),
            )
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)
