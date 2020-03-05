import os

from hypothesis import settings
from pytest import fixture
from requests.packages import urllib3

from .toolbox import Toolbox

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


settings.register_profile('default', deadline=None, max_examples=10, stateful_step_count=5, print_blob=True)
settings.register_profile('once', deadline=None, max_examples=1, stateful_step_count=5, print_blob=True)
settings.register_profile('ci', deadline=None, max_examples=500, stateful_step_count=10, print_blob=True)
settings.load_profile(os.getenv('HYPOTHESIS_PROFILE', 'default'))


@fixture(scope='session')
def toolbox():
    return Toolbox()
