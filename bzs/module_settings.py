
import json
import tornado

from . import const
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
    SUPPORTED_METHODS = ['POST']

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
                usr_password = req_data['password']
                usr_password_recheck = req_data['password-recheck']
                usr_name = req_data['username']
                usr_desc = req_data['description']
                # Done getting data, checking validity
                users.UserManager.create_user_check_password(usr_password, usr_password_recheck)
                users.UserManager.create_user_check_username(usr_name)
                users.UserManager.create_user_check_description(usr_desc)
                # Done validing, now modifying user
                this_user.password = usr_password
                this_user.usr_name = usr_name
                this_user.usr_description = usr_desc
                # Uploading to SQL database
                this_user.save_data()
                # Outputting successive information
                file_data = utils.get_static_data('./static/profile_edit_success.html')
                # Process webpage
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
            except Exception as err:
                err_data = str(err)
                print(err_data)
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
    pass

class UsergroupHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        future = tornado.concurrent.Future()
        def get_data_async(working_user):
            file_data = utils.get_static_data('./static/usergroups.html')
            # Demanding data
            current_user_groups = set()
            for nam in working_user.usergroups:
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
