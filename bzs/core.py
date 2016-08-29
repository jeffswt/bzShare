
import socket
import threading
import tornado

import tornado.concurrent
import tornado.httputil
import tornado.gen
import tornado.ioloop
import tornado.web

from bzs import files
# from bzs import db

from bzs import module_error404
from bzs import module_files
from bzs import module_home
from bzs import module_index
from bzs import module_static

WEB_PORT = 80

def main():
    # Booting and listening
    tornado.web.Application([
        (r'^/$', module_index.MainframeHandler),
        # (r'/static/.*', module_static.StaticHandler),
        (r'/static/(.*)', tornado.web.StaticFileHandler, {
            "path": "./static/" # Optimized static file handler with cache
        }),
        (r'^/home', module_home.HomeHandler),
        (r'^/files/?()$', module_files.FilesListHandler),
        (r'^/files/list/(.*)', module_files.FilesListHandler),
        (r'^/files/download/(.*)/(.*)/?$', module_files.FilesDownloadHandler),
        (r'^/files/upload/(.*)/(.*)$', module_files.FilesUploadHandler),
        (r'^/files/operation/?', module_files.FilesOperationHandler),
        (r'.*', module_error404.Error404Handler)
    ]).listen(WEB_PORT)
    # Boot I/O thread for asynchronous purposes
    global ioloop
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.start()
    return
