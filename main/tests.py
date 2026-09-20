from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from .models import News
from .models import CustomUser

# Create your tests here.

class DownloadNewsTests(TestCase):
    def setUp(self):
        media_dir = self.enterContext(TemporaryDirectory(prefix='test-news-', dir=settings.DATA_DIR))
        self.enterContext(override_settings(MEDIA_ROOT=media_dir))
        self.user = CustomUser.objects.create_user(username='newsuser', password='pass')
        self.client.force_login(self.user)
        self.uploaded = SimpleUploadedFile('f.txt', b'data', content_type='text/plain')
        self.news = News.objects.create(
            title='My Title',
            content='content',
            author=self.user,
            file=self.uploaded,
        )

    def test_download_uses_title(self):
        url = reverse('download_news', args=[self.news.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), b'data')
        # RFC 5987 encoding: spaces become %20
        self.assertIn('My%20Title.txt', resp['Content-Disposition'])

    def test_registration_invalid_group_shows_message(self):
        """При ошибочном указании группы пользователь должен получить
        понятное сообщение и форма не должна проходить валидацию."""
        self.client.logout()  # Registration is only available before login.
        data = {
            'email': 'new-student@example.org',
            'name': 'Test User',
            'student_id': '12345',
            # используем реально существующий факультет из JSON
            'faculty': 'ВМК',
            'group_number': '999',  # несуществующая группа
            'password1': 'ComplexPass123',
            'password2': 'ComplexPass123',
        }
        resp = self.client.post(reverse('register'), data)
        # В случае ошибки остаёмся на той же странице (200) и видим сообщение
        self.assertEqual(resp.status_code, 200)
        # сообщение должно упомянуть номер группы и что она не найдена
        self.assertContains(resp, 'Группа 999 факультета')
        self.assertContains(resp, 'не найдена')
        form = resp.context['form']
        self.assertTrue(form.errors.get('group_number'))
