from django import forms
from django.contrib.auth import get_user_model


from .roles import ROLE_GROUPS


PLATFORM_ROLE_CHOICES = list(ROLE_GROUPS.items())


class AnnotationMemberCreateForm(forms.Form):
    username = forms.CharField(max_length=150, label="Tên đăng nhập")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Mật khẩu")
    role = forms.ChoiceField(choices=PLATFORM_ROLE_CHOICES, label="Vai trò platform")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError("Tên đăng nhập đã tồn tại.")
        return username


class AnnotationMemberRoleForm(forms.Form):
    role = forms.ChoiceField(choices=PLATFORM_ROLE_CHOICES, label="Vai trò platform")
    is_active = forms.BooleanField(required=False, label="Tài khoản đang hoạt động")
