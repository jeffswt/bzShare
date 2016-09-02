
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
        # In case it does not exist.
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
            file_data = utils.preprocess_webpage(file_data, working_user)
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
        self.xsrf_form_html() # Prevent CSRF attacks

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
            inp_json = json.loads(self.request.body.decode('utf-8', 'ignore'))
            try: n_cookie = users.login_user(
                inp_json['handle'], inp_json['password'])
            except: n_cookie = None
            if not n_cookie:
                file_data = utils.get_static_data('./static/login_failure.html')
            else:
                self.set_cookie('user_active_login', n_cookie)
                file_data = utils.get_static_data('./static/login_success.html')
                working_user = users.get_user_by_cookie(n_cookie)
                print(working_user.handle)
            pass
        elif action_type == 'operation_logout':
            working_user.logout()
            self.set_cookies('user_active_login', '')
            pass
        elif action_type == 'operation_signup':
            inp_json = json.loads(self.request.body.decode('utf-8', 'ignore'))
            # file_data = utils.get_static_data('./static/signup_success.html')
            pass
        else:
            raise tornado.web.HTTPError(404)
        file_data = utils.preprocess_webpage(file_data, working_user)

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_data)))
        self.xsrf_form_html() # Prevent CSRF attacks

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
    pass
