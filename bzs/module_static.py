
import socket
import threading
import tornado
import re

import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.gen
import tornado.httputil
from tornado.concurrent import run_on_executor

from bzs import files
from bzs import const

class StaticHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        file_path = re.sub(r'^/static/', './static/', self.request.uri)

        # In case it does not exist.
        try:
            file_data = files.get_static_data(file_path)
        except Exception:
            self.set_status(404, "Not Found")
            self._headers = tornado.httputil.HTTPHeaders()
            self.add_header('Content-Length', '0')
            self.flush()
            return None

        # File actually exists, sending data
        self.set_status(200, "OK")
        self._headers = tornado.httputil.HTTPHeaders()
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', files.guess_mime_type(file_path))
        self.add_header('Content-Length', str(len(file_data)))
        self.add_header('Server', const.get_const('server-name'))
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    head=get
    pass
