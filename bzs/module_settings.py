
import json
import pickle
import tornado

from . import const
from . import db
from . import users
from . import utils

class ProfileHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, targ_user_name):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_data_async(working_user):
            file_data = utils.get_static_data('./static/profile.html')
            this_user = users.get_user_by_name(targ_user_name)
            # Either the kernel or the user himself would be able to edit profile
            this_user_editable = (this_user.handle == working_user.handle and this_user.handle != 'guest') or working_user.handle == 'kernel'
            # Process webpage
            file_data = utils.preprocess_webpage(file_data, working_user,
                this_user=this_user,
                this_user_editable=this_user_editable,
                xsrf_form_html=self.xsrf_form_html()
            )
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_data_async, working_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    head=get
    pass

class ProfileEditHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST', 'GET']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, targ_user_name):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))
        this_user = users.get_user_by_name(targ_user_name)

        future = tornado.concurrent.Future()
        def modify_user_async(working_user, this_user):
            # Retrieving JSON data from input
            try:
                req_data = json.loads(self.request.body.decode('utf-8', 'ignore'))
                if 'dropuser' not in req_data:
                    # Checking authority
                    if working_user.handle != 'kernel' and working_user.handle != this_user.handle:
                        raise Exception('You are unauthorized to perform this action.')
                    # Not dropping user, only modifying
                    usr_password = req_data['password']
                    usr_name = req_data['username']
                    usr_desc = req_data['description']
                    # Done getting data, checking validity
                    users.UserManager.create_user_check_username(usr_name)
                    users.UserManager.create_user_check_description(usr_desc)
                    # Done validing, now modifying user
                    if usr_password != utils.sha512_hex(''):
                        this_user.password = usr_password
                    this_user.usr_name = usr_name
                    this_user.usr_description = usr_desc
                    # Uploading to SQL database
                    this_user.save_data()
                    pass
                else:
                    if working_user.handle != 'kernel' and working_user.handle != this_user.handle:
                        raise Exception('You are unauthorized to perform this action.')
                    users.remove_user(this_user)
                    pass
                # Outputting successive information
                file_data = utils.get_static_data('./static/profile_edit_success.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
            except Exception as err:
                err_data = str(err)
                # Something wrong or inproper had happened
                file_data = utils.get_static_data('./static/profile_edit_failure.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    err_data=err_data,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            modify_user_async, working_user, this_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, targ_act):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_data_async(working_user, targ_act):
            targ_act = targ_act.split('+')
            try:
                if targ_act[0] == 'dropuser-prompt':
                    this_user = users.get_user_by_name(targ_act[1])
                    if working_user.handle != 'kernel' and working_user.handle != this_user.handle:
                        raise Exception('You are unauthorized to perform this action.')
                    # Outputting successive information
                    file_data = utils.get_static_data('./static/profile_remove_user_confirm.html')
                    # Process webpage
                    file_data = utils.preprocess_webpage(file_data, working_user,
                        this_user=this_user,
                        xsrf_form_html=self.xsrf_form_html()
                    )
                else:
                    raise Exception('Hitherto unbeknownst action invoked.')
            except Exception as err:
                err_data = str(err)
                # Something wrong or inproper had happened
                file_data = utils.get_static_data('./static/profile_edit_failure.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    err_data=err_data,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_data_async, working_user, targ_act)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return
    pass

class UsergroupHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_data_async(working_user):
            file_data = utils.get_static_data('./static/usergroups.html')
            # Demanding data
            current_user_groups = set()
            if working_user.handle != 'kernel':
                for nam in working_user.usergroups:
                    current_user_groups.add(
                        users.get_usergroup_by_name(nam).export_dynamic_usergroup()
                    )
            # Kernels have the right to allocate and view all configurations.
            else:
                for nam in users.UserManager.usergroups:
                    current_user_groups.add(
                        users.get_usergroup_by_name(nam).export_dynamic_usergroup()
                    )
            # Preprocessing page with given options
            file_data = utils.preprocess_webpage(file_data, working_user,
                current_user_groups=current_user_groups,
                xsrf_form_html=self.xsrf_form_html()
            )
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_data_async, working_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    head=get
    pass

class UsergroupEditHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST', 'GET']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, edit_method):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        future = tornado.concurrent.Future()
        def modify_data_async(working_user):
            try:
                req_func = edit_method.split('+')
                file_data = None
                if req_func[0] == 'create':
                    req_data = json.loads(self.request.body.decode('utf-8', 'ignore'))
                    grp_handle = req_data['handle']
                    grp_name = req_data['name']
                    users.create_usergroup(grp_handle, grp_name, working_user)
                elif req_func[0] == 'join':
                    req_data = json.loads(self.request.body.decode('utf-8', 'ignore'))
                    grp_handle = req_data['handle']
                    users.join_usergroup(grp_handle, working_user)
                elif req_func[0] in {'kick', 'accept', 'decline'}:
                    req_opt = req_func[0]
                    grp_handle = req_func[1]
                    usr_handle = req_func[2]
                    grp = users.get_usergroup_by_name(grp_handle)
                    if working_user.handle != 'kernel' and working_user.handle != grp.admin:
                        raise Exception('You are not authorized to perform this action.')
                    if req_opt == 'kick':
                        grp.remove_member(usr_handle)
                    elif req_opt == 'accept':
                        grp.accept_member(usr_handle)
                    elif req_opt == 'decline':
                        grp.decline_member(usr_handle)
                    else:
                        raise Exception('Hitherto unbeknownst action invoked.')
                    pass
                elif req_func[0] == 'dropgroup':
                    grp_handle = req_func[1]
                    grp = users.get_usergroup_by_name(grp_handle)
                    if working_user.handle != 'kernel' and working_user.handle != grp.admin:
                        raise Exception('You are not authorized to perform this action.')
                    users.remove_usergroup(grp)
                    pass
                elif req_func[0] == 'rename':
                    req_data = json.loads(self.request.body.decode('utf-8', 'ignore'))
                    grp_handle = req_func[1]
                    grp_name = req_data['name']
                    grp = users.get_usergroup_by_name(grp_handle)
                    if working_user.handle != 'kernel' and working_user.handle != grp.admin:
                        raise Exception('You are not authorized to perform this action.')
                    users.UserManager.create_usergroup_check_name(grp_name)
                    grp.name = grp_name
                    grp.save_data()
                    pass
                if not file_data:
                    file_data = utils.get_static_data('./static/usergroups_edit_success.html')
                    # Process webpage
                    file_data = utils.preprocess_webpage(file_data, working_user,
                        xsrf_form_html=self.xsrf_form_html()
                    )
                pass
            except Exception as err:
                err_data = str(err)
                # Something wrong or inproper had happened
                file_data = utils.get_static_data('./static/usergroups_edit_failure.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    err_data=err_data,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            modify_data_async, working_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, edit_method):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        future = tornado.concurrent.Future()
        def modify_data_async(working_user):
            try:
                req_func = edit_method.split('+')
                file_data = None
                if req_func[0] == 'dropgroup-prompt':
                    grp_handle = req_func[1]
                    grp = users.get_usergroup_by_name(grp_handle)
                    if working_user.handle != 'kernel' and working_user.handle != grp.admin:
                        raise Exception('You are not authorized to perform this action.')
                    file_data = utils.get_static_data('./static/usergroups_remove_group_confirm.html')
                    # Process webpage
                    file_data = utils.preprocess_webpage(file_data, working_user,
                        grp_handle=grp_handle,
                        xsrf_form_html=self.xsrf_form_html()
                    )
                    pass
                elif req_func[0] == 'rename-prompt':
                    grp_handle = req_func[1]
                    grp = users.get_usergroup_by_name(grp_handle)
                    if working_user.handle != 'kernel' and working_user.handle != grp.admin:
                        raise Exception('You are not authorized to perform this action.')
                    file_data = utils.get_static_data('./static/usergroups_rename.html')
                    # Process webpage
                    file_data = utils.preprocess_webpage(file_data, working_user,
                        grp_handle=grp.handle,
                        grp_name=grp.name,
                        xsrf_form_html=self.xsrf_form_html()
                    )
                    pass
                if not file_data:
                    file_data = utils.get_static_data('./static/usergroups_edit_success.html')
                    # Process webpage
                    file_data = utils.preprocess_webpage(file_data, working_user,
                        xsrf_form_html=self.xsrf_form_html()
                    )
                pass
            except Exception as err:
                err_data = str(err)
                # Something wrong or inproper had happened
                file_data = utils.get_static_data('./static/usergroups_edit_failure.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    err_data=err_data,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            modify_data_async, working_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return
    pass

class DynamicInterfaceHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_data_async(working_user):
            if working_user.handle != 'kernel':
                raise tornado.web.HTTPError(403)
            file_data = utils.get_static_data('./static/dynamic_interface.html')
            try:
                home_data = pickle.loads(db.Database.execute("SELECT data FROM core WHERE index = %s;", ('dynamic_interface_home',))[0][0])
            except:
                home_data = utils.get_static_data('./static/home.html')
            if type(home_data) == bytes:
                home_data = home_data.decode('utf-8', 'ignore')
            file_data = utils.preprocess_webpage(file_data, working_user,
                home_data=home_data,
                xsrf_form_html=self.xsrf_form_html()
            )
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_data_async, working_user)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, target):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def set_data_async(working_user, target):
            if working_user.handle != 'kernel':
                raise tornado.web.HTTPError(403)
            upload_data = pickle.dumps(self.request.body)
            if target == 'home-data':
                if self.request.body == b'<!-- RESET -->':
                    db.Database.execute("DELETE FROM core WHERE index = %s;", ('dynamic_interface_home',))
                else:
                    if db.Database.execute("SELECT index FROM core WHERE index = %s;", ('dynamic_interface_home',)):
                        db.Database.execute("UPDATE core SET data = %s WHERE index = %s;", (upload_data, 'dynamic_interface_home'))
                    else:
                        db.Database.execute("INSERT INTO core (index, data) VALUES (%s, %s);", ('dynamic_interface_home', upload_data))
                    pass
                pass
            else:
                raise tornado.web.HTTPError(403)
            future.set_result('')
        tornado.ioloop.IOLoop.instance().add_callback(
            set_data_async, working_user, target)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', '0')

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return

    pass
