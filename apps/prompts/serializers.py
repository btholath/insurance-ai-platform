"""
Serializers for the prompt library (T044).

Plain `Serializer` subclasses, never `ModelSerializer` -- there is no model.
The library is a tuple of frozen dataclasses (data-model.md), so these shape
values rather than rows.

Two variants: the list serializer omits `body`, the detail serializer adds it.
`bindings` is on BOTH, because FR-011 puts the declared field list on the list
route specifically -- the grounding contract must be readable across the whole
library without fetching seven templates one at a time.
"""
from rest_framework import serializers


class FieldBindingSerializer(serializers.Serializer):
    record_type = serializers.CharField()
    field_name = serializers.CharField()
    placeholder = serializers.CharField()


class DisqualifiedModelSerializer(serializers.Serializer):
    """
    One (model, reason) pair from Phase 0's evaluation.

    The reason is carried, not just the model name: a future evaluation should
    be able to read what disqualified phi3:mini and test its replacement
    against the same failure mode (FR-018).
    """

    model = serializers.CharField()
    reason = serializers.CharField()


class ModelPreferenceSerializer(serializers.Serializer):
    preferred = serializers.CharField()
    disqualified = serializers.SerializerMethodField()

    def get_disqualified(self, preference):
        return [
            {"model": name, "reason": reason}
            for name, reason in preference.disqualified
        ]


class PromptTemplateListSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    purpose = serializers.CharField()
    version = serializers.CharField()
    model_preference = ModelPreferenceSerializer()
    phase0_origin = serializers.CharField()
    phase0_divergence = serializers.CharField(allow_null=True)
    pii_note = serializers.CharField()
    bindings = FieldBindingSerializer(many=True)


class PromptTemplateDetailSerializer(PromptTemplateListSerializer):
    body = serializers.CharField()
