import os
import logging

from hypothesis import settings
from pytest import fixture
from requests.packages import urllib3

from .toolbox import Toolbox

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger('openmotics')


settings.register_profile('default', deadline=None, max_examples=10, stateful_step_count=5, print_blob=True)
settings.register_profile('once', deadline=None, max_examples=1, stateful_step_count=5, print_blob=True)
settings.register_profile('ci', deadline=None, max_examples=100, stateful_step_count=10, print_blob=True)
settings.load_profile(os.getenv('HYPOTHESIS_PROFILE', 'default'))


@fixture(scope='session')
def toolbox_session():
    return Toolbox()


@fixture
def toolbox(toolbox_session):
    toolbox = toolbox_session
    yield toolbox
    try:
        data = toolbox.observer.get('/plugins/syslog_receiver/logs')
        for log in data['logs']:
            print(log)
    except Exception:
        print('Failed to retrieve logs')
