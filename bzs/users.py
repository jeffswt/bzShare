
import pickle
import random
import base64

from . import utils
from . import db

class User:
    """A user that acts as a fundamental functional group in bzShare."""
    def __init__(self, handle=None, password=None, usergroups=None, usr_name=None, usr_description=None):
        # User handle, composed only of non-capital letters, numbers and underline,
        # While not exceeding the limit of 32-byte length
        self.handle          = handle or 'guest'
        # Password is defaultly set to blank.
        self.password        = password or ''
        # A group of usergroups that the user belongs to.
        self.usergroups      = usergroups or {'public'}
        # Cookies that are used to login.
        self.cookie          = None
        # IP Addresses that the user used to login.
        self.ip_addresses    = []
        # These are a set of user-defined options.
        self.usr_name        = usr_name or 'Guest'
        self.usr_description = usr_description or 'The guy who just wanders around.'
        self.usr_email       = ''
        # These are a great amount of social linkages.
        self.followers       = []
        self.friends         = []
        # Specify data indefinitely or load from pickle pls.
        return
    def save_data(self):
        bin_data = pickle.dumps(self)
        if not usr_db.execute("SELECT handle FROM users WHERE handle = %s;", (self.handle,)):
            usr_db.execute("INSERT INTO users (handle, users) VALUES (%s, %s);", (self.handle, bin_data))
        else:
            usr_db.execute("UPDATE users SET data = %s WHERE handle = %s;", (bin_data, self.handle))
        return
    def login(self):
        if not self.cookie:
            self.cookie = utils.get_new_cookie(users_cookies)
            users_cookies[self.cookie] = self.handle
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
    pass


users         = dict() # string -> User
users_cookies = dict() # string -> string(handle)
usergroups    = set() # string
usr_db        = None # Database


def add_user(n_usr):
    users[n_usr.handle] = n_usr
    if n_usr.cookie:
        users_cookies[n_usr.cookie] = n_usr.handle
    return

def add_usergroup(n_grp):
    usergroups.add(n_grp)
    usg_raw = pickle.dumps(usergroups)
    if not usr_db.execute("SELECT index FROM core WHERE index = %s;", (usg_raw,)):
        usr_db.execute("INSERT INTO core (index, data) VALUES (%s, %s)", ('usergroups', usg_raw))
    else:
        usr_db.execute("UPDATE core SET data = %s WHERE index = %s;", ('usg_raw', 'usergroups'))
    return

def load_db(database=None):
    """Loads user content and configurations from database."""
    if not database:
        raise AttributeError('Must provide a database')
    usr_db = database
    # Selecting usergroups
    item = usr_db.execute("SELECT index, data FROM core WHERE index = 'usergroups';")
    try:
        item = pickle.loads(item[0][1])
        usergroups = item # Uploaded.
    except:
        item = set()
        add_usergroup('public')
    # Done attribution, now selecting users
    for item in usr_db.execute("SELECT handle, data FROM users;"):
        handle, bin_data = item
        n_usr = pickle.loads(bin_data)
        # Injecting into index
        add_user(n_usr)
    # In case someone is missing... :)
    if 'guest' not in usr_db:
        n_usr = User()
        add_user(n_usr)
        n_usr.save_data()
    return True

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
