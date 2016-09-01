
import re
import tornado

from . import const
from . import utils

class Error404Handler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        try:
            file_data = utils.get_static_data('./static/404.html')
        except Exception:
            file_data = '404 Not Found'
        self.set_status(200, "OK")
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
