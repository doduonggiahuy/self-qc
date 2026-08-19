import json

from django import forms


class ProjectManifestForm(forms.Form):
    key = forms.SlugField(max_length=120, label="Project key")
    name = forms.CharField(max_length=160, label="Tên dự án")
    manifest = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 24, "spellcheck": "false"}),
        label="Project manifest (JSON)",
        help_text="YAML sẽ được hỗ trợ khi Platform có parser/schema validator riêng.",
    )

    def clean_manifest(self):
        try:
            value = json.loads(self.cleaned_data["manifest"])
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"JSON không hợp lệ: {exc.msg} (dòng {exc.lineno}).") from exc
        if not isinstance(value, dict):
            raise forms.ValidationError("Manifest phải là JSON object.")
        return value
