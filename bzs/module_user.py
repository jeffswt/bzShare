
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
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
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
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
    pass

class UserAvatarHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, user_name):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def get_avatar_async(working_user, user_name):
            gt_user = users.get_user_by_name(user_name)
            if not gt_user.usr_avatar:
                file_data = ('image/png', utils.get_static_data('./static/dist/img/user-guest.png'))
            else:
                file_data = gt_user.usr_avatar
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_avatar_async, working_user, user_name)
        file_mime, file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', file_mime)
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, user_name):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        future = tornado.concurrent.Future()
        def post_avatar_async(working_user, user_name):
            gt_user = users.get_user_by_name(user_name)
            # Those should not be allowed...
            if working_user.handle != 'kernel' and (working_user.handle != gt_user.handle or gt_user.handle == 'guest'):
                raise tornado.web.HTTPError(403)
            img_data = self.request.body
            # If the length is 0, then it certainly means to delete the avatar
            if len(img_data) == 0:
                gt_user.usr_avatar = None
                gt_user.save_data()
            # Then we requires an update on avatar...
            else:
                # Image size should not be larger than 1 MB.
                if len(img_data) > 1 * 1024 * 1024:
                    raise tornado.web.HTTPError(403)
                # Too small indicates that it's not a valid image.
                if len(img_data) < 68: # 1px x 1px BMP image is the minimum
                    raise tornado.web.HTTPError(403)
                # Detecting MIME type
                img_mime_idx = {'image/png', 'image/bmp', 'image/jpeg', 'image/tiff'}
                content_type = self.request.headers['Content-Type']
                if content_type not in img_mime_idx:
                    raise tornado.web.HTTPError(403)
                # Updating to structure and database
                gt_user.usr_avatar = (content_type, img_data)
                gt_user.save_data()
                pass
            # Done and return values...
            future.set_result('')
        tornado.ioloop.IOLoop.instance().add_callback(
            post_avatar_async, working_user, user_name)
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
        return self
    pass
