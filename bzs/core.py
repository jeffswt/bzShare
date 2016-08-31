
import socket
import threading
import tornado

import tornado.concurrent
import tornado.httputil
import tornado.httpserver
import tornado.gen
import tornado.ioloop
import tornado.process
import tornado.web

from bzs import const
from bzs import db
from bzs import files

from bzs import module_error404
from bzs import module_files
from bzs import module_home
from bzs import module_index
from bzs import module_static

WEB_PORT = 80

def main():
    # Creating web application
    web_app = tornado.web.Application([
            (r'^/$', module_index.MainframeHandler),
            (r'/static/.*', module_static.StaticHandler),
            # (r'/static/(.*)', tornado.web.StaticFileHandler, {
            #     "path": "./static/" # Optimized static file handler with cache
            # }),
            (r'^/home', module_home.HomeHandler),
            (r'^/files/?()$', module_files.FilesListHandler),
            (r'^/files/list/(.*)', module_files.FilesListHandler),
            (r'^/files/download/(.*)/(.*)/?$', module_files.FilesDownloadHandler),
            (r'^/files/upload/(.*)/(.*)$', module_files.FilesUploadHandler),
            (r'^/files/operation/?', module_files.FilesOperationHandler),
            (r'.*', module_error404.Error404Handler)
        ],
        xsrf_cookies=False # True to prevent CSRF third party attacks
    )
    # Starting server
    web_sockets = tornado.netutil.bind_sockets(
        const.get_const('server-port'),
        family=socket.AF_INET)
    if const.get_const('server-threads') > 1:
        if hasattr(os, 'fork'):
            # os.fork() operation unavailable on Windows.
            tornado.process.fork_processes(const.get_const('server-threads') - 1)
    web_server = tornado.httpserver.HTTPServer(web_app, xheaders=True)
    web_server.add_sockets(web_sockets)
    # Boot I/O thread for asynchronous purposes
    tornado.ioloop.IOLoop.instance().start()
    return
