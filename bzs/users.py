
import pickle
import random
import base64

def gen_cookie():
    cookie = ''
    while cookie in users_cookies:
        cookie = str(random.randrange(0, 10**32))
        cookie = base64.b64encode(cookie.encode('utf-8', 'ignore')).decode('utf-8', 'ignore')
    return cookie

class User:
    def __init__(self):
        # User handle, composed only of non-capital letters, numbers and underline,
        # While not exceeding the limit of 32-byte length
        self.handle = 'guest'
        # Password is defaultly set to blank.
        self.password = ''
        # A group of usergroups that the user belongs to.
        self.usergroups = {'Guests'}
        # Cookies that are used to login.
        self.cookie = None
        # IP Addresses that the user used to login.
        self.ip_addresses = []
        # Events / Social activities, specified in `class Event` only.
        self.events = []
        # These are a set of user-defined options.
        self.usr_name = 'Guest'
        self.usr_description = 'The guy who just wanders around.'
        self.usr_email = ''
        # These are a great amount of social linkages.
        self.followers = []
        self.friends = []
        # Specify data indefinitely or load from pickle pls.
        return

    def export_data(self):
        return pickle.dumps(self)

    def import_data(self, source):
        self = pickle.loads(source)
        return

    def set_handle(self, _handle):
        self.handle = _handle
        return

    def set_password(self, _password):
        self.password = _password
        return

    def add_usergroup(self, _usergroup):
        if _usergroup not in self.usergroups:
            self.usergroups.add(_usergroup)
        return

    def login_cookie(self):
        if not self.cookie:
            self.cookie = gen_cookie()
            users_cookies[self.cookie] = self.username
        return self.cookie

    def logout(self):
        if self.cookie:
            del users_cookies[self.cookie]
            self.cookie = None
        return

    def add_ip_address(self, _ip):
        self.ip_addresses.append(_ip)
        self.ip_addresses = self.ip_addresses[:16]
        return

    def add_event(self, _event):
        # FIXME: not right!
        self.events.append(_event)
        return


users = dict() # string -> User
users_cookies = dict() # string -> string
usergroups = set() # string


def get_user_by_name(name):
    if name in users:
        return users[name]
    if 'guest' in users:
        return users['guest']
    # Must gurantee a user
    return User()


def get_user_by_cookie(cookie):
    if cookie in users:
        return get_user_by_name(users_cookies[cookie])
    # The one who do not require a cookie to login.
    return get_user_by_name('guest')
