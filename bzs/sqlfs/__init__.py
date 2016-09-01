
from . import file_storage
from . import file_system
from . import file_system_permissions

from .. import db
from .. import utils

# Initialize file storage system

FileStorage = file_storage.FileStorage(
    database      = db.Database,
    utils_package = utils)

# Initialize filesystem

Filesystem = file_system.Filesystem(
    database      = db.Database,
    filestorage   = FileStorage,
    utils_package = utils)

# Initialize permission manager

FilesystemPermissions = file_system_permissions.FilesystemPermissions(
    filesystem = Filesystem)

################################################################################
# Exported file-system functions, thread-safe, permission-safe.

def create_file(path_parent, file_name, content, user=None):
    """Inject object into filesystem, while passing in content. The content
    itself would be indexed in FileStorage. If 'path-parent' is not writable,
    then the creation would be denied."""
    if not user or not FilesystemPermissions.writable(path_parent, user):
        return False
    ret_result = Filesystem.create_file(path_parent, file_name, {user.handle}, content)
    return ret_result

def create_directory(path_parent, file_name, user=None):
    """Create directory under path_parent into filesystem. If 'path-parent' is
    not writable, then the creation would be denied."""
    if not user or not FilesystemPermissions.writable(path_parent, user):
        return False
    ret_result = Filesystem.create_directory(path_parent, file_name, {user.handle})
    return ret_result

def copy(source, target_parent, user=None):
    """Copies content of 'source' (recursively) and hang the target object
    that was copied under the node 'target_parent'. Destination can be the
    same as source folder."""
    if user and not FilesystemPermissions.readable(source, user):
        return False
    if user and not FilesystemPermissions.writable(target_parent, user):
        return False
    ret_result = Filesystem.copy_with_handle(source, target_parent, new_owners=None)
    if user:
        FilesystemPermissions.copy_reown(ret_result, user)
    return True if ret_result != None else False

def move(source, target_parent, user=None):
    """Moves content of 'source' (recursively) and hang the target object
    that was moved under the node 'target_parent'. Destination should not
    at all be the same as source folder, otherwise operation would not be
    executed."""
    if user and not FilesystemPermissions.readable(source, user):
        return False
    if user and not FilesystemPermissions.writable_all(source, user):
        return False
    if user and not FilesystemPermissions.writable(target_parent, user):
        return False
    ret_result = Filesystem.move(source, target_parent)
    return ret_result

def remove(path, user=None):
    """Removes (recursively) all content of the folder / file itself and
    all its subdirectories. Must have read and write access."""
    if user and not FilesystemPermissions.readable(path, user):
        return False
    if user and not FilesystemPermissions.writable_all(path, user):
        return False
    ret_result = Filesystem.remove(path)
    return ret_result

def rename(path, file_name):
    """Renames object 'path' into file_name. Must have read and write access."""
    if user and not FilesystemPermissions.read_writable(path, user):
        return False
    ret_result = Filesystem.rename(path)
    return ret_result

def change_ownership(path, owners, user=None):
    """Assign owners of 'path' to new owners, recursively. Must have both read
    and write access to itself and all subfiles."""
    if user and not FilesystemPermissions.read_writable_all(path, user):
        return False
    ret_result = Filesystem.change_ownership(path, owners)
    return ret_result

def change_permissions(path, permissions, recursive=False, user=None):
    """Assign permissions of 'item' to new permissions. User has the rights
    to determine whether this is done recursively. The available modes and
    representations are:

        perm = '  r    w    x    |    r    w     x  '
                     Owners |        Non-owners  |
               Read  Write  |       Read Write   |
         Effect sub_files <-+ Effect sub_files <-+

    In 'read' mode, sub_files would not be seen if denied access at a parent
        directory.
    In 'write' mode, sub_files would not be writable if and only if it
        itself is not writable or its parent does not allow its writing."""
    if user and not FilesystemPermissions.read_writable_all(path, user):
        return False
    ret_result = Filesystem.change_permissions(path, permissions, recursive)
    return ret_result

def list_directory(path, user=None):
    """Creates a list of files in the directory 'path'. Attributes of the
    returned result contains:

        file-name   - File name
        file-size   - File size
        is-dir      - Whether is directory
        owners      - The handles of the owners
        upload-time - Time uploaded, in float since epoch.

    The result should always be a list, and please index it with your own
    habits or modify the code."""
    fil_ls = Filesystem.list_directory(path)
    ret_result = list()
    for item in fil_ls:
        if user and not FilesystemPermissions.readable(item['file-name'], user, path):
            continue
        ret_result.append(item)
    return ret_result

def get_content(path):
    """Gets binary content of the object (must be file) and returns the
    actual content in bytes."""
    if user and not FilesystemPermissions.readable(path):
        return b''
    ret_result = Filesystem.get_content(path)
    return ret_result
