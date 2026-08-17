from pathlib import Path

from django import forms
from django.utils.text import slugify

from .models import EvaluationDataset, GroundTruthRelease, InferenceModel


class EvaluationDatasetForm(forms.ModelForm):
    class Meta:
        model = EvaluationDataset
        fields = ["name", "client_project"]
        labels = {"name": "Tên evaluation task", "client_project": "Customer project"}

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        projects = self.fields["client_project"].queryset
        if not user.is_superuser:
            projects = projects.filter(owner=user)
        self.fields["client_project"].queryset = projects
        self.fields["client_project"].required = True


class TestCaseForm(forms.Form):
    name = forms.CharField(max_length=160, label="Tên test case")
    ground_truth_release = forms.ModelChoiceField(queryset=GroundTruthRelease.objects.none(), label="Ground Truth release")
    minimum_annotations = forms.IntegerField(min_value=0, initial=1, label="Số annotation tối thiểu")

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ground_truth_release"].queryset = project.gt_releases.filter(status="FROZEN")


class InferenceModelForm(forms.Form):
    provider = forms.ChoiceField(choices=InferenceModel.PROVIDER_CHOICES, label="Nguồn model")
    model_file = forms.FileField(required=False, label="File local (.pt hoặc .zip)")
    source = forms.CharField(required=False, max_length=300, label="Hugging Face repo ID")
    enabled = forms.BooleanField(required=False, initial=True, label="Cho User sử dụng sau khi sẵn sàng")

    def clean(self):
        data = super().clean()
        provider, model_file, source = data.get("provider"), data.get("model_file"), (data.get("source") or "").strip()
        if provider == "LOCAL" and not model_file:
            self.add_error("model_file", "Hãy chọn file .pt hoặc ZIP bundle.")
        if provider == "HUGGING_FACE" and not source:
            self.add_error("source", "Hãy nhập Hugging Face repo ID.")
        return data

    def create_model(self, user):
        provider = self.cleaned_data["provider"]
        uploaded = self.cleaned_data.get("model_file")
        source = (self.cleaned_data.get("source") or "").strip()
        identity = Path(uploaded.name).stem if uploaded else source.split("/")[-1].replace(":", "-")
        key = slugify(identity)
        base = key or "model"
        index = 2
        while InferenceModel.objects.filter(key=key).exists():
            key, index = f"{base}-{index}", index + 1
        adapter, task = _infer_adapter(provider, uploaded.name if uploaded else source)
        return InferenceModel.objects.create(
            key=key, name=identity, provider=provider, source=source, model_file=uploaded,
            adapter=adapter, task=task, enabled=self.cleaned_data["enabled"], created_by=user,
        )


def _infer_adapter(provider, source):
    lowered = source.lower()
    # A Hugging Face model is identified from downloaded metadata, not its
    # repository name. Any repo may be imported into the registry.
    if provider == "HUGGING_FACE":
        return "quality.adapters.UnavailableAdapter", "VISUAL_GROUNDING"
    if "florence" in lowered:
        return "quality.adapters.Florence2Adapter", "VISUAL_GROUNDING"
    if "grounding-dino" in lowered or "grounding_dino" in lowered:
        return "quality.adapters.GroundingDinoAdapter", "OPEN_VOCAB_DETECTION"
    if provider == "LOCAL" and lowered.endswith(".pt"):
        return "quality.adapters.YoloWorldAdapter", "OPEN_VOCAB_DETECTION"
    return "quality.adapters.UnavailableAdapter", "VISUAL_GROUNDING"
