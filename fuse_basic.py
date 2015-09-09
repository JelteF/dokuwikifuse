import llfuse
from llfuse import Operations as BaseOperations
from llfuse import EntryAttributes, FUSEError, ROOT_INODE

from dokuwiki import DokuWiki

import errno
import os
import stat

from os import fsencode, fsdecode
from collections import UserDict
from pprint import pprint  # noqa


class WikiEntry(EntryAttributes):
    def __init__(self, ops, wiki_data=None):
        super().__init__()

        if wiki_data is not None:
            self.inode = wiki_data['rev']
            self.name = wiki_data['id']

            for attr in ['st_atime', 'st_ctime', 'st_mtime']:
                setattr(self, attr, wiki_data['mtime'])

            self.st_size = wiki_data['size']

        else:
            self.inode = ROOT_INODE
            self.name = ''

        self.st_uid = os.getuid()
        self.st_gid = os.getgid()

        # mode = -rw-r--r--
        self.st_mode = stat.S_IRUSR | stat.S_IWUSR | \
            stat.S_IRGRP | stat.S_IROTH

        self.ops = ops
        self.ops[self.inode] = self

    def __repr__(self):
        string = '<%s(' % self.__class__.__name__
        for i, attr in enumerate(['inode', 'filename']):
            if i:
                string += ', '
            string += repr(getattr(self, attr))
        string += ', '
        string += stat.filemode(self.st_mode)

        string += ')>'
        return string

    def to_readdir_format(self):
        return fsencode(self.filename), self, self.inode

    @property
    def filename(self):
        return self.name

    @property
    def inode(self):
        return self.st_ino

    @inode.setter
    def inode(self, value):
        self.st_ino = value


class WikiFile(WikiEntry):
    _text = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IFREG

    @property
    def filename(self):
        return self.name + '.doku'

    @property
    def text(self):
        if self._text is None:
            self._refresh_text()
        return self._text

    def _refresh_text(self):
        self._text = self.ops.dw.pages.get(self.name)

    @property
    def bytes(self):
        return self.text.encode('utf8')


class WikiDir(WikiEntry):
    _children = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IFDIR | stat.S_IXUSR | stat.S_IXGRP | \
            stat.S_IXOTH

    @property
    def children(self):
        if self._children is None:
            self._refresh_children()
        return self._children

    def _refresh_children(self):
        pages = self.ops.dw.pages.list(depth=1)
        self._children = {}
        for p in pages:
            wiki_entry = WikiFile(self.ops, p)
            print(wiki_entry)
            self._children[wiki_entry.filename] = wiki_entry
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
            entry = self[inode]
            print('found it: ', entry)
            return entry
        except KeyError:
            print('Didn\'t find it :(')
            raise FUSEError(errno.ENOENT)

    def lookup(self, parent_inode, name):
        print('lookup')
        name = fsdecode(name)
        print(name)
        if name == '.':
            inode = parent_inode
        elif name == '..':
            inode = ROOT_INODE
        else:
            parent = self[parent_inode]
            pprint(parent.children)
            try:
                inode = parent.children[name].inode
                print('found')
            except:
                print('not found')
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
        wiki_dir.children
        # entries = [(fsencode('.'), self.getattr(inode), inode)]
        entries = [c.to_readdir_format() for c in wiki_dir.children.values()]
        return entries[off:]

    def open(self, inode, flags):
        print('open')
        print(inode)
        # TODO: Keep track of amount of times open
        return inode

    def read(self, inode, offset, length):
        print('read')
        print(inode, offset, length)
        return self[inode].bytes[offset: offset + length]


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
