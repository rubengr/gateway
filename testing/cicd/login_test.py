# Copyright (C) 2019 OpenMotics BVBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
""""
The login_test contains tests related to user CRUDs and authorized mode.
"""
import unittest
import time
import urllib
import logging
from random import randint
from toolbox import exception_handler
LOGGER = logging.getLogger('openmotics')


class LoginTest(unittest.TestCase):
    webinterface = None
    tools = None
    token = ''

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        i = randint(4, 36)
        cls.login = cls.tools.randomword(i)
        cls.password = cls.tools.randomword(i)
        cls.token = cls.tools._get_new_token('openmotics', '123456')

    def setUp(self):
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools._assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: {} due to discovery failure.'.format(self.id()))
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: {}'.format(self.id()))

    @exception_handler
    def test_create_user_authorized(self):
        """ Testing a creation of a user using a random login and password after entering authorized mode quick. """
        self.tools.enter_testee_authorized_mode(self.webinterface)
        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)

    @exception_handler
    def test_create_user_authorized_force_checked(self):
        """ Testing a creation of a user using a random login and password after entering authorized mode. """
        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface)  # enter_testee_authorized_mode will return True as soon as the Testee enters authorized mode, False if the timeout is reached.

        self.assertEquals(entered_authorized_mode, True, 'Should enter authorized mode within 6 seconds of pressing. Got{0}'.format(entered_authorized_mode))
        self.assertTrue(6.5 >= time.time() - start >= 4.5, 'Should enter authorized mode within 6 seconds. Got: {0}'.format(time.time() - start))
        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))

        self.tools.exit_testee_authorized_mode(self.webinterface)

    @exception_handler
    def test_login_with_user_with_terms(self):
        """ Testing login with accepted terms & conditions quick. """
        self.tools.enter_testee_authorized_mode(self.webinterface)
        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)
        self._login_testee_user(self.login, self.password, True)

    @exception_handler
    def test_login_with_user_with_terms_force_checked(self):
        """ Testing login with accepted terms & conditions. """
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 6)  # 6 is a forced timeout, 120 is default.
        self.assertEquals(entered_authorized_mode, True, 'Should enter authorized mode within 6 seconds of pressing. {0}'.format(entered_authorized_mode))
        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)
        self._login_testee_user(self.login, self.password, True)

    @exception_handler
    def test_remove_user_authorized(self):
        """ Testing a removal of a user after entering authorized mode. """
        self.tools.enter_testee_authorized_mode(self.webinterface)
        url_params = urllib.urlencode({'username': self.login})
        self.tools._api_testee('remove_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)

    @exception_handler
    def test_auto_exiting_authorized_mode_time(self):
        """ Testing if the Testee is able to exit authorized mode after some time. """
        self.tools.enter_testee_authorized_mode(self.webinterface)
        start = time.time()
        while self.tools._api_testee('get_usernames', expected_failure=True).get('success', False) is not False and time.time() - start <= self.tools.TIMEOUT:
            time.sleep(1)
        end = time.time()
        self.assertTrue(65 >= end - start >= 55, 'Should leave authorized mode after a minute.')

    @exception_handler
    def test_use_case_creating_user_logging_in_deleting_user_force_checked(self):
        """ Testing the creation, login, deletion of a user with all conditions. """
        if self.tools._api_testee('get_usernames').get('success'):
            self.tools.exit_testee_authorized_mode(self.webinterface)

        response_json = self._login_testee_user('admin', 'admin', True)
        self.assertEquals(response_json.get('msg'), "invalid_credentials")
        self.assertEquals(response_json.get('success'), False,
                          'Should not login with a non existing user. Got: {0}'.format(response_json))

        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        response_json = self.tools._api_testee('create_user?{0}'.format(url_params), expected_failure=True)
        self.assertEquals(response_json.get('success'), False,
                          'Should not create a user without being in authorized mode. Got: {0}'.format(response_json))

        self.tools.enter_testee_authorized_mode(self.webinterface, 6)

        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))

        self.tools.exit_testee_authorized_mode(self.webinterface)

        response_json = self._login_testee_user(self.login, self.password, False)
        self.assertEquals(response_json.get('next_step'), 'accept_terms',
                          'Should not login before accepting terms and conditions. Got: {0}'.format(response_json))

        self._login_testee_user(self.login, self.password, True)

        url_params = urllib.urlencode({'username': self.login})
        response_json = self.tools._api_testee('remove_user?{0}'.format(url_params), expected_failure=True)

        self.assertEquals(response_json.get('success'), False,
                          'Should fail to delete the user without authorized mode being activated. Got: {0}'.format(
                              response_json))
        self.tools.enter_testee_authorized_mode(self.webinterface, 6)

        self.tools._api_testee('remove_user?{0}'.format(url_params))

        url_params = urllib.urlencode({'username': self.login, 'password': 'new_password'})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)

        response_json = self._login_testee_user(self.login, self.password, True)
        self.assertEquals(response_json.get('success'), False,
                          'Should not be able to login with the old password. Got: {0}'.format(response_json))

        self._login_testee_user(self.login, 'new_password', True)

    @exception_handler
    def test_scenario_creating_user_logging_in_deleting_user(self):
        """ Testing the creation, login, deletion of a user with all conditions quick. """
        self.tools.enter_testee_authorized_mode(self.webinterface, 6)

        url_params = urllib.urlencode({'username': self.login, 'password': self.password})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)

        self._login_testee_user(self.login, self.password, True)

        url_params = urllib.urlencode({'username': self.login})
        self.tools.enter_testee_authorized_mode(self.webinterface, 6)

        self.tools._api_testee('remove_user?{0}'.format(url_params))

        url_params = urllib.urlencode({'username': self.login, 'password': 'new_password'})
        self.tools._api_testee('create_user?{0}'.format(url_params))
        self.tools.exit_testee_authorized_mode(self.webinterface)
        self._login_testee_user(self.login, 'new_password', True)

    @exception_handler
    def test_token_validity_force_checked(self):
        """ Testing the validity of a returned token after a login and an invalid token. """
        response_json = self._login_testee_user('openmotics', '123456', True)
        valid_token = response_json.get('token')
        self.tools._api_testee('get_features', valid_token)

        response_json = self.tools._api_testee('get_features', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token', 'Should return invalid_token when getting features with a wrong user token. Got{0}'.format(response_json))

    @exception_handler
    def test_token_validity(self):
        """ Testing the validity of a returned token after a login and an invalid token quick. """
        login_response = self._login_testee_user('openmotics', '123456', True)
        self.tools._api_testee('get_features', login_response.get('token'))
        response_json = self.tools._api_testee('get_features', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token',
                          'Should return invalid_token when getting features with a wrong user token. Got{0}'.format(response_json))

    @exception_handler
    def test_logout_existing_user_force_checked(self):
        """ Testing logging out using a valid token from a valid user. """
        response_json = self._login_testee_user('openmotics', '123456', True)
        valid_token = response_json.get('token')

        response_json = self._logout_testee_user(valid_token + 'making_it_corrupt')
        self.assertEquals(response_json, 'invalid_token',
                          'Should not logout with an invalid token. Got: {0}'.format(response_json))

        response_json = self._logout_testee_user(valid_token)
        self.assertEquals(response_json.get('status'), 'OK',
                          'Should return a status OK message indicating a successful logout action. Got: {0}'.format(response_json))

        response_json = self._logout_testee_user(valid_token)
        self.assertEquals(response_json, 'invalid_token',
                          'Should not logout again since the provided token has been invalidated. Got: {0}'.format(response_json))

    @exception_handler
    def test_logout_existing_user(self):
        """ Testing logging out using a valid token from a valid user. """
        response_json = self._login_testee_user('openmotics', '123456', True)
        valid_token = response_json.get('token')
        self._logout_testee_user(valid_token)

    @exception_handler
    def test_authorized_unauthorized_force_checked(self):
        """ Testing whether the testee is able to enter and exit authorized mode. """
        self.tools.enter_testee_authorized_mode(self.webinterface, 6)
        self.assertEquals(self.tools._api_testee('get_usernames').get('success'), True, 'Should be True after entering authorized mode and getting user names.')
        self.tools.exit_testee_authorized_mode(self.webinterface)
        self.assertEquals(self.tools._api_testee('get_usernames', token=None, expected_failure=True).get('success'), False, 'Should be False after attempting to get user names when not in authorized mode anymore.')

    @exception_handler
    def test_enter_exit_authorized_mode_duration_force_checked(self):
        """ Testing the duration to enter authorized mode. """
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 1)
        self.assertEquals(entered_authorized_mode, False, 'Should not enter authorized mode after a 1 second press. Got{0}'.format(entered_authorized_mode))
        self.tools.exit_testee_authorized_mode(self.webinterface)

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface)
        end = time.time()
        self.assertEquals(entered_authorized_mode, True, 'Should enter authorized mode within 4 seconds. Got{0}'.format(entered_authorized_mode))
        self.assertTrue(6 > end - start > 3)
        self.tools.exit_testee_authorized_mode(self.webinterface)

    @exception_handler
    def test_timed_presses_for_authorized_mode_entrance(self):
        """ Testing the necessary time in seconds to enter authorized mode. """
        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 1)
        end = time.time()
        self.assertTrue(1.2 >= end - start >= 1,
                        'Should press authorized button for 1 second and return False. Got: {0} after {1} seconds.'.format(entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, False,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 2)
        end = time.time()
        self.assertTrue(2.2 >= end - start >= 2,
                        'Should press authorized button for 2 second and return False. Got: {0} after {1} seconds.'.format(entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, False,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 3)
        end = time.time()
        self.assertTrue(3.2 >= end - start >= 3,
                        'Should press authorized button for 3 second and return False. Got: {0} after {1} seconds.'.format(entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, False,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 4)
        end = time.time()
        self.assertTrue(4.2 >= end - start >= 4,
                        'Should press authorized button for 4 second and return False. Got: {0} after {1} seconds.'.format(
                            entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, False,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(
                              entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 5)
        end = time.time()
        self.assertTrue(5.2 >= end - start >= 5,
                        'Should press authorized button for 5 second and return False. Got: {0} after {1} seconds.'.format(
                            entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, True,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(
                              entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 6)
        end = time.time()
        self.assertTrue(6.2 >= end - start >= 6,
                        'Should press authorized button for 6 second and return False. Got: {0} after {1} seconds.'.format(
                            entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, True,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(
                              entered_authorized_mode))

        start = time.time()
        entered_authorized_mode = self.tools.enter_testee_authorized_mode(self.webinterface, 7)
        end = time.time()
        self.assertTrue(7.2 >= end - start >= 7,
                        'Should press authorized button for 7 second and return False. Got: {0} after {1} seconds.'.format(
                            entered_authorized_mode, end - start))
        self.assertEquals(entered_authorized_mode, True,
                          'Should return False after attempting to enter authorized mode. Got: {0}'.format(
                              entered_authorized_mode))

    def _login_testee_user(self, username, password, accept_terms):
        """
        Makes a login API call.
        :param username: The username used to login.
        :type username: str

        :param password: The password used to login.
        :type password: str

        :param accept_terms: If the terms are (not) accepted.
        :type accept_terms: bool

        :return: json response from the login API call.
        :rtype: dict
        """
        url_params = urllib.urlencode({'username': username, 'password': password, 'accept_terms': accept_terms})
        response_json = self.tools._api_testee('login?{0}'.format(url_params), expected_failure=True)
        return response_json

    def _logout_testee_user(self, token):
        """
        Makes a logout API call.
        :param token: The used token to logout.
        :type token: str

        :return: json response from the logout API call.
        :rtype: dict
        """
        url_params = urllib.urlencode({'token': token})
        response_json = self.tools._api_testee('logout?{0}'.format(url_params), expected_failure=True)
        return response_json
