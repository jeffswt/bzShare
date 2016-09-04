
import io

from .. import db
from .. import utils

sparse_size = 2 * 1024 * 1024 # Files under 2 MB would be considered sparse

class FileStream:
    """A file stream handler used to work on both large and sparsed files."""

    def __init__(self, mode='read', est_length=1024**8, obj_oid=0, obj_data=b'', database=None):
        if not database:
            raise AttributeError('Must provide a database')
        self.db = database
        if (est_length <= sparse_size or len(obj_data) > 0) and obj_oid <= 0:
            # Create sparsed file
            self.content_data = obj_data
            self.content_obj = io.BytesIO(self.content_data) # Already seeked to begin
            self.mode = mode
            self.length = len(obj_data)
            self.is_sparse = True
        elif est_length > sparse_size:
            # Create large object
            self.content_conn = self.db.execute_raw()
            self.content_cur = self.content_conn.cursor()
            self.content_obj = self.content_conn.lobject(obj_oid, 'rb' if mode == 'read' else 'wb')
            self.content_oid = self.content_obj.oid
            self.mode = mode
            self.length = 0
            self.is_sparse = False
        self.est_length = est_length
        self.closed = False
        return

    def close(self):
        """close() -- close the file stream."""
        if self.closed:
            return
        if self.is_sparse:
            self.content_obj.seek(0, 0)
            self.content_data = self.content_obj.read()
            self.length = len(self.content_data)
            self.content_obj.close()
        else:
            self.length = self.size()
            # If original indicated as large file but now is sparsed file, destroy the original one and create BytesIO.
            if self.length < sparse_size:
                self.content_obj.seek(0, 0)
                self.content_data = self.content_obj.read()
                # Destroying lObject
                self.content_obj.unlink()
                self.content_conn.commit()
                self.content_cur.close()
                # Creating BytesIO
                del self.content_obj
                del self.content_conn
                del self.content_cur
                self.content_obj = io.BytesIO(self.content_data)
                self.is_sparse = True
                self.content_obj.close()
            else:
                self.content_obj.close()
                self.content_conn.commit()
                self.content_cur.close()
            pass
        del self.est_length
        self.closed = True
        return

    def reopen(self):
        """reopen() -- Reopen the file as reading mode."""
        if self.is_sparse:
            self.content_obj = io.BytesIO(self.content_data)
            self.est_length = len(self.content_data)
        else:
            self.content_conn = self.db.execute_raw()
            self.content_cur = self.content_conn.cursor()
            self.content_obj = self.content_conn.lobject(self.content_oid)
            self.est_length = self.length
        self.closed = False
        self.mode = 'read'
        self.content_obj.seek(0, 0)
        return

    def read(self, size=-1):
        """read(size=-1) -- Read at most size bytes or to the end of the file/"""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        if self.mode != 'read':
            return b''
        return self.content_obj.read(size)

    def seek(self, offset, whence=0):
        """seek(offset, whence=0) -- Set the file's current position."""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        if self.is_sparse:
            result = self.content_obj.seek(offset, whence)
        else:
            result = self.content_obj.seek(offset, whence)
        return result

    def tell(self):
        """tell() -- Return the file's current position."""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.content_obj.tell()

    def write(self, cont):
        """write(str) -- Write a string to the file."""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        if self.mode != 'write':
            return
        if self.tell() > self.est_length:
            raise Exception('Wrote more bytes than anticipated')
        if self.is_sparse:
            result = self.content_obj.write(cont)
        else:
            result = self.content_obj.write(cont)
            # self.content_conn.commit()
        self.length += len(cont)
        return result

    def size(self):
        """size() -- Returns the size of the file."""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        pos = self.tell()
        self.seek(0, 2)
        leng = self.tell()
        self.seek(pos, 0)
        return leng

    def destroy(self):
        """destroy() -- Remove entire content from database if is large file
        or do nothing but destroy the bytes record from database."""
        if self.closed:
            raise ValueError('I/O operation on closed file')
        if self.is_sparse:
            self.content_obj.close()
            self.content_data = None
        else:
            self.content_obj.unlink()
            self.content_conn.commit()
            self.content_cur.close()
        self.closed = True
        return

    def get_content(self):
        """get_content() -- Get entire content of file in bytes. If file is
        not sparsed, then the OID is returned."""
        if self.is_sparse:
            return self.content_data
        else:
            return self.content_oid
        raise MemoryError('Something terrible had happened')
    pass

EmptyFileStream = FileStream(
    mode='read',
    est_length=0,
    obj_data=b'',
    database=db.Database
)
EmptyFileStream.close()
