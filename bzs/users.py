
import pickle
import random
import base64

from . import const
from . import db
from . import utils
from . import sqlfs

class User:
    """A user that acts as a fundamental functional group in bzShare."""
    def __init__(self, handle=None, password=None, usergroups=None, usr_name=None, usr_description=None, master=None):
        self.master          = master # Parent
        # User handle, composed only of non-capital letters, numbers and underline,
        # While not exceeding the limit of 32-byte length
        self.handle          = handle or 'guest'
        # Password is defaultly set to blank.
        self.password        = password or ''
        # A group of usergroups that the user belongs to.
        self.usergroups      = usergroups or {'public'}
        # Cookies that are used to login.
        self.cookie          = None
        # These are a set of user-defined options.
        self.usr_name        = usr_name or 'Guest'
        self.usr_description = usr_description or 'The guy who just wanders around.'
        # Whether the user is banned.
        self.banned          = False
        # Specify data indefinitely or load from pickle pls.
        return
    def save_data(self):
        bin_data = pickle.dumps(self)
        if not self.master.usr_db.execute("SELECT handle FROM users WHERE handle = %s;", (self.handle,)):
            self.master.usr_db.execute("INSERT INTO users (handle, data) VALUES (%s, %s);", (self.handle, bin_data))
        else:
            self.master.usr_db.execute("UPDATE users SET data = %s WHERE handle = %s;", (bin_data, self.handle))
        return
    def login(self):
        if not self.cookie:
            self.cookie = utils.get_new_cookie(self.master.users_cookies)
            self.save_data()
        return self.cookie
    def logout(self):
        if self.cookie:
            self.cookie = None
            self.save_data()
        return
    pass

class Usergroup:
    """A usergroup that contains people from userspace / kernel."""
    def __init__(self, handle=None, admin=None, name=None, master=None):
        self.master  = master
        self.handle  = handle
        self.admin   = admin
        self.name    = name
        self.members = set()
        return
    def add_member(self, mem):
        if mem not in self.members:
            self.members.add(mem)
        return
    def remove_member(self, mem):
        if mem in self.members and mem != self.admin:
            self.members.remove(mem)
        return
    def save_data(self):
        bin_data = pickle.dumps(self)
        if not self.master.usr_db.execute("SELECT handle FROM usergroups WHERE handle = %s;", (self.handle,)):
            self.master.usr_db.execute("INSERT INTO usergroups (handle, data) VALUES (%s, %s);", (self.handle, bin_data))
        self.master.usr_db.execute("UPDATE usergroups SET data = %s WHERE handle = %s;", (bin_data, self.handle))
        return
    pass

class UserManagerType:
    def __init__(self, database=None):
        """Loads user content and configurations from database."""
        if not database:
            raise AttributeError('Must provide a database')
        self.users         = dict() # string -> User
        self.users_cookies = dict() # string -> string(handle)
        self.usergroups    = dict() # string -> string(name)
        self.usr_db        = database # Database
        # Selecting usergroups
        item = self.usr_db.execute("SELECT index, data FROM core WHERE index = 'usergroups';")
        try:
            item = pickle.loads(item[0][1])
            self.usergroups = item # Uploaded.
        except:
            item = set()
            self.add_usergroup('public', 'Public')
        # Done attribution, now selecting users
        for item in self.usr_db.execute("SELECT handle, data FROM users;"):
            handle, bin_data = item
            n_usr = pickle.loads(bin_data)
            # Injecting into index
            self.add_user(n_usr)
        # In case someone is missing... :)
        if 'guest' not in self.users:
            n_usr = User(master=self)
            self.add_user(n_usr)
            n_usr.save_data()
        # Adding superusers
        if 'kernel' not in self.users:
            n_usr = User(
                handle = 'kernel',
                password = const.get_const('server-admin-password'),
                usergroups = {'public'},
                usr_name = 'bzShare Kernel',
                usr_description = 'The core manager of bzShare.',
                master = self
            )
            self.add_user(n_usr)
            # This should never be inserted into server database.
        return

    def add_user(self, n_usr):
        self.users[n_usr.handle] = n_usr
        if n_usr.cookie:
            self.users_cookies[n_usr.cookie] = n_usr.handle
        return

    def add_usergroup(self, n_grp, grp_name):
        self.usergroups[n_grp] = grp_name
        usg_raw = pickle.dumps(self.usergroups)
        if not self.usr_db.execute("SELECT index FROM core WHERE index = %s;", ('usergroups',)):
            self.usr_db.execute("INSERT INTO core (index, data) VALUES (%s, %s)", ('usergroups', usg_raw))
        else:
            self.usr_db.execute("UPDATE core SET data = %s WHERE index = %s;", ('usg_raw', 'usergroups'))
        return

    def ban_user(self, handle, reason=''):
        usr = self.get_user_by_name(handle)
        if usr.handle == 'guest':
            return
        usr.banned = reason
        return

    def unban_user(self, handle):
        usr = self.get_user_by_name(handle)
        if usr.handle == 'guest':
            return
        usr.banned = False
        return

    def login_user(self, handle, password):
        usr = self.get_user_by_name(handle)
        if usr.handle == 'guest':
            raise Exception('Username or password incorrect.')
        if usr.password != password:
            raise Exception('Username or password incorrect.')
        if usr.banned != False:
            raise Exception('Access to the user had been banned by the server administrator, reason: "%s". Contact the server administrator to restore your account.' % user.banned)
        usr_cookie = usr.login()
        self.users_cookies[usr_cookie] = usr.handle
        return usr_cookie

    def logout_user(self, handle):
        usr = self.get_user_by_name(handle)
        if usr.handle == 'guest':
            return
        if usr.cookie in self.users_cookies:
            del self.users_cookies[usr.cookie]
        return usr.logout()

    def create_user_check_handle(self, usr_handle):
        if not utils.is_safe_string(usr_handle, 'letters_alpha', 'numbers'):
            raise Exception('User handle must be composed of non-capital letters and digits only.')
        if len(usr_handle) > 32 or len(usr_handle) < 3:
            raise Exception('User handle must has the length within the range of 3 letters to 32 letters.')
        if usr_handle in self.users:
            raise Exception('This user handle had already been used. Consider using another one.')
        return usr_handle

    def create_user_check_password(self, usr_password, usr_password_recheck):
        if not utils.is_safe_string(usr_password, 'letters', 'numbers', 'symbols'):
            raise Exception('Password must be composed of keys that can be retrieved directly from a QWERTY keyboard.')
        if len(usr_password) > 64 or len(usr_password) < 6:
            raise Exception('Password does not meet required length (6 letters to 64 letters)')
        if usr_password != usr_password_recheck:
            raise Exception('The two passwords you have typed in does not match.')
        return usr_password

    def create_user_check_username(self, usr_name):
        if utils.is_unsafe_string(usr_name, 'html_escape'):
            raise Exception('Your name should not contain HTML escape characters.')
        if len(usr_name) > 32:
            raise Exception('Your name should not exceed 32 characters.')
        return usr_name

    def create_user_check_description(self, usr_desc):
        if utils.is_unsafe_string(usr_desc, 'html_escape'):
            raise Exception('Your user description should not contain HTML escape characters.')
        if len(usr_desc) > 128:
            raise Exception('Your user description should not exceed 128 characters.')
        return usr_desc

    def create_user(self, json_data):
        try:
            usr_invitecode = json_data['invitecode']
            usr_handle = json_data['handle']
            usr_password = json_data['password']
            usr_password_recheck = json_data['passwordretype']
            usr_name = json_data['username']
            usr_desc = json_data['description']
        except:
            raise Exception('You have attempted to upload an incomplete form.')
        for i in [usr_invitecode, usr_handle, usr_password, usr_password_recheck, usr_name, usr_desc]:
            if type(i) != str:
                raise Exception('You have attempted to make an unsuccessful JSON exploit.')
        if usr_invitecode != const.get_const('users-invite-code'):
            raise Exception('Erroneous invitation code given, you are not authorized to access this functionality.')
        # Checking handle validity
        self.create_user_check_handle(usr_handle)
        # Checking password validity
        self.create_user_check_password(usr_password, usr_password_recheck)
        # Checking user name validity
        self.create_user_check_username(usr_name)
        # Checking description validity.
        self.create_user_check_description(usr_desc)
        # Creating user account
        usr = User(
            handle=usr_handle,
            password=usr_password,
            usr_name=usr_name,
            usr_description=usr_desc,
            master=self
        )
        usr.save_data()
        self.add_user(usr)
        # After creating account, assign folders for him.
        sqlfs.create_directory('/Users/', usr_handle)
        sqlfs.change_ownership('/Users/%s/' % usr_handle, {usr_handle})
        sqlfs.change_permissions('/Users/%s/' % usr_handle, 'rwx--x')
        return True

    def get_user_by_name(self, name):
        if name in self.users:
            return self.users[name]
        if 'guest' in self.users:
            return self.users['guest']
        # Must gurantee a user
        return self.User(master=self)

    def get_user_by_cookie(self, cookie):
        if cookie in self.users_cookies:
            return self.get_user_by_name(self.users_cookies[cookie])
        # The one who do not require a cookie to login.
        return self.get_user_by_name('guest')

    def get_name_by_id(self, n_id):
        if n_id in self.usergroups:
            return self.usergroups[n_id]
        return get_user_by_name(n_id).usr_name

UserManager = UserManagerType(
    database = db.Database
)

################################################################################
# Exported functions

def add_user(user):
    return UserManager.add_user(user)

def add_usergroup(usergroup, usergroup_name):
    return UserManager.add_usergroup(usergroup, usergroup_name)

def ban_user(handle, reason=''):
    return UserManager.ban_user(handle, reason)

def unban_user(handle):
    return UserManager.unban_user(handle)

def login_user(handle, password):
    return UserManager.login_user(handle, password)

def logout_user(handle):
    return UserManager.logout_user(handle)

def create_user(json_data):
    return UserManager.create_user(json_data)

def get_user_by_name(name):
    return UserManager.get_user_by_name(name)

def get_user_by_cookie(cookie):
    return UserManager.get_user_by_cookie(cookie)

def get_name_by_id(n_id):
    return UserManager.get_name_by_id(n_id)
