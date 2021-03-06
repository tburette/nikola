# -*- coding: utf-8 -*-

# Copyright © 2012-2014 Roberto Alsina and others.

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Utility functions."""

from __future__ import print_function, unicode_literals
from collections import defaultdict, Callable
import calendar
import datetime
import dateutil.tz
import hashlib
import locale
import logging
import os
import re
import json
import shutil
import subprocess
import sys
from zipfile import ZipFile as zip
try:
    from imp import reload
except ImportError:
    pass

import dateutil.parser
import dateutil.tz
import logbook
from logbook.more import ExceptionHandler, ColorizedStderrHandler

from . import DEBUG


class ApplicationWarning(Exception):
    pass


class ColorfulStderrHandler(ColorizedStderrHandler):
    """Stream handler with colors."""
    _colorful = False

    def should_colorize(self, record):
        """Inform about colorization using the value obtained from Nikola."""
        return self._colorful


def get_logger(name, handlers):
    """Get a logger with handlers attached."""
    l = logbook.Logger(name)
    for h in handlers:
        if isinstance(h, list):
            l.handlers = h
        else:
            l.handlers = [h]
    return l


STDERR_HANDLER = [ColorfulStderrHandler(
    level=logbook.INFO if not DEBUG else logbook.DEBUG,
    format_string=u'[{record.time:%Y-%m-%dT%H:%M:%SZ}] {record.level_name}: {record.channel}: {record.message}'
)]
LOGGER = get_logger('Nikola', STDERR_HANDLER)
STRICT_HANDLER = ExceptionHandler(ApplicationWarning, level='WARNING')

# This will block out the default handler and will hide all unwanted
# messages, properly.
logbook.NullHandler().push_application()

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


def req_missing(names, purpose, python=True, optional=False):
    """Log that we are missing some requirements."""
    if not (isinstance(names, tuple) or isinstance(names, list) or isinstance(names, set)):
        names = (names,)
    if python:
        whatarethey_s = 'Python package'
        whatarethey_p = 'Python packages'
    else:
        whatarethey_s = whatarethey_p = 'software'
    if len(names) == 1:
        msg = 'In order to {0}, you must install the "{1}" {2}.'.format(
            purpose, names[0], whatarethey_s)
    else:
        most = '", "'.join(names[:-1])
        pnames = most + '" and "' + names[-1]
        msg = 'In order to {0}, you must install the "{1}" {2}.'.format(
            purpose, pnames, whatarethey_p)

    if optional:
        LOGGER.warn(msg)
    else:
        LOGGER.error(msg)
        LOGGER.error('Exiting due to missing dependencies.')
        sys.exit(5)

    return msg

if sys.version_info[0] == 3:
    # Python 3
    bytes_str = bytes
    unicode_str = str
    unichr = chr
    from imp import reload as _reload
else:
    bytes_str = str
    unicode_str = unicode  # NOQA
    _reload = reload  # NOQA
    unichr = unichr

from doit import tools
from unidecode import unidecode
from pkg_resources import resource_filename

import PyRSS2Gen as rss

__all__ = ['get_theme_path', 'get_theme_chain', 'load_messages', 'copy_tree',
           'copy_file', 'slugify', 'unslugify', 'to_datetime', 'apply_filters',
           'config_changed', 'get_crumbs', 'get_tzname', 'get_asset_path',
           '_reload', 'unicode_str', 'bytes_str', 'unichr', 'Functionary',
           'TranslatableSetting', 'LocaleBorg', 'sys_encode', 'sys_decode',
           'makedirs', 'get_parent_theme_name', 'demote_headers',
           'get_translation_candidate', 'write_metadata']


ENCODING = sys.getfilesystemencoding() or sys.stdin.encoding


def sys_encode(thing):
    """Return bytes encoded in the system's encoding."""
    if isinstance(thing, unicode_str):
        return thing.encode(ENCODING)
    return thing


def sys_decode(thing):
    """Returns unicode."""
    if isinstance(thing, bytes_str):
        return thing.decode(ENCODING)
    return thing


def makedirs(path):
    """Create a folder."""
    if not path or os.path.isdir(path):
        return
    if os.path.exists(path):
        raise OSError('Path {0} already exists and is not a folder.')
    os.makedirs(path)


class Functionary(defaultdict):

    """Class that looks like a function, but is a defaultdict."""

    def __init__(self, default, default_lang):
        super(Functionary, self).__init__(default)
        self.default_lang = default_lang

    def __call__(self, key, lang=None):
        """When called as a function, take an optional lang
        and return self[lang][key]."""

        if lang is None:
            lang = LocaleBorg().current_lang
        return self[lang][key]


class TranslatableSetting(object):

    """
    A setting that can be translated.

    You can access it via: SETTING(lang).  You can omit lang, in which
    case Nikola will ask LocaleBorg, unless you set SETTING.lang,
    which overrides that call.

    You can also stringify the setting and you will get something
    sensible (in what LocaleBorg claims the language is, can also be
    overriden by SETTING.lang). Note that this second method is
    deprecated.  It is kept for backwards compatibility and
    safety.  It is not guaranteed.

    The underlying structure is a defaultdict.  The language that
    is the default value of the dict is provided with __init__().
    If you need access the underlying dict (you generally don’t,
    """

    # WARNING: This is generally not used and replaced with a call to
    #          LocaleBorg().  Set this to a truthy value to override that.
    lang = None

    # Note that this setting is global.  DO NOT set on a per-instance basis!
    default_lang = 'en'

    def __getattribute__(self, attr):
        """Return attributes, falling back to string attributes."""
        try:
            return super(TranslatableSetting, self).__getattribute__(attr)
        except AttributeError:
            return self().__getattribute__(attr)

    def __dir__(self):
        return list(set(self.__dict__).union(set(dir(str))))

    def __init__(self, name, inp, translations):
        """Initialize a translated setting.

        Valid inputs include:

        * a string               -- the same will be used for all languages
        * a dict ({lang: value}) -- each language will use the value specified;
                                    if there is none, default_lang is used.

        """
        self.name = name
        self._inp = inp
        self.translations = translations
        self.overriden_default = False
        self.values = defaultdict()

        if isinstance(inp, dict):
            self.translated = True
            self.values.update(inp)
            if self.default_lang not in self.values.keys():
                self.default_lang = list(self.values.keys())[0]
                self.overridden_default = True
            self.values.default_factory = lambda: self.values[self.default_lang]
            for k in translations.keys():
                if k not in self.values.keys():
                    self.values[k] = inp[self.default_lang]
        else:
            self.translated = False
            self.values[self.default_lang] = inp
            self.values.default_factory = lambda: inp

    def get_lang(self):
        """Return the language that should be used to retrieve settings."""
        if self.lang:
            return self.lang
        elif not self.translated:
            return self.default_lang
        else:
            try:
                return LocaleBorg().current_lang
            except AttributeError:
                return self.default_lang

    def __call__(self, lang=None):
        """
        Return the value in the requested language.

        While lang is None, self.lang (currently set language) is used.
        Otherwise, the standard algorithm is used (see above).

        """
        if lang is None:
            return self.values[self.get_lang()]
        else:
            return self.values[lang]

    def __str__(self):
        """Return the value in the currently set language.  (deprecated)"""
        return self.values[self.get_lang()]

    def __unicode__(self):
        """Return the value in the currently set language.  (deprecated)"""
        return self.values[self.get_lang()]

    def __repr__(self):
        """Provide a representation for programmers."""
        header = '<TranslatableSetting> '

        if not self.translated:
            values = [repr(self())]
        else:
            values = ['{0}={1!r}'.format(k, v) for k, v in self.values.items()]

        return header + ', '.join(values)

    def format(self, *args, **kwargs):
        """Format ALL the values in the setting the same way."""
        for l in self.values:
            self.values[l] = self.values[l].format(*args, **kwargs)
        self.values.default_factory = lambda: self.values[self.default_lang]
        return self

    def langformat(self, formats):
        """Format ALL the values in the setting, on a per-language basis."""
        if not formats:
            # Input is empty.
            return self
        else:
            # This is a little tricky.
            # Basically, we have some things that may very well be dicts.  Or
            # actually, TranslatableSettings in the original unprocessed dict
            # form.  We need to detect them.

            # First off, we need to check what languages we have and what
            # should we use as the default.
            keys = list(formats)
            if self.default_lang in keys:
                d = formats[self.default_lang]
            else:
                d = formats[keys[0]]
            # Discovering languages of the settings here.
            langkeys = []
            for f in formats.values():
                for a in f[0] + tuple(f[1].values()):
                    if isinstance(a, dict):
                        langkeys += list(a)
            # Now that we know all this, we go through all the languages we have.
            allvalues = set(keys + langkeys + list(self.values))
            for l in allvalues:
                if l in keys:
                    oargs, okwargs = formats[l]
                else:
                    oargs, okwargs = d

                args = []
                kwargs = {}

                for a in oargs:
                    # We create temporary TranslatableSettings and replace the
                    # values with them.
                    if isinstance(a, dict):
                        a = TranslatableSetting('NULL', a)
                        args.append(a(l))
                    else:
                        args.append(a)

                for k, v in okwargs.items():
                    if isinstance(v, dict):
                        v = TranslatableSetting('NULL', v)
                        kwargs.update({k: v(l)})
                    else:
                        kwargs.update({k: v})

                self.values[l] = self.values[l].format(*args, **kwargs)
                self.values.default_factory = lambda: self.values[self.default_lang]

        return self

    def __getitem__(self, key):
        """Provide an alternate interface via __getitem__."""
        return self.values[key]

    def __setitem__(self, key, value):
        """Set values for translations."""
        self.values[key] = value

    def __eq__(self, other):
        """Test whether two TranslatableSettings are equal."""
        return self.values == other.values

    def __ne__(self, other):
        """Test whether two TranslatableSettings are inequal."""
        return self.values != other.values


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            return json.JSONEncoder.default(self, obj)
        except TypeError:
            s = repr(obj).split('0x', 1)[0]
            return s


class config_changed(tools.config_changed):
    """ A copy of doit's but using pickle instead of serializing manually."""

    def _calc_digest(self):
        if isinstance(self.config, str):
            return self.config
        elif isinstance(self.config, dict):
            data = json.dumps(self.config, cls=CustomEncoder, sort_keys=True)
            if isinstance(data, str):  # pragma: no cover # python3
                byte_data = data.encode("utf-8")
            else:
                byte_data = data
            digest = hashlib.md5(byte_data).hexdigest()
            # LOGGER.debug('{{"{0}": {1}}}'.format(digest, byte_data))
            return digest
        else:
            raise Exception('Invalid type of config_changed parameter -- got '
                            '{0}, must be string or dict'.format(type(
                                self.config)))

    def __repr__(self):
        return "Change with config: {0}".format(json.dumps(self.config,
                                                           cls=CustomEncoder))


def get_theme_path(theme):
    """Given a theme name, returns the path where its files are located.

    Looks in ./themes and in the place where themes go when installed.
    """
    dir_name = os.path.join('themes', theme)
    if os.path.isdir(dir_name):
        return dir_name
    dir_name = resource_filename('nikola', os.path.join('data', 'themes', theme))
    if os.path.isdir(dir_name):
        return dir_name
    raise Exception("Can't find theme '{0}'".format(theme))


def get_template_engine(themes):
    for theme_name in themes:
        engine_path = os.path.join(get_theme_path(theme_name), 'engine')
        if os.path.isfile(engine_path):
            with open(engine_path) as fd:
                return fd.readlines()[0].strip()
    # default
    return 'mako'


def get_parent_theme_name(theme_name):
    parent_path = os.path.join(get_theme_path(theme_name), 'parent')
    if os.path.isfile(parent_path):
        with open(parent_path) as fd:
            return fd.readlines()[0].strip()
    return None


def get_theme_chain(theme):
    """Create the full theme inheritance chain."""
    themes = [theme]

    while True:
        parent = get_parent_theme_name(themes[-1])
        # Avoid silly loops
        if parent is None or parent in themes:
            break
        themes.append(parent)
    return themes


warned = []


class LanguageNotFoundError(Exception):
    def __init__(self, lang, orig):
        self.lang = lang
        self.orig = orig

    def __str__(self):
        return 'cannot find language {0}'.format(self.lang)


def load_messages(themes, translations, default_lang):
    """ Load theme's messages into context.

    All the messages from parent themes are loaded,
    and "younger" themes have priority.
    """
    messages = Functionary(dict, default_lang)
    oldpath = sys.path[:]
    for theme_name in themes[::-1]:
        msg_folder = os.path.join(get_theme_path(theme_name), 'messages')
        default_folder = os.path.join(get_theme_path('base'), 'messages')
        sys.path.insert(0, default_folder)
        sys.path.insert(0, msg_folder)
        english = __import__('messages_en')
        for lang in list(translations.keys()):
            try:
                translation = __import__('messages_' + lang)
                # If we don't do the reload, the module is cached
                reload(translation)
                if sorted(translation.MESSAGES.keys()) !=\
                        sorted(english.MESSAGES.keys()) and \
                        lang not in warned:
                    warned.append(lang)
                    LOGGER.warn("Incomplete translation for language "
                                "'{0}'.".format(lang))
                messages[lang].update(english.MESSAGES)
                messages[lang].update(translation.MESSAGES)
                del(translation)
            except ImportError as orig:
                raise LanguageNotFoundError(lang, orig)
    sys.path = oldpath
    return messages


def copy_tree(src, dst, link_cutoff=None):
    """Copy a src tree to the dst folder.

    Example:

    src = "themes/default/assets"
    dst = "output/assets"

    should copy "themes/defauts/assets/foo/bar" to
    "output/assets/foo/bar"

    if link_cutoff is set, then the links pointing at things
    *inside* that folder will stay as links, and links
    pointing *outside* that folder will be copied.
    """
    ignore = set(['.svn'])
    base_len = len(src.split(os.sep))
    for root, dirs, files in os.walk(src, followlinks=True):
        root_parts = root.split(os.sep)
        if set(root_parts) & ignore:
            continue
        dst_dir = os.path.join(dst, *root_parts[base_len:])
        makedirs(dst_dir)
        for src_name in files:
            if src_name in ('.DS_Store', 'Thumbs.db'):
                continue
            dst_file = os.path.join(dst_dir, src_name)
            src_file = os.path.join(root, src_name)
            yield {
                'name': dst_file,
                'file_dep': [src_file],
                'targets': [dst_file],
                'actions': [(copy_file, (src_file, dst_file, link_cutoff))],
                'clean': True,
            }


def copy_file(source, dest, cutoff=None):
    dst_dir = os.path.dirname(dest)
    makedirs(dst_dir)
    if os.path.islink(source):
        link_target = os.path.relpath(
            os.path.normpath(os.path.join(dst_dir, os.readlink(source))))
        # Now we have to decide if we copy the link target or the
        # link itself.
        if cutoff is None or not link_target.startswith(cutoff):
            # We copy
            shutil.copy2(source, dest)
        else:
            # We link
            if os.path.exists(dest) or os.path.islink(dest):
                os.unlink(dest)
            os.symlink(os.readlink(source), dest)
    else:
        shutil.copy2(source, dest)


def remove_file(source):
    if os.path.isdir(source):
        shutil.rmtree(source)
    elif os.path.isfile(source) or os.path.islink(source):
        os.remove(source)

# slugify is copied from
# http://code.activestate.com/recipes/
# 577257-slugify-make-a-string-usable-in-a-url-or-filename/
_slugify_strip_re = re.compile(r'[^\w\s-]')
_slugify_hyphenate_re = re.compile(r'[-\s]+')


def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.

    From Django's "django/template/defaultfilters.py".

    >>> print(slugify('\xe1\xe9\xed.\xf3\xfa'))
    aeiou

    >>> print(slugify('foo/bar'))
    foobar

    >>> print(slugify('foo bar'))
    foo-bar

    """
    if not isinstance(value, unicode_str):
        raise ValueError("Not a unicode object: {0}".format(value))
    value = unidecode(value)
    # WARNING: this may not be python2/3 equivalent
    # value = unicode(_slugify_strip_re.sub('', value).strip().lower())
    value = str(_slugify_strip_re.sub('', value).strip().lower())
    return _slugify_hyphenate_re.sub('-', value)


def unslugify(value):
    """
    Given a slug string (as a filename), return a human readable string
    """
    value = re.sub('^[0-9]+', '', value)
    value = re.sub('([_\-\.])', ' ', value)
    value = value.strip().capitalize()
    return value


# A very slightly safer version of zip.extractall that works on
# python < 2.6

class UnsafeZipException(Exception):
    pass


def extract_all(zipfile, path='themes'):
    pwd = os.getcwd()
    makedirs(path)
    os.chdir(path)
    with zip(zipfile) as z:
        namelist = z.namelist()
        for f in namelist:
            if f.endswith('/') and '..' in f:
                raise UnsafeZipException('The zip file contains ".." and is '
                                         'not safe to expand.')
        for f in namelist:
            if f.endswith('/'):
                makedirs(f)
            else:
                z.extract(f)
    os.chdir(pwd)


def to_datetime(value, tzinfo=None):
    try:
        if not isinstance(value, datetime.datetime):
            # dateutil does bad things with TZs like UTC-03:00.
            dateregexp = re.compile(r' UTC([+-][0-9][0-9]:[0-9][0-9])')
            value = re.sub(dateregexp, r'\1', value)
            value = dateutil.parser.parse(value)
        if not value.tzinfo:
            value = value.replace(tzinfo=tzinfo)
        return value
    except Exception:
        raise ValueError('Unrecognized date/time: {0!r}'.format(value))


def get_tzname(dt):
    """
    Given a datetime value, find the name of the time zone.

    DEPRECATED: This thing returned basically the 1st random zone
    that matched the offset.
    """
    return dt.tzname()


def current_time(tzinfo=None):
    if tzinfo is not None:
        dt = datetime.datetime.utcnow()
        dt = tzinfo.fromutc(dt)
    else:
        dt = datetime.datetime.now(dateutil.tz.tzlocal())
    return dt


def apply_filters(task, filters):
    """
    Given a task, checks its targets.
    If any of the targets has a filter that matches,
    adds the filter commands to the commands of the task,
    and the filter itself to the uptodate of the task.
    """

    def filter_matches(ext):
        for key, value in list(filters.items()):
            if isinstance(key, (tuple, list)):
                if ext in key:
                    return value
            elif isinstance(key, (bytes_str, unicode_str)):
                if ext == key:
                    return value
            else:
                assert False, key

    for target in task.get('targets', []):
        ext = os.path.splitext(target)[-1].lower()
        filter_ = filter_matches(ext)
        if filter_:
            for action in filter_:
                def unlessLink(action, target):
                    if not os.path.islink(target):
                        if isinstance(action, Callable):
                            action(target)
                        else:
                            subprocess.check_call(action % target, shell=True)

                task['actions'].append((unlessLink, (action, target)))
    return task


def get_crumbs(path, is_file=False, index_folder=None):
    """Create proper links for a crumb bar.
    index_folder is used if you want to use title from index file
    instead of folder name as breadcrumb text.

    >>> crumbs = get_crumbs('galleries')
    >>> len(crumbs)
    1
    >>> print('|'.join(crumbs[0]))
    #|galleries

    >>> crumbs = get_crumbs(os.path.join('galleries','demo'))
    >>> len(crumbs)
    2
    >>> print('|'.join(crumbs[0]))
    ..|galleries
    >>> print('|'.join(crumbs[1]))
    #|demo

    >>> crumbs = get_crumbs(os.path.join('listings','foo','bar'), is_file=True)
    >>> len(crumbs)
    3
    >>> print('|'.join(crumbs[0]))
    ..|listings
    >>> print('|'.join(crumbs[1]))
    .|foo
    >>> print('|'.join(crumbs[2]))
    #|bar
    """

    crumbs = path.split(os.sep)
    _crumbs = []
    if is_file:
        for i, crumb in enumerate(crumbs[-3::-1]):  # Up to parent folder only
            _path = '/'.join(['..'] * (i + 1))
            _crumbs.append([_path, crumb])
        _crumbs.insert(0, ['.', crumbs[-2]])  # file's folder
        _crumbs.insert(0, ['#', crumbs[-1]])  # file itself
    else:
        for i, crumb in enumerate(crumbs[::-1]):
            _path = '/'.join(['..'] * i) or '#'
            _crumbs.append([_path, crumb])
    if index_folder and hasattr(index_folder, 'parse_index'):
        folder = path
        for i, crumb in enumerate(crumbs[::-1]):
            if folder[-1] == os.sep:
                folder = folder[:-1]
            index_post = index_folder.parse_index(folder)
            folder = folder.replace(crumb, '')
            if index_post:
                crumb = index_post.title() or crumb
            _crumbs[i][1] = crumb
    return list(reversed(_crumbs))


def get_asset_path(path, themes, files_folders={'files': ''}):
    """
    .. versionchanged:: 6.1.0

    Checks which theme provides the path with the given asset,
    and returns the "real", absolute path to the asset.

    If the asset is not provided by a theme, then it will be checked for
    in the FILES_FOLDERS

    >>> print(get_asset_path('assets/css/rst.css', ['bootstrap', 'base']))
    /.../nikola/data/themes/base/assets/css/rst.css

    >>> print(get_asset_path('assets/css/theme.css', ['bootstrap', 'base']))
    /.../nikola/data/themes/bootstrap/assets/css/theme.css

    >>> print(get_asset_path('nikola.py', ['bootstrap', 'base'], {'nikola': ''}))
    /.../nikola/nikola.py

    >>> print(get_asset_path('nikola/nikola.py', ['bootstrap', 'base'], {'nikola':'nikola'}))
    None

    """
    for theme_name in themes:
        candidate = os.path.join(
            get_theme_path(theme_name),
            path
        )
        if os.path.isfile(candidate):
            return candidate
    for src, rel_dst in files_folders.items():
        candidate = os.path.abspath(os.path.join(src, path))
        if os.path.isfile(candidate):
            return candidate

    # whatever!
    return None


class LocaleBorg(object):
    """
    Provides locale related services and autoritative current_lang,
    where current_lang is the last lang for which the locale was set.

    current_lang is meant to be set only by LocaleBorg.set_locale

    python's locale code should not be directly called from code outside of
    LocaleBorg, they are compatibilty issues with py version and OS support
    better handled at one central point, LocaleBorg.

    In particular, don't call locale.setlocale outside of LocaleBorg.

    Assumptions:
        We need locales only for the languages there is a nikola translation.
        We don't need to support current_lang through nested contexts

    Usage:
        # early in cmd or test execution
        LocaleBorg.initialize(...)

        # any time later
        lang = LocaleBorg().<service>

    Available services:
        .current_lang : autoritative current_lang , the last seen in set_locale
        .set_locale(lang) : sets current_lang and sets the locale for lang
        .get_month_name(month_no, lang) : returns the localized month name

    NOTE: never use locale.getlocale() , it can return values that
    locale.setlocale will not accept in Windows XP, 7 and pythons 2.6, 2.7, 3.3
    Examples: "Spanish", "French" can't do the full circle set / get / set
    That used to break calendar, but now seems is not the case, with month at least
    """
    @classmethod
    def initialize(cls, locales, initial_lang):
        """
        locales : dict with lang: locale_n
            the same keys as in nikola's TRANSLATIONS
            locale_n a sanitized locale, meaning
                locale.setlocale(locale.LC_ALL, locale_n) will succeed
                locale_n expressed in the string form, like "en.utf8"
        """
        assert initial_lang is not None and initial_lang in locales
        cls.reset()
        cls.locales = locales

        # needed to decode some localized output in py2x
        encodings = {}
        for lang in locales:
            locale.setlocale(locale.LC_ALL, locales[lang])
            loc, encoding = locale.getlocale()
            encodings[lang] = encoding

        cls.encodings = encodings
        cls.__shared_state['current_lang'] = initial_lang
        cls.initialized = True

    @classmethod
    def reset(cls):
        """used in testing to not leak state between tests"""
        cls.locales = {}
        cls.encodings = {}
        cls.__shared_state = {'current_lang': None}
        cls.initialized = False

    def __init__(self):
        if not self.initialized:
            raise Exception("Attempt to use LocaleBorg before initialization")
        self.__dict__ = self.__shared_state

    def set_locale(self, lang):
        """Sets the locale for language lang, returns ''

        in linux the locale encoding is set to utf8,
        in windows that cannot be guaranted.
        In either case, the locale encoding is available in cls.encodings[lang]
        """
        # intentional non try-except: templates must ask locales with a lang,
        # let the code explode here and not hide the point of failure
        # Also, not guarded with an if lang==current_lang because calendar may
        # put that out of sync
        locale_n = self.locales[lang]
        self.__shared_state['current_lang'] = lang
        locale.setlocale(locale.LC_ALL, locale_n)
        return ''

    def get_month_name(self, month_no, lang):
        """returns localized month name in an unicode string"""
        if sys.version_info[0] == 3:  # Python 3
            with calendar.different_locale(self.locales[lang]):
                s = calendar.month_name[month_no]
            # for py3 s is unicode
        else:  # Python 2
            with calendar.TimeEncoding(self.locales[lang]):
                s = calendar.month_name[month_no]
            enc = self.encodings[lang]
            if not enc:
                enc = 'UTF-8'

            s = s.decode(enc)
        # paranoid about calendar ending in the wrong locale (windows)
        self.set_locale(self.current_lang)
        return s


class ExtendedItem(rss.RSSItem):

    def __init__(self, **kw):
        self.creator = kw.pop('creator')
        # It's an old style class
        return rss.RSSItem.__init__(self, **kw)

    def publish_extensions(self, handler):
        if self.creator:
            handler.startElement("dc:creator", {})
            handler.characters(self.creator)
            handler.endElement("dc:creator")


# \x00 means the "<" was backslash-escaped
explicit_title_re = re.compile(r'^(.+?)\s*(?<!\x00)<(.*?)>$', re.DOTALL)


def split_explicit_title(text):
    """Split role content into title and target, if given.

       From Sphinx's "sphinx/util/nodes.py"
    """
    match = explicit_title_re.match(text)
    if match:
        return True, match.group(1), match.group(2)
    return False, text, text


def first_line(doc):
    """extract first non-blank line from text, to extract docstring title"""
    if doc is not None:
        for line in doc.splitlines():
            striped = line.strip()
            if striped:
                return striped
    return ''


def demote_headers(doc, level=1):
    """Demote <hN> elements by one."""
    if level == 0:
        return doc
    elif level > 0:
        r = range(1, 7 - level)
    elif level < 0:
        r = range(1 + level, 7)
    for i in reversed(r):
        # html headers go to 6, so we can’t “lower” beneath five
            elements = doc.xpath('//h' + str(i))
            for e in elements:
                e.tag = 'h' + str(i + level)


def get_root_dir():
    """Find root directory of nikola installation by looking for conf.py"""
    root = os.getcwd()

    while True:
        if os.path.exists(os.path.join(root, 'conf.py')):
            return root
        else:
            basedir = os.path.split(root)[0]
            # Top directory, already checked
            if basedir == root:
                break
            root = basedir

    return None


def get_translation_candidate(config, path, lang):
    """
    Return a possible path where we can find the translated version of some page
    based on the TRANSLATIONS_PATTERN configuration variable.

    >>> config = {'TRANSLATIONS_PATTERN': '{path}.{lang}.{ext}', 'DEFAULT_LANG': 'en', 'TRANSLATIONS': {'es':'1', 'en': 1}}
    >>> print(get_translation_candidate(config, '*.rst', 'es'))
    *.es.rst
    >>> print(get_translation_candidate(config, 'fancy.post.rst', 'es'))
    fancy.post.es.rst
    >>> print(get_translation_candidate(config, '*.es.rst', 'es'))
    *.es.rst
    >>> print(get_translation_candidate(config, '*.es.rst', 'en'))
    *.rst
    >>> print(get_translation_candidate(config, 'cache/posts/fancy.post.es.html', 'en'))
    cache/posts/fancy.post.html
    >>> print(get_translation_candidate(config, 'cache/posts/fancy.post.html', 'es'))
    cache/posts/fancy.post.es.html
    >>> print(get_translation_candidate(config, 'cache/stories/charts.html', 'es'))
    cache/stories/charts.es.html
    >>> print(get_translation_candidate(config, 'cache/stories/charts.html', 'en'))
    cache/stories/charts.html

    >>> config = {'TRANSLATIONS_PATTERN': '{path}.{ext}.{lang}', 'DEFAULT_LANG': 'en', 'TRANSLATIONS': {'es':'1', 'en': 1}}
    >>> print(get_translation_candidate(config, '*.rst', 'es'))
    *.rst.es
    >>> print(get_translation_candidate(config, '*.rst.es', 'es'))
    *.rst.es
    >>> print(get_translation_candidate(config, '*.rst.es', 'en'))
    *.rst
    >>> print(get_translation_candidate(config, 'cache/posts/fancy.post.html.es', 'en'))
    cache/posts/fancy.post.html
    >>> print(get_translation_candidate(config, 'cache/posts/fancy.post.html', 'es'))
    cache/posts/fancy.post.html.es

    """
    # FIXME: this is rather slow and this function is called A LOT
    # Convert the pattern into a regexp
    pattern = config['TRANSLATIONS_PATTERN']
    # This will still break if the user has ?*[]\ in the pattern. But WHY WOULD HE?
    pattern = pattern.replace('.', r'\.')
    pattern = pattern.replace('{path}', '(?P<path>.+?)')
    pattern = pattern.replace('{ext}', '(?P<ext>[^\./]+)')
    pattern = pattern.replace('{lang}', '(?P<lang>{0})'.format('|'.join(config['TRANSLATIONS'].keys())))
    m = re.match(pattern, path)
    if m and all(m.groups()):  # It's a translated path
        p, e, l = m.group('path'), m.group('ext'), m.group('lang')
        if l == lang:  # Nothing to do
            return path
        elif lang == config['DEFAULT_LANG']:  # Return untranslated path
            return '{0}.{1}'.format(p, e)
        else:  # Change lang and return
            return config['TRANSLATIONS_PATTERN'].format(path=p, ext=e, lang=lang)
    else:
        # It's a untranslated path, assume it's path.ext
        p, e = os.path.splitext(path)
        e = e[1:]  # No initial dot
        if lang == config['DEFAULT_LANG']:  # Nothing to do
            return path
        else:  # Change lang and return
            return config['TRANSLATIONS_PATTERN'].format(path=p, ext=e, lang=lang)


def write_metadata(data):
    """Write metadata."""
    order = ('title', 'slug', 'date', 'tags', 'link', 'description', 'type')
    f = '.. {0}: {1}'
    meta = []
    for k in order:
        try:
            meta.append(f.format(k, data.pop(k)))
        except KeyError:
            pass

    # Leftover metadata (user-specified/non-default).
    for k, v in data.items():
        meta.append(f.format(k, v))

    meta.append('')

    return '\n'.join(meta)
