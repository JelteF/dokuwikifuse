import llfuse
from easyfuse import Operations as BaseOperations
from llfuse import FUSEError, ROOT_INODE
from easyfuse import Directory, File

from dokuwiki import DokuWiki

import errno

from os import fsdecode
import logging
import argparse
import http.client

from pprint import pprint  # noqa

try:
    from config import Config
except:
    from default_config import DefaultConfig as Config

parser = argparse.ArgumentParser(description='A CLI utility to mount dokuwiki'
                                 ' as a filesystem')

parser.add_argument('--url', help='url of the host running dokuwiki')
parser.add_argument('--user', '-u', help='user used to log in')
parser.add_argument('--password', '-p', help='password for the user')
parser.add_argument('--mountpoint', help='mountpoint for the filesystem')
parser.add_argument('--chroot', help='directory to chroot into')
parser.add_argument('--log', default='INFO', help='loglevel')
args = vars(parser.parse_args())

loglevel = getattr(logging, args['log'].upper(), None)

if not isinstance(loglevel, int):
    raise ValueError('Invalid log level: %s' % args['log'])

logging.basicConfig(level=loglevel, format='[%(levelname)s] %(message)s')

del args['log']

for key, val in args.items():
    if val is not None:
        setattr(Config, key, val)

if not Config.chroot.endswith('/'):
    Config.chroot += '/'


dw = DokuWiki(Config.url, Config.user, Config.password)


class WikiEntry:
    @property
    def full_depth(self):
        return self.depth + len(Config.chroot.split('/')) - 2

    @property
    def full_path(self):
        """The full path of this entry including chroot."""
        return Config.chroot + self.path.rstrip('/')

    @property
    def parents_old(self):
        if self.inode == ROOT_INODE or self.parent.inode == ROOT_INODE:
            # Ignore the last empty string when splitting
            return Config.chroot.split('/')[:-1]
        return self.parent.parents_old + [self.parent.name]


class WikiFile(WikiEntry, File):
    _text = None
    _prints = File._prints + ('doku_path',)

    @classmethod
    def from_wiki_data(cls, wiki_data, *args, **kwargs):
        self = cls(wiki_data['id'] + '.doku', *args, **kwargs)
        self.content = None

        self.modified = wiki_data['mtime']

        self.st_size = wiki_data['size']
        return self

    def refresh_content(self):
        try:
            self.content = dw.pages.get(self.doku_path).encode('utf8')
        except http.client.BadStatusLine as e:
            logging.warning('Trying again because, requesting %s '
                            'failed with: %s', self.name, e)
            raise FUSEError(errno.EAGAIN)

    @property
    def text(self):
        return self.content.decode('utf8')

    @text.setter
    def text(self, value):
        self.content = value.encode('utf8')

    @property
    def doku_path(self):
        return ':'.join(self.parents_old + [self.name.rstrip('.doku')])

    def save(self):
        super().save()
        dw.pages.set(self.doku_path, self.text)

    def delete(self):
        super().delete()
        if len(self.text):
            # Don't delete files that are already empty, since a removed page
            # is just an empty page in dokuwiki
            dw.pages.delete(self.doku_path)


class WikiAttachment(WikiEntry, File):
    _content = b''

    @classmethod
    def from_wiki_data(cls, wiki_data, *args, **kwargs):
        self = cls(wiki_data['file'], *args, **kwargs)
        # To make sure they are refreshed when read the first time
        self.content = None

        self.modified = wiki_data['mtime']

        self.st_size = wiki_data['size']
        return self

    def refresh_content(self):
        try:
            self._content = dw.medias.get(self.doku_path)
        except http.client.BadStatusLine as e:
            logging.warning('Trying again because, requesting %s '
                            'failed with: %s', self.name, e)
            raise FUSEError(errno.EAGAIN)

    @property
    def doku_path(self):
        return ':'.join(self.parents_old + [self.name])

    def save(self):
        super().save()
        dw.medias.set(self.doku_path, self.content, overwrite=True)

    def delete(self):
        super().delete()
        dw.medias.delete(self.doku_path)


class WikiDir(WikiEntry, Directory):
    def refresh_children(self):
        try:
            pages = dw.pages.list(self.full_path, depth=self.full_depth + 2)
            attachments = dw.medias.list(self.full_path,
                                         depth=self.full_depth + 2)
        except http.client.BadStatusLine as e:
            logging.warning('Trying again because, requesting children of '
                            '%s failed with: %s', self.name, e)
            raise FUSEError(errno.EAGAIN)

        super().refresh_children()

        for p in pages:
            path = p['id'].split(':')[self.full_depth:]
            if len(path) > 1:
                dir_name = path[0]
                if dir_name in self.children:
                    continue

                WikiDir(dir_name, self.fs, self)

            else:
                p['id'] = path[-1]
                WikiFile.from_wiki_data(p, self.fs, self)

        for a in attachments:
            path = a['id'].split(':')[self.full_depth:]
            if len(path) > 1:
                dir_name = path[0]
                if dir_name in self.children:
                    continue

                WikiDir(dir_name, self.fs, self)
            else:
                WikiAttachment.from_wiki_data(a, self.fs, self)


class Operations(BaseOperations):
    def __init__(self, *args, **kwargs):
        super().__init__(dir_class=WikiDir, *args, **kwargs)

    def illegal_filename(self, name):
        # Files that start with a dot, without an extension and other
        # temporary files
        return name.startswith('.') or '.' not in name or name.endswith('~')

    def get_file_class(self, name):
        if name.endswith('.doku'):
            return WikiFile
        return WikiAttachment

'''
    def release(self, inode):
        logging.debug('release')
        pass

    def releasedir(self, inode):
        logging.debug('releasedir')
        pass

    def forget(self, *args, **kwargs):
        logging.debug('forget')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def destroy(self, *args, **kwargs):
        logging.debug('destroy')
        pass

    def link(self, *args, **kwargs):
        logging.debug('link')
        pass

    def mknod(self, *args, **kwargs):
        logging.debug('mknod')
        pass

    def readlink(self, *args, **kwargs):
        logging.debug('readlink')
        pass

    def removexattr(self, *args, **kwargs):
        logging.debug('removexattr')
        pass

    def getexttr(self, *args, **kwargs):
        logging.debug('getexattr')
        pass

    def fsync(self, *args, **kwargs):
        logging.debug('fsync')
        pass

    def fsyncdir(self, *args, **kwargs):
        logging.debug('fsyncdir')
        pass

    def listxattr(self, *args, **kwargs):
        logging.debug('listxattr')
        pass

    def setxattr(self, *args, **kwargs):
        logging.debug('setxattr')
        pass

    def statfs(self, *args, **kwargs):
        logging.debug('statfs')
        pass

    def symlink(self, *args, **kwargs):
        logging.debug('symlink')
        pass
'''


if __name__ == '__main__':
    try:
        llfuse.init(Operations(), Config.mountpoint, ['nonempty',
                                                      'fsname=tmpfs'])
    except:
        llfuse.close()
        raise

    try:
        llfuse.main(workers=1)
    except:
        llfuse.close()
        raise
    llfuse.close()
