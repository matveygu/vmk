"""Email verification and Django's single-use password reset flow."""
import logging
import secrets
from ipaddress import ip_address
from datetime import timedelta
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.views import PasswordResetView
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import CustomUserCreationForm
from .models import CustomUser, EmailRateLimit, PendingSignup

logger = logging.getLogger(__name__)
SESSION_KEY = 'pending_signup'
CODE_LIFETIME = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def take_limit(scope, value, maximum, seconds):
    now = timezone.now()
    key = salted_hmac('email-rate-limit', f'{scope}:{value}', algorithm='sha256').hexdigest()
    EmailRateLimit.objects.get_or_create(key=key, defaults={'expires_at': now + timedelta(seconds=seconds)})
    EmailRateLimit.objects.filter(key=key, expires_at__lte=now).update(count=0, expires_at=now + timedelta(seconds=seconds))
    return bool(EmailRateLimit.objects.filter(key=key, count__lt=maximum).update(count=F('count') + 1))


def allow_email(request, email):
    client_ip = request.META.get('REMOTE_ADDR', '')
    if settings.TRUST_PROXY_CLIENT_IP:
        try:
            client_ip = str(ip_address(request.META.get('HTTP_X_REAL_IP', '')))
        except ValueError:
            pass
    return (take_limit('ip-hour', client_ip, 30, 3600)
            and take_limit('email-hour', email, 5, 3600)
            and take_limit('email-minute', email, 1, 60))


def code_digest(pending_id, code):
    return salted_hmac('signup-code', f'{pending_id}:{code}', algorithm='sha256').hexdigest()


def issue_code(pending):
    code = f'{secrets.randbelow(1000000):06d}'
    sent = send_mail(
        'Код подтверждения — Учебный портал ВМК МГУ',
        f'Ваш код подтверждения: {code}\n\nКод действует 10 минут. Введите его в том браузере, где начали регистрацию.\n'
        'Никому не сообщайте код. Если вы не регистрировались, просто проигнорируйте письмо.',
        settings.DEFAULT_FROM_EMAIL, [pending.email], fail_silently=False,
    )
    if sent != 1:
        raise RuntimeError('Mail backend did not accept the message')
    pending.code_hash = code_digest(pending.pk, code)
    pending.sent_at = timezone.now()
    pending.expires_at = pending.sent_at + CODE_LIFETIME
    pending.attempts = 0
    pending.save()


def pending_for_request(request):
    identity = request.session.get(SESSION_KEY)
    return PendingSignup.objects.filter(pk=identity).first() if identity else None


@never_cache
@sensitive_post_parameters('password1', 'password2')
def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if pending_for_request(request):
        return redirect('verify_email')
    form = CustomUserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        if not allow_email(request, email):
            form.add_error(None, 'Слишком много запросов. Подождите минуту; можно отправить не более 5 писем в час.')
        else:
            # Expired attempts reserve neither the email nor the student number.
            PendingSignup.objects.filter(expires_at__lte=timezone.now()).delete()
            pending = None
            try:
                user = form.save(commit=False)  # UserCreationForm hashes the password.
                with transaction.atomic():
                    pending = PendingSignup.objects.create(
                        email=email, student_id=user.student_id, name=user.name,
                        password_hash=user.password, group=form.cleaned_data['group'],
                        sent_at=timezone.now(), expires_at=timezone.now() + CODE_LIFETIME,
                    )
                    issue_code(pending)
            except IntegrityError:
                form.add_error(None, 'Регистрация с этими данными уже начата. Завершите её в исходном браузере или повторите через 10 минут.')
            except Exception as exc:
                logger.error('Signup email delivery failed (%s)', type(exc).__name__)
                form.add_error(None, 'Не удалось отправить письмо. Попробуйте позже или обратитесь к администратору.')
            else:
                request.session.cycle_key()
                request.session[SESSION_KEY] = str(pending.pk)
                return redirect('verify_email')
    return render(request, 'register.html', {'form': form})


class VerificationForm(forms.Form):
    code = forms.RegexField(
        regex=r'\A[0-9]{6}\Z', label='Код из письма', max_length=6, min_length=6,
        error_messages={'invalid': 'Введите шестизначный код из письма.'},
        widget=forms.TextInput(attrs={'class': 'ds-input', 'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'placeholder': '000000', 'autofocus': True}),
    )


@never_cache
@sensitive_post_parameters('code')
def verify_email(request):
    pending = pending_for_request(request)
    if not pending:
        return redirect('register')
    form = VerificationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                # Conditional UPDATE also serializes attempts on SQLite, where SELECT FOR UPDATE is a no-op.
                accepted = PendingSignup.objects.filter(pk=pending.pk, expires_at__gt=timezone.now(), attempts__lt=MAX_ATTEMPTS).update(attempts=F('attempts') + 1)
                if not accepted:
                    form.add_error('code', 'Код истёк или исчерпаны попытки. Запросите новый код.')
                else:
                    pending.refresh_from_db()
                    if not constant_time_compare(pending.code_hash, code_digest(pending.pk, form.cleaned_data['code'])):
                        form.add_error('code', 'Неверный код. Проверьте последнее письмо.')
                    elif CustomUser.objects.filter(Q(email__iexact=pending.email) | Q(student_id=pending.student_id) | Q(username=pending.student_id)).exists():
                        form.add_error(None, 'Аккаунт с этими данными уже существует. Войдите или восстановите пароль.')
                    else:
                        group = pending.group
                        CustomUser.objects.create(
                            username=pending.student_id, student_id=pending.student_id, email=pending.email,
                            name=pending.name, password=pending.password_hash, group=group,
                            faculty=group.faculty, course=group.course, role='student',
                        )
                        pending.delete()
                        request.session.pop(SESSION_KEY, None)
                        messages.success(request, 'Email подтверждён. Теперь можно войти в аккаунт.')
                        return redirect('login')
        except IntegrityError:
            form.add_error(None, 'Эти данные уже используются. Войдите или начните регистрацию заново.')
    return render(request, 'registration/verify_email.html', {'form': form, 'email': pending.email})


@require_POST
def resend_code(request):
    pending = pending_for_request(request)
    if not pending:
        return redirect('register')
    if not allow_email(request, pending.email):
        messages.error(request, 'Повторная отправка доступна раз в минуту, не более 5 писем в час.')
    else:
        try:
            with transaction.atomic():
                pending = PendingSignup.objects.select_for_update().get(pk=pending.pk)
                issue_code(pending)
        except PendingSignup.DoesNotExist:
            return redirect('register')
        except Exception as exc:
            logger.error('Verification email delivery failed (%s)', type(exc).__name__)
            messages.error(request, 'Письмо не отправлено. Попробуйте позже; предыдущий код сохраняет свой срок действия.')
        else:
            messages.success(request, 'Новый код отправлен. Используйте последнее письмо.')
    return redirect('verify_email')


@require_POST
def cancel_signup(request):
    pending = pending_for_request(request)
    if pending:
        pending.delete()
    request.session.pop(SESSION_KEY, None)
    return redirect('register')


class PortalPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'class': 'ds-input', 'autocomplete': 'email', 'placeholder': 'you@example.com'})

    def get_users(self, email):
        # Legacy accounts may share an address. Do not reset several accounts at once.
        users = list(super().get_users(email))
        return users if len(users) == 1 else []

    def send_mail(self, subject_template_name, email_template_name, context, from_email,
                  to_email, html_email_template_name=None):
        subject = ''.join(render_to_string(subject_template_name, context).splitlines())
        body = render_to_string(email_template_name, context)
        if send_mail(subject, body, from_email, [to_email], fail_silently=False) != 1:
            raise RuntimeError('Mail backend did not accept the message')


class PortalSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'ds-input', 'autocomplete': 'new-password'})


class PortalPasswordResetView(PasswordResetView):
    form_class = PortalPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.txt'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        if allow_email(self.request, form.cleaned_data['email'].strip().lower()):
            try:
                # Fixed origin avoids generating security links from a request Host header.
                origin = urlsplit(settings.PORTAL_PUBLIC_URL)
                if (origin.scheme not in {'http', 'https'} or not origin.hostname
                        or origin.username or origin.password or origin.query or origin.fragment
                        or origin.path not in {'', '/'}
                        or (not settings.DEBUG and origin.scheme != 'https')):
                    raise ImproperlyConfigured('Set PORTAL_PUBLIC_URL to the public HTTPS origin.')
                form.save(
                    use_https=origin.scheme == 'https', domain_override=origin.netloc,
                    from_email=settings.DEFAULT_FROM_EMAIL, request=self.request,
                    email_template_name=self.email_template_name,
                    subject_template_name=self.subject_template_name,
                )
            except Exception as exc:
                logger.error('Password reset delivery failed (%s)', type(exc).__name__)
        # Unknown/disabled accounts and throttled requests receive the same response.
        return redirect(self.success_url)
