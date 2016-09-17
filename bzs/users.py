
import pickle
import random
import base64

from . import const
from . import db
from . import utils
from . import sqlfs

class User:
    """ A user that acts as a fundamental functional group in bzShare. """
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
        self.usr_avatar      = None
        # Whether the user is banned.
        self.banned          = False
        # Specify data indefinitely or load from pickle pls.
        return
    def save_data(self):
        tmp_master = self.master
        del self.master
        bin_data = pickle.dumps(self)
        self.master = tmp_master
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
    """ A usergroup that contains people from userspace / kernel. """
    def __init__(self, handle=None, admin=None, name=None, master=None):
        self.master  = master
        self.handle  = handle
        self.admin   = admin
        self.name    = name
        self.members = set() # Already-existent members
        self.invited = set() # Those under invitation from the administrator
        self.joining = set() # Those who are pending to join
        return
    def add_member(self, mem):
        if type(mem) != str:
            mem = mem.handle
        if mem not in self.members:
            self.members.add(mem)
        return
    def remove_member(self, mem):
        if type(mem) != str:
            mem = mem.handle
        mem = self.master.get_user_by_name(mem)
        if mem.handle == self.admin:
            raise Exception('Cannot kick the administrator of the group.')
        if mem.handle not in self.members:
            return
        self.members.remove(mem.handle)
        self.save_data()
        mem.save_data()
        return
    def accept_member(self, mem):
        if type(mem) != str:
            mem = mem.handle
        mem = self.master.get_user_by_name(mem)
        mem.usergroups.add(self.handle)
        self.members.add(mem.handle)
        self.joining.remove(mem.handle)
        self.save_data()
        mem.save_data()
        return
    def decline_member(self, mem):
        if type(mem) != str:
            mem = mem.handle
        if mem in self.joining:
            self.joining.remove(mem)
        self.save_data()
        return
    def export_dynamic_usergroup(self):
        """This returns a dynamic usergroup that has references to other objects
        of the set()s without needing direct queries to the user unit. """
        class UsergroupDynamic:
            def __lt__(self, value):
                return self.handle < value.handle
            pass
        new = UsergroupDynamic()
        new.handle = self.handle
        new.admin = self.admin
        new.name = self.name
        new.members = set()
        new.joining = set()
        new.allowed_edit = set()
        for orig_st, new_st in [(self.members, new.members), (self.joining, new.joining)]:
            for i in orig_st:
                new_st.add(self.master.get_user_by_name(i))
        if self.handle != 'public':
            new.allowed_edit = {'kernel', self.admin}
        return new
    def save_data(self):
        tmp_master = self.master
        del self.master
        bin_data = pickle.dumps(self)
        self.master = tmp_master
        if not self.master.usr_db.execute("SELECT handle FROM usergroups WHERE handle = %s;", (self.handle,)):
            self.master.usr_db.execute("INSERT INTO usergroups (handle, data) VALUES (%s, %s);", (self.handle, bin_data))
        else:
            self.master.usr_db.execute("UPDATE usergroups SET data = %s WHERE handle = %s;", (bin_data, self.handle))
        return
    pass

class UserManagerType:
    def __init__(self, database=None):
        """ Loads user content and configurations from database. """
        if not database:
            raise AttributeError('Must provide a database')
        self.users         = dict() # string -> User
        self.users_cookies = dict() # string -> string(handle)
        self.usergroups    = dict() # string -> Usergroup
        self.usr_db        = database # Database
        # Done attribution, now selecting users
        for item in self.usr_db.execute("SELECT handle, data FROM users;"):
            handle, bin_data = item
            n_usr = pickle.loads(bin_data)
            n_usr.master = self
            # Injecting into index
            self.add_user(n_usr, raw_insert=True)
        # In case someone is missing... :)
        if 'guest' not in self.users:
            n_usr = User(master=self)
            self.add_user(n_usr, raw_insert=True)
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
            self.add_user(n_usr, raw_insert=True)
            # Inject into database.
            n_usr.save_data()
        # Now selecting usergroups
        for item in self.usr_db.execute("SELECT handle, data FROM usergroups;"):
            handle, bin_data = item
            n_grp = pickle.loads(bin_data)
            n_grp.master = self
            # Injecting into index
            self.add_usergroup(n_grp)
        # Adding public usergroup, in case it's not available
        if 'public' not in self.usergroups:
            n_grp = Usergroup(
                handle = 'public',
                admin = 'kernel',
                name = 'Public',
                master = self
            )
            # Must contain all users
            for usr in self.users:
                n_grp.add_member(usr)
            # Insert into memory and database
            self.add_usergroup(n_grp)
            n_grp.save_data()
        return

    def add_user(self, n_usr, raw_insert=False):
        self.users[n_usr.handle] = n_usr
        if n_usr.cookie:
            self.users_cookies[n_usr.cookie] = n_usr.handle
        if not raw_insert:
            self.get_usergroup_by_name('public').add_member(n_usr)
        return

    def add_usergroup(self, n_grp):
        self.usergroups[n_grp.handle] = n_grp
        return

    def remove_user(self, usr):
        if type(usr) == str:
            usr = self.get_user_by_name(usr)
        if usr.handle in {'guest', 'kernel'}:
            raise Exception('Cannot remove system users')
        # Remove from structure and database
        if usr.cookie:
            del self.users_cookies[usr.cookie]
        del self.users[usr.handle]
        self.usr_db.execute("DELETE FROM users WHERE handle = %s;", (usr.handle,))
        # Unlink usergroups
        for rm_grp in usr.usergroups:
            rm_grp = self.get_usergroup_by_name(rm_grp)
            if usr.handle == rm_grp.admin:
                self.remove_usergroup(rm_grp)
            else:
                rm_grp.remove_member(usr.handle)
                rm_grp.save_data()
            pass
        # Expunge user's personal data
        sqlfs.remove('/Users/%s/' % usr.handle)
        sqlfs.expunge_user_ownership(usr.handle)
        return

    def remove_usergroup(self, grp):
        if type(grp) == str:
            grp = self.get_usergroup_by_name(grp)
        if grp.handle in {'public'}:
            raise Exception('Cannot remove system usergroups')
        # Unlink users
        for rm_usr_nm in grp.members:
            rm_usr = self.get_user_by_name(rm_usr_nm)
            rm_usr.usergroups.remove(grp.handle)
            rm_usr.save_data()
        # Removing usergroup from database
        self.usr_db.execute("DELETE FROM usergroups WHERE handle = %s;", (grp.handle,))
        del self.usergroups[grp.handle]
        # Expunge usergroup's data
        sqlfs.remove('/Groups/%s/' % grp.handle)
        sqlfs.expunge_user_ownership(grp.handle)
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
        if usr_handle in self.users or usr_handle in self.usergroups:
            raise Exception('This user handle had already been used. Consider using another one.')
        return usr_handle

    def create_user_check_password(self, usr_password, usr_password_recheck, usr_handle):
        if not utils.is_safe_string(usr_password, 'letters', 'numbers', 'symbols'):
            raise Exception('Password must be composed of keys that can be retrieved directly from a QWERTY keyboard.')
        if usr_password != usr_password_recheck:
            raise Exception('The two passwords you have typed in does not match.')
        if usr_handle != 'guest':
            if len(usr_password) > 64 or len(usr_password) < 6:
                raise Exception('Password does not meet required length (6 letters to 64 letters)')
        return usr_password

    def create_user_check_username(self, usr_name):
        if utils.is_unsafe_string(usr_name, 'html_escape'):
            raise Exception('Your name should not contain HTML escape characters.')
        if len(usr_name) < 3:
            raise Exception('Your name should not be shorter than 3 characters.')
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
        self.create_user_check_password(usr_password, usr_password_recheck, usr_handle)
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
        self.usergroups['public'].members.add(usr.handle)
        self.usergroups['public'].save_data()
        self.add_user(usr)
        usr.save_data()
        # After creating account, assign folders for him.
        sqlfs.create_directory('/Users/', usr_handle)
        sqlfs.change_ownership('/Users/%s/' % usr_handle, usr_handle)
        sqlfs.change_permissions('/Users/%s/' % usr_handle, {'':'--x--x',usr_handle:'rwxrwx'})
        return True

    def create_usergroup_check_handle(self, grp_handle):
        if not utils.is_safe_string(grp_handle, 'letters_alpha', 'numbers'):
            raise Exception('Usergroup handle must be composed of non-capital letters and digits only.')
        if len(grp_handle) > 32 or len(grp_handle) < 3:
            raise Exception('Usergroup handle must has the length within the range of 3 letters to 32 letters.')
        if grp_handle in self.usergroups or grp_handle in self.users:
            raise Exception('This usergroup handle had already been used. Consider using another one.')
        return grp_handle

    def create_usergroup_check_name(self, grp_name):
        if utils.is_unsafe_string(grp_name, 'html_escape'):
            raise Exception('The name should not contain HTML escape characters.')
        if len(grp_name) < 3:
            raise Exception('The name should not be shorter than 3 characters.')
        if len(grp_name) > 32:
            raise Exception('The name should not exceed 32 characters.')
        return grp_name

    def create_usergroup(self, grp_handle, grp_name, creator):
        self.create_usergroup_check_handle(grp_handle)
        self.create_usergroup_check_name(grp_name)
        # Checked name validity, now checking authenticity
        is_admin_cnt = 0
        for gp_nm in creator.usergroups:
            gp_hn = self.usergroups[gp_nm]
            if creator.handle == gp_hn.admin:
                is_admin_cnt += 1
        if is_admin_cnt >= const.get_const('users-max-groups-allowed') and creator.handle != 'kernel':
            raise Exception('You have created too many usergroups (>= %d).' % const.get_const('users-max-groups-allowed'))
        # Checking who created this
        if creator.handle == 'guest':
            raise Exception('Guest accounts are not allowed to create usergroups.')
        # Creating new usergroup
        n_grp = Usergroup(
            handle=grp_handle,
            name=grp_name,
            admin=creator.handle,
            master=self
        )
        n_grp.add_member(creator.handle)
        creator.usergroups.add(n_grp.handle)
        self.add_usergroup(n_grp)
        n_grp.save_data()
        creator.save_data()
        # After creating group, assign folders for it.
        sqlfs.create_directory('/Groups/', grp_handle)
        sqlfs.change_ownership('/Groups/%s/' % grp_handle, grp_handle)
        sqlfs.change_permissions('/Groups/%s/' % grp_handle, {'':'--x--x',grp_handle:'rw-r-x',n_grp.admin:'rwxrwx'})
        return True

    def join_usergroup(self, grp_handle, joiner):
        grp = self.get_usergroup_by_name(grp_handle)
        if joiner.handle in grp.members:
            raise Exception('You are already an active member of this group.')
        if joiner.handle in grp.joining:
            raise Exception('You have already sent a join request to this group.')
        if joiner.handle == 'guest':
            raise Exception('Guests are not allowed to join usergroups.')
        grp.joining.add(joiner.handle)
        grp.save_data()
        joiner.save_data()
        return

    def select_member(self, handles, user):
        """ Select the most appropriate handle in handles that match handle's
        ownership or permissions. """
        for h in handles:
            if user == h:
                return h
        for h in handles:
            if h not in self.usergroups:
                continue
            if user in self.get_usergroup_by_name(h).members:
                return h
        if 'public' in handles:
            return 'public'
        if 'guest' in handles:
            return 'guest'
        return ''

    def get_user_by_name(self, name):
        if name in self.users:
            return self.users[name]
        # If not, then it's a vulnerability that needed to be caught
        return self.users['guest']

    def get_user_by_cookie(self, cookie):
        if cookie in self.users_cookies:
            usr = self.get_user_by_name(self.users_cookies[cookie])
            if not usr.banned:
                return usr
        # The one who do not require a cookie to login.
        return self.get_user_by_name('guest')

    def get_usergroup_by_name(self, name):
        if name in self.usergroups:
            return self.usergroups[name]
        # If not, then it's strange...
        raise Exception('The inquired usergroup "%s" did not exist.' % name)

    def get_name_by_id(self, n_id):
        if n_id in self.usergroups:
            return self.usergroups[n_id].name
        return get_user_by_name(n_id).usr_name

UserManager = UserManagerType(
    database = db.Database
)

################################################################################
# Exported functions

def add_user(user, raw_insert=False):
    return UserManager.add_user(user, raw_insert)

def add_usergroup(usergroup, usergroup_name):
    return UserManager.add_usergroup(usergroup, usergroup_name)

def remove_user(handle):
    return UserManager.remove_user(handle)

def remove_usergroup(handle):
    return UserManager.remove_usergroup(handle)

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

def create_usergroup(handle, name, creator):
    return UserManager.create_usergroup(handle, name, creator)

def join_usergroup(handle, joiner):
    return UserManager.join_usergroup(handle, joiner)

def select_member(handles, user):
    return UserManager.select_member(handles, user)

def get_user_by_name(name):
    return UserManager.get_user_by_name(name)

def get_user_by_cookie(cookie):
    return UserManager.get_user_by_cookie(cookie)

def get_usergroup_by_name(name):
    return UserManager.get_usergroup_by_name(name)

def get_name_by_id(n_id):
    return UserManager.get_name_by_id(n_id)
