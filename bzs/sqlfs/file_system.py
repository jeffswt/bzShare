
import copy
import re
import uuid as uuid_package

from . import file_stream

class Filesystem:
    """ This is a virtual filesystem based on a relational PostgreSQL database.
    We might call it a SQLFS. Its tree-topological structure enables it to index
    files and find siblings quickly. Yet without the B-Tree optimization it
    would not be easy to maintain a high performance. """

    class fsNode:
        """ This is a virtual node on a virtual filesystem SQLFS. The virtual
        node contains the following data:

            uuid        - The unique identifier: This uuid would be the
                          identifier pointing to the directory or the file.
            is_dir      - Whether is a directory or not
            file_name   - The actual file / directory name given by the user
            owner       - The string handle of the owner.
            permissions - A dict() of users with dict() of allowed permissions.
            upload_time - The time uploaded / copied / moved to server
            f_uuid      - If a file them this indicates its FileStorage UUID.

        Other data designed to maintain the structure of the node includes:

            master        - The filesystem itself.
            sub_items     - Set of children.
            sub_names_idx - Dictionary of children indexed by name.

        Do process with caution, and use exported methods only. """

        file_name     = ''
        is_dir        = False
        owner         = 'kernel'
        permissions   = {
            '': dict(
                read  = False,
                write = False,
                inherit = False
            )
        }
        uuid          = uuid_package.UUID('00000000-0000-0000-0000-000000000000')
        upload_time   = 0.0
        f_uuid        = uuid_package.UUID('00000000-0000-0000-0000-000000000000')
        sub_items     = set()
        sub_names_idx = dict()

        def __init__(self, is_dir=True, file_name='Untitled', owner='kernel', permissions={'':'--x'}, uuid=None, upload_time=None, sub_folders=set(), sub_files=set(), f_uuid=None, master=None):
            """ Load tree of all nodes in SQLFS filesystem. """
            # The filesystem / master of the node
            self.master = master
            # Assigning data
            self.is_dir = is_dir
            self.file_name = file_name
            self.owner = owner
            self.chmod_all(permissions)
            # Generate Universally Unique Identifier
            self.uuid = master.utils_pkg.get_new_uuid(uuid, master.fs_uuid_idx)
            master.fs_uuid_idx[self.uuid] = self
            # Get upload time
            self.upload_time = upload_time or master.utils_pkg.get_current_time()
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

        def duplicate(self):
            """ Create duplicate (mutation-invulnerable) of this node with
            a different UUID. """
            n_fl = self.master.fsNode(self.is_dir, self.file_name, self.owner,
                master=self.master)
            n_fl.permissions = copy.copy(self.permissions)
            # n_fl.uuid = None # Disabled due to new UUID necessity
            n_fl.upload_time = self.upload_time
            if not n_fl.is_dir: n_fl.f_uuid = self.f_uuid
            del n_fl.sub_folders
            del n_fl.sub_files
            n_fl.parent = self.parent
            n_fl.sub_items = copy.copy(self.sub_items)
            n_fl.sub_names_idx = copy.copy(self.sub_names_idx)
            return n_fl

        def chown(self, owner):
            """ Change owner of the file. """
            self.owner = owner
            return True

        def chmod(self, usr, perm):
            """ Changes the permission of a single user. """
            if len(perm) != 3:
                return False # Does not comply with the basics
            self.permissions = dict()
            standard = 'rwx'
            indices = ['read', 'write', 'inherit']
            self.permissions[usr] = dict()
            for i in range(0, 3):
                self.permissions[usr][indices[i]] = (perm[i] == standard[i])
            return True

        def chmod_all(self, perms):
            """ Change all permissions using a dict() of the file. """
            for usr in perms:
                if not self.chmod(usr, perms[usr]):
                    return False
            return True

        def fmtmod(self):
            """ Return formatted permissions of the file. """
            fmt_res = dict()
            for usr in self.permissions:
                fmt_res[usr] = '%s%s%s' % (
                    'r' if self.permissions[usr]['read'] else '-',
                    'w' if self.permissions[usr]['write'] else '-',
                    'x' if self.permissions[usr]['inherit'] else '-'
                )
            return fmt_res

        def fmtmod_list(self):
            """ Return (listized) formatted permissions of the file. """
            fml = self.fmtmod()
            res = list()
            for usr in fml:
                res.append([usr, fml[usr]])
            return res

        def inherit_parmod(self, usr):
            """ Inherit permissions of 'usr' from parent. """
            if not self.parent:
                return False
            if usr not in self.parent.permissions:
                return False
            if not self.parent.permissions[usr]['inherit']:
                return True
            self.permissions[usr] = dict()
            for s in ['read', 'write', 'inherit']:
                self.permissions[usr][s] = self.parent.permissions[usr][s]
            return True

        def inherit_parmod_all(self):
            """ Inherit all permission of 'usr's parent. """
            if not self.parent:
                return False
            for usr in self.parent.permissions:
                if not self.inherit_parmod(usr):
                    return False
            return True

        pass

    def __init__(self, database=None, filestorage=None, utils_package=None):
        """ Load files from database, must specify these options or will revoke
        AttributeError:

            database = The database
            filestorage = The file storage which holds handles for files

        Should return nothing elsewise. """
        if not database:
            raise AttributeError('Must provide database')
        if not filestorage:
            raise AttributeError('Must provide file storage handler')
        if not utils_package:
            raise AttributeError('Must provide bzShare utilities')
        self.fs_uuid_idx = dict()
        self.fs_root     = None
        self.fs_db       = database
        self.fs_store    = filestorage
        self.utils_pkg   = utils_package
        # Testforing items in database for building tree.
        for item in self.fs_db.execute("SELECT uuid, file_name, owner, permissions, upload_time, sub_folders, sub_files FROM file_system"):
            # Splitting tuple into parts
            uuid, file_name, owner, permissions__, upload_time, sub_folders, sub_files = item
            permissions = dict()
            for lst in permissions__:
                permissions[lst[0]] = lst[1]
            # Getting sub files which are expensive stored separately
            n_sub_files = set()
            for fil_idx in sub_files:
                # This is where the order goes, BEAWARE
                s_uuid = fil_idx[0]
                s_file_name = fil_idx[1]
                s_owner = fil_idx[2]
                # Set permissions
                s_permissions = dict()
                for lst in list(fr.split('/') for fr in fil_idx[3].split(';')):
                    s_permissions[lst[0]] = lst[1]
                # Set upload time
                try:
                    s_upload_time = float(fil_idx[4])
                except:
                    s_upload_time = self.utils_pkg.get_current_time()
                # File UUID uploading
                s_f_uuid = uuid_package.UUID(fil_idx[5])
                if s_f_uuid not in self.fs_store.st_uuid_idx:
                    continue
                # Pushing into structure...
                s_file = self.fsNode(is_dir=False, file_name=s_file_name, owner=s_owner, permissions=s_permissions, uuid=s_uuid, upload_time=s_upload_time, f_uuid=s_f_uuid, master=self)
                n_sub_files.add(s_file)
                self.fs_uuid_idx[s_uuid] = s_file
            # Getting sub folders as a set but not templating them
            n_sub_folders = set() # Since reference is passed, should not manipulate this further
            for fol_idx in sub_folders:
                n_sub_folders.add(fol_idx)
            fold_elem = self.fsNode(is_dir=True, file_name=file_name, owner=owner, permissions=permissions, uuid=uuid, upload_time=upload_time, sub_folders=n_sub_folders, sub_files=n_sub_files, master=self)
            self.fs_uuid_idx[uuid] = fold_elem
        # Done importing from SQL database, now attempting to refurbish connexions
        for uuid in self.fs_uuid_idx:
            item = self.fs_uuid_idx[uuid]
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
        for uuid in self.fs_uuid_idx: # This would fix all nodes...
            item = self.fs_uuid_idx[uuid]
            iterate_fsnode(item)
        # Finding root and finishing parent connexions
        for uuid in self.fs_uuid_idx: # Takes the first element that ever occured to me
            item = self.fs_uuid_idx[uuid]
            while item.parent:
                item = item.parent
            self.fs_root = item
            break
        else:
            self.__make_root()
        # Traversing root for filename indexing
        def iterate_node_fn(node):
            for item in node.sub_items:
                node.sub_names_idx[item.file_name]
        # All done, finished initialization
        return

    def __sqlify_fsnode(self, item):
        """ Turns a node into SQL-compatible node. """
        n_uuid = item.uuid
        n_file_name = item.file_name
        n_owner = item.owner
        n_permissions = item.fmtmod_list()
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
                    str(i_sub.owner),
                    ';'.join('/'.join(fr) for fr in i_sub.fmtmod_list()),
                    "%f" % i_sub.upload_time,
                    str(i_sub.f_uuid)
                ])
        # Formatting string
        return (n_uuid, n_file_name, n_owner, n_permissions, n_upload_time, n_sub_folders, n_sub_files)

    def __update_in_db(self, item):
        """ Push updating commit to Database for changes. Does not affect
        nonexistent nodes in Database. Otherwise please use __insert_in_db().

        Operation would not be redirected to insertion because of recursive
        risks that could potentially damage and overflow the process. """
        # This applies to items in the
        # We assert that item should be Node.
        item = self.__locate(item)
        if not item:
            return False
        # Giving a few but crucial assertions...
        if not item.is_dir:
            item = item.parent
            if not item.is_dir:
                return False # I should raise, by a matter of fact
        # Collecting data
        n_uuid, n_file_name, n_owner, n_permissions, n_upload_time, n_sub_folders, n_sub_files = self.__sqlify_fsnode(item)
        # Uploading / committing data
        if not self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return False # You already stated this is an updating operation!
        self.fs_db.execute("UPDATE file_system SET file_name = %s, owner = %s, permissions = %s, upload_time = %s, sub_folders = %s, sub_files = %s WHERE uuid = %s;", (n_file_name, n_owner, n_permissions, n_upload_time, n_sub_folders, n_sub_files, n_uuid))
        return True

    def __insert_in_db(self, item):
        """ Create filesystem record of directory 'item' inside database. You
        should not insert something that already existed. However:

        We have had a precaution for this. Update operations would be taken
        automatically instead. """
        if not item.is_dir:
            return False # Must be directory...
        n_uuid, n_file_name, n_owner, n_permissions, n_upload_time, n_sub_folders, n_sub_files = self.__sqlify_fsnode(item)
        # Uploading / committing data
        if self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return self.__update_in_db(item) # Existed, updating instead.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, permissions, upload_time, sub_folders, sub_files) VALUES (%s, %s, %s, %s, %s, %s, %s);", (n_uuid, n_file_name, n_owner, n_permissions, n_upload_time, n_sub_folders, n_sub_files))
        return

    def __make_root(self):
        """ Create root that didn't exist before. """
        # Creating items
        itm_root = self.fsNode(True, '', 'kernel', permissions={'':'r--','kernel':'rw-'}, master=self)
        itm_system = self.fsNode(True, 'System', 'kernel', permissions={'':'--x','kernel':'rw-'}, master=self)
        itm_public = self.fsNode(True, 'Public', 'public', permissions={'':'rwx','kernel':'rwx'}, master=self)
        itm_groups = self.fsNode(True, 'Groups', 'kernel', permissions={'':'r-x','kernel':'rwx'}, master=self)
        itm_users = self.fsNode(True, 'Users', 'kernel', permissions={'':'r-x','kernel':'rwx'}, master=self)
        itm_kernel_folder = self.fsNode(True, 'kernel', 'kernel', permissions={'':'--x','kernel':'rwx'}, master=self)
        # Removing extra data and linking
        large_set = {itm_system, itm_public, itm_groups, itm_users}
        # Inserting into SQL database
        # Creating root
        del itm_root.sub_files
        del itm_root.sub_folders
        itm_root.sub_items = set()
        itm_root.sub_names_idx = dict()
        itm_root.parent = None
        self.fs_root = itm_root
        # Create system folders
        for item in large_set:
            del item.sub_files
            del item.sub_folders
            item.sub_items = set()
            item.sub_names_idx = dict()
            itm_root.sub_items.add(item)
            itm_root.sub_names_idx[item.file_name] = item
            item.parent = itm_root
        # Create kernel's user folder
        del itm_kernel_folder.sub_files
        del itm_kernel_folder.sub_folders
        itm_kernel_folder.sub_items = set()
        itm_kernel_folder.sub_names_idx = dict()
        itm_kernel_folder.parent = itm_users
        itm_users.sub_items.add(itm_kernel_folder)
        itm_users.sub_names_idx[itm_kernel_folder.file_name] = itm_kernel_folder
        # Injecting nodes
        self.__insert_in_db(self.fs_root)
        for item in large_set:
            self.__insert_in_db(item)
        self.__insert_in_db(itm_kernel_folder)
        return

    def __locate(self, path, parent=None):
        """ Locate the fsNode() of the location 'path'. If 'parent' is given and
        as it should be a fsNode(), the function look to the nodes directly
        under this, non-recursively. """
        # On the case it is a referring location, path should be str.
        if parent:
            if type(parent) in [str, list]:
                parent = self.__locate(parent, None)
            try:
                item = parent.sub_names_idx[path]
            except Exception:
                return None
            return item
        # And it is not such a location.
        if type(path) not in [str, list]:
            return path
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

    def __is_child(self, node, parent):
        """ Determines whether node is a child of parent. """
        while node:
            if node == parent:
                return True
            node = node.parent
        return False

    def __make_nice_filename(self, file_name):
        """ Create a HTML-friendly file name that does not support and does not
        allow cross site scripting (XSS). """
        file_name = re.sub(r'[\\/*<>?`\'"|\r\n]', r'', file_name)
        if len(file_name) <= 0:
            file_name = 'Empty name'
        if file_name == '.' or '..':
            file_name = 'Dots'
        return file_name

    def __resolve_conflict(self, file_name, parent):
        """ Rename 'file_name' if necessary in order to make operations
        successful in case of confliction that disrupts the SQLFS. The renamed
        file / folder should be named like this:

        New Text Document.txt
        New Text Document (2).txt
        New Text Document (3).txt

        Et cetera. """
        parent = self.__locate(parent)
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

    def __mkfile(self, path_parent, file_name, owner, content_stream):
        """ Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage. """
        path_parent = self.__locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, path_parent)
        # Finished assertion.
        n_uuid = self.fs_store.new_unique_file(content_stream)
        n_fl = self.fsNode(False, file_name, owner, f_uuid=n_uuid, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        n_fl.inherit_parmod()
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self.__update_in_db(path_parent)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def __mkdir(self, path_parent, file_name, owner):
        """ Inject folder into filesystem. """
        path_parent = self.__locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, path_parent)
        # Creating new node.
        n_fl = self.fsNode(True, file_name, owner, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        n_fl.inherit_parmod()
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self.__update_in_db(path_parent)
        self.__insert_in_db(n_fl)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def __listdir(self, path):
        """ Creates a list of files in the directory 'path'. Attributes of the returned
        result contains:

            file-name   - File name
            file-size   - File size
            is-dir      - Whether is directory
            owner       - The handle of the owner
            permissions - The permissions of the file
            upload-time - Time uploaded, in float since epoch.

        The result should always be a list, and please index it with your own
        habits or modify the code. """
        path = self.__locate(path)
        if not path:
            return []
        # List directory, given the list(dict()) result...
        dirs = list()
        for item in path.sub_items:
            attrib = dict()
            try:
                attrib['file-name'] = item.file_name
                attrib['file-size'] = 0 if item.is_dir else self.fs_store.st_uuid_idx[item.f_uuid].size
                attrib['is-dir'] = item.is_dir
                attrib['owner'] = item.owner
                attrib['permissions'] = item.fmtmod()
                attrib['upload-time'] = item.upload_time
            except:
                continue
            dirs.append(attrib)
        # Give the results to downstream
        return dirs

    def __get_content(self, item):
        """ Gets file stream of binary content of the object and must be file. """
        item = self.__locate(item)
        if not item:
            return file_stream.EmptyFileStream
        if item.is_dir:
            item = None
            return file_stream.EmptyFileStream
        return self.fs_store.get_content(item.f_uuid)

    def __copy_recursive(self, item, new_owner):
        """ Copies content of a single object and recursively call all its
        children for recursive copy, targeted as a child under target_par. """
        # We assert item, target_par are all fsNode().
        new_sub_items = set()
        item.sub_names_idx = dict()
        # Recursively call tree structure.
        for i_sub in item.sub_items:
            n_sub = i_sub.duplicate()
            n_sub.parent = item
            new_sub_items.add(n_sub)
            item.sub_names_idx[i_sub.file_name] = n_sub
            self.__copy_recursive(n_sub, new_owner)
        item.sub_items = new_sub_items
        # Insert into SQL database
        item.upload_time = self.utils_pkg.get_current_time()
        if new_owner:
            item.owner = new_owner # Assignment
        # These are to maintain tree structures or relations
        if item.is_dir:
            self.__insert_in_db(item)
        else:
            self.fs_store.add_unique_file(item.f_uuid)
        return

    def __copy(self, source, target_parent, new_owner=None, return_handle=False):
        """ Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination can be the
        same as source folder. If rename required please call the related
        functions separatedly. """
        source = self.__locate(source)
        target_parent = self.__locate(target_parent)
        if not source or not target_parent:
            return False if not return_handle else None
        if self.__is_child(target_parent, source):
            return False if not return_handle else None
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(source.file_name)
        file_name = self.__resolve_conflict(file_name, target_parent)
        # Done assertion, now proceed with deep copy
        target = source.duplicate()
        target.file_name = file_name
        target.parent = target_parent
        target_parent.sub_items.add(target)
        target_parent.sub_names_idx[target.file_name] = target
        self.__copy_recursive(target, new_owner)
        # Assigning and finishing tree connexions
        self.__update_in_db(target_parent)
        return True if not return_handle else target

    def __move(self, source, target_parent, return_handle=False):
        """ Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination should not
        at all be the same as source folder, otherwise operation would not be
        executed. """
        source = self.__locate(source)
        target_parent = self.__locate(target_parent)
        if not source or not target_parent:
            return False if not return_handle else None
        # It should not move itself to itself.
        if source.parent == target_parent:
            return False if not return_handle else None
        # Neither should itself move itself to its children
        if self.__is_child(target_parent, source):
            return False if not return_handle else None
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(source.file_name)
        file_name = self.__resolve_conflict(file_name, target_parent)
        source.file_name = file_name
        # Moving an re-assigning tree structures
        par = source.parent
        par.sub_items.remove(source)
        del par.sub_names_idx[source.file_name]
        source.parent = target_parent
        target_parent.sub_items.add(source)
        target_parent.sub_names_idx[source.file_name] = source
        # Updating SQL database.
        self.__update_in_db(par)
        self.__update_in_db(target_parent)
        return True if not return_handle else source

    def __remove_recursive(self, item):
        """ Removes content of a single object and recursively call all its
        children for recursive removal. """
        # We assert item is fsNode().
        # Remove recursively.
        for i_sub in item.sub_items:
            self.__remove_recursive(i_sub)
        # Delete itself from filesystem.
        del self.fs_uuid_idx[item.uuid]
        # Delete itself from SQL database.
        self.fs_db.execute("DELETE FROM file_system WHERE uuid = %s;", (item.uuid,))
        # Also delete occurence if is file.
        if not item.is_dir:
            self.fs_store.remove_unique_file(item.f_uuid)
        return

    def __remove(self, path):
        """ Removes (recursively) all content of the folder / file itself and
        all its subdirectories. """
        path = self.__locate(path)
        if not path:
            return False
        # Done assertion, path is now fsNode().
        par = path.parent
        self.__remove_recursive(path)
        if par:
            par.sub_items.remove(path)
            del par.sub_names_idx[path.file_name]
            self.__update_in_db(par)
        # There always should be a root.
        if path == self.fs_root:
            self.__make_root()
        # Done removal.
        return True

    def __rename(self, item, file_name):
        """ Renames object 'item' into file_name. """
        item = self.__locate(item)
        if not item:
            return False
        if not item.parent:
            return False # How can you rename a root?
        # Resolving conflict and nicing file name.
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, item.parent)
        # Actually deleting
        del item.parent.sub_names_idx[item.file_name]
        item.file_name = file_name
        item.parent.sub_names_idx[item.file_name] = item
        if item.is_dir:
            self.__update_in_db(item)
        self.__update_in_db(item.parent) # At least there is a parent
        return True

    def __chown(self, item, owner):
        """ Assign owner of 'item' to new owner, recursively. """
        item = self.__locate(item)
        if not item:
            return False
        def _chown_recursive(item_, owner_):
            for sub_ in item_.sub_items:
                _chown_recursive(sub_, owner_)
            item_.chown(owner_)
            if item_.is_dir:
                self.__update_in_db(item_)
            return
        _chown_recursive(item, owner)
        if not item.is_dir:
            self.__update_in_db(item.parent)
        return True

    def __chmod(self, item, perm):
        """ Change permissions on only one node. """
        item = self.__locate(item)
        if not item:
            return False
        # Parse permission information
        ret = item.chmod(perm)
        if not item.is_dir:
            self.__update_in_db(item.parent)
        else:
            self.__update_in_db(item)
        return ret

    def __chmod_recursive(self, item, perm):
        """ Recursively change permissions. """
        item = self.__locate(item)
        if not item:
            return False
        # Done assertion.
        result = True
        def _rec_work(item_, perm_):
            for i_sub in item_.sub_items:
                _rec_work(i_sub)
            result = result and self.__chmod(item_, perm_)
        _rec_work(item, perm)
        return result

    def __shell(self):
        cwd = self.fs_root
        cuser = 'kernel'
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
                res = self.list_directory(cwd)
                # Prettify the result
                print('Owner       Perms           Upload Time         Size            Filename            ')
                print('------------------------------------------------------------------------------------')
                for item in res:
                    print('%s%s %s%s%s' % (str(item['owner']).ljust(12), str(item['permissions']).ljust(16), str(int(item['upload-time'])).ljust(20), str(item['file-size'] if not item['is-dir'] else '').ljust(16), item['file-name']))
                print('Total: %d' % len(res))
                print('')
            elif op == 'cat':
                dest = self.locate(cmd[1], parent=cwd)
                print(self.get_content(dest).read())
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
                self.change_ownership(dest, cmd[2])
            elif op == 'rename':
                dest = self.locate(cmd[1], parent=cwd)
                self.rename(dest, cmd[2])
            elif op == 'mkdir':
                self.create_directory(cwd, cmd[1], cuser)
            elif op == 'mkfile':
                if len(cmd) >= 3:
                    content = cmd[2].encode('utf-8')
                else:
                    content = b''
                content_stream = file_stream.FileStream(mode='write', est_length=len(content), obj_data=content, database=self.fs_db)
                self.create_file(cwd, cmd[1], cuser, content_stream)
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

    """ Exported functions that are *NOT* thread-safe. """

    def locate(self, path, parent=None):
        """ Locate the fsNode() of the location 'path'. If 'parent' is given and
        as it should be a fsNode(), the function look to the nodes directly
        under this, non-recursively. """
        ret_result = self.__locate(path, parent)
        return ret_result

    def is_child(self, node, parent):
        """ Determines whether node is a child of parent. """
        ret_result = self.__is_child(node, parent)
        return ret_result

    def create_file(self, path_parent, file_name, owner, content_stream):
        """ Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage. """
        ret_result = self.__mkfile(path_parent, file_name, owner, content_stream)
        return ret_result

    def create_directory(self, path_parent, file_name, owner):
        """ Create directory under path_parent into filesystem. """
        ret_result = self.__mkdir(path_parent, file_name, owner)
        return ret_result

    def copy(self, source, target_parent, new_owner=None):
        """ Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination can be the
        same as source folder. If rename required please call the related
        functions separatedly. """
        ret_result = self.__copy(source, target_parent, new_owner=new_owner)
        return ret_result

    def copy_with_handle(self, source, target_parent, new_owner=None):
        """ Same as copy(), returns HANDLE or None. """
        ret_result = self.__copy(source, target_parent, new_owner=new_owner, return_handle=True)
        return ret_result

    def move(self, source, target_parent):
        """ Moves content of 'source' (recursively) and hang the target object
        that was moved under the node 'target_parent'. Destination should not
        at all be the same as source folder, otherwise operation would not be
        executed. """
        ret_result = self.__move(source, target_parent)
        return ret_result

    def move_with_handle(self, source, target_parent):
        """ Same as move(), returns HANDLE or None. """
        ret_result = self.__copy(source, target_parent, return_handle=True)
        return ret_result

    def remove(self, path):
        """ Removes (recursively) all content of the folder / file itself and
        all its subdirectories. """
        ret_result = self.__remove(path)
        return ret_result

    def rename(self, path, file_name):
        """ Renames object 'path' into file_name. """
        ret_result = self.__rename(path, file_name)
        return ret_result

    def change_ownership(self, path, owner):
        """ Assign owner of 'path' to new owner, recursively. """
        ret_result = self.__chown(path, owner)
        return ret_result

    def change_permissions(self, path, permissions, recursive=False):
        """ Assign permissions of 'item' to new permissions. User has the rights
        to determine whether this is done recursively. The available modes and
        representations are:

            perm = '  r    w    x'
                   Read  Write  Inherit subfiles

            Whereas the permissions should be a dict from each user / usergroup
            to a certain 'perm' string.

        In 'read' mode, sub_files would not be seen if denied access at a parent
            directory.
        In 'write' mode, sub_files would not be writable if and only if it
            itself is not writable or its parent does not allow its writing. """
        if not recursive:
            ret_result = self.__chmod(path, permissions)
        else:
            ret_result = self.__chmod_recursive(path, permissions)
        return ret_result

    def expunge_user_ownership(self, handle):
        """ Must only be called from kernel / system, used when removing a
        usergroup or a user. Its ownership is expunged from the system, and
        replaced by the file node's parent. """
        root = self.fs_root
        def __exp_uown(node, handle):
            for sub in node.sub_items:
                if sub.owner == handle:
                    sub.owner = 'public' if sub.parent else sub.parent.owner
                    # Update in filesystem database
                    self.__update_in_db(sub)
                # Iterating...
                __exp_uown(sub, handle)
            return
        __exp_uown(root, handle)
        return

    def list_directory(self, path):
        """ Creates a list of files in the directory 'path'. Attributes of the
        returned result contains:

            file-name   - File name
            file-size   - File size
            is-dir      - Whether is directory
            owner       - The handles of the owner
            upload-time - Time uploaded, in float since epoch.

        The result should always be a list, and please index it with your own
        habits or modify the code. """
        ret_result = self.__listdir(path)
        return ret_result

    def get_content(self, path):
        """ Gets file stream of binary content of the object and returns the
        file handle. """
        ret_result = self.__get_content(path)
        return ret_result

    def shell(self):
        """ Interactive shell for manipulating SQLFS. May be integrated into
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

        This shell should not be used in production as is not safe. """
        ret_result = self.__shell()
        return ret_result
    pass
