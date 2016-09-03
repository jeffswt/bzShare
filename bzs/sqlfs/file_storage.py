
import hashlib
import io
import threading
import uuid as uuid_package

class FileStorage:
    """This is a storage system built for bzs.sqlfs.file_system.Filesystem,
    which handles files for Filesystem, large files directly use LOBJECT, and
    small / sparsed files use BYTEA. This could handle a great amount of files
    through manipulation of the SQL database without the loss of a great many
    rows. Sparse files should be disabled if server has no row limit."""

    class UniqueFile:
        """This is a virtual file node on a virtual filesystem SQLFS. The
        virtual file is designed to provide data for SQLFS nodes. Actual content
        are stored here instead of filesystem.

        A virtual node contains the following data:

            uuid         - The unique identifier of the file. Pointed by FS node
                           through the attribute f_uuid.
            size         - The file size, in bytes.
            count        - The occurences of this file in filesystem.
            hash         - The SHA256 hash of this file's content
            sparse_uuid  - If file is a sparsed file, then this indicates its
                           UUID in the sparsed file table.
            sparse_index - If file is in a sparsed row, then this indicated its
                           array subscript in the array of that row.

        Other data designed to maintain the content of the file includes:

            master   - The filesystem itself.

        Do process with caution, and use exported methods only.
        """

        uuid         = uuid_package.UUID('00000000-0000-0000-0000-000000000000')
        size         = 0
        count        = 0
        hash         = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        sparse_uuid  = None
        sparse_index = 0

        def __init__(self, uuid_=None, size=0, count=1, hash_=None, sparse_id=None, master=None):
            self.master = master
            self.uuid = master.utils_pkg.get_new_uuid(uuid_, self.master.st_uuid_idx)
            self.master.st_uuid_idx[self.uuid] = self
            self.size = size
            self.count = count # The number of references
            self.hash = hash_ # Either way... must specify this!
            self.master.st_hash_idx[self.hash] = self
            # If this item is sparsed, save the sparsed id as well.
            if sparse_id:
                self.sparse_uuid = sparse_id[0]
                self.sparse_index = sparse_id[1]
            else:
                self.sparse_uuid = None
                self.sparse_index = 0
            # Will not contain content, would be indexed in SQL.
            return
        pass

    def __init__(self, database=None, utils_package=None):
        """Loads index of all stored UniqueFiles in database."""
        if not database:
            raise AttributeError('Must provide a database')
        if not utils_package:
            raise AttributeError('Must provide bzShare utilites')
        self.st_uuid_idx         = dict()
        self.st_uuid_sparse_idx  = set()
        self.st_hash_idx         = dict()
        self.st_db               = database
        self.utils_pkg           = utils_package
        self.st_hash_algo        = hashlib.sha256 # Hashing algorithm, could be md5, sha1, sha224, sha256, sha384, sha512, while sha384 and sha512 are not recommended due to slow speeds on 32-bit computers
        self.st_sparse_limit     = 16 * 1024 * 1024 # Create new sparse row if sparse row exceeded 16 MB
        self.st_sparse_cnt_limit = 256 # No more than 256 files would appear in one sparse row
        self.st_sparse_size      = 2 * 1024 * 1024 # Files under 2 MB would be considered sparse
        # These are large files we are talking about.
        for item in self.st_db.execute("SELECT uuid, size, count, hash FROM file_storage;"):
            s_uuid, s_size, s_count, s_hash = item
            s_fl = self.UniqueFile(s_uuid, s_size, s_count, s_hash, master=self)
            # Inject into indexer
            self.st_uuid_idx[s_uuid] = s_fl
            self.st_hash_idx[s_hash] = s_fl
        # These are small / sparsed files we are talking about.
        for item in self.st_db.execute("SELECT uuid, sub_uuid, sub_size, sub_count, sub_hash FROM file_storage_sparse"):
            s_uuid, sub_uuid, sub_size, sub_count, sub_hash = item
            if s_uuid == uuid_package.UUID('00000000-0000-0000-0000-000000000000'):
                continue # This is a file marked unused, ignore this.
            sub_len = min(len(sub_uuid), len(sub_size), len(sub_count), len(sub_hash))
            for idx in range(0, sub_len):
                # Create sparsed file index
                s_fl = self.UniqueFile(sub_uuid[idx], sub_size[idx], sub_count[idx], sub_hash[idx], sparse_id=(s_uuid, idx + 1), master=self)
                # Inject into indexer
                self.st_uuid_idx[sub_uuid[idx]] = s_fl
                self.st_hash_idx[sub_hash[idx]] = s_fl
            # Means there is a sparse file called this
            self.st_uuid_sparse_idx.add(s_uuid)
            continue
        # Content would be ignored and later retrieved from SQL database.
        return

    def __new_unique_file_sparse(self, n_uuid, n_size, n_count, n_hash, content):
        """Creates a UniqueFile that is a sparsed file, which should be
        determined by upstream functions that it is indeed a sparsed file. Then
        we index this file in not large objects but direct raw strings. Returns
        the new file's UUID."""
        # Checking hash of the file.
        try:
            if n_hash in self.st_hash_idx:
                old_fl = self.st_hash_idx[n_hash]
                old_fl.count += 1
                self.st_db.execute("UPDATE file_storage_sparse SET sub_count[%s] = %s WHERE uuid = %s;", (old_fl.sparse_index, old_fl.count, old_fl.sparse_uuid))
                return old_fl.uuid
        except:
            pass
        # Hash not found or invalid.
        selection = self.st_db.execute("SELECT uuid, size, count FROM file_storage_sparse WHERE size < %s AND count < %s;", (self.st_sparse_limit, self.st_sparse_cnt_limit))
        f_uuid = None
        try:
            f_uuid, f_size, f_count = selection[0]
        except Exception: pass
        # In the case of having such an item that satisfies the limits, we insert.
        if f_uuid:
            # Attempt to discover unused chunk spaces in this sparse row
            try:
                unused_arr = self.st_db.execute("SELECT unused FROM file_storage_sparse WHERE uuid = %s;", (f_uuid,))[0][0] # At non-discovery (which is impossible) this would raise...
                unused_id = unused_arr[0] # At empty unused this would raise...
                # Create file in tree structure
                u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, sparse_id=(f_uuid, unused_id), master=self)
                self.st_db.execute("""
                    UPDATE file_storage_sparse SET
                            size = %s, count = %s,
                            sub_uuid[%s] = %s,
                            sub_size[%s] = %s,
                            sub_count[%s] = %s,
                            sub_hash[%s] = %s,
                            sub_content[%s] = %s,
                            unused = unused[2 : %s]
                        WHERE uuid = %s;""", (
                    f_size + n_size, f_count + 1,
                    unused_id, n_uuid,
                    unused_id, n_size,
                    unused_id, n_count,
                    unused_id, n_hash,
                    unused_id, content,
                    len(unused_arr), f_uuid
                ))
                pass
            except:
                # Create file in tree structure
                u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, sparse_id=(f_uuid, f_count + 1), master=self)
                # Indexing file in SQL database
                self.st_db.execute("""
                    UPDATE file_storage_sparse SET
                            size = %s, count = %s,
                            sub_uuid = array_cat(sub_uuid, %s),
                            sub_size = array_cat(sub_size, %s::BIGINT[]),
                            sub_count = array_cat(sub_count, %s::BIGINT[]),
                            sub_hash = array_cat(sub_hash, %s),
                            sub_content = array_cat(sub_content, %s)
                        WHERE uuid = %s;""", (
                    f_size + n_size, f_count + 1,
                    [n_uuid], [n_size], [n_count], [n_hash], [content],
                    f_uuid
                ))
                pass
            pass
        # In the case we need to create a new sparse row.
        else:
            f_uuid = self.utils_pkg.get_new_uuid(None, self.st_uuid_sparse_idx)
            self.st_uuid_sparse_idx.add(f_uuid)
            # Creating file in tree structure
            u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, sparse_id=(f_uuid, 1), master=self)
            # Creating new sparse row with content of this file in SQL database
            self.st_db.execute("""
                INSERT INTO file_storage_sparse
                        (uuid, size, count, sub_uuid, sub_size, sub_count, sub_hash, sub_content)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);""", (
                f_uuid, n_size, 1,
                [n_uuid], [n_size], [n_count], [n_hash], [content]
            ))
            pass
        # Inserting file handle into tree
        self.st_uuid_idx[n_uuid] = u_fl
        self.st_hash_idx[n_hash] = u_fl
        return n_uuid

    def __add_unique_file(self, uuid):
        if uuid not in self.st_uuid_idx:
            return False
        fl = self.st_uuid_idx[uuid]
        fl.count += 1
        if fl.sparse_uuid:
            self.st_db.execute("""
                UPDATE file_storage_sparse SET sub_count[%s] = %s WHERE uuid = %s""",
                (fl.sparse_index, fl.count, fl.sparse_uuid
            ))
        else:
            self.st_db.execute("""
                UPDATE file_storage SET count = %s WHERE uuid = %s""",
                (fl.count, fl.uuid
            ))
        return True

    def __new_unique_file(self, content):
        """Creates a UniqueFile, and returns its UUID."""
        n_uuid = self.utils_pkg.get_new_uuid(None, self.st_uuid_idx)
        n_size = len(content)
        n_count = 1
        n_hash = self.st_hash_algo(content).hexdigest()
        # If the size is too small, we sparse it
        if n_size < self.st_sparse_size:
            return self.__new_unique_file_sparse(n_uuid, n_size, n_count, n_hash, content)
        # Checking hash of the file.
        if n_hash in self.st_hash_idx:
            old_fl = self.st_hash_idx[n_hash]
            old_fl.count += 1
            self.st_db.execute("UPDATE file_storage SET count = %s WHERE uuid = %s;", (old_fl.count, old_fl.uuid))
            # We shall ignore the (1/2)**64 possibility of collisions...
            return old_fl.uuid
        # This is indeed a unique file that is large enough
        u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, master=self)
        # Done indexing, now proceeding to process content into SQL (RAW)
        with self.st_db.execute_raw() as db:
            with db.cursor() as cur:
                # Insert metadata only, for memory conservation
                cur.execute("INSERT INTO file_storage (uuid, size, count, hash, content) VALUES (%s, %s, %s, %s, lo_from_bytea(0, E'\\x'));", (n_uuid, n_size, n_count, n_hash))
                db.commit()
                # Select the last object we just inserted
                cur.execute("SELECT content FROM file_storage WHERE uuid = %s;", (n_uuid,))
                n_oid = cur.fetchone()[0] # Retrieved large object descriptor
                db.commit()
                # Making psycopg2.extensions.lobject (Large Object)
                n_lobj = db.lobject(n_oid, 'wb')
                # Writing changes to database object
                f_stream = io.BytesIO(content)
                chunk_size = 512 * 1024 # Chunk size of 64 KB
                # Continuously writing to target
                while True:
                    chunk = f_stream.read(chunk_size)
                    n_lobj.write(chunk)
                    if len(chunk) < chunk_size:
                        break
                n_lobj.close()
                f_stream.close()
                db.commit()
        # Injecting file into main indexer
        self.st_uuid_idx[n_uuid] = u_fl
        self.st_hash_idx[n_hash] = u_fl
        return n_uuid

    def __remove_unique_file_sparse(self, s_fl):
        """Removes a unique file, and if its appearances drop below 1 ( <= 0 ),
        remove the actual coincidence of this file and its content. Moreover,
        if the sparse row containing it has its count drop below 1 ( <= 0 )
        after deleting this file, we remove it as well."""
        # Decrement the count of the file by 1
        s_fl.count -= 1
        # Update the decrement in SQL database
        self.st_db.execute("UPDATE file_storage_sparse SET sub_count[%s] = %s WHERE uuid = %s;", (s_fl.sparse_index, s_fl.count, s_fl.sparse_uuid))
        # Check if this file needs to be deleted or not
        if s_fl.count >= 1:
            return True
        # Removing from filesystem
        del self.st_uuid_idx[s_fl.uuid]
        del self.st_hash_idx[s_fl.hash]
        # Retrieve details of this sparse row
        if s_fl.sparse_uuid not in self.st_uuid_sparse_idx:
            return False
        try:
            sp_uuid, sp_size, sp_count = self.st_db.execute("SELECT uuid, size, count FROM file_storage_sparse WHERE uuid = %s;", (s_fl.sparse_uuid,))[0]
            sp_size -= s_fl.size
            sp_count -= 1
        except: # There's really nothing I can do.
            return False
        # Remove this file from the sparse row
        self.st_db.execute("""
            UPDATE file_storage_sparse SET
                    size = %s, count = %s,
                    sub_uuid[%s] = '00000000-0000-0000-0000-000000000000',
                    sub_size[%s] = 0,
                    sub_count[%s] = 0,
                    sub_hash[%s] = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                    sub_content[%s] = E'\\x',
                    unused = array_cat(unused, %s::BIGINT[])
                WHERE uuid = %s;""", (sp_size, sp_count) +
            (s_fl.sparse_index,) * 5 + ([s_fl.sparse_index], s_fl.sparse_uuid)
        )
        # Now checking if we need to remove this row as well
        if sp_count >= 1:
            return True
        # Really, we need to delete it.
        self.st_db.execute("DELETE FROM file_storage_sparse WHERE uuid = %s;", (sp_uuid,))
        self.st_uuid_sparse_idx.remove(sp_uuid)
        # Done removing sparse file
        return True

    def __remove_unique_file(self, uuid_):
        """Removes a unique file, and if its appearances drop below 1 ( <= 0 ),
        remove the actual coincidence of this file and its content."""
        if uuid_ not in self.st_uuid_idx:
            return True
        s_fl = self.st_uuid_idx[uuid_]
        # If it's a sparse file, we call that function to delete it
        if s_fl.sparse_uuid:
            return self.__remove_unique_file_sparse(s_fl)
        # Now we are deleting a file large enough to fit in.
        s_fl.count -= 1
        self.st_db.execute("UPDATE file_storage SET count = %s WHERE uuid = %s;", (s_fl.count, s_fl.uuid))
        # Checking coincidence
        if s_fl.count >= 1:
            return True
        # Removing from filesystem
        del self.st_uuid_idx[s_fl.uuid]
        del self.st_hash_idx[s_fl.hash]
        # Removing from SQLDB
        s_arr = self.st_db.execute("SELECT content FROM file_storage WHERE uuid = %s;", (s_fl.uuid,), fetch_func='one')
        try:
            s_oid = s_arr[0]
        except:
            pass
        self.st_db.execute("SELECT lo_unlink(%s);", (s_oid,))
        self.st_db.execute("DELETE FROM file_storage WHERE uuid = %s;", (s_fl.uuid,))
        return True

    def __get_content_sparse(self, u_fl):
        """Retrieves content from file storage and returns the content in binary
        bytes. Consumes 8x memory per operation, but since it's a sparse file,
        it doesn't matter."""
        content = b''
        selection = self.st_db.execute("SELECT sub_content[%s] FROM file_storage_sparse WHERE uuid = %s;", (u_fl.sparse_index, u_fl.sparse_uuid))
        # Of course this writes easier...
        try: content = selection[0][0]
        except: content = b''
        return content

    def __get_content(self, uuid_):
        """Retrieves content from file storage and returns the content in binary
        bytes. Consumes 1x + 2 MB memory per operation."""
        try:
            u_fl = self.st_uuid_idx[uuid_]
        except Exception:
            return b''
        # If this is a sparse file, we call on subroutines to finish this
        if u_fl.sparse_uuid:
            return self.__get_content_sparse(u_fl)
        # Got file handle, now querying large file data
        content = b'' # Empty bytes, ready to write
        with self.st_db.execute_raw() as db:
            with db.cursor() as cur:
                # Insert metadata only, for memory conservation
                cur.execute("SELECT content FROM file_storage WHERE uuid = %s", (u_fl.uuid,))
                db.commit()
                try:
                    f_oid = cur.fetchone()[0] # Retrieved large object descriptor
                except: # Not in database
                    return b''
                db.commit()
                # Making psycopg2.extensions.lobject (Large Object)
                f_lobj = db.lobject(f_oid, 'rb')
                # Writing query results to result
                chunk_size = 2 * 1024 * 1024 # Chunk size of 2 MB
                # Continuously reading from target
                while True:
                    chunk = f_lobj.read(chunk_size)
                    content += chunk
                    if len(chunk) < chunk_size:
                        break
                f_lobj.close()
                db.commit()
        return content

    """Exported functions that are commonly available."""

    def add_unique_file(self, uuid):
        """Adds an occurence to this file."""
        ret_result = self.__add_unique_file(uuid)
        return ret_result

    def new_unique_file(self, content):
        """Creates a UniqueFile, and returns its UUID."""
        ret_result = self.__new_unique_file(content)
        return ret_result

    def remove_unique_file(self, uuid):
        """Removes a unique file, and if its appearances drop below 1 ( <= 0 ),
        remove the actual coincidence of this file and its content."""
        ret_result = self.__remove_unique_file(uuid)
        return ret_result

    def get_content(self, uuid):
        """Retrieves content from file storage and returns the content in binary
        bytes. Consumes 1x + 2 MB memory per operation."""
        ret_result = self.__get_content(uuid)
        return ret_result

    pass
