import os

from hypothesis import settings
from pytest import fixture

from .toolbox import Toolbox

settings.register_profile('default', deadline=None, max_examples=10, stateful_step_count=10, print_blob=True)
settings.register_profile('ci', deadline=None, max_examples=1000, stateful_step_count=20, print_blob=True)
settings.register_profile('once', deadline=None, max_examples=1, stateful_step_count=10, print_blob=True)
settings.load_profile(os.getenv('HYPOTHESIS_PROFILE', 'default'))


@fixture(scope='session')
def toolbox():
    return Toolbox()
