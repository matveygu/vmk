from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from docker.update import validate_checkout


class UpdateCheckoutTests(SimpleTestCase):
    def container(self, directory, service='web'):
        return {'Config': {'Labels': {'com.docker.compose.service': service,
                                      'com.docker.compose.project.working_dir': directory}}}

    def test_other_checkout_is_rejected_before_mutation(self):
        root = Path('current-portal').resolve()
        with patch('docker.update.ROOT', root):
            with self.assertRaises(RuntimeError):
                validate_checkout([self.container(str(root.parent / 'old-portal'))])
            validate_checkout([self.container(str(root))])

    def test_database_container_does_not_determine_source_checkout(self):
        validate_checkout([self.container('old-portal', service='db')])
