
import re
import tornado

from bzs import files
from bzs import const
from bzs import users
from bzs import preproc

class HomeHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        # In case it does not exist.
        try:
            future = tornado.concurrent.Future()
            def get_index_html_async():
                file_data = files.get_static_data('./static/home.html')
                working_user = users.get_user_by_cookie(
                    self.get_cookie('user_active_login', default=''))
                file_data = preproc.preprocess_webpage(file_data, working_user)
                future.set_result(file_data)
            tornado.ioloop.IOLoop.instance().add_callback(get_index_html_async)
            file_data = yield future
        except Exception:
            self.set_status(404, "Not Found")
            self._headers = tornado.httputil.HTTPHeaders()
            self.add_header('Content-Length', '0')
            self.flush()
            return None

        self.set_status(200, "OK")
        self._headers = tornado.httputil.HTTPHeaders()
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_data)))
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    head=get
    pass
