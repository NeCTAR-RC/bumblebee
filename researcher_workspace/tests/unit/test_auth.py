from unittest.mock import Mock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from researcher_workspace.auth import generate_username
from researcher_workspace.auth import OIDCAuthBackend, ClassicAuthBackend

from researcher_workspace.tests.factories import UserFactory

from guacamole import models as guac_models

from faker import Faker


User = get_user_model()

fake = Faker()


class GenerateUsernameTestCase(TestCase):
    def run_test(self, email, expected):
        actual = generate_username(email)
        self.assertEqual(actual, expected)
        self.assertEqual(type(actual), type(expected))

    def test_valid_email(self):
        self.run_test('Üsêrnamê@example.com', 'Üsêrnamê@example.com')

    def test_email_invalid_length(self):
        email = ('LlanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogochEy'
                 'jafjallajokullWolfeschlegelsteinhausenbergerdorffMicropachyc'
                 'ephalosaurusSupercalifragilisticexpialidocious@example.com')
        self.run_test(email, email[:150])


class ClassicAuthBackendTestCase(TestCase):

    @override_settings(OIDC_RP_CLIENT_SECRET='client_secret')
    def setUp(self):
        self.backend = ClassicAuthBackend()
        self.rf = RequestFactory()
        self.user = User.objects.create_user(
            username="jacob", email="jacob@nowhere.com",
            password="top_secret")

    def test_authenticate_unknown(self):
        """The user does not exist."""
        request = self.rf.get("/home/")
        user = self.backend.authenticate(request, username='fred',
                                         password='nonce')
        self.assertIsNone(user)

    def test_authenticate_new(self):
        """The user exists but has no Guacamole objects yet.  Check
        that they are created."""
        self.assertRaises(
            guac_models.GuacamoleEntity.DoesNotExist,
            lambda: guac_models.GuacamoleEntity.objects.get(
                name=self.user.email))

        request = self.rf.get("/home/")
        user = self.backend.authenticate(request, username='jacob',
                                         password='top_secret')
        self.assertEqual(user, self.user)
        gentity = guac_models.GuacamoleEntity.objects.get(name=self.user.email)
        self.assertEqual(gentity.type, 'USER')
        guser = guac_models.GuacamoleUser.objects.get(
            email_address=self.user.email)
        self.assertEqual(guser.entity, gentity)
        self.assertEqual(guser.email_address, self.user.email)
        self.assertEqual(guser.full_name, self.user.get_full_name())
        self.assertEqual(guser.password_hash, 'x')

    def test_authenticate_existing(self):
        """The user exists and has existing Guacamole objects.  Check
        that they are updated."""

        gentity = guac_models.GuacamoleEntity.objects.create(
            name=self.user.email, type='USER')
        guser = guac_models.GuacamoleUser.objects.create(
            entity=gentity, email_address=self.user.email,
            full_name="Nonsense", password_hash="y",
            disabled=False, expired=False)

        request = self.rf.get("/home/")
        user = self.backend.authenticate(request, username='jacob',
                                         password='top_secret')
        self.assertEqual(user, self.user)
        gentity = guac_models.GuacamoleEntity.objects.get(name=self.user.email)
        self.assertEqual(gentity.type, 'USER')
        guser = guac_models.GuacamoleUser.objects.get(
            email_address=self.user.email)
        self.assertEqual(guser.entity, gentity)
        self.assertEqual(guser.email_address, self.user.email)
        self.assertEqual(guser.full_name, self.user.get_full_name())
        self.assertEqual(guser.password_hash, 'x')


class OIDCAuthBackendTestCase(TestCase):

    @override_settings(OIDC_RP_CLIENT_SECRET='client_secret')
    def setUp(self):
        self.backend = OIDCAuthBackend()

    def test_missing_request_arg(self):
        """Test authentication returns `None` when `request` is not provided."""
        self.assertIsNone(self.backend.authenticate(request=None))

    def _setup_request_mock(self, request_mock, user_data):
        """Common setup for the request mock.  The 'get' method is mocked
        to deliver a 'Response' with a given JSON payload.  The 'post'
        method is mocked to minimally simulate the post request that
        returns a OIDC session token."""
        get_json_mock = Mock()
        get_json_mock.json.return_value = user_data
        request_mock.get.return_value = get_json_mock
        post_mock = MagicMock(status_code=200)
        post_mock.json = MagicMock(return_value={})
        request_mock.post.return_value = post_mock

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    @patch('researcher_workspace.auth.OIDCAuthBackend.verify_claims')
    def test_create_new_user(self, claims_mock, token_mock, request_mock):
        """Test successful creation of new user."""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': ['allow'],
        }
        self.assertEqual(
            User.objects.filter(sub=user_data['sub']).exists(), False)

        self._setup_request_mock(request_mock, user_data)
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertEqual(auth_user, User.objects.get(sub=user_data['sub']))
        self.assertFalse(auth_user.is_staff)
        self.assertFalse(auth_user.is_superuser)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    @patch('researcher_workspace.auth.OIDCAuthBackend.verify_claims')
    def test_successful_authentication_existing_user(
        self, claims_mock, token_mock, request_mock):
        """Test successful authentication for existing user."""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
        }
        self._setup_request_mock(request_mock, user_data)
        test_user = UserFactory(
            email=user_data['email'],
            first_name=user_data['given_name'],
            last_name=user_data['family_name'],
            sub=user_data['sub'],
        )
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertEqual(auth_user, test_user)
        self.assertFalse(auth_user.is_staff)
        self.assertFalse(auth_user.is_superuser)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    @patch('researcher_workspace.auth.OIDCAuthBackend.verify_claims')
    def test_successful_authentication_existing_user_without_sub(
        self, claims_mock, token_mock, request_mock):
        """Test successful authentication for existing user."""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
        }
        self._setup_request_mock(request_mock, user_data)
        test_user = UserFactory(
            email=user_data['email'],
            first_name=user_data['given_name'],
            last_name=user_data['family_name'],
            sub=None,
        )
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertEqual(auth_user, test_user)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    @patch('researcher_workspace.auth.OIDCAuthBackend.verify_claims')
    def test_auth_failure_with_mismatch_sub(
        self, claims_mock, token_mock, request_mock):
        """Test an existing user with a sub mismatch isn't authenticated."""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
        }
        self._setup_request_mock(request_mock, user_data)
        user = UserFactory(
            email=user_data['email'],
            first_name=user_data['given_name'],
            last_name=user_data['family_name'],
            sub=fake.uuid4(),
        )
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertIsNone(auth_user)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    def test_auth_succeeds_with_aaf(
        self, token_mock, request_mock):
        """Test authentication succeeds if federation is AAF"""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': ['allow'],
        }
        self._setup_request_mock(request_mock, user_data)
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertIsNotNone(auth_user)

    @override_settings(OIDC_ALLOW_GROUPS=['allow'])
    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    def test_auth_fails_without_group(
        self, token_mock, request_mock):
        """Test authentication fails without federation"""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': ['wrong_group'],
        }
        self._setup_request_mock(request_mock, user_data)
        get_json_mock = Mock()
        get_json_mock.json.return_value = user_data
        request_mock.get.return_value = get_json_mock
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertIsNone(auth_user)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    def test_user_admin_permissions_granted_from_groups(
        self, token_mock, request_mock):
        """Test admin is granted if admin role is given in claim"""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': ['admin'],
        }
        self._setup_request_mock(request_mock, user_data)
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertTrue(auth_user.is_staff)
        self.assertTrue(auth_user.is_superuser)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    def test_user_staff_permissions_granted_from_groups(
        self, token_mock, request_mock):
        """Test staff is granted if staff role is given in claim"""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        user_data = {
            'email': fake.email(),
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': ['staff'],
        }
        self._setup_request_mock(request_mock, user_data)
        auth_user = self.backend.authenticate(request=auth_request)
        self.assertTrue(auth_user.is_staff)
        self.assertFalse(auth_user.is_superuser)

    @patch('mozilla_django_oidc.auth.requests')
    @patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token')
    @patch('researcher_workspace.auth.OIDCAuthBackend.verify_claims')
    def test_update_values_existing_user(
        self, claims_mock, token_mock, request_mock):
        """Test user values are updated when claims change, especially
        for permissions"""
        auth_request = RequestFactory().get('/foo', {'code': 'foo',
                                                     'state': 'bar'})
        auth_request.session = {}
        test_new_email = fake.email()
        test_old_email = fake.email()
        user_data = {
            'email': test_new_email,
            'given_name': fake.first_name(),
            'family_name': fake.last_name(),
            'sub': fake.uuid4(),
            'groups': [],  # demote unprivileged
        }
        self._setup_request_mock(request_mock, user_data)
        test_user = UserFactory(
            email=test_old_email,
            first_name=user_data['given_name'],
            last_name=user_data['family_name'],
            sub=user_data['sub'],
            is_staff=True,
            is_superuser=True,
        )
        self.assertTrue(test_user.is_staff)
        self.assertTrue(test_user.is_superuser)

        gentity1 = guac_models.GuacamoleEntity.objects.create(
            name=test_old_email, type='USER')

        auth_user = self.backend.authenticate(request=auth_request)
        self.assertEqual(auth_user, test_user)
        self.assertFalse(auth_user.is_staff)
        self.assertFalse(auth_user.is_superuser)

        gentity2 = guac_models.GuacamoleEntity.objects.get(
            name=test_new_email, type='USER')
        # Ensure no new entity created, but just updated
        self.assertEqual(gentity1.entity_id, gentity2.entity_id)
