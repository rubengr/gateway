import re
import requests

try:
    import json
except ImportError:
    # This is the case when the plugin runtime is unittested
    import json


def _load_webinterface():
    """
    This method parses the webinterface sourcecode and parses all API calls that are available to the plugins.
    It uses this method to prevent the runtime from having to load the file and its dependencies.
    """
    import gateway
    def_regex = re.compile(r'^\s*?def ([^(]+)\((.*?)\):\s*$')
    with open('{0}/webservice.py'.format(gateway.__path__[0]), 'r') as source:
        contents = source.readlines()
    calls = {}
    found_call = False
    for line in contents:
        if found_call is True:
            # This line is a call definition and needs to be parsed/loaded
            match = def_regex.match(line)
            if match is not None:
                groups = match.groups()
                calls[groups[0]] = [argument.split('=')[0] for argument in groups[1].split(', ')
                                    if argument != 'self']
            found_call = False
        elif '@openmotics_api' in line and 'plugin_exposed=False' not in line:
            # This line is decorated, the next one is a call definition
            found_call = True
    return calls


class WebInterfaceDispatcher(object):
    # TODO: Use SDK in the future

    def __init__(self, logger, hostname='localhost', port=80):
        self.__logger = logger
        self.__hostname = hostname
        self.__port = port
        self.__warned = False
        self.__available_calls = _load_webinterface()

    def __getattr__(self, attribute):
        if attribute in self.__available_calls:
            wrapper = self.get_wrapper(attribute)
            setattr(self, attribute, wrapper)
            return wrapper
        raise AttributeError('The call \'{0}\' does not exist'.format(attribute))

    def warn(self):
        if self.__warned is False:
            self.__logger('[W] Deprecation warning:')
            self.__logger('[W] - Plugins should not pass \'token\' to API calls')
            self.__logger('[W] - Plugins should use keyword arguments for API calls')
            self.__warned = True

    def get_wrapper(self, name):
        params = self.__available_calls[name]

        def wrapper(*args, **kwargs):
            # 1. Try to remove a possible "token" parameter, which is now deprecated
            args = list(args)
            if 'token' in kwargs:
                del kwargs['token']
                self.warn()
            elif len(args) > 0:
                self.warn()
                if len(args) + len(kwargs) > len(params) or len(kwargs) == 0:
                    del args[0]
            # 2. Convert to kwargs, so it's possible to do parameter parsing
            for i in xrange(len(args)):
                kwargs[params[i]] = args[i]
            # 3. Make sure empty (`None` value) params are included
            for arg in kwargs:
                if kwargs[arg] is None:
                    kwargs[arg] = 'None'
            # 4. Perform the http call
            try:
                response = requests.get('http://{0}:{1}/{2}'.format(self.__hostname, self.__port, name),
                                        params=kwargs,
                                        timeout=30.0)
                return response.text
            except Exception:
                return json.dumps({'success': False,
                                   'msg': 'Call temporarily unavailable'})

        return wrapper
