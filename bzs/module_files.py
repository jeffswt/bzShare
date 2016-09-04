
import cgi
import io
import json
import re
import time
import tornado
import urllib

from . import const
from . import sqlfs
from . import users
from . import utils

################################################################################

class FilesListHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, target_path):
        """/files/list/HEXED_BASE64_STRING_OF_PATH/"""
        # Another concurrency blob...
        future = tornado.concurrent.Future()

        def get_final_html_async(target_path):
            # Getting file template.
            file_temp = utils.get_static_data('./static/files.html')
            working_user = users.get_user_by_cookie(
                self.get_cookie('user_active_login', default=''))

            # Retrieving list operation target.
            try:
                target_path = utils.decode_hexed_b64_to_str(target_path)
            except:
                target_path = '/'
            if not target_path:
                target_path = '/'

            # Getting hierarchical file path
            files_hierarchy = target_path.split('/')
            files_hierarchy_list = list()
            while '' in files_hierarchy:
                files_hierarchy.remove('')
            files_hierarchy = [''] + files_hierarchy
            files_hierarchy_cwd = ''
            for i in range(0, len(files_hierarchy)):
                files_hierarchy[i] += '/'
                files_hierarchy_cwd += files_hierarchy[i]
                files_hierarchy_list.append(dict(
                    folder_name=files_hierarchy[i],
                    href_path='/files/list/%s' % utils.encode_str_to_hexed_b64(files_hierarchy_cwd),
                    disabled=(i == len(files_hierarchy) - 1)))
                continue

            # Getting current directory permissions
            cwd_writable = sqlfs.writable(target_path, working_user)

            # Getting current directory content
            files_attrib_list = list()
            for f_handle in sqlfs.list_directory(target_path, user=working_user):
                try:
                    file_name = f_handle['file-name']
                    actual_path = target_path + file_name
                    attrib = dict()
                    attrib['file-name'] = file_name
                    attrib['file-name-url'] = urllib.parse.quote(file_name)
                    attrib['file-name-escaped'] = cgi.escape(file_name)
                    attrib['size'] = f_handle['file-size']
                    attrib['size-str'] = utils.format_file_size(attrib['size'])
                    attrib['date-uploaded'] = f_handle['upload-time']
                    attrib['date-uploaded-str'] = time.strftime(const.get_const('time-format'), time.localtime(attrib['date-uploaded']))
                    # Permissions
                    attrib['writable'] = f_handle['writable']
                    # Encoding owners
                    attrib['owners'] = list()
                    for ownr in f_handle['owners']:
                        attrib['owners'].append(users.get_name_by_id(ownr))
                    attrib['owners'] = ', '.join(attrib['owners'])
                    # Encoding MIME types
                    if f_handle['is-dir']:
                        attrib['mime-type'] = 'directory/folder'
                    else:
                        attrib['mime-type'] = utils.guess_mime_type(file_name)
                    # Encoding hyperlinks
                    if attrib['mime-type'] == 'directory/folder':
                        attrib['target-link'] = '/files/list/%s' % utils.encode_str_to_hexed_b64(actual_path + '/')
                    else:
                        attrib['target-link'] = '/files/download/%s/%s' % (utils.encode_str_to_hexed_b64(actual_path), attrib['file-name-url'])
                    attrib['preview-link'] = '/preview/view/%s' % utils.encode_str_to_hexed_b64(actual_path)
                    # Encoding UUID
                    attrib['uuid'] = utils.encode_str_to_hexed_b64(actual_path)
                    files_attrib_list.append(attrib)
                except Exception:
                    pass
            cwd_uuid = utils.encode_str_to_hexed_b64(files_hierarchy_cwd)

            # File actually exists, sending data
            file_temp = utils.preprocess_webpage(file_temp, working_user,
                files_attrib_list=files_attrib_list,
                files_hierarchy_list=files_hierarchy_list,
                cwd_uuid=cwd_uuid,
                cwd_writable=cwd_writable,
                xsrf_form_html=self.xsrf_form_html())
            future.set_result(file_temp)
        tornado.ioloop.IOLoop.instance().add_callback(get_final_html_async,
            target_path)
        file_temp = yield future

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_temp)))
        self.xsrf_form_html() # Prevent CSRF attacks

        # Push result to client in one blob
        self.write(file_temp)
        self.flush()
        self.finish()
        return

    head=get
    pass

################################################################################

class FilesDownloadHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, file_path, file_name):
        """/files/download/HEXED_BASE64_STRING_OF_PATH/ACTUAL_FILENAME"""
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # Get file location (exactly...)
        try:
            file_path = utils.decode_hexed_b64_to_str(file_path)
        except Exception:
            raise tornado.web.HTTPError(404)
        if not file_path:
            raise tornado.web.HTTPError(404)

        # Asynchronous web request...
        file_block_size = 64 * 1024 # 64 KiB / Chunk
        file_block = bytes()
        file_data = None

        future = tornado.concurrent.Future()
        def inquire_data_async(working_user):
            file_stream = sqlfs.get_content(file_path, user=working_user)
            future.set_result(file_stream)
        tornado.ioloop.IOLoop.instance().add_callback(
            inquire_data_async, working_user)
        file_stream = yield future

        # Detecting sent receival of ranges
        try:
            recv_range_str = re.sub('bytes=', '', self.request.headers['Range'])
            recv_range_tuple = recv_range_str.split('-')
            recv_range = int(recv_range_tuple[0])
        except:
            recv_range = 0

        if recv_range <= 0:
            self.set_status(200, "OK")
        else:
            self.set_status(206, "Partial Content")
        self.add_header('Accept-Ranges', 'bytes')
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'application/x-download')
        self.add_header('Content-Length', file_stream.length - recv_range)
        self.add_header('Content-Range', '%d-' % recv_range)

        file_stream.seek(recv_range, 0)
        while file_stream.tell() < file_stream.length:
            # Entry to the concurrency worker
            future = tornado.concurrent.Future()
            # Concurrent worker
            def retrieve_data_async():
                block = file_stream.read(file_block_size)
                future.set_result(block)
            # Injection and pending
            tornado.ioloop.IOLoop.instance().add_callback(retrieve_data_async)
            # Reset or read
            file_block = yield future
            self.write(file_block)
            self.flush()
        self.finish()

        # Release memory...
        file_stream = None
        file_data = None
        return

    pass

################################################################################

class FilesOperationHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self):
        """/files/operation/"""
        # Another concurrency blob...
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))
        future = tornado.concurrent.Future()

        def get_final_html_async(working_user):
            operation_content_raw = self.request.body
            operation_content = json.loads(operation_content_raw.decode('utf-8', 'ignore'))
            action = operation_content['action']
            sources = operation_content['source']
            if type(sources) == list:
                for i in range(0, len(sources)):
                    try:
                        sources[i] = utils.decode_hexed_b64_to_str(sources[i])
                    except:
                        pass
            else:
                sources = utils.decode_hexed_b64_to_str(sources)
            if action in ['copy', 'move']:
                try:
                    target = utils.decode_hexed_b64_to_str(operation_content['target'])
                except:
                    target = '/'
            elif action in ['rename', 'new-folder']:
                try:
                    target = operation_content['target']
                except:
                    target = sources # I am not handling more exceptions as this is brutal enough
            # Done assigning values, now attempting to perform operation
            if action == 'copy':
                for source in sources:
                    sqlfs.copy(source, target, user=working_user)
            elif action == 'move':
                for source in sources:
                    sqlfs.move(source, target, user=working_user)
            elif action == 'delete':
                for source in sources:
                    sqlfs.remove(source, user=working_user)
            elif action == 'rename':
                sqlfs.rename(sources, target, user=working_user)
            elif action == 'new-folder':
                sqlfs.create_directory(sources, target, user=working_user)
            future.set_result('')
        tornado.ioloop.IOLoop.instance().add_callback(
            get_final_html_async, working_user)
        file_temp = yield future

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_temp)))

        # Push result to client in one blob
        self.write(file_temp)
        self.flush()
        self.finish()
        return
    pass

################################################################################

@tornado.web.stream_request_body
class FilesUploadHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST']

    def prepare(self):
        """Creates file handle to write on."""
        content_length = self.request.headers['Content-Length']
        self.file_handle = sqlfs.create_file_handle(
            mode       = 'write',
            est_length = int(content_length)
        )
        # Done creating handle, proceeding.
        return

    def data_received(self, chunk):
        """Makes receival and push changes to handle."""
        self.file_handle.write(chunk)

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, target_path, file_name):
        """/files/upload/HEXED_BASE64_STRING_OF_PATH_OF_PARENT/ACTUAL_FILENAME"""
        # Another concurrency blob...
        future = tornado.concurrent.Future()
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        def save_file_async(alter_ego, target_path, file_name, working_user):
            self.file_handle.close()
            target_path = utils.decode_hexed_b64_to_str(target_path)
            # Committing changes to database
            sqlfs.create_file(target_path, file_name, self.file_handle, user=working_user)
            # Final return
            future.set_result('bzs_upload_success')
        tornado.ioloop.IOLoop.instance().add_callback(save_file_async,
            self, target_path, file_name, working_user)

        response_temp = yield future
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(response_temp)))

        # Push result to client in one blob
        self.write(response_temp)
        self.flush()
        self.finish()
        return
    pass
