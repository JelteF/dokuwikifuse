import llfuse
from llfuse import Operations as BaseOperations
from llfuse import EntryAttributes, FUSEError, ROOT_INODE

from dokuwiki import DokuWiki

import errno
import os
import stat

from os import fsencode
from collections import UserDict


class WikiEntry:
    def __init__(self, ops, wiki_data=None):
        self.entry = EntryAttributes()

        if wiki_data is not None:
            self.inode = wiki_data['rev']
            self.path = '/' + wiki_data['id']
        else:
            self.inode = ROOT_INODE
            self.path = '/'

        self.entry.st_ino = self.inode
        self.entry.st_uid = os.getuid()
        self.entry.st_gid = os.getgid()

        # mode = drwxr-xr-x
        self.entry.st_mode = stat.S_IFDIR | stat.S_IRUSR | stat.S_IWUSR | \
            stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | \
            stat.S_IXOTH

        self.ops = ops
        self.ops[self.entry.st_ino] = self

    def __repr__(self):
        string = '<%s(' % self.__class__.__name__
        for i, attr in enumerate(['inode', 'path']):
            if i:
                string += ', '
            string += repr(getattr(self, attr))

        string += ')>'
        return string

    def to_readdir_format(self):
        return fsencode(self.path), self.entry, self.inode


class WikiDir(WikiEntry):
    _children = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def children(self):
        if self._children is None:
            self._refresh_children()
        return self._children

    def _refresh_children(self):
        pages = self.ops.dw.pages.list(depth=1)
        self._children = []
        for p in pages:
            wiki_entry = WikiEntry(self.ops, p)
            print(wiki_entry)
            self._children.append(wiki_entry)
        print(pages)


class Operations(BaseOperations, UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.dw = DokuWiki('https://os3.nl', '', '')

        self.data = {}
        WikiDir(self)

    def getattr(self, inode):
        print('trying to find inode: ' + str(inode))
        try:
            entry = self[inode].entry
            print('found it: ', entry)
            return entry
        except KeyError:
            print('Didn\'t find it :(')
            raise FUSEError(errno.ENOENT)

    def lookup(self, parent_inode, name):
        print('lookup')
        print(parent_inode, name)
        if name == '.':
            inode = parent_inode
        elif name == '..':
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
        print('readdir', inode, off)
        # pages = self.dw.pages.list(depth=1)
        # print(pages)
        wiki_dir = self[inode]
        print(wiki_dir)
        wiki_dir.children
        # entries = [(fsencode('.'), self.getattr(inode), inode)]
        entries = [c.to_readdir_format() for c in wiki_dir.children]
        print(entries)
        print(wiki_dir.children)
        return entries[off:]


if __name__ == '__main__':
    ops = Operations()

    try:
        llfuse.init(ops, 'wiki', [])
    except:
        llfuse.close()
        raise

    try:
        llfuse.main()
    except:
        llfuse.close()
        raise
    llfuse.close()
