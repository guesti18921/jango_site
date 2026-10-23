from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Profile


class UserRegisterForm(UserCreationForm):
    """Расширенная регистрация — сразу с email"""
    email = forms.EmailField(required=True, label="Email")

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class UserLoginForm(AuthenticationForm):
    """Обычный вход для юзеров"""
    pass


class StaffLoginForm(AuthenticationForm):
    """Вход только для админов — проверяем is_staff"""
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(
                "Это вход только для администраторов. Используйте обычную страницу входа.",
                code='not_staff',
            )


class ProfileForm(forms.ModelForm):
    """Редактирование профиля"""
    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'city', 'birth_date']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Пара слов о себе...'}),
        }


class UserForm(forms.ModelForm):
    """Редактирование базовых полей юзера"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']