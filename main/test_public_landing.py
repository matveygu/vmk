"""The faculty overview belongs to the anonymous homepage only."""
from html.parser import HTMLParser

from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import CustomUser


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []
        self.section_labels = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs)
        if tag == 'section' and 'aria-labelledby' in attrs:
            self.section_labels.append(attrs['aria-labelledby'])


@override_settings(SECURE_SSL_REDIRECT=False)
class PublicLandingTests(TestCase):
    def test_anonymous_home_has_faculty_life_stories_and_faq(self):
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'public_landing.html')
        for text in ('Математика в основе.', 'Найти своих.',
                     'Учёба глазами выпускников', 'О чём часто спрашивают',
                     'Андрей Шохин', 'Валентин Степанович', 'Влада Розова',
                     'не дословные цитаты', 'Неофициальный студенческий проект'):
            self.assertContains(response, text)
        self.assertContains(response, '<details ', count=4)
        self.assertContains(response, 'css/ds/faculty_landing.css')

    def test_sources_and_section_labels_are_accessible(self):
        parser = LandingParser()
        parser.feed(self.client.get(reverse('home')).content.decode())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertTrue(set(parser.section_labels).issubset(parser.ids))
        urls = {link.get('href') for link in parser.links}
        for source in ('https://cs.msu.ru/faculty', 'https://cs.msu.ru/students',
                       'https://pk.cs.msu.ru/faculty', 'https://sa.cs.msu.ru/alumni_stories'):
            self.assertIn(source, urls)
        for link in parser.links:
            if link.get('target') == '_blank':
                self.assertIn('noopener', link.get('rel', '').split())

    def test_programs_do_not_advertise_incorrect_specialist_degree(self):
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'Специалитет')
        self.assertContains(response, '«Прикладная математика и информатика»')
        self.assertContains(response, '«Фундаментальные информатика и информационные технологии»')

    def test_authenticated_home_remains_personal(self):
        user = CustomUser.objects.create_user(username='landing-student',
                                               student_id='landing-student', role='student')
        self.client.force_login(user)
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'home.html')
        self.assertNotContains(response, 'faculty-stories-title')
        self.assertNotContains(response, 'css/ds/faculty_landing.css')
