import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth.hashers import check_password
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CustomUser, EmailRateLimit, Group, PendingSignup


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PORTAL_PUBLIC_URL='https://portal.example.org',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
)
class EmailAuthTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(number=105, faculty='ВМК', course=1)
        self.data = {
            'name': 'Тестовый студент', 'email': 'Student@Example.org', 'student_id': 'email-test-105',
            'faculty': 'ВМК', 'group_number': 105,
            'password1': 'StrongNewPass47!', 'password2': 'StrongNewPass47!',
        }

    def signup(self):
        response = self.client.post(reverse('register'), self.data)
        self.assertRedirects(response, reverse('verify_email'))
        return re.search(r'\b[0-9]{6}\b', mail.outbox[-1].body).group()

    def account(self, **extra):
        return CustomUser.objects.create_user(
            username='reset-user', student_id='reset-user', email='reset@example.org',
            password='OldStrongPassword47!', **extra,
        )

    def reset_url(self):
        response = self.client.post(reverse('password_reset'), {'email': 'RESET@example.org'})
        self.assertRedirects(response, reverse('password_reset_done'))
        url = re.search(r'https://\S+', mail.outbox[-1].body).group()
        self.assertEqual(urlsplit(url).netloc, 'portal.example.org')
        return urlsplit(url).path

    def test_registration_requires_email(self):
        del self.data['email']
        response = self.client.post(reverse('register'), self.data)
        self.assertIn('email', response.context['form'].errors)
        self.assertFalse(CustomUser.objects.exists())

    def test_code_is_required_before_account_exists_and_is_not_stored_plaintext(self):
        code = self.signup()
        pending = PendingSignup.objects.get()
        self.assertFalse(CustomUser.objects.exists())
        self.assertNotEqual(pending.code_hash, code)
        self.assertTrue(check_password(self.data['password1'], pending.password_hash))
        self.assertNotIn('password', str(dict(self.client.session)))
        self.assertFalse(self.client.login(student_id=self.data['student_id'], password=self.data['password1']))
        response = self.client.post(reverse('verify_email'), {'code': code})
        self.assertRedirects(response, reverse('login'))
        user = CustomUser.objects.get()
        self.assertEqual(user.email, 'student@example.org')
        self.assertEqual(user.group, self.group)
        self.assertEqual(user.role, 'student')
        self.assertFalse(PendingSignup.objects.exists())
        self.assertTrue(self.client.login(student_id=user.student_id, password=self.data['password1']))

    def test_wrong_code_exhausts_attempts(self):
        code = self.signup()
        wrong = '111111' if code != '111111' else '222222'
        for _ in range(5):
            self.client.post(reverse('verify_email'), {'code': wrong})
        self.assertContains(self.client.post(reverse('verify_email'), {'code': code}), 'исчерпаны попытки')
        self.assertFalse(CustomUser.objects.exists())

    def test_expired_code_is_rejected(self):
        code = self.signup()
        PendingSignup.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.client.post(reverse('verify_email'), {'code': code}), 'Код истёк')
        self.assertFalse(CustomUser.objects.exists())

    def test_code_cannot_be_used_from_another_session_or_replayed(self):
        code = self.signup()
        other = Client()
        self.assertRedirects(other.post(reverse('verify_email'), {'code': code}), reverse('register'))
        self.assertFalse(CustomUser.objects.exists())
        self.client.post(reverse('verify_email'), {'code': code})
        self.client.post(reverse('verify_email'), {'code': code})
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_resend_cooldown_and_old_code_invalidation(self):
        code = self.signup()
        self.client.post(reverse('resend_verification_code'))
        self.assertEqual(len(mail.outbox), 1)
        EmailRateLimit.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        new_code = '111111' if code != '111111' else '222222'
        with patch('main.email_auth.secrets.randbelow', return_value=int(new_code)):
            self.client.post(reverse('resend_verification_code'))
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(reverse('verify_email'), {'code': code})
        self.assertFalse(CustomUser.objects.exists())
        self.client.post(reverse('verify_email'), {'code': new_code})
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_delivery_failure_rolls_back_signup(self):
        with patch('main.email_auth.send_mail', side_effect=OSError('offline')), self.assertLogs('main.email_auth', level='ERROR'):
            response = self.client.post(reverse('register'), self.data)
        self.assertContains(response, 'Не удалось отправить письмо')
        self.assertFalse(PendingSignup.objects.exists())
        self.assertFalse(CustomUser.objects.exists())

    def test_failed_resend_keeps_original_code(self):
        code = self.signup()
        EmailRateLimit.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with patch('main.email_auth.send_mail', side_effect=OSError('offline')), self.assertLogs('main.email_auth', level='ERROR'):
            self.client.post(reverse('resend_verification_code'))
        self.client.post(reverse('verify_email'), {'code': code})
        self.assertTrue(CustomUser.objects.exists())

    def test_case_insensitive_duplicate_email_is_rejected(self):
        self.account()
        self.data['email'] = 'RESET@EXAMPLE.ORG'
        response = self.client.post(reverse('register'), self.data)
        self.assertIn('email', response.context['form'].errors)

    def test_pending_signup_does_not_allow_cross_session_replacement(self):
        code = self.signup()
        EmailRateLimit.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        other = Client()
        other.post(reverse('register'), {**self.data, 'password1': 'OtherPassword84!', 'password2': 'OtherPassword84!'})
        self.client.post(reverse('verify_email'), {'code': code})
        self.assertTrue(CustomUser.objects.get().check_password(self.data['password1']))

    def test_resend_and_cancel_require_post_and_csrf(self):
        self.signup()
        protected = Client(enforce_csrf_checks=True)
        for route in ('resend_verification_code', 'cancel_signup'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 405)
            self.assertEqual(protected.post(reverse(route)).status_code, 403)

    def test_password_reset_link_changes_password_and_is_single_use(self):
        user = self.account()
        url = self.reset_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        confirm_url = response.url
        self.assertContains(self.client.get(confirm_url), 'Создайте новый пароль')
        response = self.client.post(confirm_url, {'new_password1': 'ChangedPassword84!', 'new_password2': 'ChangedPassword84!'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('ChangedPassword84!'))
        self.assertFalse(user.check_password('OldStrongPassword47!'))
        self.assertContains(Client().get(url), 'Ссылка недействительна')

    def test_unknown_or_disabled_email_is_not_disclosed(self):
        self.account(is_active=False)
        for email in ('unknown@example.org', 'reset@example.org'):
            response = self.client.post(reverse('password_reset'), {'email': email})
            self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_rate_limit(self):
        self.account()
        self.reset_url()
        self.client.post(reverse('password_reset'), {'email': 'reset@example.org'})
        self.assertEqual(len(mail.outbox), 1)

    def test_ambiguous_legacy_email_does_not_reset_multiple_accounts(self):
        self.account()
        CustomUser.objects.create_user(username='other', student_id='other', email='RESET@example.org', password='OtherPassword84!')
        self.client.post(reverse('password_reset'), {'email': 'reset@example.org'})
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_expiry(self):
        user = self.account()
        with patch.object(default_token_generator, '_now', return_value=timezone.now().replace(tzinfo=None) - timedelta(hours=2)):
            url = self.reset_url()
        self.assertContains(self.client.get(url), 'Ссылка недействительна')

    def test_reset_failure_does_not_expose_mail_credentials(self):
        self.account()
        with patch('main.email_auth.send_mail', side_effect=OSError('SECRET')), self.assertLogs('main.email_auth', level='ERROR') as logs:
            response = self.client.post(reverse('password_reset'), {'email': 'reset@example.org'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertNotIn('SECRET', str(logs.output))

    def test_disabled_account_cannot_login_or_keep_its_session(self):
        user = self.account(is_active=False)
        response = self.client.post(reverse('login'), {'username': user.student_id, 'password': 'OldStrongPassword47!'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_deactivation_invalidates_existing_login(self):
        user = self.account()
        self.client.force_login(user)
        user.is_active = False
        user.save(update_fields=['is_active'])
        self.assertRedirects(self.client.get(reverse('profile')), reverse('login') + '?next=/profile/')

    def test_login_form_uses_student_id_backend(self):
        user = self.account()
        response = self.client.post(reverse('login'), {'username': user.student_id, 'password': 'OldStrongPassword47!'})
        self.assertRedirects(response, reverse('home'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_reset_uses_fixed_origin_even_if_request_host_is_allowed(self):
        self.account()
        with override_settings(ALLOWED_HOSTS=['unrelated.example.org']):
            self.client.post(reverse('password_reset'), {'email': 'reset@example.org'}, HTTP_HOST='unrelated.example.org')
        self.assertIn('https://portal.example.org/', mail.outbox[0].body)
        self.assertNotIn('unrelated.example.org', mail.outbox[0].body)

    def test_weak_password_cannot_be_set_from_reset_link(self):
        user = self.account()
        confirm_url = self.client.get(self.reset_url()).url
        response = self.client.post(confirm_url, {'new_password1': '123', 'new_password2': '123'})
        self.assertTrue(response.context['form'].errors)
        user.refresh_from_db()
        self.assertTrue(user.check_password('OldStrongPassword47!'))

    def test_cleanup_keeps_unexpired_signup_and_accounts(self):
        from django.core.management import call_command
        import io
        user = self.account()
        self.signup()
        call_command('cleanup_email_auth', stdout=io.StringIO())
        self.assertTrue(PendingSignup.objects.exists())
        PendingSignup.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command('cleanup_email_auth', stdout=io.StringIO())
        self.assertFalse(PendingSignup.objects.exists())
        self.assertTrue(CustomUser.objects.filter(pk=user.pk).exists())
