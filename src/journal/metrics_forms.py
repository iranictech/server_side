"""Manager-editable settings for each journal's metrics profile."""
from django import forms
from journal.models import JournalMetrics


class JournalMetricsForm(forms.ModelForm):
    class Meta:
        model = JournalMetrics
        fields = (
            "review_target_days",
            "issues_per_year",
            "open_access_policy",
            "apc_policy",
            "apc_amount",
            "apc_currency",
            "manual_acceptance_rate",
            "manual_review_days",
            "manual_source",
        )
        help_texts = {
            "review_target_days": "Editorial target in days; not an observed average.",
            "issues_per_year": "Planned annual frequency, not the count published so far.",
            "manual_acceptance_rate": "Fallback percentage when reliable site data is unavailable.",
            "manual_review_days": "Fallback observed duration, not the editorial target.",
            "manual_source": "Required for any manually supplied fallback measurement.",
        }
        widgets = {
            "manual_source": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        data = super().clean()
        manual_used = (
            data.get("manual_acceptance_rate") is not None
            or data.get("manual_review_days") is not None
        )
        if manual_used and not (data.get("manual_source") or "").strip():
            self.add_error("manual_source", "Source is required for manual measurements.")
        apc_policy = data.get("apc_policy")
        amount = data.get("apc_amount")
        currency = (data.get("apc_currency") or "").strip().upper()
        data["apc_currency"] = currency
        if apc_policy == "paid":
            if amount is None:
                self.add_error("apc_amount", "Enter the actual APC amount.")
            if not currency or len(currency) != 3 or not currency.isalpha():
                self.add_error("apc_currency", "Enter a three-letter currency code.")
        elif amount is not None or currency:
            self.add_error("apc_policy", "Choose APC payable for an amount/currency, or clear them.")
        return data
