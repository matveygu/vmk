from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from main.models import CustomUser
from schedule.models import Subject
from .forms import MaterialEditForm, MaterialUploadForm
from .models import Material, MaterialFavorite, MaterialFolder


@override_settings(SECURE_SSL_REDIRECT=False)
class MaterialCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username='catalog-user', student_id='catalog-user', role='teacher')
        cls.other = CustomUser.objects.create_user(username='catalog-other', student_id='catalog-other')
        cls.subject = Subject.objects.create(name='Математический анализ')
        cls.folder = MaterialFolder.objects.create(name='Лекции', created_by=cls.user)
        cls.nested = MaterialFolder.objects.create(name='Вложенная', parent_folder=cls.folder,
                                                  created_by=cls.user)
        cls.root_file = Material.objects.create(name='Корневой файл', file='materials/root.pdf',
                                               uploaded_by=cls.user)
        cls.material = Material.objects.create(name='Лекция 1', file='materials/lecture.pdf',
            uploaded_by=cls.user, folder=cls.nested, subject=cls.subject, semester=2)

    def setUp(self):
        media_dir = self.enterContext(TemporaryDirectory(prefix='test-catalog-', dir=settings.DATA_DIR))
        self.enterContext(override_settings(MEDIA_ROOT=media_dir))
        self.client.force_login(self.user)
        self.url = reverse('materials_drive_root')
        self.favorite_url = reverse('material_favorite', args=[self.material.pk])

    def test_unfiltered_browsing_keeps_folder_scope(self):
        response = self.client.get(self.url)
        self.assertEqual([m.pk for m in response.context['materials']], [self.root_file.pk])
        self.assertEqual([f.pk for f in response.context['subfolders']], [self.folder.pk])
        response = self.client.get(reverse('materials_drive_folder', args=[self.nested.pk]))
        self.assertEqual([m.pk for m in response.context['materials']], [self.material.pk])
        self.assertEqual([f.pk for f in response.context['breadcrumbs']],
                         [self.folder.pk, self.nested.pk])

    def test_filters_intersect_and_search_all_folders(self):
        MaterialFavorite.objects.create(user=self.user, material=self.material)
        params = {'q': 'Лекция', 'subject': self.subject.pk, 'semester': 2,
                  'material_type': 'document', 'favorites': '1'}
        response = self.client.get(self.url, params)
        self.assertEqual([m.pk for m in response.context['materials']], [self.material.pk])
        self.assertTrue(response.context['materials'][0].is_favorite)
        self.assertEqual(response.context['subfolders'], [])
        response = self.client.get(self.url, {**params, 'semester': 3})
        self.assertEqual(response.context['total_items'], 0)

    def test_name_search_finds_nested_folders_and_files(self):
        response = self.client.get(self.url, {'q': 'Лек'})
        self.assertEqual([m.pk for m in response.context['materials']], [self.material.pk])
        self.assertEqual([f.pk for f in response.context['subfolders']], [self.folder.pk])

    def test_invalid_filters_show_errors_without_unfiltered_results(self):
        for params in ({'semester': 99}, {'subject': 'bad'}, {'material_type': 'bad'}, {'q': 'x' * 201}):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['filter_form'].errors)
                self.assertEqual(response.context['total_items'], 0)

    def test_favorites_are_personal_and_idempotent(self):
        MaterialFavorite.objects.create(user=self.other, material=self.material)
        self.assertEqual(self.client.get(self.url, {'favorites': '1'}).context['total_items'], 0)
        for _ in range(2):
            response = self.client.post(self.favorite_url, {'favorite': '1', 'next': self.url + '?favorites=1'})
            self.assertRedirects(response, self.url + '?favorites=1', fetch_redirect_response=False)
        self.assertEqual(MaterialFavorite.objects.filter(user=self.user).count(), 1)
        for _ in range(2):
            self.client.post(self.favorite_url, {'favorite': '0'})
        self.assertFalse(MaterialFavorite.objects.filter(user=self.user).exists())
        self.assertTrue(MaterialFavorite.objects.filter(user=self.other).exists())

    def test_favorite_endpoint_requires_login_post_and_valid_state(self):
        self.assertEqual(self.client.get(self.favorite_url).status_code, 405)
        self.assertEqual(self.client.post(self.favorite_url, {'favorite': 'bad'}).status_code, 400)
        self.assertFalse(MaterialFavorite.objects.exists())
        self.client.logout()
        self.assertEqual(self.client.post(self.favorite_url, {'favorite': '1'}).status_code, 302)
        self.assertFalse(MaterialFavorite.objects.exists())

    def test_favorite_does_not_redirect_to_external_site(self):
        for target in ('https://example.org/', '//example.org/', '/admin-panel/'):
            response = self.client.post(self.favorite_url, {'favorite': '1', 'next': target})
            self.assertRedirects(response, reverse('view_material', args=[self.material.pk]),
                                 fetch_redirect_response=False)

    def test_pagination_is_stable_and_keeps_filters(self):
        Material.objects.bulk_create([
            Material(name=f'Лекция {n}', file=f'materials/{n}.pdf', type='document',
                     uploaded_by=self.user, subject=self.subject, semester=2)
            for n in range(40)
        ])
        params = {'subject': self.subject.pk, 'semester': 2}
        first = self.client.get(self.url, params)
        second = self.client.get(self.url, {**params, 'page': 2})
        first_ids = {m.pk for m in first.context['materials']}
        second_ids = {m.pk for m in second.context['materials']}
        self.assertEqual(len(first_ids), 36)
        self.assertEqual(len(second_ids), 5)
        self.assertFalse(first_ids & second_ids)
        self.assertContains(first, f'?subject={self.subject.pk}&amp;semester=2&amp;page=2')
        self.assertNotIn('page=', second.context['filter_query'])

    def test_subjects_and_favorites_do_not_add_queries_per_file(self):
        def measure():
            self.client.get(self.url, {'semester': 2})
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.url, {'semester': 2})
            self.assertEqual(response.status_code, 200)
            return len(queries)
        before = measure()
        for n in range(10):
            subject = Subject.objects.create(name=f'Предмет {n}')
            material = Material.objects.create(name=f'Файл {n}', file=f'materials/{n}.pdf',
                subject=subject, semester=2, uploaded_by=self.user)
            MaterialFavorite.objects.create(user=self.user, material=material)
        self.assertEqual(measure(), before)

    def test_upload_form_saves_optional_metadata(self):
        form = MaterialUploadForm({'subject': self.subject.pk, 'semester': 2},
            {'file': SimpleUploadedFile('lecture.pdf', b'%PDF-1.4 test')})
        self.assertTrue(form.is_valid(), form.errors)
        material = form.save(commit=False)
        material.uploaded_by = self.user
        material.save()
        material.refresh_from_db()
        self.assertEqual(material.subject, self.subject)
        self.assertEqual(material.semester, 2)
        self.assertEqual(material.type, 'document')

    def test_metadata_edit_keeps_original_file_without_replacement(self):
        material = Material.objects.create(uploaded_by=self.user,
            file=SimpleUploadedFile('original.pdf', b'original'))
        original = material.file.name
        for files in ({}, {'file': SimpleUploadedFile('replacement.pdf', b'replacement')}):
            form = MaterialEditForm({'name': 'Новое имя', 'subject': self.subject.pk, 'semester': 3},
                                    files, instance=material)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            material.refresh_from_db()
            self.assertEqual(material.file.name, original)
            self.assertEqual(material.semester, 3)
            with material.file.open('rb') as stored:
                self.assertEqual(stored.read(), b'original')

    def test_material_form_rejects_invalid_semester(self):
        form = MaterialEditForm({'name': 'Лекция', 'semester': 13}, instance=self.material)
        self.assertFalse(form.is_valid())
        self.assertIn('semester', form.errors)

    def test_metadata_can_be_edited_when_stored_file_is_missing(self):
        form = MaterialEditForm({'name': 'Лекция', 'semester': 3}, instance=self.material)
        self.assertTrue(form.is_valid(), form.errors)
        material = form.save()
        self.assertEqual(material.file.name, 'materials/lecture.pdf')
        self.assertEqual(material.semester, 3)

    def test_replacement_requires_checkbox_and_validates_new_file(self):
        form = MaterialEditForm({'name': 'Лекция', 'replace_file': 'on'},
            {'file': SimpleUploadedFile('new.pdf', b'new content')}, instance=self.material)
        self.assertTrue(form.is_valid(), form.errors)
        material = form.save()
        with material.file.open('rb') as stored:
            self.assertEqual(stored.read(), b'new content')
        invalid = MaterialEditForm({'name': 'Лекция', 'replace_file': 'on'},
            {'file': SimpleUploadedFile('bad.exe', b'invalid')}, instance=material)
        self.assertFalse(invalid.is_valid())
        self.assertIn('file', invalid.errors)

    def test_mobile_nav_is_authenticated_only(self):
        self.assertContains(self.client.get(self.url), 'aria-label="Быстрая навигация"')
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('home')), 'aria-label="Быстрая навигация"')
