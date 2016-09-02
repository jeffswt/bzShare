
import re
import tornado

from . import const
from . import users
from . import utils

class MainframeHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        try:
            future = tornado.concurrent.Future()
            def get_index_html_async(working_user):
                file_data = utils.get_static_data('./static/index.html')
                logged_in = working_user.handle != 'guest'
                file_data = utils.preprocess_webpage(file_data, working_user,
                    login_status=logged_in
                )
                future.set_result(file_data)
            tornado.ioloop.IOLoop.instance().add_callback(
                get_index_html_async, working_user)
            file_data = yield future
        except Exception:
            print(Exception)
            self.set_status(404, "Not Found")
            self.add_header('Content-Length', '0')
            self.flush()
            return None

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
    pass
