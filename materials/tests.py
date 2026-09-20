from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from .models import Material, MaterialFolder
from main.models import CustomUser
import os

# Create your tests here.

class DownloadMaterialTests(TestCase):
    def setUp(self):
        media_dir = self.enterContext(TemporaryDirectory(prefix='test-materials-', dir=settings.DATA_DIR))
        self.enterContext(override_settings(MEDIA_ROOT=media_dir))
        # create a user and a material with a fake file
        self.user = CustomUser.objects.create_user(username='test', password='pass')
        # ensure user can manage materials
        self.user.role = 'teacher'
        self.user.save(update_fields=['role'])
        # login via force_login to bypass credential issues
        self.client.force_login(self.user)
        self.file_content = b'hello'
        self.uploaded = SimpleUploadedFile('origname.pdf', self.file_content, content_type='application/pdf')
        self.material = Material.objects.create(
            name='Display Name',
            file=self.uploaded,
            uploaded_by=self.user,
        )

    def test_download_uses_display_name(self):
        url = reverse('download_material', args=[self.material.id])
        response = self.client.get(url)
        self.addCleanup(response.file_to_stream.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Content-Disposition', response)
        disp = response['Content-Disposition']
        # RFC 5987 encoding: spaces become %20
        self.assertIn('Display%20Name.pdf', disp)

    def test_download_extension_added_if_missing(self):
        # rename material name w/o extension
        self.material.name = 'AnotherName'
        self.material.save()
        url = reverse('download_material', args=[self.material.id])
        response = self.client.get(url)
        self.addCleanup(response.file_to_stream.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Content-Disposition', response)
        # RFC 5987 encoded filename
        self.assertIn('AnotherName.pdf', response['Content-Disposition'])

    def test_type_inferred_from_extension(self):
        txtfile = SimpleUploadedFile('note.txt', b'hello world', content_type='text/plain')
        m = Material.objects.create(file=txtfile, uploaded_by=self.user)
        self.assertEqual(m.type, 'text')
        # view page should show content
        resp = self.client.get(reverse('view_material', args=[m.id]))
        self.assertContains(resp, 'hello world')
        self.assertTrue(resp.context['material'].file.closed)
        self.assertFalse(resp.context['text_truncated'])

    def test_large_text_preview_is_bounded_but_download_is_complete(self):
        content = b'a' * (1024 * 1024) + b'END-OF-FILE'
        material = Material.objects.create(file=SimpleUploadedFile('large.txt', content), uploaded_by=self.user)
        response = self.client.get(reverse('view_material', args=[material.pk]))
        self.assertTrue(response.context['text_truncated'])
        self.assertEqual(len(response.context['text_content']), 1024 * 1024)
        self.assertNotContains(response, 'END-OF-FILE')
        self.assertContains(response, 'скачайте его')
        self.assertTrue(response.context['material'].file.closed)
        download = self.client.get(reverse('download_material', args=[material.pk]))
        self.addCleanup(download.file_to_stream.close)
        self.assertEqual(b''.join(download.streaming_content), content)

    def test_view_has_no_inline_styles(self):
        # create generic material
        resp = self.client.get(reverse('view_material', args=[self.material.id]))
        html = resp.content.decode('utf-8')
        # only inspect the material-viewer section to ignore header/footer
        idx = html.find('class="material-viewer-container"')
        if idx != -1:
            html = html[idx:]
        self.assertNotIn('style="', html)

    def test_folder_counts_and_size_displayed(self):
        # create folder and two materials inside
        folder = MaterialFolder.objects.create(name='F', created_by=self.user)
        m1 = Material.objects.create(file=self.uploaded, uploaded_by=self.user, folder=folder)
        m2 = Material.objects.create(file=SimpleUploadedFile('a.txt', b'abc', content_type='text/plain'), uploaded_by=self.user, folder=folder)
        # navigate to root to see folder info
        resp = self.client.get(reverse('materials_drive_root'))
        text = resp.content.decode('utf-8')
        self.assertIn('F', text)
        # should show total item count (2 files + 0 subfolders) and size
        self.assertIn('Элементов: 2', text)
        self.assertRegex(text, r"\(.*?\)")

    def test_folder_count_includes_subfolders(self):
        folder = MaterialFolder.objects.create(name='Parent', created_by=self.user)
        MaterialFolder.objects.create(name='Child', created_by=self.user, parent_folder=folder)
        Material.objects.create(file=SimpleUploadedFile('a.txt', b'a', content_type='text/plain'), uploaded_by=self.user, folder=folder)
        Material.objects.create(file=SimpleUploadedFile('b.txt', b'b', content_type='text/plain'), uploaded_by=self.user, folder=folder)
        resp = self.client.get(reverse('materials_drive_root'))
        text = resp.content.decode('utf-8')
        # 2 files + 1 subfolder = 3, not just the 2 direct files
        self.assertIn('Элементов: 3', text)

    def test_template_has_download_attribute(self):
        # request drive view and ensure download link uses download attribute
        resp = self.client.get(reverse('materials_drive_root'))
        self.assertEqual(resp.status_code, 200)
        # find anchor for download with keyword (boolean attribute)
        self.assertIn(' download>', resp.content.decode('utf-8'))

    def test_delete_redirects_to_same_folder(self):
        # create a folder and a material inside it
        folder = MaterialFolder.objects.create(name='F', created_by=self.user)
        mat = Material.objects.create(
            name='InFolder',
            file=self.uploaded,
            type='other',
            uploaded_by=self.user,
            folder=folder,
        )
        # navigate to folder to set session
        self.client.get(reverse('materials_drive_folder', args=[folder.id]))
        # perform delete
        resp = self.client.post(reverse('delete_material', args=[mat.id]))
        # should redirect back to folder view
        self.assertRedirects(resp, reverse('materials_drive_folder', args=[folder.id]))
        # ensure material is gone
        self.assertFalse(Material.objects.filter(id=mat.id).exists())
