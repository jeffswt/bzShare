
import re
import tornado
import urllib

from . import const
from . import users
from . import utils
from . import sqlfs

class PreviewHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, mode, file_hash):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        future = tornado.concurrent.Future()
        def get_index_html_async(working_user, file_hash):
            # Determine file path and file type
            # try:
            import binascii
            print(binascii.unhexlify(file_hash))
            file_path = utils.decode_hexed_b64_to_str(file_hash)
            file_name = sqlfs.get_file_name(file_path)
            file_mime = utils.guess_mime_type(file_name)

            # Sorting according to MIME type
            if file_mime == 'application/pdf':
                # PDF document
                if mode == 'view':
                    file_data = utils.get_static_data('./static/preview_pdf.html')
                else:
                    file_data = utils.get_static_data('./static/pdfjs/viewer.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_name_url=urllib.parse.quote(file_name),
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            elif file_mime == 'text/plain':
                # Plain text
                file_data = 'something'
                pass
            else:
                # None of the provided has been detected
                file_data = utils.get_static_data('./static/preview_none.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_index_html_async, working_user, file_hash)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    head=get
    pass
