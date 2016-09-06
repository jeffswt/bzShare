
import re
import tornado

from . import const
from . import users
from . import utils

class HomeHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        # In case it does not exist.
        try:
            future = tornado.concurrent.Future()
            def get_index_html_async():
                file_data = utils.get_static_data('./static/home.html')
                working_user = users.get_user_by_cookie(
                    self.get_cookie('user_active_login', default=''))
                file_data = utils.preprocess_webpage(file_data, working_user)
                future.set_result(file_data)
            tornado.ioloop.IOLoop.instance().add_callback(get_index_html_async)
            file_data = yield future
        except Exception:
            raise tornado.web.HTTPError(404)

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
    pass
