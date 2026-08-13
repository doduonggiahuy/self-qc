from django import forms
from .models import ClientProject, Project, Rule


class ClientProjectForm(forms.ModelForm):
    class Meta:
        model = ClientProject
        fields = ["name", "description"]
        labels = {"name": "Tên khách hàng / dự án", "description": "Mô tả"}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class RuleForm(forms.ModelForm):
    class Meta:
        model = Rule
        fields = ["name", "description", "enabled", "videos"]
        labels = {"name": "Tên rule", "description": "Mô tả logic", "enabled": "Đang sử dụng", "videos": "Video áp dụng"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "videos": forms.CheckboxSelectMultiple()}

    def __init__(self, client_project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["videos"].queryset = client_project.videos.all()


class ProjectForm(forms.ModelForm):
    classes = forms.CharField(
        help_text="Mỗi dòng: class | prompt. Ví dụ: person | person",
        widget=forms.Textarea(attrs={"rows": 6}),
        initial="person | person\ntable | dining table\nphone | mobile phone",
    )

    class Meta:
        model = Project
        fields = ["name", "video", "coverage"]
