
import copy
import hashlib
import io
import re
import time
import uuid

from bzs import db
from bzs import utils

################################################################################

class FileStorageType:
    st_uuid_idx = dict()
    st_uuid_sparse_idx = set()
    st_hash_idx = dict()
    # Database entry
    st_db = db.Database
    # Hashing algorithm, could be md5, sha1, sha224, sha256, sha384, sha512
    # sha384 and sha512 are not recommended due to slow speeds on 32-bit computers
    st_hash_algo = hashlib.sha256
    # Limit for sparsed file detection, should not be too big for the sake of performance
    st_sparse_limit = 16 * 1024 * 1024 # Create new sparse row if sparse row exceeded 16 MB
    st_sparse_cnt_limit = 256 # No more than 256 files would appear in one sparse row
    st_sparse_size = 2 * 1024 * 1024 # Files under 2 MB would be considered sparse

    class UniqueFile:
        def __init__(self, uuid_=None, size=0, count=1, hash_=None, sparse_id=None, master=None):
            self.master = master
            self.uuid = utils.get_new_uuid(uuid_, self.master.st_uuid_idx)
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

    def __init__(self, db=db.Database):
        return self.load_sql(db)

    def load_sql(self, db=db.Database):
        """Loads index of all stored UniqueFiles in database."""
        self.st_db = db
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

    def new_unique_file_sparse(self, n_uuid, n_size, n_count, n_hash, content):
        """Creates a UniqueFile that is a sparsed file, which should be
        determined by upstream functions that it is indeed a sparsed file. Then
        we index this file in not large objects but direct raw strings. Returns
        the new file's UUID."""
        # Checking hash of the file.
        print('Creating sparse file %d' % n_size)
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
            # Create file in tree structure
            u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, sparse_id=(f_uuid, f_count + 1), master=self)
            # Indexing file in SQL database
            self.st_db.execute("""
                UPDATE file_storage_sparse SET
                        size = %s, count = %s,
                        sub_uuid = array_cat(sub_uuid, %s),
                        sub_size = array_cat(sub_size, %s::bigint[]),
                        sub_count = array_cat(sub_count, %s::bigint[]),
                        sub_hash = array_cat(sub_hash, %s),
                        sub_content = array_cat(sub_content, %s)
                    WHERE uuid = %s;""", (
                f_size + n_size, f_count + 1,
                [n_uuid], [n_size], [n_count], [n_hash], [content],
                f_uuid
            ))
            pass
        # In the case we need to create a new sparse row.
        else:
            f_uuid = utils.get_new_uuid(None, self.st_uuid_sparse_idx)
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

    def new_unique_file(self, content):
        """Creates a UniqueFile, and returns its UUID."""
        n_uuid = utils.get_new_uuid(None, self.st_uuid_idx)
        n_size = len(content)
        n_count = 1
        n_hash = self.st_hash_algo(content).hexdigest()
        # If the size is too small, we sparse it
        if n_size < self.st_sparse_size:
            return self.new_unique_file_sparse(n_uuid, n_size, n_count, n_hash, content)
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

    def remove_unique_file_sparse(self, s_fl):
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
            sp_count = sp_count - 1
        except: # There's really nothing I can do.
            return False
        # Remove this file from the sparse row
        self.st_db.execute("""
            UPDATE file_storage_sparse SET
                    size = %s, count = %s,
                    sub_uuid = array_cat(sub_uuid[0 : %s], sub_uuid[%s : %s]),
                    sub_size = array_cat(sub_size[0 : %s], sub_size[%s : %s]),
                    sub_count = array_cat(sub_count[0 : %s], sub_count[%s : %s]),
                    sub_hash = array_cat(sub_hash[0 : %s], sub_hash[%s : %s]),
                    sub_content = array_cat(sub_content[0 : %s], sub_content[%s : %s])
                WHERE uuid = %s;""", (sp_size - s_fl.size, sp_count) + (
            s_fl.sparse_index - 1, s_fl.sparse_index + 1, sp_count + 2
        ) * 5 + (sp_uuid,))
        # After removal the index of all other files must have changed representation in the tree...
        try:
            results = self.st_db.execute("SELECT sub_uuid FROM file_storage_sparse WHERE uuid = %s;", (sp_uuid,))[0][0]
            for idx in range(0, len(results)):
                sub_uuid = results[idx]
                try: sub_fl = self.st_uuid_idx[sub_uuid]
                except: continue
                sub_fl.sparse_uuid = sp_uuid
                sub_fl.sparse_index = idx + 1
        except:
            return False
        # Now checking if we need to remove this row as well
        if sp_count >= 1:
            return True
        # Really, we need to delete it.
        self.st_db.execute("DELETE FROM file_storage_sparse WHERE uuid = %s;", (sp_uuid,))
        self.st_uuid_sparse_idx.remove(sp_uuid)
        # Done removing sparse file
        return True

    def remove_unique_file(self, uuid_):
        """Removes a unique file, and if its appearances drop below 1 ( <= 0 ),
        remove the actual coincidence of this file and its content."""
        if uuid_ not in self.st_uuid_idx:
            return True
        s_fl = self.st_uuid_idx[uuid_]
        # If it's a sparse file, we call that function to delete it
        if s_fl.sparse_uuid:
            return self.remove_unique_file_sparse(s_fl)
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

    def get_content_sparse(self, u_fl):
        """Retrieves content from file storage and returns the content in binary
        bytes. Consumes 8x memory per operation, but since it's a sparse file,
        it doesn't matter."""
        content = b''
        selection = self.st_db.execute("SELECT sub_content[%s] FROM file_storage_sparse WHERE uuid = %s;", (u_fl.sparse_index, u_fl.sparse_uuid))
        # Of course this writes easier...
        try: content = selection[0][0]
        except: content = b''
        return content

    def get_content(self, uuid_):
        """Retrieves content from file storage and returns the content in binary
        bytes. Consumes 1x + 2 MB memory per operation."""
        try:
            u_fl = self.st_uuid_idx[uuid_]
        except Exception:
            return b''
        # If this is a sparse file, we call on subroutines to finish this
        if u_fl.sparse_uuid:
            return self.get_content_sparse(u_fl)
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
    pass

FileStorage = FileStorageType()

################################################################################

class FilesystemType:
    """This is a virtual filesystem based on a relational PostgreSQL database.
    We might call it a SQLFS. Its tree-topological structure enables it to index
    files and find siblings quickly. Yet without the B-Tree optimization it
    would not be easy to maintain a high performance.
    """
    fs_uuid_idx = dict()
    fs_root = None
    fs_db = None

    class fsNode:
        """This is a virtual node on a virtual filesystem SQLFS. The virtual
        node contains the following data:

            uuid        - The unique identifier: if node is a directory, then
                          this uuid would be the identifier pointing to the
                          directory; if node is a file, this identifier would be
                          pointing to the UUID among the actual files instead of
                          the filesystem.
            is_dir      - Whether is a directory or not
            filename    - The actual file / directory name given by the user
            upload_time - The time uploaded / copied / moved to server
            f_uuid      - If a file them this indicates its FileStorage UUID.

        Other data designed to maintain the structure of the node includes:

            master        - The filesystem itself.
            sub_folder    - Removed after filesystem init, temporary use only.
            sub_files     - Removed after filesystem init, temporary use only.
            sub_items     - Set of children.
            sub_names_idx - Dictionary of children indexed by name.

        Do process with caution, and use exported methods only.
        """

        def __init__(self, is_dir, file_name, owner, uuid_=None, upload_time=None, sub_folders=set(), sub_files=set(), f_uuid=None, master=None):
            # The filesystem / master of the node
            self.master = master
            # Assigning data
            self.is_dir = is_dir
            self.file_name = file_name
            self.owner = owner
            # Generate Universally Unique Identifier
            self.uuid = utils.get_new_uuid(uuid_, master.fs_uuid_idx)
            master.fs_uuid_idx[self.uuid] = self
            # Get upload time
            self.upload_time = upload_time or utils.get_current_time()
            if not self.is_dir:
                self.sub_folders = set()
                self.sub_files = set()
                self.f_uuid = f_uuid
            else:
                # Folder initialization needs to be accounted after init as whole by the main caller
                self.sub_folders = sub_folders # Temporary
                self.sub_files = sub_files # Temporary
            # This is a traversal thing...
            self.parent = None
            self.sub_items = set()
            self.sub_names_idx = dict()
            return
        pass

    def __init__(self, db=db.Database):
        return self.load_sqlfs(db)

    def load_sqlfs(self, db=db.Database):
        self.fs_db = db
        for item in self.fs_db.execute("SELECT uuid, file_name, owner, upload_time, sub_folders, sub_files FROM file_system"):
            # Splitting tuple into parts
            uuid_, file_name, owner, upload_time, sub_folders, sub_files = item
            # Getting sub files which are expensive stored separately
            n_sub_files = set()
            for fil_idx in sub_files:
                # This is where the order goes, BEAWARE
                s_uuid = fil_idx[0]
                s_file_name = fil_idx[1]
                s_owner = set(fil_idx[2].split(';'))
                try:
                    s_upload_time = float(fil_idx[3])
                except:
                    s_upload_time = utils.get_current_time()
                s_f_uuid = uuid.UUID(fil_idx[4])
                if s_f_uuid not in FileStorage.st_uuid_idx:
                    continue
                # Pushing...
                s_file = self.fsNode(False, s_file_name, s_owner, s_uuid, s_upload_time, f_uuid=s_f_uuid, master=self)
                n_sub_files.add(s_file)
                self.fs_uuid_idx[s_uuid] = s_file
            # Getting sub folders as a set but not templating them
            n_sub_folders = set() # Since reference is passed, should not manipulate this further
            for fol_idx in sub_folders:
                n_sub_folders.add(fol_idx)
            fold_elem = self.fsNode(True, file_name, set(owner), uuid_, upload_time, n_sub_folders, n_sub_files, master=self)
            self.fs_uuid_idx[uuid_] = fold_elem
        # Done importing from SQL database, now attempting to refurbish connexions
        for uuid_ in self.fs_uuid_idx:
            item = self.fs_uuid_idx[uuid_]
            if not item.is_dir:
                continue
            # Asserted that it was a folder.
            for n_sub in item.sub_files:
                item.sub_items.add(n_sub)
                item.sub_names_idx[n_sub.file_name] = n_sub
            for n_sub_uuid in item.sub_folders:
                try:
                    n_sub = self.fs_uuid_idx[n_sub_uuid]
                    item.sub_items.add(n_sub)
                    item.sub_names_idx[n_sub.file_name] = n_sub
                except Exception:
                    pass
            del item.sub_files
            del item.sub_folders
        # Fixing parental occlusions
        def iterate_fsnode(node):
            for item in node.sub_items:
                if item.parent:
                    continue
                # Never iterated before
                item.parent = node
                iterate_fsnode(item)
            return
        for uuid_ in self.fs_uuid_idx: # This would fix all nodes...
            item = self.fs_uuid_idx[uuid_]
            iterate_fsnode(item)
        # Finding root and finishing parent connexions
        for uuid_ in self.fs_uuid_idx: # Takes the first element that ever occured to me
            item = self.fs_uuid_idx[uuid_]
            while item.parent:
                item = item.parent
            self.fs_root = item
            break
        else:
            self.make_root()
        # Traversing root for filename indexing
        def iterate_node_fn(node):
            for item in node.sub_items:
                node.sub_names_idx[item.file_name]
        # All done, finished initialization
        return

    def _sqlify_fsnode(self, item):
        """Turns a node into SQL-compatible node."""
        n_uuid = item.uuid
        n_file_name = item.file_name
        n_owner = list(item.owner)
        n_upload_time = item.upload_time
        n_sub_folders = list()
        n_sub_files = list()
        for i_sub in item.sub_items:
            if i_sub.is_dir:
                n_sub_folders.append(i_sub.uuid)
            else:
                n_sub_files.append([
                    str(i_sub.uuid),
                    str(i_sub.file_name),
                    ';'.join(i_sub.owner),
                    "%f" % i_sub.upload_time,
                    str(i_sub.f_uuid)
                ])
        # Formatting string
        return (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files)

    def _update_in_db(self, item):
        """Push updating commit to Database for changes. Does not affect
        nonexistent nodes in Database. Otherwise please use _insert_in_db().

        Operation would not be redirected to insertion because of recursive
        risks that could potentially damage and overflow the process."""
        # This applies to items in the
        # We assert that item should be Node.
        if type(item) == str:
            item = self.locate(item)
        if not item:
            return False
        # Giving a few but crucial assertions...
        if not item.is_dir:
            item = item.parent
            if not item.is_dir:
                return False # I should raise, by a matter of fact
        # Collecting data
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files = self._sqlify_fsnode(item)
        # Uploading / committing data
        if not self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return False # You already stated this is an updating operation!
        self.fs_db.execute("UPDATE file_system SET file_name = %s, owner = %s, upload_time = %s, sub_folders = %s, sub_files = %s WHERE uuid = %s;", (n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files, n_uuid))
        return True

    def _insert_in_db(self, item):
        """Create filesystem record of directory 'item' inside database. You
        should not insert something that already existed. However:

        We have had a precaution for this. Update operations would be taken
        automatically instead."""
        if not item.is_dir:
            return False # Must be directory...
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files = self._sqlify_fsnode(item)
        # Uploading / committing data
        if self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return self._update_in_db(item) # Existed, updating instead.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES (%s, %s, %s, %s, %s, %s);", (n_uuid, n_file_name, list(n_owner), n_upload_time, n_sub_folders, n_sub_files))
        return

    def make_root(self):
        item = self.fsNode(True, '', {'kernel'}, master=self)
        del item.sub_files
        del item.sub_folders
        item.sub_items = set()
        item.parent = None
        # Done generation, inserting.
        self.fs_root = item
        self.fs_uuid_idx[item.uuid] = item
        # Inserting to SQL.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES (%s, %s, %s, %s, %s, %s);", (item.uuid, item.file_name, list(item.owner), item.upload_time, [], []))
        return

    def locate(self, path, parent=None):
        """Locate the fsNode() of the location 'path'. If 'parent' is given and
        as it should be a fsNode(), the function look to the nodes directly
        under this, non-recursively."""
        # On the case it is a referring location, path should be str.
        if parent:
            try:
                item = parent.sub_names_idx[path]
            except Exception:
                return None
            return item
        # And it is not such a location.
        # We assert that path should be list().
        if type(path) == str:
            path = path.split('/')
            while '' in path:
                path.remove('')
        # Now got array, traversing...
        item = self.fs_root
        while path:
            try:
                item = item.sub_names_idx[path[0]]
            except Exception:
                return None # This object does not exist.
            path = path[1:]
        # Guranteed correctness.
        return item

    def is_child(self, node, parent):
        while node:
            if node == parent:
                return True
            node = node.parent
        return False

    def make_nice_filename(self, file_name):
        """Create a HTML-friendly file name that does not support and does not
        allow cross site scripting (XSS)."""
        file_name = re.sub(r'[\\/*<>?`\'"|]', r'', file_name)
        return file_name

    def resolve_conflict(self, file_name, parent):
        """Rename 'file_name' if necessary in order to make operations
        successful in case of confliction that disrupts the SQLFS. The renamed
        file / folder should be named like this:

        New Text Document.txt
        New Text Document (2).txt
        New Text Document (3).txt

        Et cetera."""
        if type(parent) == str:
            parent = self.locate(parent)
        if not parent:
            return file_name
        # File path assertion complete, attempting to resolve.
        if file_name not in parent.sub_names_idx:
            return file_name
        # There must have been a conflict.
        if '.' in file_name:
            f_name = re.sub(r'^(.*)\.(.*?)$', r'\1', file_name)
            f_suffix = '.' + re.sub(r'^(.*)\.(.*?)$', r'\2', file_name)
        else:
            f_name = file_name
            f_suffix = ''
        for i in range(2, 10**18):
            n_fn = '%s (%d)%s' % (f_name, i, f_suffix)
            if n_fn not in parent.sub_names_idx:
                return n_fn
        # This should never happen!
        return file_name

    def mkfile(self, path_parent, file_name, owner, content):
        """Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.make_nice_filename(file_name)
        file_name = self.resolve_conflict(file_name, path_parent)
        # Finished assertion.
        n_uuid = FileStorage.new_unique_file(content)
        n_fl = self.fsNode(False, file_name, owner, f_uuid=n_uuid, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def mkdir(self, path_parent, file_name, owner):
        """Inject folder into filesystem."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.make_nice_filename(file_name)
        file_name = self.resolve_conflict(file_name, path_parent)
        # Creating new node.
        n_fl = self.fsNode(True, file_name, owner, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        self._insert_in_db(n_fl)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def listdir(self, path):
        """Creates a list of files in the directory 'path'. Attributes of the returned
        result contains:

            file-name   - File name
            file-size   - File size
            is-dir      - Whether is directory
            owner       - The handle of the owner
            upload-time - Time uploaded, in float since epoch.

        The result should always be a list, and please index it with your own
        habits or modify the code."""
        if type(path) == str:
            path = self.locate(path)
            if not path:
                return []
        # List directory, given the list(dict()) result...
        dirs = list()
        for item in path.sub_items:
            attrib = dict()
            try:
                attrib['file-name'] = item.file_name
                attrib['file-size'] = 0 if item.is_dir else FileStorage.st_uuid_idx[item.f_uuid].size
                attrib['is-dir'] = item.is_dir
                attrib['owner'] = item.owner
                attrib['upload-time'] = item.upload_time
            except:
                continue
            dirs.append(attrib)
        # Give the results to downstream
        return dirs

    def get_content(self, item):
        """Gets binary content of the object (must be file) and returns the
        actual content in bytes."""
        if type(item) == str:
            item = self.locate(item)
        if not item:
            return b''
        if item.is_dir:
            item = None
            return b''
        return FileStorage.get_content(item.f_uuid)

    def _copy_recursive(self, item, target_par, new_owner):
        """Copies content of a single object and recursively call all its
        children for recursive copy, targeted as a child under target_par."""
        # We assert item, target_par are all fsNode().
        target_node = target_par.sub_names_idx[item.file_name]
        for i_sub in item.sub_items:
            i_sub.parent = item
            item.sub_names_idx[i_sub.file_name] = i_sub
            self._copy_recursive(i_sub, target_node, new_owner)
        # Insert into SQL database
        item.uuid = utils.get_new_uuid(None, self.fs_uuid_idx)
        self.fs_uuid_idx[item.uuid] = item
        item.upload_time = utils.get_current_time()
        if new_owner:
            item.owner = new_owner # Assignment
        if item.is_dir:
            self._insert_in_db(item)
        return

    def copy(self, source, target_parent, new_owner=None):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination can be the
        same as source folder. If rename required please call the related
        functions separatedly."""
        if type(source) == str:
            source = self.locate(source)
        if type(target_parent) == str:
            target_parent = self.locate(target_parent)
        if not source or not target_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.make_nice_filename(source.file_name)
        file_name = self.resolve_conflict(file_name, target_parent)
        # Done assertion, now proceed with deep copy
        target = copy.deepcopy(source)
        # Assigning and finishing tree connexions
        target.file_name = file_name
        target.parent = target_parent
        target_parent.sub_items.add(target)
        target_parent.sub_names_idx[target.file_name] = target
        self._copy_recursive(target, target_parent, new_owner)
        # Update target_parent data and return
        self._update_in_db(target_parent)
        return True

    def move(self, source, target_parent):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination should not
        at all be the same as source folder, otherwise operation would not be
        executed."""
        if type(source) == str:
            source = self.locate(source)
        if type(target_parent) == str:
            target_parent = self.locate(target_parent)
        if not source or not target_parent:
            return False
        # It should not move itself to itself.
        if source.parent == target_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.make_nice_filename(source.file_name)
        file_name = self.resolve_conflict(file_name, target_parent)
        source.file_name = file_name
        # Moving an re-assigning tree structures
        par = source.parent
        par.sub_items.remove(source)
        del par.sub_names_idx[source.file_name]
        source.parent = target_parent
        target_parent.sub_items.add(source)
        target_parent.sub_names_idx[source.file_name] = source
        # Updating SQL database.
        self._update_in_db(par)
        self._update_in_db(target_parent)
        return

    def _remove_recursive(self, item):
        """Removes content of a single object and recursively call all its
        children for recursive removal."""
        # We assert item is fsNode().
        # Remove recursively.
        for i_sub in item.sub_items:
            self._remove_recursive(i_sub)
        # Delete itself from filesystem.
        del self.fs_uuid_idx[item.uuid]
        # Delete itself from SQL database.
        self.fs_db.execute("DELETE FROM file_system WHERE uuid = %s;", (item.uuid,))
        # Also delete occurence if is file.
        if not item.is_dir:
            FileStorage.remove_unique_file(item.f_uuid)
        return

    def remove(self, path):
        """Removes (recursively) all content of the folder / file itself and
        all its subdirectories."""
        if type(path) == str:
            path = self.locate(path)
        if not path:
            return False
        # Done assertion, path is now fsNode().
        par = path.parent
        self._remove_recursive(path)
        if par:
            par.sub_items.remove(path)
            del par.sub_names_idx[path.file_name]
            self._update_in_db(par)
        # There always should be a root.
        if path == self.fs_root:
            self.make_root()
        # Done removal.
        return True

    def rename(self, item, file_name):
        """Renames object 'item' into file_name."""
        if type(item) == str:
            item = self.locate(item)
            if not item:
                return False
        if not item.parent:
            return False # How can you rename a root?
        # Resolving conflict and nicing file name.
        file_name = self.make_nice_filename(file_name)
        file_name = self.resolve_conflict(file_name, item.parent)
        # Actually deleting
        del item.parent.sub_names_idx[item.file_name]
        item.file_name = file_name
        item.parent.sub_names_idx[item.file_name] = item
        if item.is_dir:
            self._update_in_db(item)
        self._update_in_db(item.parent) # At least there is a parent
        return True

    def chown(self, item, owner):
        """Assign owner of 'item' to new owner, recursively."""
        if type(item) == str:
            item = self.locate(item)
        if not item:
            return False
        def _chown_recursive(item_, owner_):
            for sub_ in item_.sub_items:
                _chown_recursive(sub_, owner_)
            item_.owner = owner_
            if item_.is_dir:
                self._update_in_db(item_)
            return
        _chown_recursive(item, owner)
        if not item.is_dir:
            self._update_in_db(item.parent)
        return True

    def shell(self):
        """Interactive shell for manipulating SQLFS. May be integrated into
        other utilites in the (far) futuure. Possible commands are:

            db command     - Execute 'command' in Database.
            ls             - List content of current directory.
            cat name       - View binary content of the object 'name'.
            cd             - Change CWD into the given directory, must be
                             relative. Or use '..' to go to parent directory.
            chown src usr  - Change ownership recursively of 'src' to 'usr'.
            rename src nam - Rename file / folder 'src' to 'nam'.
            mkdir name     - Make directory of 'name' under this directory.
            mkfile name dt - Make empty file of 'name' under this directory. If
                             'dt' is specified, then its content would not be
                             empty instead of the specified data.
            rm name        - Remove (recursively) object of 'name' under this
                             directory.
            cp src dest    - Copy object 'src' to under 'dest' as destination.
            mv src dest    - Move object 'src' to under 'dest' as destination.
            exit           - Exit shell.

        This shell should not be used in production as is not safe."""
        cwd = self.fs_root
        cuser = {'kernel'}
        cwd_list = ['']
        while True:
            cwd_fl = ''.join((i + '/') for i in cwd_list)
            print('%s@%s %s$ ' % (self.fs_db.connect_params['user'], self.fs_db.connect_params['database'], cwd_fl), end='')
            cmd_input = input()
            cmd = cmd_input.split(' ')
            op = cmd[0]
            if op == 'db':
                db_cmd = cmd_input.split(' ', 1)[1] or ''
                res = self.fs_db.execute(db_cmd)
                print(res)
            elif op == 'ls':
                res = self.listdir(cwd)
                # Prettify the result
                print('Owner       Upload Time         Size            Filename            ')
                print('--------------------------------------------------------------------')
                for item in res:
                    print('%s%s%s%s' % (str(item['owner']).ljust(12), str(int(item['upload-time'])).ljust(20), str(item['file-size'] if not item['is-dir'] else '').ljust(16), item['file-name']))
                print('Total: %d' % len(res))
                print('')
            elif op == 'cat':
                dest = self.locate(cmd[1], parent=cwd)
                print(bytes(self.get_content(dest)))
            elif op == 'cd':
                if cmd[1] == '..':
                    cwd_dest = cwd.parent
                    if cwd_dest:
                        cwd = cwd_dest
                        cwd_list = cwd_list[:-1]
                else:
                    try:
                        cwd_dest = cwd.sub_names_idx[cmd[1]]
                        if cwd_dest:
                            cwd = cwd_dest
                            cwd_list.append(cmd[1])
                    except:
                        print('Directory "%s" does not exist.' % cmd[1])
                        pass
            elif op == 'chown':
                dest = self.locate(cmd[1], parent=cwd)
                self.chown(dest, cmd[2])
            elif op == 'rename':
                dest = self.locate(cmd[1], parent=cwd)
                self.rename(dest, cmd[2])
            elif op == 'mkdir':
                self.mkdir(cwd, cmd[1], cuser)
            elif op == 'mkfile':
                content = b''
                if len(cmd) >= 3:
                    content = cmd[2].encode('utf-8')
                self.mkfile(cwd, cmd[1], cuser, content)
            elif op == 'rm':
                self.remove(self.locate(cmd[1], parent=cwd))
            elif op == 'cp':
                src = self.locate(cmd[1], parent=cwd)
                self.copy(src, cmd[2])
            elif op == 'mv':
                src = self.locate(cmd[1], parent=cwd)
                self.move(src, cmd[2])
            elif op == 'exit':
                break
            else:
                print('Unknown command "%s".' % op)
        return
    pass

Filesystem = FilesystemType()

################################################################################
