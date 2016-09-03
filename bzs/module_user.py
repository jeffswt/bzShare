
import json
import re
import tornado

from . import const
from . import users
from . import utils

class UserActivityHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD', 'POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, action_type):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_index_html_async(working_user, action_type):
            if action_type == 'login':
                file_data = utils.get_static_data('./static/login.html')
                pass
            elif action_type == 'signup':
                file_data = utils.get_static_data('./static/signup.html')
                pass
            else:
                file_data = ''
            file_data = utils.preprocess_webpage(file_data, working_user,
                xsrf_form_html=self.xsrf_form_html()
            )
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_index_html_async, working_user, action_type)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    head=get
    def post(self, action_type):
        # In case it does not exist.
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        if action_type == 'operation_login':
            try:
                inp_json = json.loads(self.request.body.decode('utf-8', 'ignore'))
                n_cookie = users.login_user(inp_json['handle'], inp_json['password'])
                self.set_cookie('user_active_login', n_cookie)
                working_user = users.get_user_by_cookie(n_cookie)
                file_data = utils.get_static_data('./static/login_success.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
            except Exception as err:
                n_cookie = None
                err_data = str(err)
                file_data = utils.get_static_data('./static/login_failure.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html(),
                    err_data=err_data
                )
            pass
        elif action_type == 'operation_logout':
            users.logout_user(working_user.handle)
            self.set_cookie('user_active_login', '')
            file_data = ''
            pass
        elif action_type == 'operation_signup':
            try:
                inp_json = json.loads(self.request.body.decode('utf-8', 'ignore'))
                users.create_user(inp_json)
                file_data = utils.get_static_data('./static/signup_success.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
            except Exception as err:
                err_data = str(err)
                file_data = utils.get_static_data('./static/signup_failure.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html(),
                    err_data = err_data
                )
            pass
        else:
            raise tornado.web.HTTPError(404)

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
    pass
