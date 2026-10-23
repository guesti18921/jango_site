from django.utils.translation import gettext_lazy
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from .models import Profile


class RecoveryRequestForm(forms.Form):
    identifier = forms.CharField(
        label=gettext_lazy('Логин или email'), max_length=254,
        widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True,
                                     'placeholder': gettext_lazy('Введите логин или email')}),
    )


class RecoveryConfirmForm(SetPasswordForm):
    code = forms.RegexField(
        regex=r'^[0-9]{6}$', label=gettext_lazy('Код подтверждения'),
        error_messages={'invalid': gettext_lazy('Введите код из шести цифр.')},
        widget=forms.PasswordInput(attrs={'type': 'text', 'inputmode': 'numeric', 'autocomplete': 'one-time-code',
                                     'maxlength': 6, 'placeholder': '000000', 'autofocus': True}),
    )
    field_order = ['code', 'new_password1', 'new_password2']


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
                gettext_lazy("Это вход только для администраторов. Используйте обычную страницу входа."),
                code='not_staff',
            )


class ProfileForm(forms.ModelForm):
    """Редактирование профиля"""
    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'city', 'birth_date']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': gettext_lazy('Пара слов о себе...')}),
        }


class UserForm(forms.ModelForm):
    """Редактирование базовых полей юзера"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class CommentForm(forms.Form):
    text = forms.CharField(
        label=gettext_lazy('Ваш комментарий'), max_length=2000,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': gettext_lazy('Поделитесь впечатлением о посте…'), 'maxlength': 2000}),
    )


class RatingForm(forms.Form):
    value = forms.TypedChoiceField(
        label=gettext_lazy('Ваша оценка'), choices=[(n, f'{n} ★') for n in range(1, 6)], coerce=int,
        widget=forms.RadioSelect,
    )
