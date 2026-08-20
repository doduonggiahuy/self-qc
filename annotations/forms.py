import json

from django import forms
from django.contrib.auth import get_user_model

from .models import AnnotationTask, AutoAnnotationFunction, ClientProject, LabelClass, Project, Rule
from .application.project_schema import normalize_cvat_labels


class ClientProjectForm(forms.ModelForm):
    labels_schema = forms.CharField(widget=forms.HiddenInput(), initial="[]")
    rules_schema = forms.CharField(widget=forms.HiddenInput(), initial="[]")

    class Meta:
        model = ClientProject
        fields = ["name", "description"]
        labels = {"name": "Tên khách hàng / dự án", "description": "Mô tả"}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_labels_schema(self):
        try:
            labels = json.loads(self.cleaned_data["labels_schema"])
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError("Label schema JSON không hợp lệ.") from exc
        if not labels:
            raise forms.ValidationError("Project phải có ít nhất một label.")
        names = [str(label.get("name", "")).strip() for label in labels]
        if any(not name for name in names) or len(names) != len(set(names)):
            raise forms.ValidationError("Tên label phải có giá trị và không trùng nhau.")
        return normalize_cvat_labels(labels)

    def clean_rules_schema(self):
        try:
            return json.loads(self.cleaned_data["rules_schema"])
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError("Rule schema JSON không hợp lệ.") from exc


class RuleForm(forms.ModelForm):
    class Meta:
        model = Rule
        fields = ["name", "description", "enabled"]
        labels = {"name": "Tên rule", "description": "Mô tả logic", "enabled": "Đang sử dụng"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ProjectLabelForm(forms.ModelForm):
    class Meta:
        model = LabelClass
        fields = ["name", "label_type", "color"]
        labels = {"name": "Label class", "label_type": "Loại label", "color": "Màu"}
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def clean_label_type(self):
        label_type = self.cleaned_data["label_type"]
        if not self.instance.pk:
            return label_type
        has_annotations = self.instance.shapes.exists() or self.instance.boxes.exists()
        if label_type != self.instance.label_type and (has_annotations or self.instance.label_type == "skeleton" or label_type == "skeleton"):
            raise forms.ValidationError("Không thể đổi loại của skeleton hoặc label đã có annotation.")
        return label_type


class AutoAnnotationFunctionForm(forms.ModelForm):
    spec_json = forms.CharField(label="Model label spec", widget=forms.Textarea(attrs={"rows": 14}))

    class Meta:
        model = AutoAnnotationFunction
        fields = ["name", "key", "endpoint_url", "kind", "timeout_seconds", "enabled"]
        labels = {"key": "Function key", "endpoint_url": "Inference endpoint", "kind": "Loại model", "timeout_seconds": "Timeout (giây)", "enabled": "Cho phép sử dụng"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["spec_json"].initial = json.dumps(self.instance.spec, ensure_ascii=False, indent=2)

    def clean_spec_json(self):
        try:
            spec = json.loads(self.cleaned_data["spec_json"])
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError("Spec phải là JSON array tương thích CVAT.") from exc
        if not isinstance(spec, list) or not spec or any(not item.get("name") or not item.get("type") for item in spec):
            raise forms.ValidationError("Spec cần ít nhất một label có name và type.")
        return spec


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "video/*,image/*,.zip,.mp4,.avi,.mov,.mkv,.webm,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)] if data else []


class ProjectForm(forms.Form):
    name = forms.CharField(max_length=160, required=False, label="Tên data/job")
    data_files = MultipleFileField(required=True, label="Data files")
    coverage = forms.ChoiceField(choices=Project._meta.get_field("coverage").choices, initial="partial")


class AnnotationTaskForm(forms.ModelForm):
    data_files = MultipleFileField(required=False, label="Data files")

    class Meta:
        model = AnnotationTask
        fields = ["name", "description", "rules", "assignees", "reviewers", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "rules": forms.CheckboxSelectMultiple(), "assignees": forms.CheckboxSelectMultiple(), "reviewers": forms.CheckboxSelectMultiple()}

    def __init__(self, client_project, *args, allow_assignment=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rules"].queryset = client_project.rules.all()
        self.fields["assignees"].queryset = get_user_model().objects.filter(is_active=True, groups__name="Data Annotator").distinct()
        self.fields["reviewers"].queryset = get_user_model().objects.filter(is_active=True, groups__name="QA/QC Engineer").distinct()
        if not allow_assignment:
            self.fields.pop("assignees")
            self.fields.pop("reviewers")
