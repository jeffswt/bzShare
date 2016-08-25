

import socket
import threading
import tornado

import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.gen
import tornado.httputil
from tornado.concurrent import run_on_executor

from bzs import files

from bzs import mainframe
from bzs import staticfile
from bzs import home

WEB_PORT = 80

def main():
    tornado.web.Application([
        (r'^/$', mainframe.MainframeHandler),
        (r'/static/.*', staticfile.StaticHandler),
        (r'^/home', home.HomeHandler)
        # (r'.*', error404.Error404Handler),
    ]).listen(WEB_PORT)
    global ioloop
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.start()

    return
