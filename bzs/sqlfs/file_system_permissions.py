
import copy

from .. import users

class FilesystemPermissions:
    """Manages the permissions of the filesystem, separated from the main
    filesystem manager. This requires the use of user management, which is
    equipped in the users module.

    Remote operations on the file system should be verified through this module
    before operating.

    Specific operations on the file system should also call the post-process
    procedures in this class for special security precautions, to prevent the
    user from viewing anything inappropriate."""

    def __init__(self, filesystem=None):
        if not filesystem:
            raise AttributeError('Must provide a file system')
        self.fs = filesystem
        return

    def __is_owner(self, user, owners):
        """Check if user is one of the owners."""
        for grp in user.usergroups:
            if grp in owners:
                return True
        return user in owners

    def __accessible(self, node, user, mode):
        """Wrapping function for determining a single attribute."""
        # Kernel has ultimate access to files
        if user in ['kernel', 'root']:
            return True
        # Otherwise normal users
        grp = 'owner' if self.__is_owner(user, node.owners) else 'other'
        res_1 = node.permissions['%s_%s' % (grp, mode)]
        if node.parent:
            res_2 = node.parent.permissions['%s_%s' % (grp, mode)] if node.parent.permissions['%s_%s' % (grp, 'pass')] else True
        else:
            res_2 = True
        return res_1 and res_2

    def readable(self, node, user):
        """Whether an object is readable. If one of its parents are unreadable,
        then itself will also be unreadable."""
        node = self.fs.locate(node)
        if not node:
            return False
        # Check itself and all its parents to see if readable
        p_nd = node
        res = True
        while p_nd.parent:
            if not self.__accessible(p_nd, user, 'read'):
                res = False
            p_nd = p_nd.parent
        # If we don't check all there may be a possibility that people can determine which folders are unreadable through the response timing
        return res

    def writable(self, node, user):
        """Whether an object is writable. It only matters that its direct
        parent does not allow children to be writable and itself does not
        gurantee write access likewise."""
        node = self.fs.locate(node)
        if not node:
            return False
        return self.__accessible(node, user, 'write')

    def writable_all(self, path, user, parent=None):
        """Check permissions of a folder whether it should be writable - all of
        its contents and subfolders should be writable."""
        node = self.fs.locate(path, parent)
        if not node:
            return False
        def _wr_all(item, user):
            c_res = True
            for i_sub in item.sub_items:
                c_res = c_res and _wr_all(i_sub, user)
            c_res = c_res and self.__writable()
            return c_res
        return _wr_all(node, user)

    def copy_reown(self, path, user, parent=None):
        """Reset ownership of a folder, and if ownership does not gurantee
        the user read access, then remove this file."""
        node = self.fs.locate(path, parent)
        if not node:
            return False
        # A nice node, now attempting to search and remove
        def _cp_rown(item, user):
            sub_items = copy.copy(item.sub_items) # Otherwise would raise KeyError()
            for i_sub in sub_items:
                _cp_rown(i_sub, user)
            if not self.__readable(item, user):
                self.fs.remove(item)
        _cp_rown(node, user)
        # Done re-assigning
        return True

    pass
