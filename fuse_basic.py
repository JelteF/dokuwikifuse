import llfuse
from llfuse import Operations as BaseOperations
from llfuse import EntryAttributes, FUSEError, ROOT_INODE

import errno
import os
import stat

from os import fsencode


class Operations(BaseOperations):
    def getattr(self, inode):
        entry = EntryAttributes()
        entry.st_ino = ROOT_INODE
        entry.st_uid = os.getuid()
        entry.st_gid = os.getgid()

        # mode = drwxr-xr-x
        entry.st_mode = stat.S_IFDIR | stat.S_IRUSR | stat.S_IWUSR | \
            stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | \
            stat.S_IXOTH

        return entry

    def lookup(self, parent_inode, name):
        print('lookup')
        print(parent_inode, name)
        if name == '.':
            print('current dir')
            inode = parent_inode
        elif name == '..':
            print('dir up')
            inode = ROOT_INODE
        else:
            raise FUSEError(errno.ENOENT)

        return self.getattr(inode)

    def access(self, inode, mode, ctx):
        print('access')
        print(inode)
        return True

    def opendir(self, inode):
        print('opendir')
        print(inode)
        return inode

    def readdir(self, inode, off):
        print('readdir')
        entries = [(fsencode('.'), self.getattr(inode), inode)]
        return entries[off:]


if __name__ == '__main__':
    llfuse.init(Operations(), 'wiki', [])

    try:
        llfuse.main()
    except:
        llfuse.close()
        raise
    llfuse.close()
