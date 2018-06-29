#! /usr/bin/env python
# coding=utf-8

#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.


import os

# Unix-like with GTK systems use gstreamer as media backend.
# gstreamer leaves applications to invoke XInitThreads()
# in libX11, and the wxWidgets wxMediaCtrl crashes
# with X errors so frequently it is unusable if that
# initialization is not done.
# Fortunately, it can probably be done here -- this seems
# to work
X11hack = None
if os.name == 'posix' and ('DISPLAY' in os.environ):
    # this env var has had no effect in my testing --
    # probably needs later version -- but leave it
    os.environ["GST_GL_XINITTHREADS"] = "1"

    import ctypes
    import ctypes.util
    X11hack = {
        "libname" : ctypes.util.find_library("X11") or "libX11.so",
        "lib_ptr" : None,
        "lib_fun" : None,
        "lib_ret" : None,
        "lib_err" : None
    }

    try:
        X11hack["lib_ptr"] = ctypes.cdll.LoadLibrary(X11hack["libname"])
        X11hack["lib_fun"] = X11hack["lib_ptr"].XInitThreads
        X11hack["lib_fun"].argtypes = []
        X11hack["lib_fun"].restype = ctypes.c_int # X11 'Status'

        try:
            X11hack["lib_ret"] = X11hack["lib_fun"]()
        except Exception as m:
            X11hack["lib_err"] = "Call Exception: {}".format(m)
        except:
            X11hack["lib_err"] = "Call Exception: unknown"

    except AttributeError:
        X11hack["lib_err"] = "AttributeError"
    except Exception as m:
        X11hack["lib_err"] = "Exception: {}".format(m)
    except:
        X11hack["lib_err"] = "Exception: unknown"

    if False and X11hack["lib_err"]:
        print("Cannot load {} : '{}'".format(
            X11hack["libname"], X11hack["lib_err"]))


import codecs
import copy
import math
import random
import re
import select
import shutil
import signal
import sys
import threading
import time
try:
    import urllib.error
    import urllib.parse
    import urllib.request
    uriopen = urllib.request.urlopen
    uri_unquote = urllib.parse.unquote
    uri_unquote_plus = urllib.parse.unquote_plus
    uri_parse = urllib.parse.urlparse
    v_urllib = 3
except ImportError:
    try:
        import urlparse
        uri_parse = urlparse.urlparse
        # arg! urllib2 is not a complete substitute for urllib
        import urllib
        #uri_unquote = urllib.unquote
        uri_unquote_plus = urllib.unquote_plus
        # zappa's boots say urlopen from urllib2 is preferred
        import urllib2
        uri_unquote = urllib2.unquote
        uriopen = urllib2.urlopen
        v_urllib = 2
    except ImportError:
        import urlparse
        uri_parse = urlparse.urlparse
        import urllib
        uriopen = urllib.urlopen
        v_urllib = 1
        uri_unquote = urllib.unquote
        uri_unquote_plus = urllib.unquote_plus

import wx
import wx.media
try:
    import wx.adv
    wxcombo = wx
    wxadv = wx.adv
    custom_data_fmt = wx.DataFormat
    phoenix = True
except ImportError:
    import wx.combo
    wxcombo = wx.combo
    wxadv = wx
    custom_data_fmt = wx.CustomDataFormat
    phoenix = False
from wx.lib.embeddedimage import PyEmbeddedImage

have_tagsmod = False
# mutagen is a media file tag module in pure python
if not have_tagsmod:
    try:
        import mutagen
        have_mutagen = True
        have_tagsmod = True
    except ImportError:
        have_mutagen = False


"""
sigh
"""

_in_msw = ('wxMSW' in wx.PlatformInfo)
_in_gtk = ('wxGTK' in wx.PlatformInfo)
_in_psx = (os.name == 'posix')
_in_xws = (_in_psx and ('DISPLAY' in os.environ))

# will often need to know whether interpreter is Python 3
py_v_is_3 = (sys.version_info.major >= 3)

# python version wrappers
if py_v_is_3:
    import queue
    q_fifo       = queue.Queue
    q_fifo_empty = queue.Empty
    q_fifo_full  = queue.Full
    def p_filt(*args):
        return list(filter(*args))
    def p_map(*args):
        return list(map(*args))
    def long(v):
        return int(v)
else:
    import Queue
    q_fifo       = Queue.Queue
    q_fifo_empty = Queue.Empty
    q_fifo_full  = Queue.Full
    def p_filt(*args):
        return filter(*args)
    def p_map(*args):
        return map(*args)

# wxPython version wrappers
if phoenix:
    general_droptarget_base = wx.DropTarget
    select_cursor = wx.Cursor
    # wxPython 4.x docs re. wx.QueueEvent and wx.PostEvent
    # state that wx.QueueEvent is safer across threads than
    # wx.PostEvent due to some possible issue with strings.
    # had been using wx.PostEvent w/o observed problems, but
    # use wx.QueueEvent if it is safer and _nearly_ equivalent
    # (difference is it is put in queue and not processed
    # immediately . . . should not be a problem here, but
    # watch it) . . .
    def put_thd_event(*args):
        return wx.QueueEvent(*args)
else:
    general_droptarget_base = wx.PyDropTarget
    select_cursor = wx.StockCursor
    # . . . OTOH, wxPython 3.x does not have wx.QueueEvent, and
    # wx.PostEvent has been regarded/stated as safe across threads
    def put_thd_event(*args):
        return wx.PostEvent(*args)

# As of wxPython 4.0.2 (Pheonix) wx.NewId() is deprecated --
# there was a discussion of the on the mailing list, June 2018
def new_wx_id():
    try:
        # this is a new replacement function for deprecated NewId();
        # note that return is not int, but object w/ __int__ method
        return wx.NewIdRef()
    except AttributeError:
        return wx.NewId()

"""
main proc to get the show on the road
"""

# this can be set for the wx.App class --
# used only for Unix w/ X Window System,
# ignored elsewise
x_helper_prog = None

##
## main function callable if this is imported as module,
## or herein in a if __name__ == '__main__': block
##
def wxmav_main(argv = None, x_help_path = None):
    if argv == None:
        argv = sys.argv

    if _in_xws and x_help_path != None:
        global x_helper_prog
        x_helper_prog = x_help_path

    # http://wiki.wxpython.org/MakingSampleApps:
    if "-inspection" in argv:
        import wx.lib.inspection
        wx.lib.inspection.InspectionTool().Show()

    app = TheAppClass(ac = len(argv), av = argv)
    app.MainLoop()
    # FPO: not reached
    return 0


"""
string handling
"""

filesys_encoding = sys.getfilesystemencoding() or 'utf_8'

_encoding_tuple_1 = (
"ascii",
"utf_7", "utf_8", "utf_8_sig",
"iso8859_15", "iso8859_16", "iso8859_14", "iso8859_13",
"iso8859_11", "iso8859_10", "iso8859_9", "iso8859_8",
"iso8859_7", "iso8859_6", "iso8859_5", "iso8859_4",
"iso8859_3", "iso8859_2", "latin_1",
"cp1252", "cp1258", "cp1257", "cp1256", "cp1255", "cp1254", "cp1253",
"cp1251", "cp1250", "cp1140", "cp1026", "cp1006", "cp950", "cp949",
"cp932", "cp875", "cp874", "cp869", "cp866", "cp865", "cp864", "cp863",
"cp862", "cp861", "cp860", "cp858", "cp857", "cp856", "cp855", "cp852",
"cp850", "cp775", "cp737", "cp720", "cp500", "cp437", "cp424", "cp037",
"utf_16", "utf_16_be", "utf_16_le",
"utf_32", "utf_32_be", "utf_32_le"
)
_encoding_tuple_2 = (
"mac_cyrillic", "mac_greek", "mac_iceland",
"mac_latin2", "mac_roman", "mac_turkish",
"big5hkscs", "big5",
"euc_jp", "euc_jis_2004", "euc_jisx0213", "euc_kr",
"gb2312", "gbk", "gb18030", "hz",
"iso2022_jp", "iso2022_jp_1", "iso2022_jp_2", "iso2022_jp_2004",
"iso2022_jp_3", "iso2022_jp_ext", "iso2022_kr",
"johab", "koi8_r", "koi8_u",
"ptcp154", "shift_jis", "shift_jis_2004", "shift_jisx0213"
)
_encoding_tuple_all = _encoding_tuple_1 + _encoding_tuple_2
python_encoding_tuple = _encoding_tuple_all

def find_display_encoding(s, ign_cmp = False, pref_enc = None):
    # if arg is python 'unicode' object then try to encode
    # it to utf-8; if that raises an exception then return
    # it unchanged with the bogus encoding 'unicode'
    # python 3 needs more testing
    if not py_v_is_3 and isinstance(s, unicode):
        try:
            #enc = filesys_encoding
            enc = 'utf_8'
            t = s.encode(enc)
            return (t, s, enc, 'strict')
        except:
            return (s, s, 'unicode', 'strict')
    elif py_v_is_3:
        # Will this encoding work w/ MSW?
        enc = filesys_encoding # 'utf_8'
        s = s.encode(enc, "surrogateescape")

    if pref_enc == None:
        pref_enc = filesys_encoding

    try:
        d = s.decode(pref_enc, 'strict')
        if ign_cmp or _bytes_cmp(s, d.encode(pref_enc)):
            return (d, s, pref_enc, 'strict')
    except:
        pass

    return _encoding_find_gspot(s, 'strict', ign_cmp)

def _bytes_cmp(a1, a2):
    return (bytes(a1) == bytes(a2))

def _encoding_find_gspot(s, dec_arg = 'strict', ign_cmp = False):
    for enc in python_encoding_tuple:
        try:
            d = s.decode(enc, dec_arg)
            if ign_cmp or _bytes_cmp(s, d.encode(enc)):
                return (d, s, enc, dec_arg)
        except:
            pass

    # not found
    if dec_arg == 'strict':
        return _encoding_find_gspot(s, 'replace', ign_cmp)
    elif dec_arg == 'replace':
        return _encoding_find_gspot(s, 'ignore', ign_cmp)

    return (None, s, None, dec_arg)

# class attempts to find a displayable version of
# a resource (e.g., filesystem or URI) name -- this
# can be needed if e.g. a Unix system set up for UTF-8
# still has filesystem entries with iso-8859-* strings,
# or a MSW system encounters UTF-8 from a playlist with
# URLs. etc.
# The original unmolested string is stored, a display
# version is stored if decoding succeeds, and details
# of conversion are stored: codec that succeeded (self.codec),
# the codecs module error method (strict or replace or ignore),
# and boolean self.pass_cmp indicating whether the display form
# compared equal to orginal when re-encoded
#
# There is, of course, a large possibility that decoding success
# happened with the wrong codec and the display string is garbage.
# It should, at least, be displayable garbage (good enough for PR:
# 'If you can't baffle them with brilliance, befuddle them
# with bullshit.').
class resourcename_with_displayname:
    fail_string = "[string has no display form]"
    def __init__(self, fsname):
        self.orig = fsname
        disp, orig, cod, meth = find_display_encoding(fsname)
        if disp == None:
            disp, orig, cod, meth = find_display_encoding(fsname, True)
            self.pass_cmp = False
        else:
            self.pass_cmp = True
        self.disp = disp
        self.orig = orig
        self.codec = cod
        self.meth = meth

    def succeeded(self):
        return (self.disp != None and self.pass_cmp)

    def half_succeeded(self):
        return (self.disp != None and not self.pass_cmp)

    def failed(self):
        return self.disp == None

    def get_disp_str(self, allow_none = False):
        if not self.disp and not allow_none:
            return resourcename_with_displayname.fail_string
        return self.disp


# Charset and string hacks
# Python 2.7 and 3.x differ significantly --
# moreover Unix and MSW differ in that on Unix the following
# conversions are needed or encoding exceptions are raised,
# while on MSW the conversions cause encoding exceptions
# that do not happen w/o conversion; hence the conditional here
_ucode_type = 'utf-8'

if not py_v_is_3:
    try:
        unicode('\xc3\xb6\xc3\xba\xc2\xa9', _ucode_type)
    except UnicodeEncodeError:
        _ucode_type = None
    except NameError:
        # NameError happens w/ py 3.x,
        # should not happen w/ 2.x; if it
        # happens, assume version check
        # was bogus and try (probably in
        # vain) to proceed as with py 3.x
        py_v_is_3 = True
        unicode = str
else:
    unicode = str

# use _T() or _() for all* strings for string safety -- _("") for
# strings that should get language translation, and _T("") for
# string that should not be translated -- as in wxWidgets C++
if not py_v_is_3:
    def _T(s):
        try:
            return s.decode(_ucode_type, 'replace')
        except:
            pass

        try:
            return _U(s).decode(_ucode_type, 'replace')
        except:
            pass

        try:
            return unicode(s, _ucode_type)
        except:
            pass

        return s

    def _U(s):
        try:
            return s.encode(_ucode_type, 'replace')
        except:
            return bytes(s)

    # F: file path/name -- do not *code -- rely on os, or
    # user, to do right thing -- open/close() should work
    # even if the path is not unicode (read/write might be
    # another thing ...)
    def _F(s):
        return bytes(s)

    # for strings pass to wx that cause trouble after _T()
    # like set_statusbar
    def _WX(s):
        if not _in_msw:
            s = resourcename_with_displayname(s).get_disp_str()
        if False and _in_msw:
            if isinstance(s, unicode):
                return s
            try:
                return s.decode(_ucode_type, 'replace')
            except:
                pass
        return s

    def fd_write(fd, s):
        # sys.version
        # 2.7.13 (default, Jun 26 2017, 10:20:05) \n
        #  [GCC 7.1.1 20170622 (Red Hat 7.1.1-3)]
        os.write(fd, _T(s).encode(_ucode_type))
        # sys.version
        #
        #os.write(fd, s)

else:
    def _T(s):
        try:
            return s.decode('utf-8', 'replace')
        except:
            return str(s)

    def _U(s):
        return s

    # F: file path/name
    def _F(s):
        return s

    def _WX(s):
        return s

    def fd_write(fd, s):
        os.write(fd, _Tnec(s).encode('utf_8'))

# use _T as necessary
if not py_v_is_3:
    def _Tnec(s):
        if isinstance(s, str):
            return _T(s)
        return s
else:
    def _Tnec(s):
        if not isinstance(s, str):
            return _T(s)
        return s

# inefficient string equality test, unicode vs. ascii safe
def s_eq(s1, s2):
    if _Tnec(s1) == _Tnec(s2):
        return True
    return False

def s_ne(s1, s2):
    if _Tnec(s1) != _Tnec(s2):
        return True
    return False

# E.g.: _("Sounds more poetic in Klingon.")
# TODO: other hookup needed for i18n -- can wait
# until translation volunteers materialize
#_ = wx.GetTranslation
def _(s):
    return _T(wx.GetTranslation(s))


# Coding problems extend to reading and writing, the latter
# in particular raising encoding exceptions; the codecs module
# has an open() that returns an object with a mostly compatible
# r/w interface, _but_ cannot accept "[rw]t", text translation
# mode (i.e. \r\n on MSW).  This is a big problem because this
# program wants to read and write playlist files which should
# be line oriented editable text.
#
# So, try some vile ugly hacks here to see if an at least
# partial work-around is possible

def cv_open_r(name):
    # madness ... see comment at cv_open_w below . . .
    if not _in_msw or _ucode_type == None:
        return open(name, 'r')
    else:
        return codecs.open(name, encoding = _ucode_type, mode = 'r')

def cv_open_w(name):
    # . . . insanity: on msw codecs.open is needed to *read* utf8
    # _BUT_ but to *write* utf8 using codecs.open with python 2.7
    # writes garbage and and plain open must be used, _but_ with
    # python 3.x plain open writes garbage and codecs.open must
    # be used (best described by the quaint old expression
    # "I don't know whether to shit or wind my watch.")
    if not py_v_is_3 or (not _in_msw or _ucode_type == None):
        return open(name, 'wt')
    else:
        return codecs.open(name, encoding = _ucode_type, mode = 'w')


"""
    about dialog data
"""

# version globals: r/o
version_string = _T("1.0.0")
version_name   = _("Parallel Coils")
version_mjr    = 1
version_mjrrev = 0
version_mnr    = 0
version_mnrrev = 0
version = (
    version_mjr<<24|version_mjrrev<<16|version_mnr<<8|version_mnrrev)
maintainer_name = _T("Ed Hynan")
maintainer_addr = _T("<edhynan@gmail.com>")
copyright_years = _T("2017")
program_site    = _T("https://github.com/ehy/wxmav")
program_desc    = _T("(WX) M Audio/Visual Media Player.")
program_devs    = [maintainer_name]


"""
some useful standalone functions
"""

# make a typical hr:mn:ss string; arg 'tm' must be in milliseconds,
# 'with_ms' will include .ms; append_orig appends " ([tm]ms)"
def mk_colon_time_str(tm, with_ms = False, append_orig = False):
    tm = int(tm)
    ss = tm / 1000
    ms = tm % 1000
    if not with_ms:
        ss += int((ms + 500) / 1000)
    mn = int(ss / 60)
    ss = int(ss % 60)
    hr = int(mn / 60)
    mn = int(mn % 60)

    if with_ms:
        r = _T("{hr:02d}:{mn:02d}:{ss:02d}.{ms:03d}").format(
                hr = hr, mn = mn, ss = ss, ms = int(ms))
    else:
        r = _T("{hr:02d}:{mn:02d}:{ss:02d}").format(
                hr = hr, mn = mn, ss = ss)

    if append_orig:
        r += _T(" ({}ms)").format(tm)

    return r


if not _in_psx:
    cdr_ls_dir = os.listdir
    cdr_walk_dir = os.walk
else:
    # alternative to os.listdir so that r'.' can be used as arg ...
    # pending a better solution to os.listdir returning coded results
    # posix systems only until tested elsewhere
    def cdr_ls_dir(d, allow_reg = False, throw = True):
        pwd = os.getcwd()
        try:
            os.chdir(d)
            r = os.listdir(r'.')
            os.chdir(pwd)
            return r
        except:
            os.chdir(pwd)
            if throw:
                raise
            if allow_reg:
                try:
                    return os.listdir(d)
                except:
                    if throw:
                        raise

        return None

    # minimal substitue for os.walk, just to use cdr_ls_dir
    # for each dir listing
    class cdr_walk_dir():
        def __init__(self, a_dir, followlinks = False):
            self.d = a_dir
            self.first = True
            self.nx = None
            self.oklinks = followlinks

        def _get_first(self, d):
            cur = cdr_ls_dir(d)
            if cur == None:
                return None

            fl = []
            self.dl = []
            for c in cur:
                cf = os.path.join(_T(d), _T(c))
                if os.path.isdir(cf):
                    if self.oklinks or not os.path.islink(c):
                        self.dl.append(c)
                else:
                    fl.append(c)

            return (d, self.dl, fl)

        def next(self):
            if self.first:
                self.first = False
                r = self._get_first(self.d)
                if r == None:
                    raise StopIteration
                return r

            if self.nx != None:
                try:
                    return self.nx.next()
                except StopIteration:
                    self.nx = None

            while self.dl:
                d = os.path.join(self.d, _T(self.dl[0]))
                del self.dl[0]
                self.nx = cdr_walk_dir(d, followlinks = self.oklinks)
                try:
                    return self.nx.next()
                except StopIteration:
                    continue

            raise StopIteration

        if py_v_is_3:
            def __next__(self): return self.next()

        def __iter__(self):
            return self


# invoke readlines on fd,
# optionally strip lines, optionally close fd, optionally filter blanks:
def fd2linelist(fd,
                do_strip = False, do_close = False, wantblanks = False):
    fun = fd.readlines
    flst = [ln.strip() for ln in fun()] if do_strip else fun()
    # argh! py3 is yielding bytes rather than str, and a subsequent
    # re.match is raising exception because don't like bytes, etc.;
    # lousy hack conversion
    if py_v_is_3:
        for i, l in enumerate(flst):
            flst[i] = _T(l)
    wx.GetApp().prdbg(_T("fd2linelist: lst len {}").format(len(flst)))

    if do_close:
        fd.close()

    return flst if wantblanks else p_filt(len, flst)

# get fd from uri -- caller should catch Exception
def uri_open_fd(nm, prx = False):
    fd = None

    if not prx:
        prx = {}

    if v_urllib == 1:
        fd = urllib.urlopen(url = nm, proxies = prx)
    elif v_urllib == 2:
        hdlr = urllib2.ProxyHandler(prx)
        opnr = urllib2.build_opener(hdlr)
        fd = opnr.open(nm)
    elif v_urllib == 3:
        hdlr = urllib.request.ProxyHandler(prx)
        opnr = urllib.request.build_opener(hdlr)
        fd = opnr.open(nm)
    else:
        raise Exception(_("Cannot open URI ({})").format(nm))

    return fd

# can't os.fdopen the urllib fd -- exceptions for expected attributes
## get file object from uri -- should catch OSError and Exception
#def uri_open_file(nm, prx = False):
#    return os.fdopen(uri_open_fd(nm, prx), "r", 0)

# get a list of lines from uri -- should catch Exception
def urifile2linelist(nm, prx = False, wantblanks = False):
    return fd2linelist(uri_open_fd(nm, prx),
                    do_strip=True, do_close=True, wantblanks=wantblanks)

# use if testable return is wanted, (value, error) one will be None:
def urifile2linelist_tup(nm, prx = False, wantblanks = False):
    try:
        return (urifile2linelist(nm, prx, wantblanks=wantblanks), None)
    except (OSError, IOError) as e: #, URLError) as e:
        return (None, _("error with '{nm}': {ex}").format(nm=nm, ex=e))
    except Exception as s:
        return (None, _("exception: {}").format(s))
    except:
        return (None, _("exception: error with '{}'").format(nm))

# use if exceptions are wanted:
def textfile2linelist(nm, wantblanks = False):
    return fd2linelist(cv_open_r(nm),
                    do_strip=True, do_close=True, wantblanks=wantblanks)

# use if testable return is wanted, (value, error) one will be None:
def textfile2linelist_tup(nm, wantblanks = False):
    try:
        return (textfile2linelist(nm, wantblanks=wantblanks), None)
    except (OSError, IOError) as e:
        return (None, _("error with '{nm}': {ex}").format(nm=nm, ex=e))
    except Exception as s:
        return (None, _("exception: {}").format(s))
    except:
        return (None, _("exception: error with '{}'").format(nm))


"""
    classes for media tags
"""

class media_tags:
    """Media tags base which if instantiated directly simply
    yields failure indicative values"""
    def __init__(self, fname = None):
        """Simply assign a small set of members to None, False etc.
        so that using code can simply test them"""
        self.fname = fname
        self.is_ok = False
        self.tracknumber = self.title = None
        self.artist = self.album = None

    def from_file(self, fname):
        return False

    def ok(self):
        return self.is_ok

    def processed_title(self, tr_wid = 2, tr_sep = '. '):
        return get_processed_title(self, tr_wid, tr_sep)

    def get_album(self):
        return None

    def get_tracknumber(self):
        return None

    def get_title(self):
        return None

    def get_artist(self):
        return None

    def get_genre(self):
        return None

    def get_date(self):
        return None

    def get_tracknum_int(self):
        return None

if have_mutagen:
    class media_tags_mutagen(media_tags):
        """subclass of media_tags attempting to use the
        mutagen module -- do not instantiate directly unless
        caertain that mutagen is available"""
        def __init__(self, fname = None):
            media_tags.__init__(self, fname)

            if fname:
                self.from_file(fname)

        def from_file(self, fname):
            self.fname = fname

            try:
                mg = mutagen.File(fname, easy = True)
            except:
                return False

            try:
                if py_v_is_3:
                    ii = mg.items()
                else:
                    ii = mg.iteritems()
                for k, v in ii:
                    if isinstance(v, list):
                        v = _T('; ').join(v)
                    if k == 'album':
                        self.album = v
                    elif k == 'tracknumber':
                        # Note: not using possible joined list:
                        self.tracknumber = mg[k]
                    elif k == 'title':
                        self.title = v
                    elif k == 'artist':
                        self.artist = v
                    elif k == 'genre':
                        self.genre = v
                    elif k == 'date':
                        self.date = v
            except:
                return False

            self.is_ok = (self.title != None and self.title)

            return self.is_ok

        def get_album(self):
            try:
                return self.album
            except AttributeError:
                return None

        def get_tracknumber(self):
            try:
                return self.tracknumber
            except AttributeError:
                return None

        def get_title(self):
            try:
                return self.title
            except AttributeError:
                return None

        def get_artist(self):
            try:
                return self.artist
            except AttributeError:
                return None

        def get_genre(self):
            try:
                return self.genre
            except AttributeError:
                return None

        def get_date(self):
            try:
                return self.date
            except AttributeError:
                return None

        def get_tracknum_int(self):
            try:
                tn = self.tracknumber
            except AttributeError:
                return None

            if tn is None:
                return None

            if isinstance(tn, list):
                if len(tn) == 1:
                    tn = tn[0]
                else:
                    tn = _T(' ').join(tn)
                    m = re.search(_T(r"\b([0-9]+)\b"), _T(tn))
                    if m:
                        tn = m.group(1)
                    else:
                        tn = None

            if tn is None:
                return None

            # not done yet: some tags might not be simple decimal
            # digits, but something like '1/7' or 'screw you' so
            # so try to filter with a regexp, then convert to
            # int in a try block
            m = re.search(_T(r'\b([0-9]+)(?:[^0-9]+[0-9]*)?'), _T(tn))
            if m:
                tn = m.group(1)
            try:
                return int(tn)
            except:
                pass

            return None


# return a media tags object -- possibly one that merely
# fails if tags module was not loaded
def get_media_tags_obj(fname):
    if have_mutagen:
        return media_tags_mutagen(fname)
    return media_tags(fname)

# for a list of AVItem in arg avi, return a tuple with a list
# of equal length, where each item is a media_tags object if
# that object is OK, else None, and with a count of list members
# that contain an ok tag object
def get_tags_for_avitems(avi):
    ret = []
    cnt = 0

    if not isinstance(avi, list):
        return (ret, cnt)

    for i in avi:
        v = None
        tags = get_media_tags_obj(i.resname)
        if tags.ok():
            cnt += 1
            v = tags
        ret.append(v)

    return (ret, cnt)

# for a media_tag object, get a title string which might be
# the title tag alone, or prepended with the track number if
# it is present; return None if title is not available --
# arg tr_wid will be the format width of the (possible) track
# number, and tr_sep will appear between number and title
# (note that if space is wanted it must be included in tr_sep)
def get_processed_title(tags, tr_wid = 2, tr_sep = '. '):
    if not tags.title:
        return None

    t = tags.title

    if isinstance(t, list):
        t = _T('; ').join(t)
        if not t:
            return None

    tn = tags.get_tracknum_int() # None or int()
    if tn != None:
        try:
            t = _T('{num:0{wid}d}{sep}{title}').format(
                            wid = tr_wid, num = tn,
                            sep = _T(tr_sep), title = _T(t)
                            )
        except:
            pass

    return t


if _in_xws:
    # this is for freedesktop.org MPRIS2 support
    def get_xesam_map(fname):
        tg = get_media_tags_obj(fname)

        u = _T(fname)
        if os.path.isfile(u):
            u = _T("file://") + _Tnec(os.path.abspath(u))

        xm = {
            "album" :           tg.get_album(),
            #"albumArtist" :     None,
            "artist" :          tg.get_artist(),
            #"asText" :          None,
            #"audioBPM" :        None,
            #"autoRating" :      None,
            #"comment" :         None,
            #"composer" :        None,
            #"contentCreated" :  tg.get_date(), # not correct
            #"discNumber" :      None,
            #"firstUsed" :       None,
            "genre" :           tg.get_genre(),
            #"lastUsed" :        None,
            #"lyricist" :        None,
            "title" :           tg.get_title(),
            "trackNumber" :     tg.get_tracknum_int(),
            "url" :             u,
            #"useCount" :        None,
            #"userRating" :      None,
            "DUMMY" : None
        }

        return xm


"""
    classes and data Unix and MPRIS2
"""
if _in_xws:
    # gstreamer URI schemes (might be incomplete)
    gst_uri_schemes = ["file", "rtp", "rtsp", "http", "https"]
    # gstreamer mime types:
    # https://gstreamer.freedesktop.org/documentation/ [...cont...]
    #  plugin-development/advanced/media-types.html
    gst_mime = [
    "audio/x-ac3",  #AC-3 or A52 audio streams.
    "audio/x-adpcm",    #ADPCM Audio streams.
    "audio/x-cinepak",  #Audio as provided in a Cinepak (Quicktime) stream.
    "audio/x-dv",   #Audio as provided in a Digital Video stream.
    "audio/x-flac", #Free Lossless Audio codec (FLAC).
    "audio/x-gsm",  #Data encoded by the GSM codec.
    "audio/x-alaw", #A-Law Audio.
    "audio/x-mulaw",    #Mu-Law Audio.
    "audio/x-mace", #MACE Audio (used in Quicktime).
    "audio/mpeg",   #Audio data compressed using the MPEG audio encoding scheme.
    "audio/x-qdm2", #Data encoded by the QDM version 2 codec.
    "audio/x-pn-realaudio", #Realmedia Audio data.
    "audio/x-speex",    #Data encoded by the Speex audio codec
    "audio/x-vorbis",   #Vorbis audio data
    "audio/x-wma",  #Windows Media Audio
    "audio/x-paris",    #Ensoniq PARIS audio
    "audio/x-svx",  #Amiga IFF / SVX8 / SV16 audio
    "audio/x-nist", #Sphere NIST audio
    "audio/x-voc",  #Sound Blaster VOC audio
    "audio/x-ircam",    #Berkeley/IRCAM/CARL audio
    "audio/x-w64",  #Sonic Foundry's 64 bit RIFF/WAV
    "video/x-raw",  #Unstructured and uncompressed raw video data.
    "video/x-3ivx", #3ivx video.
    "video/x-divx", #DivX video.
    "video/x-dv",   #Digital Video.
    "video/x-ffv",  #FFMpeg video.
    "video/x-h263", #H-263 video.
    "video/x-h264", #H-264 video.
    "video/x-huffyuv",  #Huffyuv video.
    "video/x-indeo",    #Indeo video.
    "video/x-intel-h263",   #H-263 video.
    "video/x-jpeg", #Motion-JPEG video.
    "video/mpeg",   #MPEG video.
    "video/x-msmpeg",   #Microsoft MPEG-4 video deviations.
    "video/x-msvideocodec", #Microsoft Video 1 (oldish codec).
    "video/x-pn-realvideo", #Realmedia video.
    "video/x-rle",  #RLE animation format.
    "video/x-svq",  #Sorensen Video.
    "video/x-tarkin",   #Tarkin video.
    "video/x-theora",   #Theora video.
    "video/x-vp3",  #VP-3 video.
    "video/x-wmv",  #Windows Media Video
    "video/x-xvid", #XviD video.
    "video/x-ms-asf",   #Advanced Streaming Format (ASF).
    "video/x-msvideo",  #AVI.
    "video/x-dv",   #Digital Video.
    "video/x-matroska", #Matroska.
    "video/mpeg",   #Motion Pictures Expert Group System Stream.
    "application/ogg",  #Ogg.
    "video/quicktime",  #Quicktime.
    "application/vnd.rn-realmedia", #RealMedia.
    "audio/x-wav",  #WAV.
    # Added EH -- additional
    "video/x-flv"   # Is this correct?
    ]

    #
    class IODescriptorPair:
        """Pass this possibly by posted message across threads
        to the application object when poll/select indicates
        a read is ready on the input descriptor for MPRIS2 in
        the X helper coprocess -- contains both read and write
        descriptors so that on receipt app can read and respond
        NOTE: do not close descriptors
        """
        def __init__(self, read_desc, write_desc):
            self.fd_rd = read_desc
            self.fd_wr = write_desc

        def get_fds(self):
            """Return tuple (read, write)"""
            return (self.fd_rd, self.fd_wr)

        def set_fds(self, rd = -1, wr = -1):
            """assign fds; e.g., -1, -1"""
            self.fd_rd = rd
            self.fd_wr = wr

        def close_rd(self):
            if self.fd_rd >= 0:
                os.close(self.fd_rd)
                self.fd_rd = -1

        def close_wr(self):
            if self.fd_wr >= 0:
                os.close(self.fd_wr)
                self.fd_wr = -1

        def close(self):
            self.close_rd()
            self.close_wr()

"""
    classes for data type and file IO
"""

class UniqueSet:
    def __init__(self):
        self.set = set()

    def check(self, val, put = False):
        if val in self.set:
            return True
        if put == True:
            self.set.add(val)
        return False

    def remove(self, val):
        if val in self.set:
            self.set.discard(val)
            return True
        return False

unique_set_global = UniqueSet()

class UniqueIdManager:
    """AVItem and AVGroup need a unique identifier at
    runtime, to distinguish equivalent objects (and where
    MPRIS2 is supported, other reasons too)
    """
    def __init__(self, width = 8, uniqset = None):
        """width must be an integer between 2 and 16 inclusive --
        preferably a power of 2 so that hexadecimal presentations
        will have maximum values like FFFF, FFFFFFFF, etc.
        """
        self.uniqset = uniqset if uniqset else unique_set_global
        self.width   = int(min(max(width, 2), 16))
        self.limit   = 16**self.width

    def _prnd(self):
        try:
            return random.getrandbits(4 * self.width)
        except:
            return random.randint(15, self.limit - 1)

    def get_new(self):
        while True:
            v = self._prnd()
            if not self.uniqset.check(val = v, put = True):
                return (v, '{v:0{w}X}'.format(v=v, w=self.width))

    def remove(self, value):
        if isinstance(value, tuple):
            value = value[0]
        return self.uniqset.remove(value)

    def check(self, val, put = False):
        if isinstance(value, tuple):
            value = value[0]
        return self.uniqset.check(val = value, put = False)


av_uniq_digits  = 8
av_uniq_manager = UniqueIdManager(av_uniq_digits, unique_set_global)
# remove av uniq id's from set on __del__? probably not --
# should remain uniq for duration of runtime so that external
# clients (e.g. MPRIS2) are not confused if an id is reused
av_uniq_remove_in_dtor = False

class AVItem:
    """Structure for an a/v resource which, it is hoped,
    will be found agreeable by the wxMediaCtrl backend in use
    -- all data members are public, use as {l,r}values at will
    """
    def __init__(self,
                comment = None,
                desc = None,
                resname = None,
                err = None,
                length = -1):
        self.comment = comment
        self.desc = desc if desc else resname
        self.resname = resname
        self.err = err
        self.length = length

        self.res_dispname = None
        self.des_dispname = None

        self.uniqint, self.uniqhex = av_uniq_manager.get_new()

    def __del__(self):
        try:
            if av_uniq_remove_in_dtor:
                av_uniq_manager.remove(self.uniq)
        except:
            pass

    @property
    def uniq(self):
        """unique id as hexadecimal string, good for display"""
        return self.uniqhex

    @property
    def uniq_i(self):
        """unique id as integer, good for comparison"""
        return self.uniqint

    def get_resourcename_with_displayname(self):
        if self.res_dispname == None:
            self.res_dispname = resourcename_with_displayname(
                                self.resname)
        return self.res_dispname

    def get_res_disp_str(self, allow_none = False):
        a = allow_none
        return self.get_resourcename_with_displayname().get_disp_str(a)

    def get_description_with_displayname(self):
        self.des_dispname = resourcename_with_displayname(
                                self.desc)
        return self.des_dispname

    def get_desc_disp_str(self, allow_none = False):
        a = allow_none
        return self.get_description_with_displayname().get_disp_str(a)


def res_lst_to_avitem_lst(lst):
    return [AVItem(desc = i, resname = i)
                for i in p_filt(len, lst)] if lst else None

# filename suffixes suggesting a known A/V medium file type . . .
# will always need editing, mostly additions, possibly removals
av_ext_default = [
    "flac", "shn", "shnf",
    "ogg", "oga", "ogv", "mp3",
    "mp4", "mpg4", "mpeg4", "mp2", "m4v", "m4a",
    "mpg", "mpeg", "mjpeg", "mjpg", "mpa",
    "webm", "vp8", "vp9",
    "wm", "wmv", "wma", "wav", "aif", "iff",
    "avi", "avc", "flv", "mkv", "mov", "vob",
    "rv", "rm", "qt",
    "divx", "aac", "ac3", "xvid",
]

av_ext_ok = av_ext_default

def av_dir_find(name, recurse = False, ext_list = None):
    ext = ext_list if ext_list else av_ext_ok
    err = None
    res = None

    curdir = _T(name)

    def __xck(fname):
        try:
            f = os.path.join(curdir, _T(fname))
            if os.path.isfile(f):
                if ext == '*': # allow 'accept all' option
                    return True
                n, x = os.path.splitext(f)
                if x and x[1:].lower() in ext:
                    return True
        except Exception as e:
            raise Exception(e)
        return False

    if not recurse:
        try:
            dl = cdr_ls_dir(name)
            if not dl:
                return (res, _("directory empty"))
            res = [os.path.join(curdir, _T(f))
                    for f in p_filt(__xck, dl)]
            res.sort()
        except (OSError, IOError) as e:
            return (None, _("error with '{nm}': {ex}").format(
                                                    nm=name, ex=e))
        except Exception as s:
            return (None, _("exception: {}").format(s))
        except:
            return (None, _("exception: error with '{}'").format(
                                                    name))
        return (res, err)

    # recursive
    res = []
    for dp, dd, df in cdr_walk_dir(name, followlinks = False):
        curdir = dp
        dd.sort()
        df.sort()
        res += [os.path.join(curdir, _T(f)) for f in p_filt(__xck, df)]

    if not res:
        res = None
        err = _("error no suitable files in '{}'").format(name)

    return (res, err)

class AVGroup:
    """Contains a list of AVItem,
    and a description for the group
    """
    defdesc = _T("a/v group")
    def __init__(self, desc = defdesc, data = None, index = 0):
        self.desc = desc
        self.data = data
        self.icur = index
        self.user_desc = False

        self.uniqint, self.uniqhex = av_uniq_manager.get_new()

    def __del__(self):
        try:
            if av_uniq_remove_in_dtor:
                av_uniq_manager.remove(self.uniq)
        except:
            pass

    @property
    def uniq(self):
        """unique id as hexadecimal string, good for display"""
        return self.uniqhex

    @property
    def uniq_i(self):
        """unique id as integer, good for comparison"""
        return self.uniqint

    def write_file(self, out, do_close = True, put_desc = True):
        return wr_xpls_file(out, self, do_close, put_desc)

    # for use by subclasses
    def _wr_f(self, out, desc, do_close = True, put_desc = True):
        tdesc = self.desc

        if not tdesc or s_eq(tdesc, desc):
            if self.name:
                self.desc = self.name

        r = AVGroup.write_file(self, out, do_close, put_desc)

        self.desc = tdesc

        return r

    def has_unique_desc(self, defdesc = None):
        if self.has_user_desc():
            return True

        if defdesc == None:
            defdesc = AVGroup.defdesc

        if type(defdesc) != type(self.desc):
            return True

        try:
            return not (self.desc == defdesc or
                        self.desc == None)
        except:
            pass

        return not (_T(self.desc) == defdesc or
                    self.desc == None)

    def has_user_desc(self):
        return self.user_desc

    def set_user_desc(self, desc):
        # desc set by user interaction,
        # do not subject to coding, etc.
        self.desc = desc
        self.user_desc = True

    def get_len(self):
        return len(self.data) if self.data else 0

    def get_desc(self):
        return self.desc

    def check_next(self):
        if self.data == None:
            return False
        if self.icur == None or self.icur >= (len(self.data) - 1):
            return False
        return True

    def check_prev(self):
        if self.data == None:
            return False
        if self.icur == None or self.icur < 1:
            return False
        return True

    def get_next(self, set_index = True):
        if not self.check_next():
            return None
        if set_index:
            self.icur += 1
            return self.get_current()
        return self.get_at_index(self.icur + 1)

    def get_prev(self, set_index = True):
        if not self.check_prev():
            return None
        if set_index:
            self.icur -= 1
            return self.get_current()
        return self.get_at_index(self.icur - 1)

    def get_current(self):
        if self.icur == None:
            return None
        return self.get_at_index(self.icur)

    def get_at_index(self, idx):
        try:
            return self.data[idx]
        except:
            return None

    def del_at_index(self, idx):
        try:
            del self.data[idx]
            return True
        except:
            return False

    def get_comment_index(self, idx):
        try:
            return self.get_at_index(idx).comment
        except:
            return None

    def get_desc_index(self, idx):
        try:
            return self.get_at_index(idx).desc
        except:
            return None

    def get_resname_index(self, idx):
        try:
            return self.get_at_index(idx).resname
        except:
            return None

    def get_res_disp_str(self, idx, allow_none = False):
        try:
            return self.get_at_index(idx).get_res_disp_str(allow_none)
        except:
            return None

    def get_err_index(self, idx):
        try:
            return self.get_at_index(idx).err
        except:
            return None

    def get_length_index(self, idx):
        try:
            return self.get_at_index(idx).length
        except:
            return None


class AVGroupList(AVGroup):
    """Init from a simple list of resources, e.g. argv[1:] --
    Note that the desc parameter will be overridden by any
    description found in our app-specific description comment,
    which is checked for in .pls and .m3u sources"""
    defdesc = _T("a/v resources")
    def __init__(self, desc = defdesc, data = None):
        dat, fdesc = self.chew_dat(data)
        AVGroup.__init__(self, desc = fdesc or desc, data = dat)
        if fdesc:
            self.set_user_desc(fdesc)

    def has_unique_desc(self):
        return AVGroup.has_unique_desc(self, AVGroupList.defdesc)

    @staticmethod
    def chew_dat(dat):
        if not dat:
            return ([], None)
        if re.match(_T(r"^\[playlist\]\s*$"), _T(dat[0]), re.I):
            return AVGroupList.chew_dat_xpls(dat[1:])
        if re.match(_T(r"^#EXTM3U\s*$"), _T(dat[0])):
            return AVGroupList.chew_dat_xm3u(dat[1:])
        return AVGroupList.chew_dat_plain(dat)

    @staticmethod
    def chew_dat_xpls(dat):
        ret = []
        filedesc = None

        if len(dat) < 2:
            return (ret, filedesc)

        # cannot rely on order although loose spec specifies order ...
        #l = dat[-1]
        #m = re.match(_T(r"Version\s*=\s*([0-9]+)"), _T(l))
        #ver = int(m.group(1)) if m else None
        #
        #l = dat[-2]
        #m = re.match(
        #   _T(r"NumberOfEntries\s*=\s*([0-9]+)"), _T(l))
        #num = int(m.group(1)) if m else 0

        # ... so inefficiently loop and check data
        ver = None
        num = 0
        dorm = []
        for i, l in enumerate(dat):
            m = re.match(_T(r"Version\s*=\s*([0-9]+)"), _T(l), re.I)
            if m:
                ver = int(m.group(1))
                dorm.append(i)
                continue
            m = re.match(
                _T(r"NumberOfEntries\s*=\s*([0-9]+)"), _T(l), re.I)
            if m:
                num = int(m.group(1))
                dorm.append(i)
                continue

        dorm.reverse()
        for i in dorm:
            del dat[i]

        try:
            i = 0
            while i < num:
                j = i + 1

                got_f = got_t = got_l = False
                resname = desc = None
                length = -1

                # accept comments, especially an app-specific
                # comment used herein
                got_comment = False

                #while True:
                while dat:
                    l = _T(dat[0])
                    m = re.match(
                        _T(r"^(File|Title|Length)([0-9]+)\s*=\s*(.*)$"),
                        l)

                    if not m:
                        m = re.match(_T(r"^\s*[;#](.*)$"), l)
                        if m:
                            got_comment = True
                            dat = dat[1:]
                            t = m.group(1)
                            # check for app's description comment
                            m = re.match(_T(r"^\s*ListDesc:(.*)$"), t)
                            if m:
                                # got one: use it as this object's
                                # description -- if several, last wins
                                filedesc = m.group(1).strip()
                        break

                    if int(m.group(2)) != j:
                        # return partial success on error
                        return (ret, filedesc)

                    dat = dat[1:]

                    tag = m.group(1)

                    if tag == _T("File"):
                        if got_f:
                            # return partial success on error
                            return (ret, filedesc)
                        got_f = True

                        v = m.group(3)
                        if v:
                            resname = v

                    elif tag == _T("Title"):
                        if got_t:
                            # return partial success on error
                            return (ret, filedesc)
                        got_t = True

                        v = m.group(3)
                        if v:
                            desc = v

                    elif tag == _T("Length"):
                        if got_l:
                            # return partial success on error
                            return (ret, filedesc)
                        got_l = True

                        v = int(m.group(3))
                        if v >= 0:
                            length = v * 1000 # millisecs

                    else:
                        # cannot happen in an orderly universe
                        return (ret, filedesc)

                    if got_f and got_t and got_l:
                        break

                # comment allowed
                if got_comment:
                    continue

                # 'File' is required
                if not (got_f and resname):
                    # return partial success on error
                    return (ret, filedesc)

                comment = _T("Length {}").format(length)
                ret.append(AVItem(comment = comment,
                                  desc = desc,
                                  resname = resname,
                                  length = length))

                i = j
        except Exception as e:
            #print("chew_dat_xpls EXCEPTION == {}".format(e))
            pass
        except:
            #print("chew_dat_xpls EXCEPTION")
            pass

        return (ret, filedesc)

    @staticmethod
    def chew_dat_xm3u(dat):
        ret = []
        filedesc = None

        while len(dat) > 1:
            l = _T(dat[0])
            m = re.match(_T(r"^#EXTINF:([\+\-]?[0-9]+),(.*)$"), l)

            if not m:
                m = re.match(_T(r"^\s*#(.*)$"), l)
                if m:
                    dat = dat[1:]
                    t = m.group(1)
                    # check for app's description comment
                    m = re.match(_T(r"^\s*ListDesc:(.*)$"), t)
                    if m:
                        # got one: use it as this object's
                        # description -- if several, last wins
                        filedesc = m.group(1).strip()
                    # comment accepted
                    continue

                length  = -1
                comment = _T("Length -1")
                desc    = None
            else:
                length  = int(m.group(1))
                comment = _T("Length {}").format(length)
                desc    = m.group(2)

            resname = _T(dat[1])
            dat = dat[2:]

            if not desc:
                desc = resname

            if length > 0:
                length *= 1000

            ret.append(AVItem(comment = comment,
                              desc = desc,
                              resname = resname,
                              length = length))

        return (ret, filedesc)

    @staticmethod
    def chew_dat_plain(dat):
        """Expect blank lines already are removed"""
        return (res_lst_to_avitem_lst(dat), None)

class AVGroupListFile(AVGroupList):
    """Init from a simple list of resources file, e.g. PLS v1
    -- this will raise an exception if name arg is n.g. for reading
    """
    defdesc = _T("a/v file")
    def __init__(self, desc = defdesc, name = None):
        dat, err = textfile2linelist_tup(name) if name else (
            None, _("no file name"))

        wx.GetApp().prdbg(
            _T("AVGroupListFile: n '{}' d '{}' e '{}'").format(
                    name, dat, err))

        if err:
            AVGroupList.__init__(self, desc = desc)
            self.data = [AVItem(err = err, desc = name)]
        else:
            AVGroupList.__init__(self, desc = desc, data = dat)

        self.name = name

    def has_unique_desc(self):
        return AVGroup.has_unique_desc(self, AVGroupListFile.defdesc)

    def write_file(self, out, do_close = True, put_desc = True):
        return self._wr_f(out,
                          AVGroupListFile.defdesc,
                          do_close, put_desc)

class AVGroupListDir(AVGroupList):
    """Init from a simple list of resources file, e.g. PLS v1
    -- this will raise an exception if name arg is n.g. for reading
    """
    defdesc = _T("directory")
    def __init__(self, desc = defdesc, name = None, recurse = True):
        self.name = name
        self.recursive = recurse

        dat, err = self._mk() if name else (
            None, _("no directory name"))
        if err:
            AVGroupList.__init__(self, desc = desc)
            self.data = [AVItem(err = err, desc = name)]
        else:
            AVGroupList.__init__(self, desc = desc, data = dat)

    def has_unique_desc(self):
        return AVGroup.has_unique_desc(self, AVGroupListDir.defdesc)

    def _mk(self):
        name = self.name
        recurse = self.recursive
        return av_dir_find(name, recurse)

    def write_file(self, out, do_close = True, put_desc = True):
        return self._wr_f(out,
                          AVGroupListDir.defdesc,
                          do_close, put_desc)

class AVGroupListURIFile(AVGroupList):
    """Init from a simple list of resources file, e.g. PLS v1, by URI
    -- this will raise an exception if name arg is n.g. for reading
    """
    defdesc = _T("a/v file URL")
    def __init__(self, desc = defdesc, name = None):
        dat, err = urifile2linelist_tup(name) if name else (
            None, _("no file URL"))

        wx.GetApp().prdbg(
            _T("AVGroupListURIFile: n '{}' d '{}' e '{}'").format(
                    name, dat, err))

        if err:
            AVGroupList.__init__(self, desc = desc)
            self.data = [AVItem(err = err, desc = name)]
        else:
            AVGroupList.__init__(self, desc = desc, data = dat)

        self.name = name

    def has_unique_desc(self):
        return AVGroup.has_unique_desc(self, AVGroupListURIFile.defdesc)

    def write_file(self, out, do_close = True, put_desc = True):
        return self._wr_f(out,
                          AVGroupListURIFile.defdesc,
                          do_close, put_desc)


# make a file:// URI just be a file
def un_uri_file(furi):
    if furi[:7] != _T("file://"):
        return furi

    p = uri_parse(furi)

    if _in_psx and p.netloc:
        # cannot think of how a host part could be valid
        # (i.e., used) on a Unix-like system; there is nothing
        # like MSW 'share' locations -- but accept localhost
        # and 127.0.0.1, else return unchanged
        if not (p.netloc == 'localhost' or p.netloc == '127.0.0.1'):
            return furi

    # Incredibly, with Python 2.7 urllib{,2}.unquote() (uri_unquote
    # below) if the argument it receives is unicode, then it
    # decodes to **latin1** characters and returns unicode; but,
    # if the argument it receives is str, then it decodes to
    # **utf-8** and returns str!! I mean, WTF!
    # Bonus question: Is this documented at Python site?
    # Correct answer: No.
    # At least, things seem to work as expected w/ Python 3 versions.
    f = p.path
    if not py_v_is_3:
        # of course, this deserves testing with a large set of
        # varied input; unfortunately, the quantity of available
        # time has fallen below infinity.
        try:
            f = (p.path).encode('utf_8')
        except:
            f = p.path

    # Argh grumble sheesh, etc..
    f = uri_unquote(f)

    # This is backup (see comment above); needs more testing, and
    # might never execute, but if it does, good luck . . .
    if not py_v_is_3 and isinstance(f, unicode):
        try:
            f = f.encode('latin1').decode('utf_8')
        except:
            pass

    if _in_msw:
        lf = len(f)
        if f[0] == '/' and lf > 1:
            f = f[1:]
            lf -= 1
        f = f.replace('/', '\\')
        # this is untested: it seems that a MSW file:// URI may
        # have a host part -- so if one exists make one of the
        # \\foo\path type paths -- _try_ to find a real source
        # of such URIs for testing!
        if p.netloc and p.netloc != '.':
            if lf < 2 or f[1] != ':':
                f = '\\\\' + p.netloc + '\\' + f

    return f


playlist_pattern = _T(r".*\.(m3u8?|pls)$")
playlist_pattern_permissive = _T(r".*[^a-z0-9](m3u8?|pls)(?:\?\S+)?$")
scheme_pattern = _T(r"^(file|rtp|rtsp|http|https)://")
scheme_pattern_permissive = _T(r"^([a-z0-9]+)://")

def mk_from_args(*args, **kwargs):
    fpat  = playlist_pattern
    upat  = scheme_pattern
    ufpat = upat + fpat

    wx.GetApp().prdbg(_T("mk_from_args: args '{}'").format(args))
    wx.GetApp().prdbg(_T("mk_from_args: kwargs '{}'").format(kwargs))

    dir_recurse = False
    # option to reduce file:// to a plain path; otherwise
    # urllib will get the resource -- that's works for regular
    # files but not directories -- so default to filtering file://
    file_uri_filter = True

    if py_v_is_3:
        ii = kwargs.items()
    else:
        ii = kwargs.iteritems()
    for k, v in ii:
        if k == "dir_recurse":
            dir_recurse = v
        elif k == "file_uri_filter":
            file_uri_filter = v
        elif k == "uri_filter_permissive":
            if v != True:
                continue
            upat  = scheme_pattern_permissive
            ufpat = upat + playlist_pattern_permissive

    def _mpfn(f):
        fs  = _T(f).strip()

        if file_uri_filter:
            fs = un_uri_file(fs)

        isd = os.path.isdir(fs)
        isf = False if isd else os.path.isfile(fs)

        if isd:
            return AVGroupListDir(name = fs, recurse = dir_recurse)
        elif not isf and re.match(ufpat, fs, re.I):
            return AVGroupListURIFile(name = fs)
        elif not isf and re.match(upat, fs, re.I):
            return AVGroupList(data = [fs])
        elif isf and re.match(fpat, fs, re.I):
            return AVGroupListFile(name = fs)
        elif isf:
            return AVGroupList(data = [fs])
        else:
            # TODO: make AVGroupError
            return AVGroupList(data = [])

    return p_map(_mpfn, args)

def get_lst_from_args(*args, **kwargs):
    avl = mk_from_args(*args, **kwargs)

    res = []
    err = []
    accum = []
    rm = []

    for g in avl:
        if (isinstance(g, AVGroupListFile) or
            isinstance(g, AVGroupListURIFile) or
            isinstance(g, AVGroupListDir)):
            if accum:
                res.append(AVGroup(data = accum))
                accum = []
            for i, aviitem in enumerate(g.data):
                rnm = aviitem.resname
                if rnm == None:
                    err.append((aviitem.desc, aviitem.err))
                    rm.append(i)
                elif re.match(playlist_pattern_permissive, rnm, re.I):
                    # nested playlist file/url?
                    tl, te = get_lst_from_args(*[rnm], **kwargs)
                    if tl:
                        if te:
                            err += te
                        rm.append(i)
                        res += tl

            rm.reverse()
            for i in rm:
                g.del_at_index(i)
            if g.get_len() > 0:
                res.append(g)
        else:
            for i, aviitem in enumerate(g.data):
                rnm = aviitem.resname
                if rnm == None:
                    err.append((aviitem.desc, aviitem.err))
                else:
                    accum.append(aviitem)

    if accum:
        res.append(AVGroup(data = accum))

    wx.GetApp().prdbg(
        _T("get_lst_from_args avl cnt {}, res cnt {}").format(
                len(avl), len(res)))
    return res, err


# write extended .pls --
# arg one may be an open 'file' object or filename
# arg two must be an AVGroup subclass
# arg three says close file when done -- _only_
#           pass False if passing open file!
# -- use in try block: exceptions not handled here
def wr_xpls_file(out, group, do_close = True, put_desc = True):
    def _ck(obj):
        try:
            if obj.write:
                return True
        except:
            pass
        return False

    fd = out if _ck(out) else cv_open_w(out)

    dat = p_filt(lambda i: i.resname != None, group.data)

    # for errors; optional
    errf = wx.GetApp().err_msg

    num = len(dat) if dat else 0
    ver = 2

    if num < 1:
        errf(_T("Found empty group '{}'").format(group.desc))
        return False

    fd.write(_U("[playlist]\n"))

    # write app specific description comment if present
    if put_desc and group.desc:
        des = _T(
            group.desc).replace('\r', ' ').replace('\n', ' ').strip()
        if des:
            fd.write(_U(_T("#ListDesc: {}\n").format(des)))

    fd.write(_U("\n"))

    err_sub = 0

    for nz, it in enumerate(dat):
        n = nz + 1 - err_sub
        try:
            fd.write(_U("File{:d}={}\n").format(n, _U(it.resname)))
        except:
            errf("Python cannot write file name of unexpected type")
            err_sub += 1
            num -= 1
            continue

        tit = it.desc or it.resname
        des = _T(tit).replace('\r', ' ').replace('\n', ' ').strip()
        fd.write(_U("Title{:d}={}\n").format(n, _U(des)))

        # length is in millisecs
        try:
            li = int(it.length)
        except:
            li = -1
        ln = int(-1 if li < 0 else (li + 500) / 1000)
        fd.write(_U("Length{:d}={:d}\n\n").format(n, ln))

    fd.write(_U("NumberOfEntries={:d}\n").format(num))
    fd.write(_U("Version={:d}\n").format(ver))

    if do_close:
        fd.close()

    if num < 1:
        return False

    return True


# write list of AVGroup into directory
def wr_groups(grlist, in_dir, namebase = _T("group-"), do_exc = False):
    n = 0

    if not os.path.isdir(in_dir):
        os.makedirs(in_dir)

    wid = max(3, len(_T("{}").format(len(grlist))))
    pat = _T("{g}{n:0{wid}d}.pls")

    for g in grlist:
        fbase = pat.format(wid = wid, g = namebase, n = n)
        fpath = os.path.join(in_dir, fbase)

        res = False
        if do_exc:
            try:
                res = g.write_file(fpath)
            except:
                wx.GetApp().prdbg(
                    _T("Failed to write {}").format(fpath))
        else:
            res = g.write_file(fpath)

        if res:
            n += 1
        else:
            try:
                os.path.remove(fpath)
            except:
                pass

    return (n > 0)

# takes list of AVGroup sublass objects,
# and writes sequential .PLS files for each
# in set_dir directory, or dir from wx.GetApp()
def wr_current_set(grlist, set_dir = None, do_exc = False):
    od = set_dir if set_dir else wx.GetApp().get_data_dir_curset()

    if do_exc:
        # existing current set is removed
        if os.path.exists(od):
            try:
                shutil.rmtree(od)
            except:
                return False

        try:
            os.makedirs(od)
        except:
            return False

        res = False
        try:
            res = wr_groups(grlist, od, do_exc = do_exc)
        except:
            return False
    else:
        if os.path.exists(od):
            try:
                shutil.rmtree(od)
            except:
                # just try to use existing
                pass
        if not os.path.exists(od):
            try:
                os.makedirs(od)
            except:
                return False
        res = wr_groups(grlist, od, do_exc = do_exc)

    return res

# returns a list of the .PLS files written with wr_current_set();
# NOTE: does _not_ return AVGroup objects
def rd_current_set(set_dir = None):
    res = err = None
    sd = set_dir if set_dir else wx.GetApp().get_data_dir_curset()

    if not os.path.exists(sd):
        return (res, _("does not exist: '{}'").format(sd))

    if not os.path.isdir(sd):
        return (res, _("not a directory: '{}'").format(sd))

    ext = ["pls"]

    def __xck(fname):
        f = os.path.join(sd, fname)
        if os.path.isfile(f):
            n, x = os.path.splitext(f)
            if x and x[1:].lower() in ext:
                return True
        return False

    try:
        res = [os.path.join(sd, f)
                for f in p_filt(__xck, cdr_ls_dir(sd))]
        res.sort()
    except (OSError, IOError) as e:
        return (None, _("error with '{nm}': {ex}").format(
                                                nm=sd, ex=e))
    except Exception as s:
        return (None, _("exception: {}").format(s))
    except:
        return (None, _("exception: error with '{}'").format(sd))

    return (res, err)


"""
    classes for threads --

    NOTE: testing suggests that the event delivery is picky, as follows:
    *   wx.PyCommandEvent will not be delivered to the application
        object; wx.PyEvent will
    *   wx.PyEvent will not be delivered to the top frame window, at
        least not after Window::Show(false) is called
    therefore be thought full about which (sub-)class to choose,
    according to delivery target type
"""

T_EVT_CHILDPROC_MESSAGE = wx.NewEventType()
EVT_CHILDPROC_MESSAGE = wx.PyEventBinder(T_EVT_CHILDPROC_MESSAGE, 1)
class AThreadEvent(wx.PyEvent):
    """A custom event for the wxWidgets event mechanism:
    thread safe, i.e. may pass to main thread from other threads
    (which is particularly useful to initiate anything that will
    update the GUI, which must be done in the main thread with
    wxWidgets).  The evttag argument to the constructor *must*
    be passed (it associates the event with a type), and the
    payload argument *may* be passed if the event should carry
    a message or some data (but be mindful of threading issues),
    and finally the event will by default be delivered to the
    main top window, but a different window id may be given
    in the destid argument.
    """
    def __init__(self, evttag, payload = None, destid = -1):
        wx.PyEvent.__init__(
            self, destid,
            T_EVT_CHILDPROC_MESSAGE)

        # use deepcopy out of paranoia re. data in events that
        # are delivered across threads -- see wxPython 4.x docs re.
        # wx.QueueEvent and wx.PostEvent (re. string fields)
        self.ev_type = copy.deepcopy(evttag)
        self.ev_data = copy.deepcopy(payload)

    def get_content(self):
        """on receipt, get_content() may be called on the event
        object to return a tuple with the event type tag at [0]
        and any data payload (by default None) at [1]
        """
        return (self.ev_type, self.ev_data)

"""
Utility event for app to send top window to inicate self.Destroy()
"""
APP_EVT_DESTROY = wx.NewEventType()
APP_EVT_DESTROY_BINDME = wx.PyEventBinder(APP_EVT_DESTROY, 1)
class AppDestroyEvent(wx.PyCommandEvent):
    def __init__(self, target_window = None):
        wx.PyCommandEvent.__init__(
            self,
            APP_EVT_DESTROY,
            target_window or wx.GetApp().GetTopWindow().GetId())

"""
Thread classes
"""

class AChildThread(threading.Thread):
    """
    A thread for child process --
    cb is a callback, args is/are arguments to pass
    """
    def __init__(self, destobj, destid, cb, args):
        threading.Thread.__init__(self)

        self.destobj = destobj
        self.destid = destid
        self.cb = cb or (lambda a: False)
        self.args = args

        self.status = -1
        self.got_quit = False

    def run(self):
        tid = threading.current_thread().ident
        t = _T("tid {tid}").format(tid = tid)

        m = _T('enter run')

        put_thd_event(self.destobj, AThreadEvent(m, t, self.destid))

        self.status = self.cb(self.args)

        # no exit message with quit; just do it
        if self.got_quit:
            return

        m = _T('exit run')

        put_thd_event(self.destobj, AThreadEvent(m, t, self.destid))

    def get_status(self):
        return self.status

    def get_args(self):
        return self.args

    def set_quit(self):
        self.got_quit = True


"""
App classes
"""

if _in_msw:
    # try to call SetThreadExecutionState directly
    # using the ctypes module
    import ctypes

    class MSWScreensaverHelper:
        def __init__(self):
            self.OK = True
            self.errmsg = _("error free thus far")

            try:
                self.dllkrnl = ctypes.windll.kernel32
                self.apifunc = self.dllkrnl.SetThreadExecutionState
            except AttributeError:
                self.errmsg = _("cannot use SetThreadExecutionState()")
                self.OK = False
            except WindowsError:
                self.errmsg = _("cannot use kernel32 with py.ctypes")
                self.OK = False
            except:
                self.errmsg = _("exception using py.ctypes")
                self.OK = False

            # types and state
            self.orig_state = None
            self.in_suspend = False

            if not self.OK:
                return

            self.argtype = ctypes.c_uint32 # MSW typedef DWORD
            self.apifunc.restype  = self.argtype
            self.apifunc.argtypes = [self.argtype]
            self.ES_CONTINUOUS       = 0x80000000
            self.ES_DISPLAY_REQUIRED = 0x00000002
            self.api_arg = self.argtype(
                self.ES_CONTINUOUS | self.ES_DISPLAY_REQUIRED)


        def do_screensave(self, on = True):
            if on == False:
                return self.do_suspend()
            else:
                return self.do_resume()

        def do_suspend(self):
            res = (self.OK and
                   self.orig_state == None and
                   not self.in_suspend)
            if not res:
                return False

            res = self.apifunc(self.api_arg)

            if res == None:
                return False

            if isinstance(res, self.argtype):
                self.orig_state = res
            else:
                self.orig_state = self.argtype(res)

            self.in_suspend = True

            return True

        def do_resume(self):
            res = (self.OK and
                   self.orig_state != None and
                   self.in_suspend)
            if not res:
                return False

            res = self.apifunc(self.orig_state)

            if res == None:
                # leave self.orig_state alone for another try
                return False

            self.orig_state = None
            self.in_suspend = False

            return True

        def ok(self):
            return self.OK

        def get_errmsg(self):
            return self.errmsg

elif _in_xws:
    # this is actually not posix, but X Window System specific,
    # therefor probably is no good for Apple's BSD based products,
    # unless there is an X server available for compatiblity and
    # this wxPython is using it
    import errno
    import fcntl
    import os
    import re
    import select
    import signal
    #import stat
    import sys

    class ch_proc:
        fork_err_status = 69
        exec_err_status = 66
        exec_dup_status = 67
        pgrp_err_status = 68
        exec_wtf_status = 69

        def __init__(self,
                     cmd = None,
                     arglist = None,
                     envplus = {},
                     fd0 = None,
                     mk_pgrp = False,
                     line_rdsize = 4096):
            # I've read that file.readline(*size*) requires a non-zero
            # *size* arg to reliably return empty string *only* on EOF
            # (which is needed) so line_rdsize should by larger than
            # any line that can be expected
            self.szlin = line_rdsize

            self.mk_pgrp = mk_pgrp

            self.xcmd = cmd
            self.xcmdargs = arglist or []
            self.xcmdenv = envplus

            if isinstance(fd0, str) or isinstance(fd0, unicode):
                self.fd0 = os.open(fd0, os.O_RDONLY)
                self.fd0_opened = True
            elif isinstance(fd0, int):
                self.fd0 = fd0
                self.fd0_opened = False
            elif fd0 == None:
                self.fd0 = os.open(os.devnull, os.O_RDONLY)
                self.fd0_opened = True
            else:
                # just try opening and let caller catch anything raised
                self.fd0 = os.open(fd0, os.O_RDONLY)
                self.fd0_opened = True


            # this is orig, object, not result of a fork()
            self.root = True

            self.ch_pid = None
            self.error  = ("no error", None, None, None)


        def close_fd(self, force = False):
            # close only if opened here, or given force
            if self.fd0_opened == False and force == False:
                return -3

            r = -1
            if self.fd0 >= 0:
                try:
                    tfd = self.fd0
                    self.fd0 = -1
                    os.close(tfd)
                    r = 0
                except:
                    r = -2

            self.fd0_opened = False
            return r

        """
        public: kill (signal) child pid
        """
        def kill(self, sig = 0, kill_pgrp = False):
            if self.ch_pid == None:
                return -1

            try:
                if kill_pgrp and self.mk_pgrp:
                    return os.killpg(self.ch_pid, sig)
                else:
                    return os.kill(self.ch_pid, sig)
            except OSError as e:
                self.error = ("kill", sig, e.errno, e.strerror)
            except Exception as e:
                self.error = ("kill", sig, None, e)
            except:
                self.error = ("kill", sig, None, "unknown exception")

            return -1


        """
        public: wait on child -- opts may be "nohang" for os.WNOHANG;
        with nohang return -2 means not ready, else negative return
        means error; else status -- check with os.WIFSIGNALED and
        os.WIFEXITED, or decode_wait
        """
        def waitgrp(self, opts = 0):
            if self.ch_pid == None:
                return []

            grstat = []

            while True:
                st = self.wait(opts, True)

                if st < 0:
                    return grstat

                grstat.append(st)

        def wait(self, opts = 0, kill_pgrp = False):
            if self.ch_pid == None:
                return -1

            if opts == "nohang":
                opts = os.WNOHANG
            elif opts != 0 and opts != os.WNOHANG:
                return -1

            pid = self.ch_pid
            if kill_pgrp and self.mk_pgrp:
                pid = -pid

            while True:
                try:
                    retpid, stat = os.waitpid(pid, opts)

                    # had WNOHANG and nothing ready:
                    if retpid == 0 and stat == 0:
                        return -2

                    # not handling WIFSTOPPED; we're not tracing and
                    # opt WUNTRACED is disallowed
                    # likewise WIFCONTINUED as WCONTINUED is disallowed

                    if os.WIFSIGNALED(stat) or os.WIFEXITED(stat):
                        if not kill_pgrp:
                            self.ch_pid = None
                            self.close_fd()
                        return stat

                    return -1

                except OSError as e:
                    if e.errno  == errno.EINTR:
                        continue
                    self.error = ("wait", pid, e.errno, e.strerror)
                    break
                except Exception as e:
                    self.error = ("wait", pid, None, e)
                    break
                except:
                    self.error = ("wait",
                                  pid, None, "unknown exception")
                    break

            return -1

        def decode_wait(self, stat):
            if os.WIFSIGNALED(stat):
                return ("signalled", os.WTERMSIG(stat))
            elif os.WIFEXITED(stat):
                return ("exited", os.WEXITSTATUS(stat))

            return ("unknown", stat)

        """
        public: do kill and wait on current child -- -2 means not ready
        """
        def kill_wait(self, sig = 0, opts = 0):
            if self.kill(sig):
                return -1

            return self.wait(opts)

        """
        fork() and return tuple (child_pid, read_fd, err_fd(2)),
        """
        def go(self):
            if not self.xcmd:
                self.error = ("go", None, None,
                              "error: no child command")
                return (-1, None, None)

            # return (pid, pr.stdout, pr.stderr, pr.stdin)
            rlst = [None, None, None]
            wr_fd = self.fd0

            try:
                rfd, wfd1 = os.pipe()
            except OSError as e:
                self.error = ("go", None, e.errno, e.strerror)
                return (-1, None, None)

            try:
                efd, wfd2 = os.pipe()
            except OSError as e:
                os.close(rfd)
                os.close(wfd1)
                self.error = ("go", None, e.errno, e.strerror)
                return (-1, None, None)

            try:
                pid = os.fork()
            except OSError as e:
                os.close(rfd)
                os.close(wfd1)
                os.close(efd)
                os.close(wfd2)
                self.error = ("go", None, e.errno, e.strerror)
                return (-1, None, None)

            self.ch_pid = pid
            rlst[0] = pid
            rlst[1] = rfd
            rlst[2] = efd

            if pid == 0:
                # for reference in methods
                self.root = False

                if self.mk_pgrp:
                    # start new group giving parent kill group option
                    mpid = os.getpid()
                    try:
                        pgrp = os.getpgrp()
                        if pgrp != mpid:
                            os.setpgrp()
                        pgrp = os.getpgrp()
                    except OSError as e:
                        os._exit(self.pgrp_err_status)

                    # success?
                    if mpid != pgrp:
                        os._exit(self.pgrp_err_status)

                os.close(rfd)
                os.close(efd)

                try:
                    os.dup2(wr_fd, 0)
                    os.close(wr_fd)
                    os.dup2(wfd1, 1)
                    os.close(wfd1)
                    os.dup2(wfd2, 2)
                    os.close(wfd2)
                except OSError as e:
                    os._exit(self.exec_dup_status)

                is_path = os.path.split(self.xcmd)
                if len(is_path[0]) > 0:
                    is_path = True
                else:
                    is_path = False

                try:
                    self._putenv_cntnr(self._mk_sane_env(self.xcmdenv))
                    if is_path:
                        os.execv(self.xcmd, self.xcmdargs)
                    else:
                        os.execvp(self.xcmd, self.xcmdargs)
                    os._exit(self.exec_wtf_status)
                except OSError as e:
                    os._exit(self.exec_err_status)

            else:
                os.close(wfd1)
                os.close(wfd2)

            return tuple(rlst)

        @staticmethod
        def _putenv_cntnr(cntnr):
            try:
                if (isinstance(cntnr, tuple) or
                    isinstance(cntnr, list)):
                    for envtuple in cntnr:
                        os.environ[envtuple[0]] = envtuple[1]
                elif isinstance(cntnr, dict):
                    for k in cntnr:
                        os.environ[k] = cntnr[k]
            except:
                pass

        @staticmethod
        def _mk_sane_env(cntnr):
            o = []
            try:
                if (isinstance(cntnr, tuple) or
                    isinstance(cntnr, list)):
                    for ctuple in cntnr:
                        k = ctuple[0]
                        v = ctuple[1]
                        tstr  = v.replace(_T("\n"), _T("<NL>"))
                        v = tstr.replace(_T("\r"), _T("<CR>"))
                        o.append((k, v))
                elif isinstance(cntnr, dict):
                    for k in cntnr:
                        v = cntnr[k]
                        tstr  = v.replace(_T("\n"), _T("<NL>"))
                        v = tstr.replace(_T("\r"), _T("<CR>"))
                        o.append((k, v))
            except:
                pass

            return o

    class XWSHelperProcClass:
        common_signals = [
            signal.SIGHUP, signal.SIGINT, # leave out: signal.SIGQUIT,
            signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2
        ]

        def __init__(self, app, procargs = None, go = False,
                     mpris2 = True):
            self.thd = self.pwr = self.ch_proc = self.linemax = None
            self.quitting = False

            self.app = app

            sig_lamb = lambda s, t: self._handle_common_signal(s, t)
            for sig in self.common_signals:
                signal.signal(sig, sig_lamb)

            self.xhelperargs = procargs or [_T('wxmav-x-helper'),
                                            _T('--appname=wxmav'),
                                            _T('--xautolock'),
                                            _T('--xscreensaver')]

            self.mpris2_parent = self.mpris2_child = None
            self.mpris2_parsig = self.mpris2_chsig = None
            self.mpris2_control = None

            if mpris2:
                ch_rd, ch_wr = self.mpris2_setup()
                if ch_rd >= 0 and ch_wr >= 0:
                    srd, swr = self.mpris2_chsig.get_fds()
                    self.xhelperargs.append(
                        _T("--mpris2-fd-read={},{}").format(ch_rd,srd))
                    self.xhelperargs.append(
                        _T("--mpris2-fd-write={},{}").format(ch_wr,swr))

            self.status = None
            if go:
                self.do_keystart(self.xhelperargs)


        def mpris2_setup(self):
            efd = []


            def _clerr():
                for n in efd:
                    try:
                        os.close(n)
                    except:
                        pass


            # ensure all < 3 are open, so pipe()
            # will not return those -- close all tfd at end
            tfd = []
            for fd in (0, 1, 2):
                try:
                    fcntl.fcntl(fd, fcntl.F_GETFL, 0)
                except IOError:
                    # descriptor n is not open
                    self.err_msg(_(
                        "UNEXPECTED: fd {} not open".format(fd)))
                    n = os.open(os.devnull)
                    if n != fd:
                        os.dup2(n, fd)
                        os.close(n)
                    tfd.append(fd)

            efd += tfd

            # internal control pipe: when poll() reports
            # IPC pipe (below) is ready, the read end is removed
            # from the poll() list so that I/O over the pipe does
            # not trigger poll -- which might happen since I/O is
            # in main thread and poll() in worker thread --
            # likewise when main thread would initiate an I/O dialog,
            # it should arrange for the read fd to be removed from
            # poll() list -- and in each case when I/O dialog is
            # complete the read fd should return to the poll() list --
            # so writing to the control pipe will wake poll() and
            # read end will be read: if read says "poll" IPC pipe
            # read end is added to poll() list (if needed) and if
            # "unpoll" it is removed -- future extended uses may
            # be added
            try:
                ctrl_rd, ctrl_wr = os.pipe()
                efd += [ctrl_rd, ctrl_wr]
            except OSError as e:
                self.mpris2_pipe_error = e
                return (-1, -1)

            # write (from parent) end of IPC pipe
            try:
                ch_rd, par_wr = os.pipe()
                efd += [ch_rd, par_wr]
            except OSError as e:
                _clerr()
                self.mpris2_pipe_error = e
                return (-1, -1)

            # read (from parent) end of IPC pipe
            try:
                par_rd, ch_wr = os.pipe()
                efd += [par_rd, ch_wr]
            except OSError as e:
                _clerr()
                self.mpris2_pipe_error = e
                return (-1, -1)

            # write (from parent) end of signal IPC pipe
            try:
                chsig_rd, parsig_wr = os.pipe()
                efd += [chsig_rd, parsig_wr]
            except OSError as e:
                _clerr()
                self.mpris2_pipe_error = e
                return (-1, -1)

            # read (from parent) end of signal IPC pipe
            try:
                parsig_rd, chsig_wr = os.pipe()
                efd += [parsig_rd, chsig_wr]
            except OSError as e:
                _clerr()
                self.mpris2_pipe_error = e
                return (-1, -1)

            opn = (ch_rd,ch_wr,chsig_rd,chsig_wr)
            cls = (par_rd,par_wr,parsig_rd,parsig_wr,ctrl_rd,ctrl_wr)
            for fd in opn:
                fcntl.fcntl(fd, fcntl.F_SETFD, 0)
            for fd in cls:
                fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
            for fd in tfd:
                os.close(fd)

            self.mpris2_parent  = IODescriptorPair(par_rd, par_wr)
            self.mpris2_child   = IODescriptorPair(ch_rd,  ch_wr)
            self.mpris2_parsig  = IODescriptorPair(parsig_rd, parsig_wr)
            self.mpris2_chsig   = IODescriptorPair(chsig_rd,  chsig_wr)
            self.mpris2_control = IODescriptorPair(ctrl_rd, ctrl_wr)

            return (ch_rd, ch_wr)

        def close_mpris_io(self):
            t = (self.mpris2_parent,
                 self.mpris2_parsig,
                 self.mpris2_child,
                 self.mpris2_chsig,
                 self.mpris2_control)

            for io in t:
                if not io:
                    continue
                try:
                    io.close()
                except (OSError, IOError) as e:
                    self.err_msg(_T(
                        "close mpris fd: error '{e}'").format(
                        e = e.strerror))
                except:
                    pass

            self.mpris2_parent  = None
            self.mpris2_child   = None
            self.mpris2_parsig  = None
            self.mpris2_chsig   = None
            self.mpris2_control = None

        def get_mpris_pipe_obj(self):
            return self.mpris2_parent

        def get_mpris_pipe_desc(self):
            """Return tuple (read, write)"""
            if not self.mpris2_parent:
                return (-1, -1)
            return self.mpris2_parent.get_fds()

        def get_mpris_pipe_signal_obj(self):
            return self.mpris2_parsig

        def get_mpris_pipe_signal_desc(self):
            """Return tuple (read, write)"""
            if not self.mpris2_parsig:
                return (-1, -1)
            return self.mpris2_parsig.get_fds()

        def get_mpris_pipe_control_obj(self):
            return self.mpris2_control

        def get_mpris_pipe_control_desc(self):
            """Return tuple (read, write)"""
            if not self.mpris2_control:
                return (-1, -1)
            return self.mpris2_control.get_fds()

        def mpris_on(self):
            rd, wr = self.get_mpris_pipe_signal_desc()
            if wr < 0:
                self.close_mpris_io()
                return False
            try:
                m = "mpris:on\n".encode('ascii')
                fd_write(wr, m)
            except (OSError, IOError) as e:
                self.err_msg(_T(
                    "MPRIS2 write '{m}' failed '{e}'").format(
                                m = m, e = e.strerror))
                self.close_mpris_io()
                return False
            return True

        def mpris_off(self):
            self.err_msg(_T("mpris_off: entry"))
            ret = False
            rd, wr = self.get_mpris_pipe_signal_desc()
            if wr < 0:
                self.err_msg(_T("mpris_off: wr < 0"))
                self.close_mpris_io()
                return ret
            try:
                m = "mpris:off\n".encode('ascii')
                fd_write(wr, m)
                ret = True
            except (OSError, IOError) as e:
                self.err_msg(_T(
                    "MPRIS2 write '{m}' failed '{e}'").format(
                                m = m, e = e.strerror))
            self.close_mpris_io()
            self.err_msg(_T("mpris_off: io closed ({})").format(
                self.get_mpris_pipe_signal_obj()))
            return ret


        def _handle_common_signal(self, signum, stack_frame):
            self.app._on_signal(signum)

        def go(self):
            if self.status == None:
                self.do_keystart(self.xhelperargs)
                return (self.status[3] == "running")
            return False

        def get_status(self):
            return self.status

        def on_exit(self):
            if self.thd and self.ch_proc:
                self.quitting = False # prevent posting message
                self.do_keyend(False, True)

            return 0


        def prdbg(self, *args):
            self.app.prdbg(*args)

        def err_msg(self, msg):
            self.app.err_msg(msg)

        """
        The remainder of the methods of this class concern the child
        process (under X) that reports media keys
        """
        def do_keystart(self, xcmdargs):
            if self.thd or self.ch_proc:
                return self.status[3]

            pip = os.pipe()
            self.pwr = pip[1]

            self.ch_proc = ch_proc(cmd = xcmdargs[0],
                                   arglist = xcmdargs,
                                   fd0 = pip[0],
                                   mk_pgrp = True)

            pid, rfd, efd = self.ch_proc.go()

            # exec*() success detection - short sleep then
            # ch_proc.wait nohang, which should return -2,
            # meaning pid was found but not exited or signalled,
            # or > 0 meaning exited or signalled, or other
            # negative value meaning a wait error, like pid NG
            dec_msg = None
            dec_sta = 0
            if pid > 0:
                wx.MilliSleep(50)
                st = self.ch_proc.wait(opts = "nohang")
                if st >= 0:
                    d = self.ch_proc.decode_wait(st)
                    if d[0] == "unknown":
                        # the wait return is unexpected, so
                        # try to kill(0) to test the pid,
                        # keeping that result in st
                        st = self.ch_proc.kill(sig = 0)
                        self.err_msg(
                            "CHILD EXEC KILL(0) STATUS: {}".format(st))
                    else:
                        # wait return indicates normal exit or
                        # killed by signal; either way it is a
                        # mysterious error
                        self.err_msg(
                            "CHILD EXEC EARLY EXIT: {}".format(d))
                        st = -1
                        # save returns from decode_wait(st) for
                        # use in this object's status
                        dec_msg, dec_sta = d
                elif st == -2:
                    # wait WNOHANG and not ready for the reaper
                    # (this is good)
                    st = 0
                if (self.ch_proc.error[0] != "no error" or
                   (st != 0 and st != None)):
                    che = self.ch_proc.error
                    self.err_msg(
                        "CHILD EXEC ERROR STATUS: {} ({})".format(
                            st, che))
                    self.ch_proc.wait()
                    pid = -1

            # XXX: close child fds here?
            # did have code, which was wrong, and caused
            # a bad descriptor in libpulse->abort() --
            # not closing child fds is safe, at least

            # error?
            if pid < 0:
                if self.mpris2_parent:
                    ch_r, ch_w = self.mpris2_parent.get_fds()
                    os.close(ch_r)
                    os.close(ch_w)
                    self.mpris2_parent = None

                os.close(pip[0])
                os.close(pip[1])
                self.pwr = None
                self.status = self.ch_proc.error # error tuple
                if dec_msg or self.status[3] == "running":
                    t0, t1, t2, t3 = self.status
                    self.status = (t0, dec_sta or t1,
                                   t2, dec_msg or "unknown")
                self.ch_proc = None
                return self.status[3]


            self.thd = AChildThread(self.app, new_wx_id(),
                                    self.run_ch_proc,
                                    (self.ch_proc, pip[1], rfd, efd))

            self.thd.start()
            os.close(pip[0])

            self.status = (None, None, None, "running")
            return self.status[3]

        def do_keyend(self, quitting = False, use_signal = True):
            if quitting:
                self.quitting = True

            if self.ch_proc:
                if use_signal == False and self.pwr != None:
                    try:
                        os.write(self.pwr, "Quit\n".encode('ascii'))
                    except:
                        self.pwr = None
                else:
                    # SIGUSR2 is handled by childproc handler,
                    # and will send SIGINT to the process
                    # group which it sets up at fork()
                    # with setp{grp,gid}
                    self.ch_proc.kill(signal.SIGINT, kill_pgrp = True)

        # when top window gets close event that can be vetoed,
        # it calls this, and only self.Destroy() if this
        # returns True, else veto the event and wait until
        # it gets event AppDestroyEvent then it can destroy
        def test_exit(self):
            self.mpris_off()
            if self.thd or self.ch_proc:
                wx.CallAfter(self.do_keyend, True)
                return False

            return True

        def do_screensave(self, on = True):
            if self.pwr == None or self.pwr < 0:
                return

            if on == False:
                m = "ssaver_off\n".encode('ascii')
                os.write(self.pwr, m)
            else:
                m = "ssaver_on\n".encode('ascii')
                os.write(self.pwr, m)

        def do_query(self):
            if self.pwr == None or self.pwr < 0:
                return

            m = "Query\n".encode('ascii')

            os.write(self.pwr, m)

        def do_wname(self):
            if self.pwr == None or self.pwr < 0:
                return

            m = "WName\n".encode('ascii')

            os.write(self.pwr, m)
            self.prdbg("do_wname")

        def do_setwname(self, s_title):
            if self.pwr == None or self.pwr < 0 or self.linemax == None:
                self.prdbg("do_setwname FAIL 1 pwr {} lmax {}".format(
                            self.pwr, self.linemax))
                return

            m = _T("{s}\n").format(s=s_title).encode('utf_8')

            if self.linemax <= len(m):
                return

            os.write(self.pwr, "SETWName\n".encode('ascii'))
            self.prdbg("do_setwname SETWName")

            wx.MilliSleep(333)

            os.write(self.pwr, m)
            self.prdbg(_T("do_setwname '{}'").format(m))

        def do_wroot(self):
            if self.pwr == None or self.pwr < 0:
                return

            os.write(self.pwr, "WRoot\n".encode('ascii'))

        def do_enter_run(self):
            pass

        def do_exit_run(self):
            ch_proc = self.ch_proc
            self.ch_proc = None
            thd = self.thd
            self.thd = None
            pwr = self.pwr
            self.pwr = None

            st = self.status
            self.status = None

            if thd:
                self.prdbg(_T("PRE JOIN"))
                while thd.is_alive():
                    thd.join()

                st = thd.get_status()
                self.prdbg(_T("POST JOIN -- STATUS {}").format(st))

            self.status = st

            if ch_proc:
                self.prdbg(_T("PRE WAIT"))
                if not st:
                    st = ch_proc.waitgrp()
                    for i, s in enumerate(st):
                        st[i] = ch_proc.decode_wait(s)
                else:
                    st = ch_proc.kill_wait(signal.SIGTERM)
                    st = ch_proc.decode_wait(st)

                self.prdbg(
                    _T("POST WAIT -- TERM+STAT '{}' -- "
                       "PROC ERR '{}'").format(st, ch_proc.error))

                ch_proc.close_fd(True)
            elif pwr != None:
                os.close(pwr)

            if self.quitting:
                self.prdbg(_T("PRE QUIT EVENT"))
                wx.PostEvent(self.app.frame, AppDestroyEvent())
                self.prdbg(_T("POST QUIT EVENT"))

            return self.status


        def run_ch_proc(self, argtuple):
            ch_proc, fdwr, fdr1, fdr2 = argtuple

            bufsize = 4096

            try:
                f1 = os.fdopen(fdr1, "r", bufsize)
                f2 = os.fdopen(fdr2, "r", bufsize)
            except OSError as e:
                put_thd_event(
                    self.app, AThreadEvent(_T("X"), e.strerror, -1))
                return -1
            except Exception as e:
                e = _T("Exception '{}'").format(e)
                put_thd_event(self.app, AThreadEvent(_T("X"), e, -1))
                return -1
            except:
                e = _T("unknown exception")
                put_thd_event(self.app, AThreadEvent(_T("X"), e, -1))
                return -1

            # immediately get line max
            try:
                os.write(fdwr, "linemax\n".encode('ascii'))
                lin = f1.readline(bufsize)
                self.check_linemax(lin)
                bufsize = max(self.linemax, bufsize)
                self.prdbg("linemax read== '{}' check == '{}'".format(
                            lin.rstrip(), self.linemax))
            except OSError as e:
                self.prdbg("linemax exception '{}'".format(e.strerror))
            except Exception as e:
                self.prdbg("linemax exception '{}'".format(e))
            except:
                e = "unknown"
                self.prdbg("linemax exception '{}'".format(e))

            flist = [fdr1, fdr2]

            mpctrl = mprd = mpwr = -1
            mpctrl = (-1, -1)
            if self.mpris2_control:
                mpctrl = self.mpris2_control.get_fds()
            if self.mpris2_parent:
                mprd, mpwr = self.mpris2_parent.get_fds()

            errbits = select.POLLERR|select.POLLHUP|select.POLLNVAL
            pl = select.poll()
            pl.register(flist[0], select.POLLIN|errbits)
            pl.register(flist[1], select.POLLIN|errbits)
            if mprd >= 0:
                flist.append(mprd)
                pl.register(mprd, select.POLLIN|errbits)
            if mpctrl[0] >= 0:
                pl.register(mpctrl[0], select.POLLIN|errbits)

            while True:
                try:
                    rl = pl.poll(None)
                except select.error as e:
                    err, msg = e
                    if err == errno.EINTR or err == errno.EAGAIN:
                        continue
                    put_thd_event(
                        self.app, AThreadEvent(_T("X"), msg, -1))
                    return -1

                if len(rl) == 0:
                    break

                lin = ""
                for fd, bits in rl:
                    if fd < 0:
                        continue
                    err = bits & errbits
                    if err:
                        if fd in flist: flist.remove(fd)
                        try:
                            pl.unregister(fd)
                        except:
                            pass
                        if fd == mprd:
                            try:
                                pl.unregister(mpctrl[0])
                            except:
                                pass
                            try:
                                self.mpris2_control.close()
                                self.mpris2_parent.close()
                            except:
                                pass
                            if self.mpris2_parent:
                                self.mpris2_parent.poll_err = err
                                put_thd_event(self.app,
                                    AThreadEvent(_T("M"),
                                    (lin, self.mpris2_parent, -1)))
                        continue

                    if fd == fdr1:
                        pfx = _T("1")
                        fN = f1
                    elif fd == fdr2:
                        pfx = _T("2")
                        fN = f2
                    elif fd == mprd and fd >= 0:
                        flist.remove(fd)
                        pl.unregister(fd)
                        pfx = _T("M") # The MPRIS2 desc.
                        fN = None
                    elif fd == mpctrl[0] and fd >= 0:
                        fN = None
                    else:
                        continue

                    if bits & select.POLLIN:
                        # internal control fd?
                        if fd == mpctrl[0]:
                            lin = _T(os.read(mpctrl[0], 128))
                            if s_eq(lin, "poll") and mprd not in flist:
                                flist.append(mprd)
                                pl.register(mprd, select.POLLIN|errbits)
                            elif s_eq(lin, "unpoll") and mprd in flist:
                                flist.remove(mprd)
                                pl.unregister(mprd)
                            continue
                        # MPRIS coproc IPC pipe?
                        elif fd == mprd:
                            # reading first line and passing it is
                            # optional -- event recipient will read
                            # 1st line if lin arg (in tuple) is
                            # empty; so, best not
                            lin = "" #os.read(mprd, 16384)
                            put_thd_event(self.app,
                                          AThreadEvent(pfx,
                                            (lin,
                                             self.mpris2_parent,
                                             mpctrl[1])))
                            continue

                        # X helper std IO fds?
                        lin = fN.readline(bufsize)

                        if len(lin) > 0:
                            put_thd_event(self.app,
                                          AThreadEvent(pfx, lin))
                        else:
                            #flist.remove(fd)
                            #pl.unregister(fd)
                            pass
                    else:
                        pass

                if len(flist) == 0:
                    break

            try:
                f1.close()
                f2.close()
            except:
                pass

            return 0

        def check_linemax(self, s):
            r = re.search(_T(r'^([YN]):([0-9]+)' + '\n*$'), s)
            if r and r.group(1) == _T('Y'):
                self.linemax = int(r.group(2))
            return self.linemax

    class MPRIS2Handler:
        def __init__(self, wnd, dat):
            self.w      = wnd
            self.line_1 = dat[0]
            self.io_obj = dat[1]
            self.donefd = dat[2]

            self._rbuf = _T("")

        def go(self):
            self.on_mpris2(self.line_1, self.io_obj)

        def done(self):
            #self.err_msg(_T(
            #    "mpris2hdlr::done donefd '{}'").format(self.donefd))
            if self.donefd >= 0:
                # rapid pace of property queries at startup
                # seems to overwhelm something (wx wvent loop?
                # python poll()?) and lockups occur -- try using
                # bothe callafter and sleep to slow things down
                def _done_mp(w, fd, sl):
                    if sl > 0:
                        wx.MilliSleep(sl)
                    # use try in case reentrant events closed this
                    try:
                        fd_write(fd, _T("poll"))
                    except (IOError, OSError) as e:
                        w.err_msg(_T(
                            "mpris2hdlr::done donefd write error '{}'"
                            ).format(e.strerror))
                    w.block_mpris_signals = False

                if True:
                    _done_mp(self.w, self.donefd, 0)
                else:
                    wx.CallAfter(_done_mp, self.w, self.donefd, 0)

        def wr(self, fd, v):
            return fd_write(fd, _Tnec(v))

        def rd(self, fd, nbuf = 128):
            while True:
                p = self._rbuf.find(_T('\n'))
                if p >= 0:
                    p += 1
                    r = self._rbuf[:p]
                    self._rbuf = self._rbuf[p:]
                    return r
                self._rbuf += _T(os.read(fd, nbuf))

        def rdstp(self, fd, nbuf = 128):
            return self.rd(fd, nbuf).strip(_T('\n'))

        def mpris2_send_ack(self, fd_rd, fd_wr, ack):
            ack = _T(ack).rstrip(_T('\n')) + _T('\n')
            self.err_msg(_T("mpris2_send_ack '{}'").format(ack))

            try:
                self.wr(fd_wr, ack)
                self.err_msg(_T("MPRIS2 after mpris2_send_ack"))
            except (IOError, OSError) as e:
                self.err_msg(_T("MPRIS2 write error '{}' in {}").format(
                    e.strerror, _T('mpris2_send_ack')))
                return False
            except:
                self.err_msg(_T("MPRIS2 exception in '{}'").format(
                    _T('mpris2_send_ack')))
                return False

            return True

        def mpris2_send(self, fd_rd, fd_wr, ack, level):
            if not self.mpris2_send_ack(fd_rd, fd_wr, ack):
                return False

            if s_eq(level, "base"):
                return self.mpris2_send_base(fd_rd, fd_wr)
            elif s_eq(level, "player"):
                return self.mpris2_send_player(fd_rd, fd_wr)

            return False

        def mpris2_send_base(self, fd_rd, fd_wr):
            prop = self.rdstp(fd_rd, 128)
            return self.mpris2_send_prop_or_signal(fd_rd, fd_wr,
                                                   prop, "base")

        def mpris2_send_player(self, fd_rd, fd_wr):
            prop = self.rdstp(fd_rd, 128)
            return self.mpris2_send_prop_or_signal(fd_rd, fd_wr,
                                                   prop, "player")

        def mpris2_send_signal(self, rd_ch, wr_ch, signal):
            # dbus signal/property maps as tuples:
            # (object_path, interface_name,
            #  signal-type, (tuple-of-property-or-signal-names))
            # do NOT forget NL on strings for witing to coproc!
            sigbasesigs = (
                _T("/org/mpris/MediaPlayer2\n"),
                _T("org.mpris.MediaPlayer2\n"),
                _T("signal\n"),
                ( # base signal signals
                    _T(""), # this interface ain't got none
                )
                )
            sigbaseprops = (
                _T("/org/mpris/MediaPlayer2\n"),
                _T("org.mpris.MediaPlayer2\n"),
                _T("property\n"),
                ( # base property signals
                    _T("CanQuit"),             # b  Read only
                    _T("Fullscreen"),          # b  Read/Write(optional)
                    _T("CanSetFullscreen"),    # b  Read only (optional)
                    _T("CanRaise"),            # b  Read only
                    _T("HasTrackList"),        # b  Read only
                    _T("Identity"),            # s  Read only
                    _T("DesktopEntry"),        # s  Read only (optional)
                    _T("SupportedUriSchemes"), # as Read only
                    _T("SupportedMimeTypes")   # as Read only
                )
                )

            sigplayersigs = (
                _T("/org/mpris/MediaPlayer2\n"),
                _T("org.mpris.MediaPlayer2.Player\n"),
                _T("signal\n"),
                ( # player signal signals
                    _T("Seeked"), # (x: Position) [usecs]
                )
                )
            sigplayerprops = (
                _T("/org/mpris/MediaPlayer2\n"),
                _T("org.mpris.MediaPlayer2.Player\n"),
                _T("property\n"),
                ( # player property signals
                    _T("PlaybackStatus"), # s     Read only
                    _T("LoopStatus"),     # s     Read/Write (optional)
                    _T("Rate"),           # d     Read/Write
                    _T("Shuffle"),        # b     Read/Write (optional)
                    _T("Metadata"),       # a{sv} Read only
                    _T("Volume"),         # d     Read/Write
                    _T("Position"),       # x     Read only
                    _T("MinimumRate"),    # d     Read only
                    _T("MaximumRate"),    # d     Read only
                    _T("CanGoNext"),      # b     Read only
                    _T("CanGoPrevious"),  # b     Read only
                    _T("CanPlay"),        # b     Read only
                    _T("CanPause"),       # b     Read only
                    _T("CanSeek"),        # b     Read only
                    _T("CanControl")      # b     Read only
                )
                )

            ttup = (sigbasesigs, sigbaseprops,
                    sigplayersigs, sigplayerprops)

            opath = ifname = sigtype = None
            for tup in ttup:
                if signal in tup[3]:
                    opath = tup[0]
                    ifname = tup[1]
                    sigtype = tup[2]
                    break

            if opath == None:
                self.err_msg(
                    _T("signal_emit: unknown signal '{}'").format(
                        signal))
                self.wr(wr_ch, _T("ACK:NA\n"))
                return False

            rsz = 256

            # write ack string
            #static const char *ack = "signal";
            self.wr(wr_ch, _T("signal\n"))

            # read method/property -- not used here but
            # the line must be read
            r = self.rdstp(rd_ch, rsz)
            if r != _T("signaldata"):
                # warn, no error
                self.err_msg(
                    _T("signal_emit: unexpected method '{}'").format(r))

            if False:
                # write object path
                self.wr(wr_ch, opath)
                # write interface name
                self.wr(wr_ch, ifname)
                # write signal name
                self.wr(wr_ch, _T("{}\n").format(signal))
                # write signal type !!! "property" or "signal"
                self.wr(wr_ch, sigtype)
            else:
                # multiline write
                self.wr(wr_ch, _T("{}{}{}{}").format(
                    opath, ifname, _T("{}\n").format(signal), sigtype))

            # use mpris handler to write GIO/dbus format string and data
            r = self.mpris2_send_prop_or_signal(rd_ch, wr_ch,
                                                signal, "signal")

            # cleanup and return
            return r

        def mpris2_send_prop_or_signal(self,
                                       fd_rd, fd_wr,
                                       prop, level):
            self.err_msg(
                _T("mpris2 send {} property '{}'").format(
                    level, prop))

            m = _T("b:true\n")

            # Cases that would return "b:true\n" will just pass
            #
            # base (or signal)
            if s_eq(prop, "CanQuit"):
                pass
            elif s_eq(prop, "Fullscreen"):
                t = "true" if self.w.is_fullscreen() else "false"
                m = _T("b:{}\n").format(_T(t))
            elif s_eq(prop, "CanSetFullscreen"):
                pass
            elif s_eq(prop, "CanRaise"):
                pass
            elif s_eq(prop, "HasTrackList"):
                # TODO:
                #set true when org.mpris.MediaPlayer2.TrackList done
                m = _T("b:false\n")
            elif s_eq(prop, "Identity"):
                t = self.w.get_identity()
                m = _T("s:{}\n").format(t)
            elif s_eq(prop, "DesktopEntry"):
                m = _T("s:wxmav\n")
            elif s_eq(prop, "SupportedUriSchemes"):
                m = _T("as:\n")
                self.wr(fd_wr, m)
                for s in gst_uri_schemes:
                    m = _T("{}\n").format(s)
                    self.wr(fd_wr, m)
                m = _T(":END ARRAY:\n")
            elif s_eq(prop, "SupportedMimeTypes"):
                m = _T("as:\n")
                self.wr(fd_wr, m)
                for s in gst_mime:
                    m = _T("{}\n").format(s)
                    self.wr(fd_wr, m)
                m = _T(":END ARRAY:\n")
            # player (or signal)
            elif s_eq(prop, "PlaybackStatus"):
                m = _T("s:{}\n").format(
                    self.w.get_playback_state_string())
            elif s_eq(prop, "LoopStatus"):
                t = "Track" if self.w.loop_track else "None"
                m = _T("s:{}\n").format(_T(t))
            elif s_eq(prop, "Rate"):
                m = _T("d:1.0\n")
            elif s_eq(prop, "Shuffle"):
                # TODO: set true when implemented
                m = _T("b:false\n")
            elif s_eq(prop, "Metadata"):
                a = self.w.get_mpris2_metadata()
                m = _T("a{sv}:\n")
                self.wr(fd_wr, m)
                for s, v in a:
                    m = _T("{}\n").format(s)
                    self.wr(fd_wr, m)
                    if v[:3] == _T('as:'):
                        m = _T("as:\n")
                        self.wr(fd_wr, m)
                        m = _T("{}\n").format(v[3:])
                        self.wr(fd_wr, m)
                        m = _T(":END ARRAY:\n")
                        self.wr(fd_wr, m)
                    else:
                        m = _T("{}\n").format(v)
                        self.wr(fd_wr, m)
                m = _T(":END ARRAY:\n")
            elif s_eq(prop, "Volume"):
                d = float(self.w.vol_max - self.w.vol_min)
                v = float(self.w.vol_cur - self.w.vol_min) / d
                m = _T("d:{:f}\n").format(v)
            elif s_eq(prop, "Position"):
                # Note >=0 : unbounded Tell() gives playing time
                if self.w.load_ok and self.w.medi.Length() >= 0:
                    v = self.w.medi.Tell() * 1000
                else:
                    v = 0
                m = _T("x:{}\n").format(long(v))
            elif s_eq(prop, "Seeked"):
                # dbus signal -- glib wants a tuple
                v = 0 if (self.w.medi.Length() < 1) else (
                    self.w.medi.Tell() * 1000)
                m = _T("(x):{}\n").format(long(v))
            elif s_eq(prop, "MinimumRate") or s_eq(prop, "MaximumRate"):
                m = _T("d:1.0\n")
            elif s_eq(prop, "CanGoNext"):
                if self.w.get_next_index() == None:
                    m = _T("b:false\n")
            elif s_eq(prop, "CanGoPrevious"):
                if self.w.get_prev_index() == None:
                    m = _T("b:false\n")
            elif s_eq(prop, "CanPlay") or s_eq(prop, "CanPause"):
                if not self.w.reslist:
                    m = _T("b:false\n")
            elif s_eq(prop, "CanSeek"):
                if not (self.w.load_ok and self.w.medi.Length() > 0):
                    m = _T("b:false\n")
            elif s_eq(prop, "CanControl"):
                m = _T("b:true\n")
            else:
                m = _T("b:false\n")
                self.wr(fd_wr, m)
                return False

            self.err_msg(
                _T("mpris2 send {} property '{}' -> '{}'").format(
                    level, prop, m))

            self.wr(fd_wr, m)
            return True

        def mpris2_recv(self, fd_rd, fd_wr, ack, level):
            if not self.mpris2_send_ack(fd_rd, fd_wr, ack):
                return False

            if s_eq(level, "base"):
                return self.mpris2_recv_base(fd_rd, fd_wr)
            elif s_eq(level, "player"):
                return self.mpris2_recv_player(fd_rd, fd_wr)

            return False

        def mpris2_recv_base(self, fd_rd, fd_wr):
            def _propresp(t, ok):
                m = _T("{t}:{s}\n").format(t = t,
                    s = "ok" if ok else "ng")
                self.wr(fd_wr, m)

            prop = self.rdstp(fd_rd, 128)
            if False:
                pass
            elif s_eq(prop, "Fullscreen"):
                _propresp("b", True)
                resp = self.rdstp(fd_rd, 128)
                off = True if s_ne(resp, "true") else False
                self.w.do_fullscreen(off)
            else:
                _propresp("b", False)
                return False

            return True

        def mpris2_recv_player(self, fd_rd, fd_wr):
            def _propresp(t, ok):
                m = _T("{t}:{s}\n").format(t = t,
                    s = "ok" if ok else "ng")
                self.wr(fd_wr, m)

            prop = self.rdstp(fd_rd, 128)
            if False:
                pass
            elif s_eq(prop, "LoopStatus"):
                _propresp("s", True)
                resp = self.rdstp(fd_rd, 128)
                if s_eq(resp, "Track"):
                    self.w.set_loop_track(do_loop = True)
                elif s_eq(resp, "Playlist"):
                    self.w.set_loop_track(
                        do_loop = False, force_signal = True)
                elif s_eq(resp, "None"):
                    self.w.set_loop_track(do_loop = False)
                else:
                    self.w.set_loop_track(force_signal = True)
            elif s_eq(prop, "Rate"):
                _propresp("d", True)
                resp = self.rdstp(fd_rd, 128)
                self.prdbg(_T("MPRIS2 set rate {}").format(resp))
            elif s_eq(prop, "Shuffle"):
                _propresp("b", True)
                resp = self.rdstp(fd_rd, 128)
                self.prdbg(_T("MPRIS2 set shuffle {}").format(resp))
            elif s_eq(prop, "Volume"):
                _propresp("d", True)
                resp = self.rdstp(fd_rd, 128)
                v = int(float(resp) * 100.0 + 0.5)
                self.w.do_volume(v)
                self.prdbg(_T("MPRIS2 set volume {}").format(v))
            else:
                _propresp("b", False)
                return False

            return True

        def mpris2_meth(self, fd_rd, fd_wr, ack, level):
            self.err_msg(_T("mpris2_meth '{}'").format(ack))
            if not self.mpris2_send_ack(fd_rd, fd_wr, ack):
                return False

            self.err_msg(_T("mpris2_meth {}").format(level))
            if s_eq(level, "base"):
                return self.mpris2_meth_base(fd_rd, fd_wr)
            elif s_eq(level, "player"):
                return self.mpris2_meth_player(fd_rd, fd_wr)

            return False

        def mpris2_meth_base(self, fd_rd, fd_wr):
            def _methresp(t, ok):
                m = _T("{t}:{s}\n").format(t = t,
                    s = "ok" if ok else "ng")
                self.wr(fd_wr, m)

            self.err_msg(_T("MPRIS2 before mpris2_meth_base READ"))
            meth = self.rdstp(fd_rd, 128)
            self.err_msg(_T("MPRIS2 after mpris2_meth_base READ"))

            # org.mpris.MediaPlayer2 [base] methods
            if s_eq(meth, "Quit"):
                _methresp("VOID", True)
                #self.w.Close(False)
                #wx.CallAfter(self.w.Close, False)
                self.w._quit_signal = -2
            elif s_eq(meth, "Raise"):
                _methresp("VOID", True)
                self.w.Raise()
            else:
                _methresp("UNSUPPORTED", True)

            return True

        def mpris2_meth_player(self, fd_rd, fd_wr):
            def _methresp(t, ok):
                m = _T("{t}:{s}\n").format(t = t,
                    s = "ok" if ok else "ng")
                self.wr(fd_wr, m)

            meth = self.rdstp(fd_rd, 128)
            if False:
                pass
            # org.mpris.MediaPlayer2 [base] methods
            elif s_eq(meth, "Next"):
                _methresp("VOID", True)
                self.w.cmd_on_next(True)
            elif s_eq(meth, "Previous"):
                _methresp("VOID", True)
                self.w.cmd_on_prev(True)
            elif s_eq(meth, "PlayPause"):
                _methresp("VOID", True)
                self.w.do_command_button(self.w.id_play)
            elif s_eq(meth, "Stop"):
                _methresp("VOID", True)
                self.w.do_command_button(self.w.id_stop)
            elif s_eq(meth, "Play"):
                _methresp("VOID", True)
                st = self.w.get_medi_state()
                if st != wx.media.MEDIASTATE_PLAYING:
                    self.w.do_command_button(self.w.id_play)
            elif s_eq(meth, "Pause"):
                _methresp("VOID", True)
                st = self.w.get_medi_state()
                if st == wx.media.MEDIASTATE_PLAYING:
                    self.w.do_command_button(self.w.id_play)
            elif s_eq(meth, "Seek"):
                self.wr(fd_wr, _T("ARGS:x\n"))
                val = self.rdstp(fd_rd, 128)
                self.w.mpris_seek_method(val, True)
                _methresp("VOID", True)
            elif s_eq(meth, "SetPosition"):
                self.wr(fd_wr, _T("ARGS:o:x\n"))
                pth = self.rdstp(fd_rd, 4096)
                val = self.rdstp(fd_rd, 128)
                if self.w.check_dbus_itempath_current(pth):
                    self.w.mpris_seek_method(val, False)
                _methresp("VOID", True)
            elif s_eq(meth, "OpenUri"):
                self.wr(fd_wr, _T("ARGS:s\n"))
                val = self.rdstp(fd_rd, 4096)
                reslist, errs = self.w.do_arg_list([val],
                                            append = True,
                                            recurse = False,
                                            play = True)
                self.err_msg(
                    _T("MPRIS2 OpenUri ({}): errs == '{}'").format(
                        val, errs))
                _methresp("VOID", True)
            else:
                _methresp("UNSUPPORTED", True)

            return True

        def prdbg(self, m):
            self.w.prdbg(m)

        def err_msg(self, m):
            self.w.err_msg(m)

        def on_mpris2(self, cmd, io_desc_pair):
            fd_rd, fd_wr = io_desc_pair.get_fds()

            self.w.mpris = (fd_rd >= 0 and fd_wr >= 0)
            self.w.mpris_fd_rd = fd_rd
            self.w.mpris_fd_wr = fd_wr

            self.err_msg(_T("self.w.mpris : {}").format(self.w.mpris))
            if not self.w.mpris:
                return False

            self.w.block_mpris_signals = True

            if not cmd:
                cmd = self.rdstp(fd_rd, 128)
            self.err_msg(_T("on_mpris2 cmd '{}'").format(cmd))

            ret = False

            if s_eq(cmd, "send:signal"):
                sig = self.w.coproc_queue_get()
                if sig == None:
                    self.wr(fd_wr, _T("ACK:NA\n"))
                    self.err_msg(_T("MPRIS cmd signal is N.A."))
                    ret = False
                else:
                    ret = self.mpris2_send_signal(fd_rd, fd_wr, sig)
            elif s_eq(cmd[:5], "base:"):
                cmd = cmd[5:]
                if s_eq(cmd, "getproperty"):
                    ret = self.mpris2_send(fd_rd, fd_wr, cmd, "base")
                elif s_eq(cmd, "setproperty"):
                    ret = self.mpris2_recv(fd_rd, fd_wr, cmd, "base")
                elif s_eq(cmd, "method"):
                    self.err_msg(_T("on_mpris2 > method"))
                    ret = self.mpris2_meth(fd_rd, fd_wr, cmd, "base")
            elif s_eq(cmd[:7], "player:"):
                cmd = cmd[7:]
                if s_eq(cmd, "getproperty"):
                    ret = self.mpris2_send(fd_rd, fd_wr, cmd, "player")
                elif s_eq(cmd, "setproperty"):
                    ret = self.mpris2_recv(fd_rd, fd_wr, cmd, "player")
                elif s_eq(cmd, "method"):
                    ret = self.mpris2_meth(fd_rd, fd_wr, cmd, "player")
            else:
                self.wr(fd_wr, _T("UNSUPPORTED\n"))
                self.err_msg(_T("MPRIS cmd is unsupported"))

            self.done()
            return ret

# end if _in_xws:

# a null log class

if py_v_is_3:
    _log_base = wx.Log
    _log_settarget = wx.Log.SetActiveTarget
else:
    _log_base = wx.PyLog
    _log_settarget = wx.Log.SetActiveTarget

class AppNullLog(_log_base):
    def __init__(self):
        _log_base.__init__(self)

    def DoLogRecord(self, l, message, i):
        pass

    def DoLogString(self, message, timeStamp):
        pass

T_EVT_GREPLOG_MESSAGE = wx.NewEventType()
EVT_GREPLOG_MESSAGE = wx.PyEventBinder(T_EVT_GREPLOG_MESSAGE, 1)
class AppGrepLogEvent(wx.PyEvent):
    """A custom event for the wxWidgets event mechanism:
    to be sent by AppGrepLog when it finds a log message
    passing the 'grep'.
    """
    def __init__(self, e_id, level, message, log_info, inverse):
        wx.PyEvent.__init__(
            self, e_id,
            T_EVT_GREPLOG_MESSAGE)

        self.level = level
        self.message = message
        self.log_info = log_info
        self.inverse = inverse

    def get_message(self):
        return self.message

    def get_content(self):
        return (self.level,
                self.message,
                self.log_info,
                self.inverse)

class AppGrepLog(_log_base):
    """Logging class that inspects the messages passing through
    with a regular expression (i.e., greps), and on match[*] will
    either post an event (AppGrepLogEvent), ar call a function.
    args:
    ev_destobj -- if ev_id is an int this must be an event handler
                  derived object; the target of the posted event
    ev_id      -- may be an int in which case upon a grep match will
                  post an event (and this int should be returned
                  by event.GetId(), and the ev_destobj must be valid);
                  or, may be a function and it will be called with
                  args: wxLogLevel, the message, timestamp, and
                  the 'inverse' boolean passed to our ctor -- see
                  AppGrepLogEvent for the event that might be posted
    rx         -- the regular expression to use; do not compile
                  it, that is done in ctor
    inverse    -- boolean: if False respond to rx matches, or else
                  respond to match failures; e.g., if all app code
                  prefixes log messages with '>>> ' then if inverse
                  is True messages from the wx library can be found
    target_log -- a wxLog object that is passed the logging data to
                  do the actual logging; may be None and this will
                  be a 'null' log

    [*] although writing of matches, rx.search() is used, so anchor!
    """
    def __init__(self, ev_destobj, ev_id, rx, inverse, target_log):
        _log_base.__init__(self)
        self.ev_destobj = ev_destobj
        self.ev_id      = ev_id
        self.rx         = re.compile(rx)
        self.inverse    = inverse
        self.target_log = target_log

    def DoLogRecord(self, l, message, i):
        if self.target_log:
            self.target_log.LogRecord(l, message, i)
        m = self.rx.search(message)
        if (m and not self.inverse) or (self.inverse and not m):
            eid = self.ev_id
            inv = self.inverse
            tim = i.timestamp
            if isinstance(eid, int):
                evt = AppGrepLogEvent(eid, l, message, tim, inv)
                wx.PostEvent(self.ev_destobj, evt)
            elif callable(eid):
                # callable() builtin is not certain, e.g. if
                # arg is a string callable() might be True
                try: eid(l, message, tim, inv)
                except: pass


# the main app [wx.App]

_re_fsopt = r'--?fs(?:-e(?:n(?:c(?:o(?:d(?:i(?:n(?:g)?)?)?)?)?)?)?)?'
_re_fsopt += r'=(\S+)'
_re_fsopt = re.compile(_re_fsopt)

class TheAppClass(wx.App):
    def __init__(self, ac = None, av = None):
        self.av = av if av else sys.argv
        self.ac = ac if ac else len(self.av)

        pth, x   = os.path.splitext(self.av[0])
        pth, nam = os.path.split(pth)

        self.prog = nam

        self.debug   = ("-debug" in self.av)
        self.verbose = ("-verbose" in self.av)
        if _in_xws:
            self.dompris = not ("-no-mpris" in self.av)
        else:
            self.dompris = False

        def _args_re_filt(arg):
            m = re.match(_re_fsopt, arg)
            if m:
                global filesys_encoding
                filesys_encoding = m.group(1)
                return False
            return (arg != "-inspection" and
                    arg != "-no-mpris" and
                    arg != "-verbose" and
                    arg != "-debug")

        self.av = p_filt(_args_re_filt, self.av)

        wx.App.__init__(self)

    def OnExit(self):
        wx.Log.DontCreateOnDemand()

        if self.reslist:
            dset = self.get_data_dir_curset()
            wr_current_set(self.reslist, dset)

        if self.mshelper:
            self.mshelper.do_resume()
        #elif self.xhelper:
        #    self.xhelper.on_exit()

        return 0

    def OnInit(self):
        self.linemax = None
        self.quitting = False

        self.frame = None

        # Use function for AppGrepLog, rather than event, since
        # matches will be synchronous with source of message
        if True:
            self.filterlog_id = self.do_filterlog
        else:
            # get events from filter log
            self.Bind(EVT_GREPLOG_MESSAGE, self.on_filterlog)
            self.filterlog_id = new_wx_id()

        rx = _(r'^>>>\s.*$')
        log = wx.LogStderr() if (self.debug or
                                self.verbose) else AppNullLog()
        self.wxlog = AppGrepLog(self, self.filterlog_id, rx, True, log)
        self.wxlog_orig = wx.Log.SetActiveTarget(self.wxlog)

        self.xhelper  = None
        self.mshelper = None
        if _in_xws:
            try:
                procargs = [_T(os.environ['WXMAV_XHELPERPATH']),
                            _T('--appname={}').format(self.prog),
                            _T('--xautolock'),
                            _T('--xscreensaver')]
            except:
                global x_helper_prog
                if x_helper_prog:
                    procargs = [x_helper_prog,
                                _T('--appname={}').format(self.prog),
                                _T('--xautolock'),
                                _T('--xscreensaver')]
                else:
                    procargs = None

            self.xhelper = XWSHelperProcClass(
                            self,
                            procargs = procargs,
                            mpris2 = self.should_do_mpris())
            global X11hack
            if X11hack and X11hack["lib_err"]:
                self.err_msg(_T("Cannot load {} : '{}'").format(
                            X11hack["libname"], X11hack["lib_err"]))
                del X11hack
                X11hack = None
        elif _in_msw:
            self.mshelper = MSWScreensaverHelper()

        if self.xhelper:
            # Custom event from child handler threads
            self.Bind(EVT_CHILDPROC_MESSAGE, self.on_chmsg)

        # Bind handlers for {QUERY_,}END_SESSION events --
        # These might be delivered only on MSW, but the
        # binding should be OK in any case
        self.Bind(wx.EVT_QUERY_END_SESSION, self.on_query_endsession)
        self.Bind(wx.EVT_END_SESSION, self.on_do_endsession)

        #self.SetAppName(self.prog)
        self.std_paths = wx.StandardPaths.Get()

        config = self.get_config()
        config.SetPath(_T('/main'))

        # main window holds data and should call
        # set_reslist, at least before closing, so
        # that this can be used to save set on exit
        self.reslist = None

        acmd = self.av[1:]
        if acmd:
            # if given command args, begin playing
            argplay = True
        else:
            acmd, errs = rd_current_set(self.get_data_dir_curset())
            # for save data, wait for play command
            argplay = False

        # pos is repeated later in frame's conf_rd() -- w/o
        # both, vertical position is off.
        if config.HasEntry(_T("x")) and config.HasEntry(_T("y")):
            pos = wx.Point(
                x = max(config.ReadInt(_T("x"), 0), 0),
                y = max(config.ReadInt(_T("y"), 0), 0)
            )
        else:
            pos = wx.DefaultPosition

        w = config.ReadInt(_T("w"), -1)
        h = config.ReadInt(_T("h"), -1)
        if w < 100 or h < 100:
            w = 800
            h = 640
        size = wx.Size(w, h)

        self.frame = TopWnd(
            None, wx.ID_ANY,
            _("(WX) M A/V (Player)"),
            size = size, pos = pos,
            cmdargs = acmd, argplay = argplay)

        self.SetTopWindow(self.frame)

        self.frame.Show(True)

        if config.ReadBool(_T("iconized"), False):
            self.frame.Iconize(True)
        elif config.ReadBool(_T("maximized"), False):
            self.frame.Maximize(True)

        if self.xhelper:
            if self.xhelper.go():
                wx.CallAfter(self.frame.xhelper_ready, self.xhelper)
            else:
                # problem execing child: must do without
                s = self.xhelper.get_status()
                self.xhelper = None
                self.err_msg(
                    "APP OnInit: Xhelper exec FAIL {}".format(s))

        self.err_msg("PYTHON VERSION: '{}'".format(sys.version))

        return True


    def _on_signal(self, signum):
        """This should only be called from a platform helper
        oblect -- the X Window System helper presently --
        and we should *only* set an (atomic) flag here, since
        it is meant to be called from a signal handler.
        """
        if self.frame:
            self.frame._quit_signal = signum
        else:
            self._quit_signal = signum
            wx.Exit()

    def get_prog_name(self):
        return self.prog

    def get_config(self):
        try:
            return self.config
        except AttributeError:
            # Phoenix: wx.CONFIG_USE_LOCAL_FILE is missing, although
            # mentioned in core classes Config docs.
            if _in_msw:
                self.config = wx.Config(self.prog,
                    vendorName = _T("GPLFreeSoftwareApplications"))
            else:
                cfnam = os.path.join(self.get_data_dir(), "config")
                self.config = wx.Config(self.prog,
                    localFilename = cfnam,
                    vendorName = _T("GPLFreeSoftwareApplications"))
        return self.config


    def set_reslist(self, lst = None):
        if not lst:
            lst = []
        self.reslist = lst

    def get_data_curset_dir_name(self):
        return _T("current.set")

    def get_data_dir_curset(self):
        return os.path.join(self.get_data_dir(),
                            self.get_data_curset_dir_name())

    def get_data_dir(self):
        return self.std_paths.GetUserDataDir()

    def get_data_dir_local(self):
        # only different on MSW
        return self.std_paths.GetUserLocalDataDir()

    def get_config_dir(self):
        return self.std_paths.GetUserConfigDir()

    def should_do_mpris(self):
        return self.dompris

    def get_mpris2_signal_io(self):
        if not _in_xws:
            return None

        if self.xhelper and self.should_do_mpris():
            return (self.xhelper.get_mpris_pipe_signal_obj(),
                    self.xhelper.get_mpris_pipe_control_obj())

        return None

    def get_debug(self):
        return self.debug

    def prdbg(self, *args):
        if self.get_debug():
            wx.LogWarning(str().join(p_map(lambda s: s + '\n', args)))

    def err_msg(self, msg):
        fn = wx.LogError
        fn(_T(">>> {}\n").format(msg.rstrip()))

    def do_filterlog(self, l, msg, tim, inv):
        if self.frame:
            self.frame.do_filter_msg(l, msg, tim, inv)

    def on_filterlog(self, event):
        eid = event.GetId()
        if eid != self.filterlog_id:
            return
        l, msg, tim, inv = event.get_content()
        self.do_filterlog(l, msg, tim, inv)

    def on_do_endsession(self, event):
        """on_do_endsession to handle wx.EVT_END_SESSION --
        non-optional quit for logout/shutdown -- close frame
        with argument True meaning cannot veto, do not query
        user, just close down
        """
        if True:
            self.save_self_state()

        try:
            self.frame.Close(True)
        except:
            pass

    def on_query_endsession(self, event):
        """on_query_endsession to handle wx.EVT_QUERY_END_SESSION --
        optional quit for logout/shutdown -- the event arg has
        CanVeto(), and if true it might be possible to veto
        the impending doom; but, this app has no need to do so,
        so this event is merely taken as a sign that data should be
        written
        """
        #self.save_self_state()
        pass

    def save_self_state(self):
        """Save state here, prefereably such that next start
        can restore equivalent state -- call from
        *_ENDSESSION events (MSW) of SmcSaveYourselfProc
        (X, using x-helper program [if implemented])
        """
        try:
            self.reslist = self.frame.get_reslist()
        except:
            self.reslist = None

        if self.reslist:
            self.frame.config_wr(flush = True)
            dset = self.get_data_dir_curset()
            wr_current_set(self.reslist, dset)
        else:
            pass

        #config = self.get_config()
        #if config:
        #    config.Flush()

    def on_chmsg(self, event):
        eid = event.GetId()

        t, dat = event.get_content()

        if t == _T("M"):
            try:
                lin, obj, donefd = dat
                err = obj.poll_err
                errbits = select.POLLERR|select.POLLHUP|select.POLLNVAL
                if err & errbits:
                    self.frame.mpris = False
                    self.frame.mpris_fd_rd = -1
                    self.frame.mpris_fd_wr = -1
                    e = "closed" if (err & select.POLLHUP) else "error"
                    self.err_msg(
                        _T("X-mpris helper pipe: {}").format(e))
                    self.xhelper.mpris_off()
                    return
            except AttributeError:
                pass

        if t == _T("M") or t == _T('time period'):
            self.frame.on_chmsg(event)
            return

        if t == _T('enter run'):
            self.do_enter_run()
            return

        if t == _T('exit run'):
            self.do_exit_run()
            return

        if t == _T('2'):
            self.do_stderr_msg(dat)
            return

        if dat[0:4] == _T("tid "):
            return

        if t != _T('1'):
            self.do_handler_msg(dat)
            return

        if not self.quitting:
            self.frame.on_chmsg(event)

    """
    The remainder of the methods of this class concern the child
    process (under X) that reports media keys
    """
    # when top window gets close event that can be vetoed,
    # it must this, and only self.Destroy() if this returns True,
    # else veto the event and wait until it gets event AppDestroyEvent
    # then it can destroy
    def test_exit(self):
        self.save_self_state()
        if self.xhelper:
            try:
                return self.xhelper.test_exit()
            except:
                self.err_msg(_T("EXCEPTION: xhelper.test_exit()"))
                return False

        return True

    def do_screensave(self, on = True):
        if self.mshelper:
            self.mshelper.do_screensave(on)
        elif self.xhelper:
            self.xhelper.do_screensave(on)

    def do_query(self):
        if self.xhelper:
            return self.xhelper.do_query()

    def do_wname(self):
        if self.xhelper:
            return self.xhelper.do_wname()

    def do_setwname(self, s_title):
        if self.xhelper:
            return self.xhelper.do_setwname(s_title)

    def do_wroot(self):
        if self.xhelper:
            return self.xhelper.do_wroot()

    def do_enter_run(self):
        if self.xhelper:
            return self.xhelper.do_enter_run()

    def do_exit_run(self):
        if self.xhelper:
            return self.xhelper.do_exit_run()

    def do_stderr_msg(self, dat):
        m = _("subprocess warning: {s}").format(s = dat.rstrip())
        self.err_msg(m)

    def do_handler_msg(self, dat):
        m = _("subprocess handler: {s}").format(s = dat.rstrip())
        self.err_msg(m)

    def check_linemax(self, s):
        if self.xhelper:
            return self.xhelper.check_linemax(s)



class SliderPanel(wx.Panel):
    def __init__(self, parent, ID,
                       slider_id = wx.ID_ANY,
                       slider_style = wx.SL_HORIZONTAL | wx.SL_LABELS,
                       item_margin = 4,
                       sizer_flags = wx.EXPAND | wx.LEFT | wx.RIGHT
                                   | wx.ALIGN_CENTRE_VERTICAL):
        wx.Panel.__init__(self, parent, ID)

        szr = wx.BoxSizer(wx.VERTICAL)

        self.slider = wx.Slider(self, slider_id, style = slider_style)

        szr.Add(self.slider, 1, sizer_flags, item_margin)

        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_KEY_UP,   self.on_key)
        self.slider.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.slider.Bind(wx.EVT_KEY_UP,   self.on_key)
        self.slider.Bind(wx.EVT_CHAR,   self.on_key)

        # for wxPython 4.0.0a1
        self.Bind(wx.EVT_SIZE, self.on_size)

        self.SetSizer(szr)
        self.Layout()

    def get_slider(self):
        return self.slider

    # for wxPython 4.0.0a1 -- this should not be necessary, but with
    # new phoenix background in one of two instances did not paint
    # properly on fullscreen or maximize; this should be harmless
    # otherwise.
    def on_size(self, event):
        wx.CallAfter(self.Layout)

    def on_key(self, event):
        if True:
            event.Skip()
        else:
            t = event.GetEventType()
            p = self.GetParent()

            if t == wx.wxEVT_KEY_DOWN:
                p.handle_key_down(self.slider, event)
            elif t == wx.wxEVT_KEY_UP:
                p.handle_key_up(self.slider, event)
            elif t == wx.wxEVT_CHAR:
                p.handle_key_up(self.slider, event)
            else:
                event.Skip()


class ButtonData:
    def __init__(self, parent = None,
                       ID = wx.ID_ANY,
                       label = _("DEFAULT LABEL"),
                       pos = wx.DefaultPosition,
                       size = wx.DefaultSize,
                       style = wx.NO_BORDER,
                       handler = None):

        self.parent = parent
        self.ID = ID
        self.label = label
        self.pos = pos
        self.size = size
        self.style = style
        self.handler = handler

    def mk(self):
        # parent is required
        if not self.parent:
            return None

        return wx.Button(self.parent,
                         self.ID,
                         self.label,
                         self.pos,
                         self.size,
                         style = self.style)


class ButtonPanel(wx.ScrolledWindow):
    def __init__(self, parent, ID,
                       button_data,
                       item_margin = 4,
                       spacer_width = 2,
                       sizer_flags = wx.EXPAND | wx.LEFT | wx.RIGHT
                                   | wx.ALIGN_CENTRE_VERTICAL):
        wx.ScrolledWindow.__init__(self, parent, ID)

        self.panel = wx.Panel(self, wx.ID_ANY)
        szr = wx.BoxSizer(wx.HORIZONTAL)

        szr.AddSpacer(spacer_width)

        self.id_map = []

        for bd in button_data:
            if not bd.parent:
                bd.parent = self.panel

            btn = bd.mk()
            hdlr = bd.handler or self.null_handler
            btn.Bind(wx.EVT_BUTTON, hdlr, btn, bd.ID)
            szr.Add(btn, 1, sizer_flags, item_margin)
            szr.AddSpacer(spacer_width)

            self.id_map.append((bd.ID, btn))

        self.Bind(wx.EVT_SIZE, self.on_size)

        self.panel.SetSizer(szr)
        self.panel.Fit()

        sz = self.panel.GetSize()
        self.SetVirtualSize(sz)
        self.SetScrollRate(1, 0)

        szr = wx.BoxSizer(wx.HORIZONTAL)
        szr.Add(self.panel, 0, 0, 0)
        self.Fit()

    def get_id_map(self):
        return self.id_map

    def get_sizer(self):
        return self.panel.GetSizer()

    def on_size(self, event):
        event.Skip()

    def null_handler(self, event):
        event.Skip()


class MediaPanel(wx.Panel):
    def __init__(self, parent, ID, size = (640, 480), handlers = None):
        wx.Panel.__init__(self, parent, ID, size = size)

        self.medi = None

        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.handlers = handlers

        # bindings
        for event, handler in self.handlers:
            self.Bind(event, handler)

        self._mk_medi()

        self.Bind(wx.EVT_SIZE, self.on_size)

        self.new_size = False
        self.load_ok = False
        self.med_len = 0
        self.med_sz  = wx.Size(0, 0)

        self.last_mouse_pos = wx.DefaultPosition

    def _hack_on_color(self):
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

    def _mk_medi(self):
        # the following try block with the wxMSW code is from an
        # example found at
        #    github.com/wxWidgets/wxPython/blob/master/demo/MediaCtrl.py
        # but unfortunately it is not working well either,
        # and furthermore Quicktime for MSW seems to be dead since
        # ~2009
        try:
            backend = ""
            if True and _in_msw:
                # [original comment:]
                # the default backend doesn't
                # always send the EVT_MEDIA_LOADED
                # event which we depend upon, so use
                # a different backend by default for this demo.
                # [new comment, EH:]
                # will need to code around missing EVT_MEDIA_LOADED
                # MEDIABACKEND_WMP10 seems best overall on MSW 7,
                # and it does a little oscilloscope thingy for audio
                # TODO: make backend menu option for MSW
                #backend = wx.media.MEDIABACKEND_QUICKTIME
                # Note: DIRECTSHOW is no longer an option: does
                # not do unbounded streams
                #backend = wx.media.MEDIABACKEND_DIRECTSHOW
                backend = wx.media.MEDIABACKEND_WMP10

            if phoenix:
                self.medi = wx.media.MediaCtrl()
            else:
                self.medi = wx.media.PreMediaCtrl()

            ok = self.medi.Create(
                self, wx.ID_ANY,
                pos = wx.DefaultPosition, size = wx.DefaultSize,
                style = wx.BORDER_NONE,
                szBackend = backend)

            if not ok:
                raise NotImplementedError

            if not phoenix:
                self.medi.PostCreate(self.medi)
        except NotImplementedError:
            self.medi = wx.media.MediaCtrl(
                self, wx.ID_ANY,
                pos = wx.DefaultPosition, size = wx.DefaultSize,
                style = wx.BORDER_NONE)

        # bindings
        for event, handler in self.handlers:
            self.medi.Bind(event, handler)

    def prdbg(self, *args):
        self.GetParent().prdbg(*args)

    def err_msg(self, msg):
        self.GetParent().err_msg(msg)

    def get_length(self, size, length):
        return self.med_len

    def get_size(self, size, length):
        return self.med_sz

    def set_meta(self, size, length):
        self.med_len = length
        self.med_sz  = size

    def do_new_size(self):
        xoff = yoff = 0
        ssz = self.GetSize()
        msz = self.medi.GetBestSize()

        # can this happen?
        if ssz.height < 1 or ssz.width < 1:
            return

        # can happen
        if msz.height < 1 or msz.width < 1:
            msz = self.med_sz
        else:
            self.prdbg(_T("MEDIA BEST SIZE {},{}").format(
                        msz.width, msz.height))

        # can happen
        if msz.height < 1 or msz.width < 1:
            # returning 0,0 for http stream; but ok for local files
            if False:
                self.err_msg(_T("BAD VIDEO SIZE {},{}").format(
                                msz.width, msz.height))
            msz = ssz

        sr = float(ssz.width) / float(ssz.height)
        mr = float(msz.width) / float(msz.height)

        if mr > sr:
            w = ssz.width
            h = int(float(w) / mr)
            yoff = (ssz.height - h) / 2
            ssz = wx.Size(w, h)
        else:
            h = ssz.height
            w = int(float(h) * mr)
            xoff = (ssz.width - w) / 2
            ssz = wx.Size(w, h)

        self.medi.SetSize(ssz)
        self.medi.SetPosition(wx.Point(xoff, yoff))

    def on_size(self, event):
        self.new_size = True
        self.do_new_size()

    def do_idle(self, event):
        if self.new_size and self.load_ok:
            self.new_size = False
            self.do_new_size()



"""
Media Group edit dialog and associated classes to provide
drag and drop editing within a wxTreeCtrl
"""

class EditTreeCtrlDropSource(wx.DropSource):
    """Based on -- with much copying -- example at wxPython Wiki
    https://wiki.wxpython.org/TreeControls"""
    def __init__(self, tree):
        wx.DropSource.__init__(self, tree)
        self.tree = tree


    def SetData(self, obj, origdata):
        wx.DropSource.SetData(self, obj)
        self.data = origdata

    def GiveFeedback(self, effect):
        x, y = wx.GetMousePosition()
        if phoenix:
            x, y = self.tree.ScreenToClient(x, y)
        else:
            x, y = self.tree.ScreenToClientXY(x, y)
        ID, flag = self.tree.HitTest((x, y))

        if not ID.IsOk():
            # does not appear:
            #self.SetCursor(wx.DragNone,
            #               select_cursor(wx.CURSOR_NO_ENTRY))
            return True

        self.tree.SelectItem(ID)
        return False


class EditTreeCtrlDropData:
    def __init__(self,
                 ID    = None, # wxTreeItemId
                 label = None, # item label/text
                 data  = None  # item data
                 ):
        self.ID = ID
        self.label = label
        self.data = data

    def __repr__(self):
        return _T('ID: {}\n'
                  'label: {}\n'
                  'data: {}').format(self.ID, self.label, self.data)

    def SetSource(self, ID, label, data):
        self.ID = ID
        self.label = label
        self.data = data

    def get_tuple(self):
        return (self.ID, self.label, self.data)


edit_tree_droptarget_base = general_droptarget_base

class EditTreeCtrlDropTarget(edit_tree_droptarget_base):
    dformat = 'EditTreeCtrlDndData'

    def __init__(self, tree):
        edit_tree_droptarget_base.__init__(self)
        self.tree = tree

        self.df = custom_data_fmt(EditTreeCtrlDropTarget.dformat)
        self.cdo = wx.CustomDataObject(self.df)
        self.SetDataObject(self.cdo)

    def OnEnter(self, x, y, d):
        return d

    def OnLeave(self):
        pass

    def qualify_hit_flag(self, flag):
        hit_res = 0 # 0 NG, 1 above, 2 below, 3 child

        # Above the client area.
        if flag & wx.TREE_HITTEST_ABOVE:
            hit_res = 1
        # Below the client area.
        elif flag & wx.TREE_HITTEST_BELOW:
            hit_res = 2
        # In the client area but below the last item.
        elif flag & wx.TREE_HITTEST_NOWHERE:
            pass
        # On the button associated with an item.
        elif flag & wx.TREE_HITTEST_ONITEMBUTTON:
            hit_res = 1
        # On the bitmap associated with an item.
        elif flag & wx.TREE_HITTEST_ONITEMICON:
            hit_res = 1
        # In the indentation associated with an item.
        elif flag & wx.TREE_HITTEST_ONITEMINDENT:
            hit_res = 1
        # On the label (string) associated with an item.
        elif flag & wx.TREE_HITTEST_ONITEMLABEL:
            hit_res = 2
        # In the area to the right of an item.
        elif flag & wx.TREE_HITTEST_ONITEMRIGHT:
            hit_res = 2
        # On the state icon for a tree view item that
        # is in a user-defined state.
        elif flag & wx.TREE_HITTEST_ONITEMSTATEICON:
            pass
        # To the right of the client area.
        elif flag & wx.TREE_HITTEST_TOLEFT:
            hit_res = 1
        # To the left of the client area.
        elif flag & wx.TREE_HITTEST_TORIGHT:
            hit_res = 2

        return hit_res


    def delete_item_and_children(self, ID = None, flush = False):
        self.tree.delete_item_and_children(ID = ID, flush = flush)

    def copy_item_children(self, src, dst):
        self.tree.copy_item_children(src = src, dst = dst)

    def OnDragOver(self, x, y, default):
        ID, flag = self.tree.HitTest((x, y))
        if not ID.IsOk():
            return wx.DragNone
        return default

    def OnDrop(self, x, y):
        ID, flag = self.tree.HitTest((x, y))
        if not ID.IsOk():
            return False

        hit_res = self.qualify_hit_flag(flag)

        if hit_res < 1:
            # don't want it dropped here
            return False

        return True

    def OnData(self, x, y, d):
        if not (d == wx.DragCopy or d == wx.DragMove):
            return wx.DragNone

        if not self.GetData():
            return wx.DragNone

        tr = self.tree
        (ID, flag) = tr.HitTest((x, y))

        if not ID.IsOk():
            return wx.DragNone

        tr.SelectItem(ID)
        hit_res = self.qualify_hit_flag(flag)

        if hit_res < 1:
            # don't want it dropped here
            return wx.DragNone

        src_str = self.cdo.GetData()
        src_dat = tr.item_id_get(src_str)
        if not src_dat:
            return wx.DragNone

        tr.item_id_free(src_str)

        orig_ID, orig_label, orig_data = src_dat.get_tuple()

        if not orig_ID.IsOk():
            return wx.DragNone

        if ID == orig_ID:
            # no self service allowed
            return wx.DragNone

        new_prt  = tr.GetItemParent(ID)
        orig_prt = tr.GetItemParent(orig_ID)
        root = tr.GetRootItem()

        # the 'hidden' root can be accessed and selected with
        # tabbing (sigh) in which case get parent etc. return
        # invalid items and failing to check might produce an
        # assertion in underlying wxWidgets C++ code
        if not (new_prt.IsOk() and orig_prt.IsOk() and root.IsOk()):
            return wx.DragNone

        lvlnew  = 1 if (root == new_prt) else (
            2 if (root == tr.GetItemParent(new_prt)) else 3)
        lvlorig = 1 if (root == orig_prt) else (
            2 if (root == tr.GetItemParent(orig_prt)) else 3)

        # each level represents a type, so only accept
        # drop at same level, or target level 1 up from
        # source item meaning append as child
        as_child = False
        if (lvlnew + 1) == lvlorig:
            as_child = True
        elif lvlnew != lvlorig:
            return wx.DragNone

        # ok, can do
        if as_child:
            delitem = None
            if lvlorig == 3:
                # level 2 parent allowed only one level 3 child
                delitem, CK = tr. GetFirstChild(ID)

            if hit_res == 1:
                #print("PREPEND AS CHILD")
                N = tr.PrependItem(ID, orig_label)
                tr.set_it_dat(N, orig_data)
                self.copy_item_children(orig_ID, N)
            else:
                #print("APPEND AS CHILD")
                N = tr.AppendItem(ID, orig_label)
                tr.set_it_dat(N, orig_data)
                self.copy_item_children(orig_ID, N)

            tr.SelectItem(N)

            if delitem and delitem.IsOk():
                try:
                    self.delete_item_and_children(delitem)
                except:
                    pass

        elif hit_res == 1:
            pre = tr.GetPrevSibling(ID)
            if pre and pre.IsOk():
                #print("PREPEND AS SIBLING 1")
                N = tr.InsertItem(new_prt, pre, orig_label)
                tr.set_it_dat(N, orig_data)
                self.copy_item_children(orig_ID, N)
            else:
                #print("PREPEND AS SIBLING 2")
                N = tr.PrependItem(new_prt, orig_label)
                tr.set_it_dat(N, orig_data)
                self.copy_item_children(orig_ID, N)

            tr.SelectItem(N)

            if lvlorig == 3:
                try:
                    self.delete_item_and_children(ID)
                except:
                    pass

        else:
            #print("APPEND AS SIBLING")
            N = tr.InsertItem(new_prt, ID, orig_label)
            tr.set_it_dat(N, orig_data)
            self.copy_item_children(orig_ID, N)

            tr.SelectItem(N)

            if lvlorig == 3:
                try:
                    self.delete_item_and_children(ID)
                except:
                    pass

        if d == wx.DragCopy:
            pass
        elif d == wx.DragMove:
            self.delete_item_and_children(orig_ID)
        else:
            pass

        # with (flush = True), does actual pending deletes,
        # and with [default] item = None, that is all
        self.delete_item_and_children(flush = True)

        return d


class EditTreeCtrl(wx.TreeCtrl):
    def __init__(self, parent, ID, pos, size, style):
        wx.TreeCtrl.__init__(self, parent, ID, pos, size, style)

        self.Bind(wx.EVT_TREE_BEGIN_DRAG, self.begin_drag)
        self.Bind(wx.EVT_TREE_END_DRAG, self.end_drag)

        # ARGH! after basic development of tree w/ drag and drop etc.
        # in a small test app, code was pasted here, the intended
        # application, at which point label-edit initiated by
        # left click ceased to function.  It still works in test
        # app.  Bug is not caused by changes herein, but is somehow
        # elicited by context -- suspect is timing issue, since
        # in the test app the label must be clicked _just so_ to
        # invoke editing; present context is much more complex --
        # so must offer alternatives to invoke this essential
        # functionality; right and middle clicks seem obvious,
        # but does Apple still have that one-legged mouse? That's
        # no good! Need an Apple box to test on.
        self.Bind(wx.EVT_TREE_ITEM_MIDDLE_CLICK, self.mid_click)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.right_click)

        # will need some key handling, _careful_ not to
        # interfere with default behavior
        self.Bind(wx.EVT_TREE_KEY_DOWN, self.key_down)

        # root item is hidden, but can still be selected with
        # tabbing, which is not wanted -- try to move selection
        # from root to its first child
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.sel_changed)

        self.SetDropTarget(EditTreeCtrlDropTarget(self))

        # unfortunate hack bacause A) wxPython version of
        # wxCustomDataObject.SetData takes a string argument --
        # no objects -- and B) cPickle cannot 'pickle' a
        # python object and C) wxTreeItemId is not an integer
        # but an object and D) I need a way to uniquely
        # identify the tree item source for internal DND
        # and item label or data might not be unique --
        # so keep a list, with item added at drag start,
        # and return the index as a string key; also provide
        # a 'free' method and get method and alloc method
        # -- see item_id_*() below
        self.dnd_item_list = []

        # a drop might need to arrange some deletes, but
        # should not delete at that stage, but call proc
        # that will append this (add_pending_delete), then
        # after completing ops, finally call delete_pending
        self.deletes_pending = []

        # these are used when populating the tree, for
        # empty fields, and for comparison when fetching data
        self.no_media = _("[Press space to add file or URL.]")
        self.no_desc  = _("[Press space to edit description.]")



    def sel_changed(self, event):
        # root item is hidden, but can still be selected with
        # tabbing, which is not wanted -- try to move selection
        # from root to its first child
        sID   = self.GetSelection()
        root  = self.GetRootItem()

        if not (sID.IsOk() and root.IsOk() and sID == root):
            return

        self.make_default_selection(sID)

    def make_default_selection(self, root = None):
        if not root:
            root = self.GetRootItem()

        if not root.IsOk():
            return

        nID, cookie = self.GetFirstChild(root)

        if nID.IsOk():
            self.SelectItem(nID)


    # user initiated insert, prompt as needed
    def user_insert_item(self, ID):
        if not ID.IsOk():
            return

        tr = self

        pID   = tr.GetItemParent(ID)
        root  = tr.GetRootItem()

        # the 'hidden' root can be accessed and selected with
        # tabbing (sigh) in which case get parent etc. return
        # invalid items and failing to check might produce an
        # assertion in underlying wxWidgets C++ code
        if not (pID.IsOk() and root.IsOk()):
            return

        level = 1 if (root == pID) else (
            2 if (root == tr.GetItemParent(pID)) else 3)

        if level == 3:
            # no insert at this level, but assume
            # the level 2 resource was intended
            self.user_insert_item(pID)
            return

        if level == 1:
            title = _("What would you do?")
            qry = _("Add a new group/playlist, or add a new\n"
                    "media resource to this group?\n\n"
                    "Click yes to add a new group, or "
                    "no to add new media,\n"
                    "or else cancel to forget about it.")

            rsp = wx.MessageBox(qry, title,
                    style = wx.YES_NO | wx.CANCEL |
                            wx.ICON_QUESTION)

            if rsp == wx.CANCEL:
                return
            if rsp == wx.NO:
                # trickery, diddle vars and fall through to
                # level == 2 block
                level = 2
                pID = ID
            else:
                # add new group ...
                nID = tr.AppendItem(root, _("empty playlist"))
                if nID.IsOk():
                    avg = AVGroup()
                    tr.set_it_dat(nID, avg)
                    # ... and trickery again
                    level = 2
                    pID = nID
                else:
                    return

        if level == 2:
            nID = tr.AppendItem(pID, tr.no_media)
            if nID.IsOk():
                it = AVItem(resname = os.devnull)
                tr.set_it_dat(nID, it)
                dID = tr.AppendItem(nID, tr.no_desc)
                tr.set_it_dat(dID, tr.no_desc)

    # user initiated delete, optional prompt
    def user_delete_item(self, ID, prompt = True):
        if not ID.IsOk():
            return

        tr = self

        pID   = tr.GetItemParent(ID)
        root  = tr.GetRootItem()
        # the 'hidden' root can be accessed and selected with
        # tabbing (sigh) in which case get parent etc. return
        # invalid items and failing to check might produce an
        # assertion in underlying wxWidgets C++ code
        if not (pID.IsOk() and root.IsOk()):
            return

        if prompt:
            level = 1 if (root == pID) else (
                2 if (root == tr.GetItemParent(pID)) else 3)

            title = _("Confirm Item Delete")
            lbl = tr.GetItemText(ID)

            if level == 1:
                nch = tr.GetChildrenCount(ID, False)
                qry = _(
                    "The selected group/playlist\n"
                    "'{name}'\n"
                    "has {count} media resources.\n\n"
                    "Really delete it?"
                    ).format(name = lbl, count = nch)
            elif level == 2:
                qry = _("Really delete media resource\n'{}'?").format(
                        lbl)
            elif level == 3:
                res = tr.GetItemText(pID)
                qry = _("Really delete description of\n'{}'?").format(
                        res)

            rsp = wx.MessageBox(qry, title,
                                style = wx.YES_NO | wx.ICON_QUESTION)

            if rsp != wx.YES:
                return

        tr.delete_item_and_children(ID, True)

    # see comment in __init__ at self.deletes_pending
    def delete_item_and_children(self, ID = None,
                                       flush = False,
                                       flush_now = False):
        tr = self
        if ID:
            tr.add_pending_delete(ID)
        if flush:
            tr.delete_pending(flush_now)

    # clear it all out -- use instead if treectrl::DeleteAllItems()
    def delete_all_items(self, flush = True):
        tr = self
        ID = tr.GetRootItem()
        if not ID.IsOk():
            return

        tr.delete_item_and_children(ID, flush = flush, flush_now = True)

        tr.DeleteAllItems()

    def copy_item_children(self, src, dst):
        tr = self
        if not tr.ItemHasChildren(src):
            return

        ID, cookie = tr.GetFirstChild(src)

        try:
            while ID.IsOk():
                lbl = tr.GetItemText(ID)
                dat = tr.get_it_dat(ID)

                NI = tr.AppendItem(dst, lbl)
                tr.set_it_dat(NI, dat)

                self.copy_item_children(ID, NI)

                ID, cookie = tr.GetNextChild(src, cookie)

        except:
            return

    def key_down(self, event):
        kc = event.GetKeyCode()
        # Use space to initiate label edit: space is OK
        # while editing the label, and apparently not used
        # elsewise in the tree control --
        # don't forget to doc'mnt this
        if kc == wx.WXK_SPACE or kc == wx.WXK_CONTROL_E:
            self.edit_label_of(self.GetSelection())
        # user must have ability to delete items
        elif kc == wx.WXK_DELETE or kc == wx.WXK_CONTROL_K:
            self.user_delete_item(self.GetSelection())
        # user must have ability to add new items
        # NOTE had tried wx.WXK_CONTROL_I, but the tab key
        # produces that code!
        elif kc == wx.WXK_INSERT or kc == wx.WXK_CONTROL_N:
            self.user_insert_item(self.GetSelection())

        event.Skip()

    def edit_label_of(self, ID):
        if ID.IsOk():
            self.EditLabel(ID)

    def edit_label_at(self, x_y_pt):
        ID, flags = self.HitTest(x_y_pt)
        if flags & wx.TREE_HITTEST_ONITEMLABEL:
            self.edit_label_of(ID)

    def mid_click(self, event):
        self.edit_label_at(event.GetPoint())

    def right_click(self, event):
        self.edit_label_at(event.GetPoint())

    # tree item delete procedures, so that items are not
    # deleted in the middle of e.g., the drop target handler;
    # delete_pending does the actual deletion of items in
    # storage ...
    def delete_pending(self, do_now = False):
        tr = self
        tlst = []

        for i in tr.deletes_pending:
            if i in tlst or not i.IsOk():
                continue
            tlst.append(i)

        tr.deletes_pending = []

        def _del_later(tr, tlst):
            for i in tlst:
                if not i.IsOk():
                    continue
                if tr.ItemHasChildren(i):
                    tr.DeleteChildren(i)
                tr.Delete(i)

        if do_now:
            _del_later(tr, tlst)
        else:
            wx.CallAfter(_del_later, tr, tlst)

    # ... add_pending_delete adds a tree item to
    # storage for eventual deletion in delete_pending()
    def add_pending_delete(self, item):
        if not item or not item.IsOk():
            return

        if item in self.deletes_pending:
            return

        self.deletes_pending.append(item)

    # Use {g,s}et_it_dat instead of {G,S}etItem{Py}Data so that
    # correct use can be easily checked
    def set_it_dat(self, it, dat):
        if phoenix:
            return self.SetItemData(it, dat)
        else:
            return self.SetItemPyData(it, dat)

    def get_it_dat(self, it):
        if phoenix:
            return self.GetItemData(it)
        else:
            return self.GetItemPyData(it)

    # Keep a list of dnd data objects, because the wxPython
    # drop source cannot take an object, except str() (and
    # object cannot be 'pickled' if it contains a wxPython
    # swig object) -- so ...
    # ... item_id_alloc stores data_obj and returns string
    # key to stored object ...
    # (Oh, more fun: wxPython 4.x [Phoenix] is no longer
    # requiring strings, but rather bytes or bytearray, memoryview.)
    def item_id_alloc(self, data_obj):
        if None in self.dnd_item_list:
            idx = self.dnd_item_list.index(None)
            self.dnd_item_list[idx] = data_obj
        else:
            idx = len(self.dnd_item_list)
            self.dnd_item_list.append(data_obj)

        # simple modification of index, merely so that
        # returned keys have more meat than, e.g., '0'
        r = str(idx + 0xFFFF)
        if phoenix:
            r = r.encode('ascii')

        return r

    # ... item_id_get takes a key (in key) that had been
    # provided by item_id_alloc, and returns the object reference
    # without removal ...
    def item_id_get(self, key):
        try:
            if phoenix:
                if isinstance(key, memoryview):
                    key = bytes(key[:])
                if isinstance(key, bytes):
                    key = key.decode('ascii')
                if not (isinstance(key, str) or isinstance(key, int)):
                    key = str(key)

            idx = int(key) - 0xFFFF
            if idx >= 0 and idx < len(self.dnd_item_list):
                return self.dnd_item_list[idx]
        except:
            pass

        return None

    # ... item_id_free takes a key (in key) that had been
    # provided by item_id_alloc, and removes the object reference
    # from storage; nothing returned, if object is needed use
    # item_id_get prior to this
    def item_id_free(self, key):
        try:
            if phoenix:
                if isinstance(key, memoryview):
                    key = bytes(key[:])
                if isinstance(key, bytes):
                    key = key.decode('ascii')
                if not (isinstance(key, str) or isinstance(key, int)):
                    key = str(key)

            idx = int(key) - 0xFFFF
            # cannot simply del from list -- would screw any
            # higher index in use -- so del only if idx is last
            if idx >= 0 and len(self.dnd_item_list) == (idx + 1):
                del self.dnd_item_list[idx]
            elif idx >= 0 and idx < len(self.dnd_item_list):
                self.dnd_item_list[idx] = None
        except:
            pass

    # drag event handler(s)
    def begin_drag(self, event):
        ID, flags = self.HitTest(event.GetPoint())
        if not ID.IsOk():
            return

        try:
            self.SelectItem(ID)
        except:
            # exception if ID is N.G.
            return

        lbl = self.GetItemText(ID)
        dat = self.get_it_dat(ID)

        ddd = EditTreeCtrlDropData(ID, lbl, dat)

        cdf = custom_data_fmt(EditTreeCtrlDropTarget.dformat)
        cdo = wx.CustomDataObject(cdf)
        dat_idx = self.item_id_alloc(ddd)
        sdr = cdo.SetData(dat_idx)

        tds = EditTreeCtrlDropSource(self)
        tds.SetData(cdo, ddd)

        res = tds.DoDragDrop(wx.Drag_DefaultMove) #wx.Drag_AllowMove)

        if res == wx.DragCopy:
            pass
        elif res == wx.DragMove:
            pass
        else:
            # not done, so return selected highlight to origin
            self.SelectItem(ID)

    # never did get this event
    def end_drag(self, event):
        pass

    # don't want sorting -- do want order preserved
    #def OnCompareItems(self, item1, item2):


class GroupSetEditPanel(wx.Panel):
    def __init__(self, parent, ID):
        wx.Panel.__init__(self, parent, ID)

        szr = wx.BoxSizer(wx.VERTICAL)
        bdr = 1

        stxt = _("Edit playlist groups.  Use '+' or "
                 "double click to expand a group. "
                 "(Place pointer over this text for more "
                 "explanation.)\n")

        stip = wx.ToolTip(_(
                 "Items at left are groups or 'playlists', "
                 "the children of those are the A/V media "
                 "files or URLs, and each of those has one child "
                 "which is a description for the item."
                 "\n\n"
                 "Arrow keys move among the items, the '+' "
                 "key will expand an item that has child items, "
                 "the space key will put a selected item in "
                 "editing mode; the insert key will make a new "
                 "item, and the delete key will remove the "
                 "selected item."
                 "\n\n"
                 "Items may be moved or copied using the mouse "
                 "with drag-and-drop."
                 ))
        sctl = wx.StaticText(self, wx.ID_ANY, stxt)
        sctl.SetToolTip(stip)

        szr.Add(sctl,
                proportion = 0,
                flag = wx.EXPAND | wx.ALL,
                border = bdr)

        szr.AddSpacer(bdr)

        self.tree = EditTreeCtrl(self, wx.ID_ANY,
                                 wx.DefaultPosition,
                                 wx.DefaultSize,
                                 wx.TR_HAS_BUTTONS
                                 | wx.TR_EDIT_LABELS
                                 #| wx.TR_MULTIPLE
                                 | wx.TR_HIDE_ROOT)

        szr.Add(self.tree,
                proportion = 1,
                flag = wx.EXPAND | wx.ALL,
                border = bdr)

        self.SetSizer(szr)
        self.Layout()

    def get_tree(self):
        return self.tree


class GroupSetEditDialog(wx.Dialog):
    def __init__(self, parent, ID,
                 title = _("Edit Media Groups"),
                 size  =  (600, 450),
                 pos = wx.DefaultPosition,
                 style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                 data = []):
        wx.Dialog.__init__(self, parent, ID,
                           title = title, size = size, pos = pos,
                           style = style)

        self.data = data

        szr = wx.BoxSizer(wx.VERTICAL)
        bdr = 16

        self.data = data
        self.edit_panel = GroupSetEditPanel(self, wx.ID_ANY)

        self.tree = self.edit_panel.get_tree()
        if self.data:
            self.set_data(self.data)

        szr.Add(self.edit_panel,
                proportion = 1,
                flag = wx.EXPAND | wx.LEFT|wx.RIGHT|wx.TOP,
                border = bdr)

        bsz = self.CreateButtonSizer(wx.OK | wx.CANCEL)

        szr.Add(bsz,
                proportion = 0,
                flag = wx.EXPAND | wx.ALL,
                border = bdr)

        self.SetSizer(szr)
        self.Layout()

        self.tree.SetFocus()

    def _get_tree_children(self, grp_ID):
        tr   = self.tree
        data = []

        ID, cookie = tr.GetFirstChild(grp_ID)

        try:
            while ID.IsOk():
                lbl = tr.GetItemText(ID)
                old = tr.get_it_dat(ID)

                i = copy.deepcopy(old)
                odn = old.get_res_disp_str(True) or old.resname
                if s_ne(lbl, tr.no_media) and s_ne(lbl, odn):
                    i.resname = lbl
                    i.res_dispname = None

                # if this item has more than one child,
                # it is a bug
                ch_ID, ignore = tr.GetFirstChild(ID)
                if ch_ID.IsOk():
                    desc = tr.GetItemText(ch_ID)
                    if desc != tr.no_desc:
                        i.desc = desc

                data.append(i)

                ID, cookie = tr.GetNextChild(grp_ID, cookie)

        except Exception as e:
            #print("dialog _get_tree_children: std exc '{}'".format(e))
            pass
        except:
            #print("dialog _get_tree_children: EXCEPTION 2")
            pass

        return data

    def get_data(self):
        tr   = self.tree
        data = []

        root = self.treeroot = tr.GetRootItem()
        ID, cookie = tr.GetFirstChild(root)

        try:
            while ID.IsOk():
                lbl = tr.GetItemText(ID)
                dat = tr.get_it_dat(ID)

                g = copy.deepcopy(dat)

                if s_ne(lbl, g.desc):
                    g.set_user_desc(lbl)

                g.data = self._get_tree_children(ID)

                if g.icur >= len(g.data):
                    g.icur = len(g.data) - 1

                data.append(g)

                ID, cookie = tr.GetNextChild(root, cookie)

        except Exception as e:
            #print("dialog get_data: std exc '{}'".format(e))
            pass
        except:
            #print("dialog get_data: EXCEPTION 1")
            pass

        return data

    def set_data(self, data):
        tr = self.tree
        tr.delete_all_items()
        self.data = data
        self._setup_tree()
        self.tree.make_default_selection()

    def _setup_tree(self):
        tr  = self.tree
        dat = self.data

        root = tr.GetRootItem()
        if not root.IsOk():
            root = tr.AddRoot(_("hidden root node"))
        self.treeroot = root

        if phoenix:
            tr.SetItemData(root, None)
        else:
            tr.SetPyData(root, None)

        def _S(s):
            if _in_msw:
                return _T(s)
            return s

        # dat is list of AVGroup
        for gseq, g in enumerate(dat):
            gds = g.get_desc()
            if not g.has_unique_desc():
                gds = _("Group/Playlist {}").format(gseq + 1)

            group = tr.AppendItem(root,
                                  gds if g.has_user_desc() else _S(gds))
            # save original as item data
            tr.set_it_dat(group, g)

            # g.data are AVItem
            idat = g.data
            for iseq, i in enumerate(idat):
                res = i.get_res_disp_str(True) or _T(i.resname)
                lbl = res or tr.no_media
                des = _T(i.desc)
                if not des or s_eq(i.desc, i.resname):
                    des = tr.no_desc

                # append resource as child of group
                rsrc = tr.AppendItem(group, _S(lbl))
                # use orig AVItem as item data
                tr.set_it_dat(rsrc, i)

                # append description as child of resource
                item = tr.AppendItem(rsrc, _S(des))
                # store orig desc -- DO NOT use
                tr.set_it_dat(item, i.desc)



"""
Classes for drag-n-drop hopefully made portable by wxWidgets
"""

class uri_list_dataformat(wx.DataFormat):
    def __init__(self):
        wx.DataFormat.__init__(self, wx.DF_UNICODETEXT)
        self.SetId("text/uri-list")

class uri_list_dataobject(wx.CustomDataObject):
    def __init__(self):
        wx.CustomDataObject.__init__(self, uri_list_dataformat())


class x_moz_url_dataformat(wx.DataFormat):
    def __init__(self):
        wx.DataFormat.__init__(self, wx.DF_UNICODETEXT)
        self.SetId("text/x-moz-url")

class x_moz_url_dataobject(wx.CustomDataObject):
    def __init__(self):
       wx.CustomDataObject.__init__(self, x_moz_url_dataformat())


class multi_dataobject(wx.DataObjectComposite):
    def __init__(self):
        wx.DataObjectComposite.__init__(self)

        self.moz_url_dataobject  = x_moz_url_dataobject()
        self.uri_list_dataobject = uri_list_dataobject()
        self.file_dataobject     = wx.FileDataObject()
        self.text_dataobject     = wx.TextDataObject()
        # chromium in MSW provides moz_url, but in X
        # it provides 'STRING'
        self.STRING_dataobject   = wx.CustomDataObject("STRING")

        self.Add(self.moz_url_dataobject)
        self.Add(self.uri_list_dataobject)
        self.Add(self.file_dataobject)
        self.Add(self.text_dataobject)
        self.Add(self.STRING_dataobject)

    # cooked will coerce return from get_d_raw to a list of str
    def get_d_cooked(self, dfmt):
        r = self.get_d_raw(dfmt)

        if isinstance(r, list):
            return r

        # what remains is text from TextDataObject->GetText,
        # data from DataObject->GetObject->GetData, already
        # coerced to str -- the latter case might have '\0'
        # chars so filter for that first, and then return
        # the result of .splitlines
        if py_v_is_3:
            t = ''.join(p_filt(lambda v: v != '\0', r))
            return t.splitlines()

        return p_filt(lambda v: v != '\0', r).splitlines()


    # raw will return what the data object returns, except in the
    # case of CustomDataObject derivatives for which return is
    # coerced to string
    def get_d_raw(self, dfmt):
        try:
            datid = dfmt.GetId()
        except:
            datid = "bad"

        # badness: mime "text/uri-list" will produce file_dataobject
        # that returns an empty list from GetFilenames()
        if datid == "text/uri-list":
            pass # bypass following tests
        elif dfmt == self.file_dataobject.GetFormat():
            return self.file_dataobject.GetFilenames()
        elif dfmt == self.text_dataobject.GetFormat():
            return self.text_dataobject.GetText()

        if phoenix:
            o = self.GetObject(dfmt, wx.DataObject.Get)

            try:
                return o.GetFilenames()
            except AttributeError:
                pass
            try:
                return o.GetText()
            except AttributeError:
                pass

            try:
                # if this raises AttributeError then a new format
                # object has been passed, or is behaving unexpectedly
                d = o.GetData()

                if isinstance(d, bytearray):
                    d = memoryview(d[:])
                if isinstance(d, memoryview):
                    d = bytes(d[:])
                if isinstance(d, bytes):
                    d = _T(d)
                if not isinstance(d, str):
                    d = _T(d)
            except AttributeError as e:
                wx.GetApp().prdbg(
                    "multi_dataobject: exception '{}'".format(e))
                return ""
            except:
                wx.GetApp().prdbg(
                    "multi_dataobject: exception 'unknown'")
                return ""

            return d

        return self.GetDataHere(dfmt)


multi_droptarget_base = general_droptarget_base

class multi_droptarget(multi_droptarget_base):
    drag_return_type = wx.DragCopy

    def __init__(self, target_obj = None):
        multi_droptarget_base.__init__(self)

        self.target = target_obj if target_obj else wx.GetApp()
        self.do = multi_dataobject()
        self.SetDataObject(self.do)

        self.debug = wx.GetApp().debug

    def prdbg(self, *args):
        if self.debug:
            wx.GetApp().prdbg(*args)

    def OnData(self, x, y, d):
        if not self.GetData() or not self.target.do_file_drop:
            return wx.DragNone

        files = None
        datf  = self.do.GetReceivedFormat()
        datid = _("<error>")

        # MSW, the GetId() call can raise an exception
        # from some assertion "!IsStandard()"
        try:
            datid = datf.GetId()
        except:
            pass

        self.prdbg(_T("IN OnData -- fmt {}").format(datid))

        if datf == self.do.moz_url_dataobject.GetFormat():
            data = self.do.get_d_cooked(datf)

            # Firefox sends lines with link URI (i.e., the a->href)
            # first, then the link text on page (e.g., 'click
            # here to download cat video') -- the latter is
            # probably not useful
            files = [data[0].strip()]
            self.prdbg(_T("IN OnData -- 01 -- '{}'").format(files))
        elif (datf == self.do.uri_list_dataobject.GetFormat() or
              datf == self.do.file_dataobject.GetFormat() or
              datf == self.do.text_dataobject.GetFormat() or
              datf == self.do.STRING_dataobject.GetFormat() or
              (datid == _T("UTF8_STRING") or
               datid == _T("TEXT"))):
            files = self.do.get_d_cooked(datf)
            self.prdbg(_T("IN OnData -- 02 -- '{}'").format(files))
        else:
            # WTF
            self.prdbg(_T("IN OnData -- wtf: '{}'").format(datid))
            return self.drag_return_type

        self.target.do_file_drop(files, (x, y))

        return d

    def OnEnter(self, x, y, d):
        return self.drag_return_type

    def OnDragOver(self, x, y, d):
        return self.drag_return_type

    def OnDrop(self, x, y):
        return True


"""
classes for simple undo/redo as usual in GUI app
"""

class UndoItem:
    """Simply holds data -- using code may place additional
    attributed as needed
    """
    def __init__(self, data = None):
        self.data = data

class UndoStack:
    """Stack of objects for undo/redo
    """
    def __init__(self, max_cnt = 256):
        self.stack = []
        self.max_cnt = max_cnt

    def length(self):
        return len(self.stack)

    def set_max_cnt(self, max_cnt, trim_top = False):
        if self.max_cnt != None and max_cnt < 0:
            return

        self.max_cnt = max_cnt
        if self.max_cnt == None:
            return

        lcur = len(self.stack)
        if lcur > self.max_cnt:
            if trim_top:
                del self.stack[:(lcur - self.max_cnt)]
            else:
                del self.stack[self.max_cnt:]

    def push(self, item, do_copy = True):
        if self.max_cnt != None and len(self.stack) == self.max_cnt:
            del self.stack[-1]

        it = item
        if do_copy == "shallow":
            it = copy.copy(item)
        elif do_copy:
            it = copy.deepcopy(item)

        self.stack.insert(0, it)

    def pop(self):
        if len(self.stack) < 1:
            return None

        it = self.stack[0]
        del self.stack[0]
        return it

    def pushback(self, item, do_copy = True):
        """NOTE: unlike push() this trims top
        if max_count would be exceeded
        """
        if self.max_cnt != None and len(self.stack) == self.max_cnt:
            del self.stack[0]

        it = item
        if do_copy == "shallow":
            it = copy.copy(item)
        elif do_copy:
            it = copy.deepcopy(item)

        self.stack.append(it)

    def popback(self):
        if len(self.stack) < 1:
            return None

        it = self.stack[-1]
        del self.stack[-1]
        return it


class UndoRedoManager:
    def __init__(self, stack_count = 256):
        self.un = UndoStack(stack_count)
        self.re = UndoStack(stack_count)

    def undo_length(self):
        return self.un.length()

    def redo_length(self):
        return self.re.length()

    def push_undo(self, item, do_copy = True):
        self.un.push(item = item, do_copy = do_copy)

    def push_redo(self, item, do_copy = True):
        self.re.push(item = item, do_copy = do_copy)

    def pop_undo(self):
        it = self.un.pop()
        return it

    def pop_redo(self):
        it = self.re.pop()
        return it


# No, didn't want to do this -- original intent was to use
# wxComboBox or wxChoice, but on MSW the dropdown does not
# resize for long strings (GTK-2 does, and is fine) -- hence
# this additional program bloat:
# NOTE: GTK-3 is as broken as MSW
class TailorMadeComboPop(wxcombo.ComboPopup):
    def __init__(self):
        self.Init()
        wxcombo.ComboPopup.__init__(self)
        if phoenix:
            self.lbox = wx.ListBox()
        else:
            self.lbox = wx.PreListBox()
            self.lbox.PostCreate(self.lbox)

        self.cctrl = None
        self.w = None
        self.h = None
        self.lineheight = 0
        self.last_sel = 0
        self.create_parent = None
        self.font = None

    # Initialize member variables
    def Init(self):
        self.w = None
        self.h = None

    # Create popup control
    def Create(self, parent):
        self.create_parent = parent

        self.lbox.Create(
                parent,
                wx.ID_ANY,
                style = wx.LB_SINGLE | wx.LB_HSCROLL | wx.LB_NEEDED_SB,
                pos = (0, 0),
                size = (-1, 33))

        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_ldown)
        self.Bind(wx.EVT_KEY_DOWN, self.on_kdown)
        self.Bind(wx.EVT_KEY_UP, self.on_kup)
        self.Bind(wx.EVT_CHAR, self.on_char)

        return True

    def Bind(self, *a, **ka):
        return self.lbox.Bind(*a, **ka)

    def SetThemeEnabled(self, boolval):
        return self.lbox.SetThemeEnabled(boolval)

    def _handle_page_updown(self, ispagedown, iskeydown):
        if not _in_gtk:
            # Bummer: MSW does dismiss the popup on
            # page up/down key, and I don't know if that
            # can be changed; and that's it for this
            # handler.
            # Anything other than MSW or GTK is unknown
            # presently
            return

        if self.lineheight < 1 or not iskeydown:
            return

        cnt = self.lbox.GetCount()
        if cnt == 0:
            return

        csz = self.lbox.GetClientSize()
        x, y = csz.Get()

        if ispagedown:
            x /= 2
            y -= self.lineheight / 2
            n = self.lbox.HitTest((x, y))
            if n == wx.NOT_FOUND:
                n = cnt - 1
            self.lbox.SetSelection(n)
            self.cctrl.SetSelection(n)
        else:
            x /= 2
            y = self.lineheight / 2
            n = self.lbox.HitTest((x, y))
            if n == wx.NOT_FOUND:
                n = 0
            self.lbox.SetSelection(n)
            self.cctrl.SetSelection(n)

    def on_kup(self, evt):
        kc  = evt.GetKeyCode()
        kr  = evt.GetRawKeyCode()
        mod = evt.GetModifiers()

        if kc == wx.WXK_UP:
            pass
        elif kc == wx.WXK_DOWN:
            pass
        elif kc == wx.WXK_PAGEUP:
            self._handle_page_updown(ispagedown=False,iskeydown=False)
            evt.Skip()
        elif kc == wx.WXK_PAGEDOWN:
            self._handle_page_updown(ispagedown=True,iskeydown=False)
            evt.Skip()
        elif kc == wx.WXK_RETURN or kc == wx.WXK_SPACE:
            pass
        elif (kc == wx.WXK_ESCAPE or kc == wx.WXK_BACK or
                kc == wx.WXK_DELETE or
                kc == wx.WXK_SUBTRACT or kc == wx.WXK_NUMPAD_SUBTRACT):
            pass
        elif (kc == wx.WXK_ADD or kc == wx.WXK_NUMPAD_ADD or
                kr == 43 or (kc == 61 and mod == wx.MOD_SHIFT)):
            pass
        else:
            evt.Skip()

    def on_kdown(self, evt):
        kc  = evt.GetKeyCode()
        kr  = evt.GetRawKeyCode()
        mod = evt.GetModifiers()

        if kc == wx.WXK_UP:
            n = self.lbox.GetSelection()
            if n > 0:
                self.lbox.SetSelection(n - 1)
                self.cctrl.SetSelection(n - 1)
        elif kc == wx.WXK_DOWN:
            n = self.lbox.GetSelection()
            c = self.lbox.GetCount() - 1
            if n >= 0 and n < c:
                self.lbox.SetSelection(n + 1)
                self.cctrl.SetSelection(n + 1)
        elif kc == wx.WXK_PAGEUP:
            self._handle_page_updown(ispagedown=False,iskeydown=True)
            evt.Skip()
        elif kc == wx.WXK_PAGEDOWN:
            self._handle_page_updown(ispagedown=True,iskeydown=True)
            evt.Skip()
        elif kc == wx.WXK_RETURN or kc == wx.WXK_SPACE:
            self.send_select_command(self.lbox.GetSelection())
        elif (kc == wx.WXK_ESCAPE or kc == wx.WXK_BACK or
                kc == wx.WXK_DELETE or
                kc == wx.WXK_SUBTRACT or kc == wx.WXK_NUMPAD_SUBTRACT):
            self.lbox.Select(self.last_sel)
            self.Dismiss()
            self.cctrl.SetSelection(self.last_sel)
        elif (kc == wx.WXK_ADD or kc == wx.WXK_NUMPAD_ADD or
                kr == 43 or (kc == 61 and mod == wx.MOD_SHIFT)):
            if not self.cctrl.IsPopupShown():
                self.cctrl.ShowPopup()
        else:
            evt.Skip()

    def on_char(self, evt):
        evt.Skip()
        pass

    def on_motion(self, evt):
        item = self.lbox.HitTest(evt.GetPosition())
        if item >= 0:
            self.lbox.Select(item)

    def on_ldown(self, evt):
        self.send_select_command(self.lbox.HitTest(evt.GetPosition()))

    def send_select_command(self, item):
        self.Dismiss()

        if item < 0 or item >= self.lbox.GetCount():
            return

        self.last_sel = item

        # GetComboCtrl returns swig object under wxPython
        # so 'c = self.GetComboCtrl()' is no good --
        # self.cctrl is tacked on by the ComboCtrl when
        # this is set as its popup object
        try:
            c = self.cctrl
            if c:
                c.SetSelection(item)
        except:
            pass

        def _l_e(self, c, idx):
            etype = wx.EVT_LISTBOX.evtType[0]
            e = wx.CommandEvent(etype, self.GetId())
            # The following two Set*() ensure that event.IsSelection()
            # returns true, and event.GetSelection() returns the index
            e.SetExtraLong(idx + 1)
            e.SetInt(idx)
            self.Command(e)
        wx.CallAfter(_l_e, self, c, item)

    # Return pointer to the created control
    def GetControl(self):
        return self.lbox

    # Return Id of the created control
    def GetId(self):
        return self.lbox.GetId()

    # Relay Command to the created control
    def Command(self, *a):
        return self.lbox.Command(*a)

    def Append(self, txt):
        txt = _WX(txt)
        r = self.lbox.Append(txt)

        oldh = self.h
        self.w, self.h = self.get_text_extent_all()

        if oldh and oldh != self.h:
            self.lineheight = self.h - oldh

        return r

    def get_text_extent(self, txt):
        w, h, d, xl = self.lbox.GetFullTextExtent(txt, font=self.font)

        return (w, h, d, xl)

    def get_text_extent_all(self):
        a = self.lbox.GetStrings()
        ns = len(a)
        if ns < 1:
            return (-1, -1)

        wt = ht = 0
        for s in a:
            w, h, d, xl = self.get_text_extent(s)
            wt = max(wt, w)
            # sigh
            if _in_gtk and xl < 1:
                xl = d * 2
            ht += h + xl

        return (wt, ht)

        #w0, h0, d0, xl0 = self.get_text_extent(a[0])
        #
        #if ns == 1:
        #    return (w0, h0 + d0 * 2 + xl0)
        #
        #txt = os.linesep.join(a)
        #w, h, d, xl = self.get_text_extent(txt)
        #return (w, (len(a) * (h0 + d0 * 2 + xl0)))

    def Select(self, n):
        if n < 0 or n >= self.lbox.GetCount():
            return

        self.lbox.SetSelection(n)
        return self.lbox.GetSelection()

    # Translate string into a list selection
    def SetStringValue(self, s):
        self.lbox.SetStringSelection(s)

    # Get list selection as a string
    def GetStringValue(self):
        r = self.lbox.GetStringSelection()
        if not r:
            r = wx.EmptyString
        return r

    # Get list selection
    def GetSelection(self):
        return self.lbox.GetSelection()

    def Clear(self):
        self.lbox.Clear()
        self.last_sel = 0
        self.w = None
        self.h = None

    # Called immediately after the popup is shown
    def OnPopup(self):
        wxcombo.ComboPopup.OnPopup(self)
        self.last_sel = self.GetSelection()
        self.lbox.SetFocus()

    # Called when popup is dismissed
    def OnDismiss(self):
        wxcombo.ComboPopup.OnDismiss(self)

    # Receives key events from the parent ComboCtrl.  Events not
    # handled should be skipped, as usual.
    def OnComboKeyEvent(self, event):
        #wxcombo.ComboPopup.OnComboKeyEvent(self, event)
        #kc = event.GetKeyCode()
        self.on_kdown(event)

    # Implement if you need to support special action when user
    # double-clicks on the parent wxComboCtrl.
    def OnComboDoubleClick(self):
        wxcombo.ComboPopup.OnComboDoubleClick(self)

    # Return final size of popup. Called on every popup,
    # just prior to OnPopup.
    # minWidth = preferred minimum width for window
    # prefHeight = preferred height. Only applies if > 0,
    # maxHeight = max height for window, as limited by screen size
    #   and should only be rounded down, if necessary.
    def GetAdjustedSize(self, minWidth, prefHeight, maxHeight):
        if self.w == None or self.w == None:
            self.w, self.h = self.get_text_extent_all()

        # These height adjustments *must not* increase the
        # values passed to this call, which causes the list to
        # appear in bad places like off the top of screen
        mxy = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_Y)
        mxx = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_X)

        # padding hack: once lbox dimension is enlarged,
        # then reduced, scrollbars will always show -- cannot
        # find a sane way to dispose of them -- so padding is
        # needed to ensure scrollbars do not obscure text;
        # also, sigh, wxWindow::HasScrollbar(orient) is not
        # working here: always false (sigh again)
        #padx = 28 if self.lbox.HasScrollbar(wx.VERTICAL) else 0
        #pady = 28 if self.lbox.HasScrollbar(wx.HORIZONTAL) else 0
        padx = 28
        pady = 28

        mxx = min(mxx, self.w) + padx
        mxx = max(minWidth, mxx)

        mxy = min(self.h, mxy) + pady
        mxy = min(maxHeight, mxy)

        #if prefHeight < 1:
        #    prefHeight = maxHeight

        r = (mxx, mxy)

        #print("GetAdjustedSize: {} [{}] {}".format(
        #    r, (self.w, self.h), (padx, pady)))
        return r



# No, didn't want to do this -- original intent was to use
# wxComboBox or wxChoice, but on MSW the dropdown does not
# resize for long strings (GTK-2 does, and is fine) -- hence
# this additional program bloat:
# NOTE: GTK-3 is as broken as MSW
class TailorMadeComboCtrl(wxcombo.ComboCtrl):
    def __init__(self, *args, **kw):
        wxcombo.ComboCtrl.__init__(self, *args, **kw)

    def SetPopupControl(self, ctrl):
        wxcombo.ComboCtrl.SetPopupControl(self, ctrl)

        if not ctrl:
            return

        # Tack on a reference to self, had some problem
        # getting a reference to this in the popup class
        ctrl.cctrl = self
        self.ctrl = ctrl

        self.Bind(wx.EVT_LISTBOX, self.on_dbox)

    def on_dbox(self, event):
        if not event.IsSelection():
            event.Skip()
            return

        def _s_v_c(self, idx):
            etype = wx.EVT_COMBOBOX.evtType[0]
            e = wx.CommandEvent(etype, self.GetId())
            e.SetExtraLong(idx + 1)
            e.SetInt(idx)
            self.Command(e)
        wx.CallAfter(_s_v_c, self, event.GetSelection())

    def _hack_on_color(self):
        if True:
            p = self.GetParent()
            bclr = p.GetBackgroundColour()
            fclr = p.GetForegroundColour()
        else:
            c = wx.SYS_COLOUR_MENU
            bclr = wx.SystemSettings.GetColour(c)
            c = wx.SYS_COLOUR_MENUTEXT
            fclr = wx.SystemSettings.GetColour(c)

        self.SetBackgroundColour(bclr)
        self.SetForegroundColour(fclr)

    def SetThemeEnabled(self, boolval):
        self.ctrl.SetThemeEnabled(boolval)
        self.GetControl().SetThemeEnabled(boolval)
        self.GetPopupWindow().SetThemeEnabled(boolval)
        return wxcombo.ComboCtrl.SetThemeEnabled(self, boolval)

    def Append(self, item):
        self.ctrl.Append(item)

    def SetSelection(self, item):
        c = self.ctrl
        c.Select(item)
        self.SetValue(c.GetStringValue())

    def GetSelection(self):
        return self.ctrl.GetSelection()

    def Clear(self):
        self.ctrl.Clear()

    def GetControl(self):
        return self.GetPopupControl().GetControl()


"""
Object for the taskbar, system tray, whatever it's called
"""
class TaskBarObject(wxadv.TaskBarIcon):
    def __init__(self, topwnd):
        wxadv.TaskBarIcon.__init__(self)
        self.wnd = topwnd

        self.Bind(wx.EVT_MENU, self.wnd.on_menu)

        #nb = wx.SystemSettings.GetMetric(wx.SYS_MOUSE_BUTTONS)
        # the call to get number of buttons returns -1
        # on GTK -- not helpful -- so onlyc handle left
        # button if gtk or msw, to avoid Apple
        if _in_gtk or _in_msw:
            self.Bind(wxadv.EVT_TASKBAR_LEFT_DOWN, self.on_ldown)

    def CreatePopupMenu(self):
        return self.wnd.make_taskbar_menu()

    def on_ldown(self, event):
        self.wnd.do_taskbar_click(event)

"""
The main top-level window class; stuffing composed of the bulk
of the program logic -- this has grown to be larger than it would
have been had it been smaller than it is
"""

# utility for wx window objects with children: invoke a procedure
# on window's children, and their children, recursivley -- procedure
# must take window object parameter
def invoke_proc_for_window_children(window, proc):
    proc(window)
    for wnd in window.GetChildren():
        invoke_proc_for_window_children(wnd, proc)


class TopWnd(wx.Frame):
    about_info = None

    def __init__(self, parent, ID, title, size, pos = (0, 0),
                       cmdargs = None, argplay = False):
        wx.Frame.__init__(self, parent, ID , #style = wx.TAB_TRAVERSAL,
                          title = title, size = size, pos = pos)

        self.do_setwname_done = True

        self.tittime = 0
        self.orig_title = None
        self.tmp_title = None

        self.in_play = False
        self.in_stop = False
        self.load_ok = False

        # grrr
        self.seek_and_pause_hack =  0
        self.seek_and_play_hack  = -1
        # see comment at get_medi_state()
        self.medi_state = wx.media.MEDIASTATE_STOPPED
        # grrr again: wxMediaCtrl.Load*() will return True, even
        # if failing; a wxLog hack greps for wx library messages,
        # *just* maybe we can identify a media control message
        # that indicates its error in spite of returning True
        self.msg_grep = None

        # current track should loop
        self.loop_track = False
        # on current track finish, advance to next and play
        self.adv_track = True

        # set this to a callable object if something must
        # be done in media loaded event handler, e.g. seek & play
        self.load_func = None

        self.vol_min = 0
        self.vol_max = 100
        self.vol_cur = 50

        # options vars:
        # query confirmation with message box on quit?
        self.opt_quit_query = False
        # show the tray/taskbar icon?
        self.opt_tray_icon = True
        # show notification popups
        self.opt_notifymsg = True
        # load with proxy has been failing, silently
        self.can_use_proxy = False
        self.proxies = {}
        t = ((_T("https"), _T("HTTPS_PROXY")),
             (_T("http"), _T("HTTP_PROXY")))
        for p, v in t:
            try:
                self.proxies[p] = os.environ[v]
            except:
                self.proxies[p] = None

        # indice into current set of file/stream groups
        self.group_indice = 0
        # indice into current set of files/streams
        self.media_indice = 0

        # load_media() checks if resource is in URI form ('foo://')
        # and this determination can be useful elsewhere, so:
        self.media_current_is_uri = False

        # e.g., length, (w, h) size in tuple (l, wxSize)
        self.media_meta = (0, wx.Size(0, 0))

        # a basic check value for time.time(), because it
        # is subject to system time changes; the only logical
        # check is that a new time call returns a value larger
        # than this, but at least a certain amount of clock
        # set-back might be detected
        self.time_secs = 0
        self.time_secs_offset = 0

        # pause can (preumably) be of any duration for local
        # files, but not so for streams, nor even for fixed
        # size resources from remote sources -- backend
        # might not be able to resume after some long period
        # of time, and might simply play the the remainder of
        # buffered data (gstreamer, at least) and issue a finished
        # event, resulting in a stop and possible advance to next
        # resource -- so to hack around this the pause handler
        # will set a time (Unix epoch, seconds) to limit the pause
        # condition (non-local) and some sensible behavior can
        # be attempted
        # NOTE: tried 3 minutes; n.g., try 2
        self.pause_ticks_interval = 60 * 2 # minutes; needs testing
        # set at pause event and checked in tick and play handlers
        self.pause_ticks = -1 # -1 == off, 0 == expired, else time
        # long pause seek position, from MediaCtrl.Tell() --
        # 0 for streams
        self.pause_seek_pos = 0

        # mouse tracking for fullscreen mode
        self.fs_mouse_pos = (-1, -1)

        # if user drags position slider to seek, it can be pretty
        # lousy with many seeks while playing -- so pause and set
        # this > 0, and let tick handler call play when this is 0
        self.pos_seek_paused = 0
        # this stores whether state was playing when drag starts,
        # and determines whether Play() is called
        self.pos_seek_state  = None

        # manager for undo/redo stacks
        self.undo_redo = UndoRedoManager()

        # fifo queue for MPRIS2 coprocess dialog lambdas
        if _in_xws or True:
            # queue has max size in case of flurries of events;
            # handler should discard first when put() fails
            self.coproc_fifo = q_fifo(32)
            self.block_mpris_signals = False
        # set by MPRIS2 Seek and SetPosition handlers --
        # must be scrupulously reset to -1
        self.mpris_seek = -1
        # this is set to an object on mpris setup; set back
        # to None on error, and is tested in various places
        self.mpris = None

        # get config values here, in case a setting applies
        # to interface objects created below
        cfvals = self.config_rd()
        if cfvals:
            self.vol_cur = cfvals[_T("volume")]
            self.vol_cur = min(
                max(self.vol_cur, self.vol_min), self.vol_max)

        # use theme glitz?
        self.theme_support = True
        if cfvals:
            self.theme_support = cfvals[_T("theme_support")]
        self.SetThemeEnabled(self.theme_support)

        # handle color event, to refresh etc.
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_color)

        # use a backing panel for object, or just this frame window?
        if False: #_in_msw:
            back = self.backpanel = self
        else:
            back = self.backpanel = wx.Panel(self, wx.ID_ANY)
            back.prdbg = self.prdbg

        szr = wx.BoxSizer(wx.VERTICAL)

        abdat = []

        self.label_fullscreen_on  = _("Fu&llscreen")
        self.label_fullscreen_off = _("Leave Fu&llscreen")
        self.id_fullscreen = new_wx_id()
        bdat = ButtonData(
                       ID = self.id_fullscreen,
                       label = self.label_fullscreen_on,
                       handler = self.on_fullscreen)
        abdat.append(bdat)

        self.label_play_on  = _("&Play")
        self.label_play_off = _("&Pause")
        self.id_play = new_wx_id()
        bdat = ButtonData(
                       ID = self.id_play,
                       label = self.label_play_on,
                       handler = self.on_play)
        abdat.append(bdat)

        self.id_prev = new_wx_id()
        bdat = ButtonData(
                       ID = self.id_prev,
                       label = _("P&revious"),
                       handler = self.on_prev)
        abdat.append(bdat)

        self.id_next = new_wx_id()
        bdat = ButtonData(
                       ID = self.id_next,
                       label = _("&Next"),
                       handler = self.on_next)
        abdat.append(bdat)

        self.id_stop = new_wx_id()
        bdat = ButtonData(
                       ID = self.id_stop,
                       label = _("S&top"),
                       handler = self.on_stop)
        abdat.append(bdat)

        self.btn_panel = ButtonPanel(back, wx.ID_ANY,
                                     button_data = abdat)

        self.ctl_data = self.btn_panel.get_id_map()

        self.id_pos_sld = new_wx_id()
        self.pos_panel = SliderPanel(back, wx.ID_ANY,
                                     slider_id = self.id_pos_sld)
        self.pos_sld = self.pos_panel.get_slider()
        self.pos_mul = 0.001 # millisecs

        self.ctl_data.append((self.id_pos_sld, self.pos_sld))

        self.player_panel = MediaPanel(back, wx.ID_ANY, handlers = (
                                       (wx.EVT_KEY_DOWN, self.on_key),
                                       (wx.EVT_KEY_UP,   self.on_key),
                                       (wx.EVT_CHAR,   self.on_char)
                                       ))
        self.medi = self.player_panel.medi
        self.medi.SetVolume(0.5)

        self.medi_has_mouse = True #False
        self.medi_tick = -1
        self.medi_tick_span = 4

        # icons associated with app/window
        self._do_app_art()

        # put {menu,tool,status}bar on frame
        if cfvals:
            self.loop_track    = cfvals[_T("loop_play")]
            self.adv_track     = cfvals[_T("auto_advance")]
        self.make_menu_bar()
        self.make_status_bar()
        self.make_tool_bar()
        self.set_taskbar_object()

        self.SetToolBar(self.toolbar)
        szr.Add(self.toolbar2, 0, wx.EXPAND | wx.ALL, 0)

        self.id_svol = new_wx_id()
        self.vol_panel = SliderPanel(back, wx.ID_ANY,
                                     slider_id = self.id_svol)
        self.vol_sld = self.vol_panel.get_slider()
        self.vol_sld.Bind(wx.EVT_SCROLL, self.on_volume)

        self.vol_sld.SetMinSize(wx.Size(160, -1))
        self.vol_sld.SetRange(self.vol_min, self.vol_max)
        self.vol_sld.SetValue(self.vol_cur)

        self.ctl_data.append((self.id_svol, self.vol_sld))

        vszr = wx.BoxSizer(wx.VERTICAL)
        hszr = wx.BoxSizer(wx.HORIZONTAL)

        hszr.Add(self.btn_panel, 5, wx.EXPAND, 1)
        hszr.Add(self.vol_panel, 1, wx.EXPAND, 1)
        vszr.Add(self.pos_panel, 1, wx.EXPAND | wx.TOP, 4)
        vszr.Add(hszr, 1, wx.EXPAND | wx.BOTTOM | wx.TOP, 3)

        szr.Add(self.player_panel, 1, wx.EXPAND | wx.BOTTOM, 0)
        szr.Add(vszr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
        #XXX earlier in development, it seemed this that this spacer
        # was needed to prevent screen corruption going fullscreen,
        # which must have been an erroneous conclusion.
        # Remove this when certain it's OK
        #szr.AddSpacer(1)

        # re. fullscreen, do some hide/show, so:
        self.hiders = {}
        self.hiders["ppnl"] = self.pos_panel
        self.hiders["vszr"] = vszr
        self.hiders["hszr"] = hszr

        # any interface color adjustment should be in this proc
        self.color_hacks()

        # fundamental event bindings
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.Bind(wx.EVT_IDLE, self.on_idle)

        # -- a GNU/Linux system with GTK3 recently updated to
        #    version 22.11 fails to refresh frame window's contents
        #    when un-minimized after a long time minimized --
        #    so wxIconizeEvent is handled to try workaround
        #    hacks to force an interface paint job
        # -- all: use max/iconize events to record current
        #    windowed size/pos for reference in e.g. config_wr
        if isinstance(size, tuple):
            self.window_size = wx.Size(size[0], size[1])
        elif isinstance(size, wx.Size):
            self.window_size = wx.Size(size.width, size.height)
        else:
            self.window_size = wx.Size(800, 600)
        if isinstance(pos, tuple):
            self.window_pos  = wx.Point(pos[0], pos[1])
        elif isinstance(pos, wx.Point):
            self.window_pos  = wx.Point(pos.x, pos.y)
        else:
            self.window_pos  = wx.Point(0, 0)
        self.Bind(wx.EVT_ICONIZE, self.on_iconize_event)
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize_event)

        # MSW, to get multimedia 'hotkeys' -- note MS does
        # not have VK_ definition for pause, only for
        # play/pause toggle
        if _in_msw:
            self.register_hotkey_done = False
            self.Bind(wx.EVT_HOTKEY, self.on_ms_hotkey)
            self.hotk_id_base  = 0xBFFF - 64
            self.hotk_id_play  = self.hotk_id_base + 1
            self.hotk_id_pause = self.hotk_id_base + 2
            self.hotk_id_stop  = self.hotk_id_base + 3
            self.hotk_id_next  = self.hotk_id_base + 4
            self.hotk_id_prev  = self.hotk_id_base + 5

            self.msvk_id_play  = 0xB3
            self.msvk_id_pause = -1
            self.msvk_id_stop  = 0xB2
            self.msvk_id_next  = 0xB0
            self.msvk_id_prev  = 0xB1

        # position slider event
        self.pos_sld.Bind(wx.EVT_SCROLL, self.on_position)

        # media control events
        self.Bind(wx.media.EVT_MEDIA_FINISHED, self.on_media_finish)
        self.Bind(wx.media.EVT_MEDIA_STOP, self.on_media_stop)
        self.Bind(wx.media.EVT_MEDIA_LOADED, self.on_media_loaded)
        self.Bind(wx.media.EVT_MEDIA_STATECHANGED, self.on_media_state)
        self.Bind(wx.media.EVT_MEDIA_PLAY, self.on_media_play)
        self.Bind(wx.media.EVT_MEDIA_PAUSE, self.on_media_pause)

        # event for any wxTimer in use -- distinguish by GetInterval()
        self.Bind(wx.EVT_TIMER, self.on_wx_timer)

        # keys
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_KEY_UP, self.on_key)
        self.Bind(wx.EVT_CHAR, self.on_char)

        # Custom destroy event from app
        self.Bind(APP_EVT_DESTROY_BINDME, self.on_destroy)

        back.SetSizer(szr)
        if not back is self:
            bkszr = wx.BoxSizer(wx.VERTICAL)
            bkszr.Add(back, 1, wx.EXPAND, 0)
            self.SetSizer(bkszr)
        self.Layout()

        # accept DND
        self.SetDropTarget(multi_droptarget(self))

        # and BTW . . .
        self.debug = wx.GetApp().get_debug()

        # dialogs for files and directories -- keeping
        # and instance rather than creating before invocation
        # allows the dialog to keep state such as last directory
        # -- but they are created just before use
        self.dialog_file = None
        self.dialog_dirs = None
        self.dialog_savegroup = None
        self.dialog_saveset   = None

        # start main timer
        self.main_timer = wx.Timer(self, 1)
        self.main_timer.Start(1000, False)

        if not cmdargs:
            cmdargs = []
        if _in_msw:
            import glob
            t = cmdargs
            cmdargs = []
            for arg in t:
                cmdargs += glob.glob(arg)

        if not len(cmdargs):
            argplay = False

        self.reslist = []
        reslist, errs = self.do_arg_list(
                                        cmdargs, append = True,
                                        recurse = False,
                                        play = argplay,
                                        pushundo = False)
        self.prdbg(_T("LIST w/ {} groups").format(len(self.reslist)))
        if self.getdbg():
            for n, g in enumerate(self.reslist):
                self.prdbg(_T("GROUP {} ({})").format(n, g.uniqhex))
                for i, r in enumerate(g.data):
                    t = _T(r.resname)
                    h = r.uniqhex
                    self.prdbg(_T("RES ({}) {} ({})").format(i, t, h))

        for d, e in errs:
            self.err_msg(_T("Error: {} '{}'").format(d, e))

        # force a (re)sizing of 2nd toolbar: needed
        # depending on widgets/toolkit
        self.force_hack(use_hack = True)

        # setup play state with seek position, but only if
        # started without arguments, which implies load and
        # use last set of media groups -- therefore state
        do_state = False
        if cfvals and cfvals[_T("res_restart")] and not argplay:
            group_indice = cfvals[_T("group_index")]

            if group_indice >= 0 and group_indice < len(self.reslist):
                ok = True
                igrp = self.reslist[group_indice]

                if igrp.has_unique_desc():
                    ok = s_eq(cfvals[_T("group_desc")], igrp.desc)

                media_indice = cfvals[_T("resource_index")]

                if (ok and media_indice >= 0 and
                    media_indice < self.get_reslist_len()):
                    ok = self.get_res_index_in_grp(group_indice,
                                                   media_indice)
                    do_state = ok

        self.prdbg(_T("DO RESTORE STATE: {}").format(do_state))
        if do_state:
            self.media_indice = cfvals[_T("resource_index")]
            self.group_indice = cfvals[_T("group_index")]
            pos = cfvals[_T("current_pos")]
            pos = int(0.5 + float(max(0, pos)) / self.pos_mul)

            if pos < 0:
                pos = 0

            def _st_aft(self, pos, pl):
                if pl:
                    f = lambda: self._seek_and_play(pos)
                    self.load_func = f
                elif pos > 0:
                    f = lambda: self._seek_and_pause(pos)
                    self.load_func = f
                if pl or pos > 0:
                    self.load_media()
                    if not self.load_ok:
                        self.prdbg(_T(
                            "RESTORE STATE load fail of: {}"
                            ).format(_T(
                                self.get_reslist_item().resname)))
                        self.load_func = None

            self.set_tb_combos()
            wx.CallAfter(_st_aft, self, pos, cfvals[_T("playing")])


    def do_arg_list(self, files,
                    append = False, recurse = False, play = True,
                    pushundo = True, uri_filter_permissive = True):
        up = uri_filter_permissive

        if not append:
            def _daft(obj, fi, rec, pl):
                tmp_reslist, errs = get_lst_from_args(
                                            *fi,
                                            dir_recurse = rec,
                                            uri_filter_permissive = up)
                if not tmp_reslist:
                    self.cancel_undo()
                    return
                obj.reslist = tmp_reslist
                obj.group_indice = 0
                obj.media_indice = 0
                obj.set_tb_combos()
                if pl:
                    obj.cmd_on_play(from_user = False)

            if pushundo:
                self.push_undo(do_copy = False)
            self.cmd_on_stop(from_user = False)
            wx.CallAfter(_daft, self, files, recurse, play)
            return (None, None)

        reslist, errs = get_lst_from_args(*files,
                                          dir_recurse = recurse,
                                          uri_filter_permissive = up)
        if not reslist:
            return (None, errs)
        if pushundo:
            self.push_undo(do_copy = True)
        cl = self.get_reslist_len()
        self.reslist += reslist
        self.media_indice = cl
        self.set_tb_combos()

        if play:
            # use on_next (not on_play); it forces a
            # new load then play -- so indice must
            # be diddled
            self.media_indice -= 1
            self.cmd_on_next(from_user = False)

        return (self.reslist, errs)

    def do_file_drop(self, files, coord_tuple = None):
        self.do_arg_list(files, append = True, recurse = False)

    def getdbg(self):
        return self.debug

    def prdbg(self, *args):
        if self.getdbg():
            wx.GetApp().prdbg(*args)

    def get_secs(self):
        fun_secs = time.time
        #fun_secs = time.clock

        if self.time_secs == 0: # 1st secs
            self.time_secs = fun_secs()
        else:
            t = fun_secs()
            # compare because good secs can become bad secs,
            # due either to clock setback or unwanted wraparound
            # (.time() or .clock() respectively)
            if t < self.time_secs:
                # constant addition is arbitrary
                self.time_secs_offset += self.time_secs - t + 60
            self.time_secs = t

        return self.time_secs + self.time_secs_offset

    def get_time_str(self, tm = None, defstr = _("stream"), wm = False):
        if tm == None:
            tm = self.medi.Length() if self.medi else 0

        if tm == 0:
            return defstr

        return mk_colon_time_str(tm, wm)

    def get_res_group_len(self):
        return len(self.reslist)

    def get_reslist_len(self):
        l = 0
        for g in self.reslist:
            l += g.get_len()
        return l

    def get_res_group_current(self):
        g, i = self.get_res_group_with_index()
        return g

    # first (group, media_indice),
    # returning media_indice at zeroeth entry
    def get_first_res_group_with_index(self, indice = None):
        if self.reslist:
            return (self.reslist[0], 0)

        return (None, None)

    # last (group, media_indice),
    # returning media_indice at zeroeth entry
    def get_last_res_group_with_index(self, indice = None):
        if self.reslist:
            g = self.reslist[-1]
            gl = g.get_len()
            l = self.get_reslist_len() - gl
            return (g, l)

        return (None, None)

    # next (group, media_indice) relative to group in which,
    # indice lies, returning media_indice at zeroeth entry
    def get_next_res_group_with_index(self, indice = None):
        if indice == None:
            indice = self.media_indice

        l = 0
        rl = len(self.reslist)
        for i, g in enumerate(self.reslist):
            gl = g.get_len() + l
            if indice < gl:
                i += 1
                if i == rl:
                    break # returns (None, None)
                ng = self.reslist[i]
                return (ng, gl)
            l = gl

        return (None, None)

    # previous (group, media_indice) relative to group in which,
    # indice lies, returning media_indice at zeroeth entry
    def get_prev_res_group_with_index(self, indice = None):
        if indice == None:
            indice = self.media_indice

        l = 0
        for i, g in enumerate(self.reslist):
            gl = g.get_len() + l
            if indice < gl:
                if i == 0:
                    break # returns (None, None)
                pg = self.reslist[i - 1]
                return (pg, l - pg.get_len())
            l = gl

        return (None, None)

    # from total indice, get (group, group_indice)
    def get_res_group_with_index(self, indice = None):
        if indice == None:
            indice = self.media_indice

        l = 0
        for g in self.reslist:
            gl = g.get_len() + l
            if indice < gl:
                return (g, indice - l)
            l = gl

        return (None, None)

    def get_res_index_in_grp(self, group_index, indice = None):
        if indice == None:
            indice = self.media_indice

        if group_index < 0 or group_index >= len(self.reslist):
            return False

        l = 0
        for i, g in enumerate(self.reslist):
            gl = g.get_len() + l
            if indice < gl:
                return (i == group_index)
            l = gl

        return False

    def get_reslist_item(self, indice = None):
        g, i = self.get_res_group_with_index(indice)

        if g:
            return g.get_at_index(i)

        return None

    def get_reslist_item_tup(self, indice = None):
        it = self.get_reslist_item(indice)
        return (
            it.get_res_disp_str() if it else None,
            it.resname if it else None,
            _T(it.desc) if it else None,
            _T(it.comment) if it else None,
            _T(it.err) if it else None,
            it.length if it else None)

    # dbus interface/object misc. (posix or X?)
    if _in_xws:
        def get_dbus_dom(self):
            return (
                _T("/org/wxmav/mpris"),
                _T("org.wxmav.mpris")
            )

        def get_dbus_dom_app(self, app = _T("MediaPlayer2")):
            obj, ifc = self.get_dbus_dom()
            return (
                _T("{}/{}").format(obj, app),
                _T("{}.{}").format(ifc, app)
            )

        def _get_dbuspath_clean(self, v):
            return _T('^').join(_Tnec(v).split(_T('/')))

        def get_dbus_grouppath(self, grp):
            obj, ifc = self.get_dbus_dom_app()
            gid = _T(grp.uniq)
            dsc = self._get_dbuspath_clean(grp.get_desc())
            return _T("{}/{}/{}").format(obj, gid, dsc)

        def get_dbus_itempath(self, grp, item):
            obj, ifc = self.get_dbus_dom_app()
            gid = _T(grp.uniq)
            uid = _T(item.uniq)
            return _T("{}/{}/{}").format(obj, gid, uid)

        def get_dbus_itempath_current(self, zmsg = "null_data"):
            g, i = self.get_res_group_with_index()
            if g == None or i == None:
                p, i = self.get_dbus_dom_app()
                return _T("{}/{}").format(p, _T(zmsg))
            return self.get_dbus_itempath(g, g.get_at_index(i))

        def check_dbus_itempath_current(self, objpath):
            curpath = self.get_dbus_itempath_current()
            if s_eq(objpath, curpath):
                return True
            return False

        def mpris_sendsignal_check(self, force = False):
            if not self.mpris:
                return

            doemit = force
            sset = []

            try:
                b = self.cangonext
            except AttributeError:
                b = self.cangonext = None
            c = self.get_can_do_next()
            if b != c:
                self.cangonext = c
                sset.append(_T("CanGoNext"))
                doemit = True

            try:
                b = self.cangoprev
            except AttributeError:
                b = self.cangoprev = None
            c = self.get_can_do_prev()
            if b != c:
                self.cangoprev = c
                sset.append(_T("CanGoPrevious"))
                doemit = True

            try:
                b = self.canplay
            except AttributeError:
                b = self.canplay = None
            c = True if (
                self.reslist and len(self.reslist) > 0) else False
            if b != c:
                self.canplay = c
                sset.append(_T("CanPlay"))
                sset.append(_T("CanPause"))
                doemit = True

            try:
                b = self.canseek
            except AttributeError:
                b = self.canseek = None
            try:
                l = self.lastlen
            except AttributeError:
                l = self.lastlen = None
            lcur = self.medi.Length()
            c = True if lcur > 0 else False
            if b != c or (l != lcur and lcur > 0):
                self.canseek = c
                self.lastlen = lcur
                sset.append(_T("CanSeek"))
                if l != lcur:
                    sset.append(_T("Metadata"))
                doemit = True

            # hack: wanting a flush-like effect --
            # This proves necessary, else 'CanGo{Previous,Next}'
            # signals are not recognized by MPRIS2 control programs
            # until more MPRIS2 activity occurs (seen in KDE
            # "Now Playing" widget and Ubuntu 16.04 enhanced
            # volume taskbar widget).
            # Adding g_dbus_connection_flush() in the coprocess
            # does not help, but emitting "PlaybackStatus" here
            # makes the control programs work as expected --
            # maybe there is an expected sequence of signal
            # emissions that is not documented for MPRIS2.
            if doemit:
                sset.append(_T("PlaybackStatus"))
                for s in sset:
                    self.mpris2_signal_emit(s)
            else:
                # check if queue is not empty, and if not prod coproc
                fifo = self.coproc_fifo
                if not fifo.empty():
                    self._x_core_mpris2_signal_emit()

        def metadata_check(self):
            if not self.mpris:
                return

            g, i = self.get_res_group_with_index()
            curtuple = None
            try:
                curtuple = self.cur_uniq_tuple
            except AttributeError:
                pass
            if curtuple == None and (g == None or i == None):
                self.cur_uniq_tuple = None
                return
            elif g == None or i == None:
                self.cur_uniq_tuple = None
                self.mpris2_signal_emit(_T("Metadata"))
                self.mpris_sendsignal_check()
                return

            item = g.get_at_index(i)
            gid = _T(g.uniq)
            uid = _T(item.uniq)

            # for streams, metadata might have been sent before
            # length was known; check for difference here
            try:
                l = self.lastlen
            except AttributeError:
                l = self.lastlen = None
            lcur = self.medi.Length()

            if (curtuple == None or
                curtuple[0] != gid or curtuple[1] != uid or
                l != lcur):
                self.cur_uniq_tuple = (gid, uid)
                self.lastlen = lcur
                self.mpris2_signal_emit(_T("Metadata"))
                self.mpris_sendsignal_check()
                return

        def get_mpris2_metadata(self, idx = None, zmsg = "no_data"):
            #  return a list of (attribute, value), like dbus a{sv}
            r = []
            g, i = self.get_res_group_with_index(idx)

            if g == None or i == None:
                p, i = self.get_dbus_dom_app()
                ob = _T("{}/{}").format(p, _T(zmsg))
                r.append((_T("mpris:trackid"),
                          _T('o:{}').format(ob)))
                return r

            i = g.get_at_index(i)
            resid = self.get_dbus_itempath(g, i)
            # TODO - objects made here can be cached in a map
            # keyed on resid

            r.append((_T("mpris:trackid"),
                      _T('o:{}').format(resid)))

            l = 0
            if self.load_ok and self.medi.Length() > 0:
                l = self.medi.Length()
            elif i.length > 0:
                l = i.length
            # length attribute needs microsecs (we have millisecs)
            r.append((_T("mpris:length"),
                      _T('x:{}').format(l * 1000)))
            # note: we do not do 'mpris:artUrl'

            # xesam items:
            nam = _T(i.resname)
            ids = i.get_desc_disp_str(allow_none = True)
            if ids == None or s_eq(ids, i.resname):
                # if title must be the resource name,
                # then just show the name w/o path
                ids = os.path.split(i.resname)[1] or nam

            ids = _T(ids)
            gds = _T(g.get_desc())

            xm = get_xesam_map(nam)
            r.append((_T("xesam:title"),
                      _T('s:{}').format(xm['title'] or ids)))
            r.append((_T("xesam:album"),
                      _T('s:{}').format(xm['album'] or gds)))

            # artist, genre: to send type 'as' join w/ '\n'
            if xm['artist'] != None:
                if isinstance(xm['artist'], list):
                    v = '\n'.join(xm['artist'])
                else:
                    v = xm['artist']
                r.append((_T("xesam:artist"),
                          _T('as:{}').format(v)))

            if xm['genre'] != None:
                if isinstance(xm['genre'], list):
                    v = '\n'.join(xm['genre'])
                else:
                    v = xm['genre']
                r.append((_T("xesam:genre"),
                          _T('as:{}').format(v)))

            if xm['trackNumber'] != None:
                r.append((_T("xesam:trackNumber"),
                          _T('i:{}').format(xm['trackNumber'])))

            if xm['url'] != None:
                r.append((_T("xesam:url"),
                          _T('s:{}').format(xm['url'])))

            return r


    # not in _in_xws, but stubs convenient
    else:
        def mpris_sendsignal_check(self, force = False):
            pass

        def metadata_check(self):
            pass

    # END dbus interface/object misc.

    def set_statusbar(self, txt, pane, notify = False):
        sb = self.GetStatusBar()
        t = _WX(txt)
        sb.SetStatusText(t, pane)
        if pane == 0 and self.mpris_seek < 0:
            self.set_taskbar_tooltip(t, notify = notify)

    def set_tb_combos(self, do_group = True, do_resrc = True):
        ix = self.media_indice
        g, ig = self.get_res_group_with_index(ix)

        if not g:
            if do_group:
                self.cbox_group.Clear()
            if do_resrc:
                self.cbox_resrc.Clear()
            return

        cur_gi = self.reslist.index(g)

        if do_group:
            self.cbox_group.Clear()
            for cur in self.reslist:
                des = cur.get_desc()
                if not g.has_unique_desc():
                    dn = resourcename_with_displayname(des)
                    s = dn.get_disp_str()
                else:
                    s = des
                self.cbox_group.Append(s)
            self.cbox_group.SetSelection(cur_gi)

        if do_resrc:
            self.cbox_resrc.Clear()
            for cur in g.data:
                s = _T(cur.get_desc_disp_str(True) or
                       cur.get_res_disp_str())
                self.cbox_resrc.Append(s)
            self.cbox_resrc.SetSelection(ig)

    def _do_app_art(self):
        getters = (
            getwxmav_16Icon,
            getwxmav_24Icon,
            getwxmav_32Icon,
            getwxmav_48Icon,
            getwxmav_64Icon,
            )

        self.icons = icons = wx.IconBundle()
        for fimg in getters:
            icons.AddIcon(fimg())

        self.SetIcons(icons)

    def _do_taskbar_object(self):
        try:
            if self.taskbar_obj:
                return self.taskbar_obj
        except AttributeError:
            pass

        self.taskbar_obj = TaskBarObject(self)
        self.set_taskbar_tooltip()

        return self.taskbar_obj

    def get_taskbar_object(self, make_if_needed = False):
        try:
            tob = self.taskbar_obj
        except AttributeError:
            tob = None

        if tob == None and make_if_needed:
            return self._do_taskbar_object()

        return tob

    def del_taskbar_object(self):
        tob = self.get_taskbar_object(make_if_needed = False)
        if tob:
            tob.RemoveIcon()
            tob.Destroy()
            self.taskbar_obj = None
            return self.taskbar_obj
        return None

    def set_taskbar_object(self, set_on = None):
        do = self.opt_tray_icon
        if set_on == True:
            do = True
        elif set_on == False:
            do = False

        if do:
            return self.get_taskbar_object(make_if_needed = True)
        else:
            return self.del_taskbar_object()

    def set_taskbar_tooltip(self, tip = "", ico = None, notify = False):
        if self.opt_tray_icon:
            tob = self.get_taskbar_object(make_if_needed = True)
        else:
            tob = None

        if tob == None and not notify:
            return

        if ico == None and tob:
            if _in_msw:
                ico = getwxmav_16Icon()
            else:
                ico = getwxmav_24Icon()

        nam = _T(self.GetTitle())
        # the strip() here is important: this is usually called
        # from set_statusbar(), and that sometimes gets a string
        # of whitespace to clear a field (since an empty string
        # might not work).  so, strip and test
        ts = _T(tip).strip()

        if ts and tob:
            t = _T("{}\n\n{}").format(nam, ts)
        else:
            t = nam

        if tob:
            tob.SetIcon(ico, t)

        if notify:
            self.do_notification_message(nam, ts)


    def is_fullscreen(self):
        #back = self.backpanel
        return self.IsFullScreen()


    def do_notification_message(self, title, message, force = False):
        # notification popup (but not if in fullscreen)
        if self.is_fullscreen():
            return

        if not (self.opt_notifymsg or force):
            return

        if _in_msw:
            if self.opt_tray_icon:
                tob = self.get_taskbar_object(make_if_needed = True)
            else:
                tob = None

            # these are added in wxWidgets 3.1, but currently (2017)
            # wxPython uses 3.0.x, so they are not implemented
            try:
                if tob:
                    wxadv.NotificationMessage.UseTaskBarIcon(tob)
                wxadv.NotificationMessage.MSWUseToasts()
            except:
                pass

        self.pending_notification = (title, message)

    def _show_notification_message(self):
        try:
            title, message = self.pending_notification
            self.pending_notification = None
            n = wxadv.NotificationMessage()
            n.SetTitle(_T(title))
            n.SetMessage(_T(message))
            n.Show()
        except:
            pass


    def color_hacks(self):
        # hack: because top window is not using a panel, exposed
        # areas might differ in color from panels, which is not wanted
        self.SetOwnBackgroundColour(
            self.pos_panel.GetBackgroundColour())

    def make_menu_bar(self):
        I = wx.NewId
        mb = wx.MenuBar()

        # conventional File menu
        #
        self.mfile = mfile = wx.Menu()
        ## opens
        # open local file
        self.mfile_openfile = cur = wx.ID_OPEN
        mfile.Append(cur, _("&Open Files"), _("Open a local files"))
        # open local directory
        self.mfile_opendir = cur = I()
        mfile.Append(cur, _("Open &Directory"),
                          _("Open a local directory"))
        # open local directory recursively
        self.mfile_opendir_recurse = cur = I()
        mfile.Append(cur, _("&Recursively Open Directory"),
                    _("Open a local directory and its subdirectories"))
        # open URL
        self.mfile_openurl = cur = I()
        mfile.Append(cur, _("Open &URL"), _("Open a URL"))
        # separator
        mfile.AppendSeparator()
        ## saves
        # Save current group as a .pls file
        self.mfile_savegrp = cur = wx.ID_SAVE
        mfile.Append(cur, _("Save Current Media &Group"),
                          _("Save current media group in a playlist"))
        # Save all groups as a set in a directory
        self.mfile_saveset = cur = I()
        mfile.Append(cur, _("Save Whole &Media Set"),
                          _("Save all media groups in a directory"))
        # separator
        mfile.AppendSeparator()
        # quit item
        self.mfile_quit = cur = wx.ID_EXIT
        mfile.Append(cur, _("&Quit"), _("Quit the program"))

        # add file menu
        mb.Append(mfile, _("&File"))

        # conventional Edit menu
        #
        self.medit = medit = wx.Menu()
        ## regrets
        # undo change
        self.medit_undo = cur = wx.ID_UNDO
        medit.Append(cur, _("&Undo"), _("Undo last change"))
        # redo change
        self.medit_redo = cur = wx.ID_REDO
        medit.Append(cur, _("&Redo"), _("Redo last change"))
        # separator
        medit.AppendSeparator()
        ## set editor dialog
        self.medit_editor = cur = I()
        medit.Append(cur, _("Use Media Set &Editor"),
                          _("Run media group set editor dialog"))
        ## set items apply title tags
        self.medit_grtags = cur = I()
        if have_tagsmod:
            medit.Append(cur, _("&Set track description from tags"),
                              _("Apply media title tags to current"
                                " group tracks"))
            self.Bind(wx.EVT_MENU, self.on_menu, id = cur)
        # separator
        medit.AppendSeparator()
        ## deletes
        # Delete current group
        self.medit_delegrp = cur = wx.ID_DELETE
        medit.Append(cur, _("&Delete Current Group"),
                          _("Delete current media group/playlist"))
        # Delete all groups as a set
        self.medit_deleset = cur = I()
        medit.Append(cur, _("Delete &Whole Media Set"),
                          _("Delete all media groups/playlists"))

        # add edit menu
        mb.Append(medit, _("&Edit"))

        # Controls menu
        #
        self.mctrl = mctrl = wx.Menu()
        # loop play
        self.mctrl_loop = cur = I()
        mctrl.Append(cur, _("L&oop"),
                        _("Play current source in a loop"),
                        wx.ITEM_CHECK)
        mctrl.Check(cur, self.loop_track)
        # auto advance to next track and play
        self.mctrl_advance = cur = I()
        mctrl.Append(cur, _("Ad&vance to next"),
                        _("Auto play next track after current"),
                        wx.ITEM_CHECK)
        mctrl.Check(cur, self.adv_track)
        # separator
        mctrl.AppendSeparator()
        # play
        self.mctrl_play = cur = I()
        mctrl.Append(cur, _("&Play"), _("Play current source"))
        # pause
        self.mctrl_pause = cur = I()
        mctrl.Append(cur, _("P&ause"), _("Pause current source"))
        # stop
        self.mctrl_stop = cur = I()
        mctrl.Append(cur, _("S&top"), _("Stop current source"))
        # separator
        mctrl.AppendSeparator()
        # next
        self.mctrl_next = cur = I()
        mctrl.Append(cur, _("&Next Track"), _("Go to next track"))
        # previous
        self.mctrl_previous = cur = I()
        mctrl.Append(cur, _("P&revious Track"),
                        _("Go to previous track"))
        # separator
        mctrl.AppendSeparator()
        # next group
        self.mctrl_next_grp = cur = wx.ID_DOWN
        mctrl.Append(cur, _("Next &Group"),
                        _("Go to next group"))
        # previous group
        self.mctrl_previous_grp = cur = wx.ID_UP
        mctrl.Append(cur, _("Previous Gro&up"),
                        _("Go to previous group"))
        # separator
        mctrl.AppendSeparator()
        # last group
        self.mctrl_last_grp = cur = I()
        mctrl.Append(cur, _("&Last Group"),
                        _("Go to the last group"))
        # first group
        self.mctrl_first_grp = cur = I()
        mctrl.Append(cur, _("F&irst Group"),
                        _("Go to the first group"))

        # add controls menu
        mb.Append(mctrl, _("&Controls"))

        # Tools menu
        #
        #self.mtool = mtool = wx.Menu()
        #
        #mb.Append(mtool, _("&Tools"))

        # Options menu
        #
        self.mopts = mopts = wx.Menu()
        # show quit confirm message box?
        self.mopts_quitquery = cur = I()
        mopts.Append(cur, _("&Confirm On Quit"),
                        _("Prompt for confirmation on quitting"),
                        wx.ITEM_CHECK)
        mopts.Check(cur, self.opt_quit_query)
        # separator
        mopts.AppendSeparator()
        # show taskbar/tray icon?
        self.mopts_trayicon = cur = I()
        mopts.Append(cur, _("Use &Tray Icon"),
                        _("Show or hide the system tray icon and menu"),
                        wx.ITEM_CHECK)
        mopts.Check(cur, self.opt_tray_icon)
        # show notification popups?
        self.mopts_notifymsg = cur = I()
        mopts.Append(cur, _("Notice &Message Popups"),
                        _("Show notification temporary popup messages"),
                        wx.ITEM_CHECK)
        mopts.Check(cur, self.opt_notifymsg)
        # use proxy for media URI? self.can_use_proxy
        self.mopts_proxy = cur = I()
        # disable this item until further testing
        #mopts.Append(cur, _("Use &URL Proxy"),
        #            _("Use a proxy per protocol if available for URLs"),
        #                wx.ITEM_CHECK)
        #mopts.Check(cur, self.can_use_proxy)
        # end disable item
        # use SetThemeEnabled and handle change event
        self.mopts_themeok = cur = I()
        # theme support: option has no effect in GTK or MSW
        if False:
            # separator
            mopts.AppendSeparator()
            mopts.Append(cur, _("Use Theme &Support"),
                        _("Support desktop theme style changes"),
                            wx.ITEM_CHECK)
            mopts.Check(cur, self.theme_support)

        # add options menu
        mb.Append(mopts, _("&Options"))

        # Help menu
        #
        self.mhelp = mhelp = wx.Menu()
        # view python and wx version in message box
        self.mhelp_ckver = cur = new_wx_id()
        mhelp.Append(cur, _("See Versions"),
                        _("See version iformation."))
        # separator
        mhelp.AppendSeparator()
        # usual help menu -- TODO uncomment when help is ready
        self.mhelp_help = cur = wx.ID_HELP
        #mhelp.Append(cur, _("&Help"),
        #                _("Show help."))
        # separator
        #mhelp.AppendSeparator()
        # usual about menu
        self.mhelp_about = cur = wx.ID_ABOUT
        mhelp.Append(cur, _("&About"),
                        _("Show about dialog."))
        # Add Help menu
        mb.Append(mhelp, _("&Help"))

        # put menu bar on frame window
        self.SetMenuBar(mb)

        # bondage
        self.Bind(wx.EVT_MENU, self.on_menu)


    def make_taskbar_menu(self):
        def _get_mi(m, mid):
            if phoenix:
                return m.FindItem(mid)[0]
            return m.FindItemById(mid)

        cl = (self.mctrl_loop,
              self.mctrl_advance)
        ml = (self.mctrl_play,
              self.mctrl_pause,
              self.mctrl_stop,
              self.mctrl_next,
              self.mctrl_previous,
              self.mctrl_next_grp,
              self.mctrl_previous_grp,
              self.mctrl_last_grp,
              self.mctrl_first_grp)

        mtico = wx.Menu()

        # Controls menu
        for cur in cl:
            mit = _get_mi(self.mctrl, cur)
            mtico.Append(cur, mit.GetItemLabel(), wx.EmptyString,
                         wx.ITEM_CHECK)
            mtico.Check(cur, mit.IsChecked())
            mtico.Enable(cur, mit.IsEnabled())

        mtico.AppendSeparator()

        for cur in ml:
            mit = _get_mi(self.mctrl, cur)
            mtico.Append(cur, mit.GetItemLabel(), wx.EmptyString)
            mtico.Enable(cur, mit.IsEnabled())
            if (cur == self.mctrl_previous or
                cur == self.mctrl_previous_grp):
                mtico.AppendSeparator()

        mtico.AppendSeparator()

        # quit, from file menu
        cur = self.mfile_quit
        mit = _get_mi(self.mfile, cur)
        mtico.Append(cur, mit.GetItemLabel(), wx.EmptyString)
        mtico.Enable(cur, mit.IsEnabled())

        return mtico


    def make_tool_bar(self, mk_two = True, wxtb_2nd = False):
        self.make_std_tool_bar(not mk_two)
        if mk_two:
            self.make_std_tool_bar2(use_wxtoolbar = wxtb_2nd)

    def make_std_tool_bar(self, include_combos = False):
        sty = sty2 = (wx.TB_DOCKABLE | wx.NO_BORDER | wx.TB_FLAT)
        sty |= wx.TB_HORIZONTAL #wx.TB_VERTICAL
        sty2 |= wx.TB_HORIZONTAL
        #tb = self.CreateToolBar(sty, wx.ID_ANY)
        tb = wx.ToolBar(self, wx.ID_ANY, style = sty)

        tb.SetMargins((2, 2))
        tb.SetToolPacking(2)
        tb.SetToolSeparation(5)

        _art = wx.ArtProvider

        self.toolbar = tb

        def _mi_tup(mnu, mid):
            mi = mnu.FindItemById(mid)
            lbl = mi.GetLabel()
            hlp = mi.GetHelp()
            return (lbl, hlp)

        def _t_add(t, *a):
            if phoenix:
                t.AddTool(*a)
            else:
                t.AddLabelTool(*a)

        lbl, hlp = _mi_tup(self.mfile, self.mfile_quit)
        _t_add(tb, self.mfile_quit, lbl,
                        _art.GetBitmap(
                            wx.ART_QUIT, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        tb.AddSeparator()

        lbl, hlp = _mi_tup(self.mfile, self.mfile_openfile)
        _t_add(tb, self.mfile_openfile, lbl,
                        _art.GetBitmap(
                            wx.ART_FILE_OPEN, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        lbl, hlp = _mi_tup(self.mfile, self.mfile_savegrp)
        _t_add(tb, self.mfile_savegrp, lbl,
                        _art.GetBitmap(
                            wx.ART_FILE_SAVE, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        tb.AddSeparator()

        lbl, hlp = _mi_tup(self.medit, self.medit_undo)
        _t_add(tb, self.medit_undo, lbl,
                        _art.GetBitmap(
                            wx.ART_UNDO, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        lbl, hlp = _mi_tup(self.medit, self.medit_redo)
        _t_add(tb, self.medit_redo, lbl,
                        _art.GetBitmap(
                            wx.ART_REDO, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        tb.AddSeparator()

        lbl, hlp = _mi_tup(self.mctrl, self.mctrl_previous_grp)
        _t_add(tb, self.mctrl_previous_grp, lbl,
                        _art.GetBitmap(
                            wx.ART_GO_UP, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        lbl, hlp = _mi_tup(self.mctrl, self.mctrl_next_grp)
        _t_add(tb, self.mctrl_next_grp, lbl,
                        _art.GetBitmap(
                            wx.ART_GO_DOWN, wx.ART_TOOLBAR),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        lbl, hlp)

        #tb.AddSeparator()
        #
        #lbl, hlp = _mi_tup(self.mhelp, self.mhelp_help)
        #_t_add(tb, self.mhelp_help, lbl,
        #                _art.GetBitmap(
        #                    wx.ART_HELP, wx.ART_TOOLBAR),
        #                wx.NullBitmap, wx.ITEM_NORMAL,
        #                lbl, hlp)

        if include_combos:
            self.make_std_tool_bar2(True, tb)

        tb.Realize()


    def make_std_tool_bar2(self, use_wxtoolbar = False, tb_ext = None):
        back = self.backpanel

        if tb_ext != None:
            tb = tb_ext
        elif use_wxtoolbar:
            sty2 = (wx.TB_DOCKABLE | wx.NO_BORDER | wx.TB_FLAT)
            sty2 |= wx.TB_HORIZONTAL
            tb = wx.ToolBar(self, wx.ID_ANY, style = sty2)
            tb.SetMargins((3, 1))
        else:
            tb = wx.Panel(back, wx.ID_ANY)
            self.toolbar2 = tb

        # In GTK2 the wxChoice is far better than this app's
        # 'TailorMadeComboCtrl' but MSW Choice and ComboBox
        # suck WRT dropdown size and GTK-3 wxChoice does not
        # truncate long strings and if too long, just destroys
        # the control, never to be seen again, soo . . .
        # UPDATE: wxChoice behavior on getting tab->focus is
        # unexpected, don't use until that's figured out
        # TODO: figure wxChoice focus behavior
        #use_choice = (_in_gtk and 'gtk2' in wx.PlatformInfo)
        use_choice = False
        if use_choice:
            sty = 0

            self.cbox_group_id = cur = new_wx_id()
            self.cbox_group = wx.Choice(tb, cur, style = sty)
            if use_wxtoolbar:
                self.cbox_group.SetSize((100, -1))

            self.cbox_group.SetMinSize((100, -1))
            stip = wx.ToolTip(_("Select Group/Playlist"))
            self.cbox_group.SetToolTip(stip)
            self.Bind(wx.EVT_CHOICE, self.on_cbox, id = cur)

            self.cbox_resrc_id = cur = new_wx_id()
            self.cbox_resrc = wx.Choice(tb, cur, style = sty)
            if use_wxtoolbar:
                self.cbox_resrc.SetSize((100, -1))

            self.cbox_resrc.SetMinSize((100, -1))
            self.cbox_resrc.SetMinClientSize((800, -1))

            stip = wx.ToolTip(_("Select Track/Title"))
            self.cbox_resrc.SetToolTip(stip)
            self.Bind(wx.EVT_CHOICE, self.on_cbox, id = cur)
        else:
            sty = wx.CB_DROPDOWN | wx.CB_READONLY

            self.cbox_group_id = cur = new_wx_id()
            self.cbox_group = TailorMadeComboCtrl(tb, cur, style = sty)
            self.cbox_group.SetPopupControl(TailorMadeComboPop())
            self.cbox_group.SetSize((100, -1))
            self.cbox_group.SetMinSize((100, -1))

            stip = wx.ToolTip(_("Select Group/Playlist"))
            self.cbox_group.SetToolTip(stip)
            self.Bind(wx.EVT_COMBOBOX, self.on_cbox, id = cur)

            self.cbox_resrc_id = cur = new_wx_id()
            self.cbox_resrc = TailorMadeComboCtrl(tb, cur, style = sty)
            self.cbox_resrc.SetPopupControl(TailorMadeComboPop())
            self.cbox_resrc.SetSize((100, -1))
            self.cbox_resrc.SetMinSize((100, -1))

            stip = wx.ToolTip(_("Select Track/Title"))
            self.cbox_resrc.SetToolTip(stip)
            self.Bind(wx.EVT_COMBOBOX, self.on_cbox, id = cur)

        if use_wxtoolbar:
            tb.AddControl(self.cbox_group)
            tb.AddSeparator()
            tb.AddControl(self.cbox_resrc)

            if tb_ext == None:
                tb.Realize()
                self.toolbar2.Bind(wx.EVT_SIZE, self.on_tb2_size)
        else:
            if use_choice:
                grsz = self.cbox_group.GetSize()
                tb.SetSize((-1, grsz.height + 6))
                tb.SetMinSize((100, grsz.height + 6))
                self.toolbar2.Bind(wx.EVT_SIZE, self.on_tb2_size)
            else:
                szr = wx.BoxSizer(wx.HORIZONTAL)
                szr.Add(self.cbox_group, 1, wx.EXPAND | wx.ALL, 6)
                szr.AddSpacer(6)
                szr.Add(self.cbox_resrc, 1, wx.EXPAND | wx.ALL, 6)

                tb.SetSizer(szr)
                tb.Layout()

    def do_tb2_size(self, event):
        clsz = self.toolbar2.GetClientSize()
        grsz = self.cbox_group.GetSize()

        w = (clsz.width / 2) - 6
        h = grsz.height

        offs = (clsz.height - h) / 2

        self.cbox_group.SetSize((w, h))
        self.cbox_resrc.SetSize((w, h))

        pos = self.cbox_group.GetPosition()
        pos.x = pos.y = offs
        self.cbox_group.SetPosition(pos)
        pos.x += w + 6
        self.cbox_resrc.SetPosition(pos)

    def make_status_bar(self):
        sty = (wx.STB_DEFAULT_STYLE &
             ~(wx.STB_ELLIPSIZE_MIDDLE | wx.STB_ELLIPSIZE_END) |
               wx.STB_ELLIPSIZE_START)
        sb = self.CreateStatusBar(number = 2, style = sty)
        sb.SetStatusWidths([-6, -1])


    def do_version_dialog(self):
        m = _T(
            "{} version {}\n\nPython '{}'\n\nwxPython '{}'").format(
            wx.GetApp().get_prog_name(), version_string,
            sys.version, wx.version())

        wx.MessageBox(m, _("Version Information"),
            style = wx.OK | wx.ICON_INFORMATION)

    def do_about_dialog(self):
        if not self.__class__.about_info:
            import zlib
            import base64

            lic = licence_data
            t = wxadv.AboutDialogInfo()

            t.SetName(wx.GetApp().get_prog_name())
            t.SetVersion(_T("{vs} {vn}").format(
                vs = version_string, vn = version_name))
            t.SetDevelopers(program_devs)
            t.SetLicence(zlib.decompress(base64.b64decode(lic)))
            t.SetDescription(program_desc)
            cpyrt = _T("{year} {name} {addr}").format(
                year = copyright_years,
                name = maintainer_name,
                addr = maintainer_addr)
            if _ucode_type == 'utf-8':
                try:
                    t.SetCopyright(_T("© ") + cpyrt)
                except:
                    t.SetCopyright(_T("(C) ") + cpyrt)
            else:
                t.SetCopyright(_T("(C) ") + cpyrt)
            t.SetWebSite(program_site)
            t.SetIcon(self.icons.GetIcon((64, 64)))

            dw = [
                _T("Nona Wordsworth"),
                _T("Rita Manuel")
                ]
            t.SetDocWriters(dw)
            tr = [
                _T("Saul \"Greek\" Tomey"),
                _("Translation volunteers welcome!"),
                _("Contact {email}.").format(email = maintainer_addr)
                ]
            t.SetTranslators(tr)
            t.SetArtists([_T("I. Burns")])

            self.__class__.about_info = t

        wxadv.AboutBox(self.__class__.about_info)

    def dialog_set_editor(self):
        try:
            dlg = self.group_edit_dialog
        except AttributeError:
            dlg = GroupSetEditDialog(self, wx.ID_ANY)
            self.group_edit_dialog = dlg

        dlg.set_data(self.reslist)

        if dlg.ShowModal() != wx.ID_OK:
            dlg.set_data([])
            return False

        dat = dlg.get_data()
        dlg.set_data([])
        # if user wants to delete all, let it be done
        # through the edit menu delete items
        if not dat:
            return False

        st = self.get_medi_state()

        # orig data is not changed
        self.push_undo(do_copy = False)

        cur = self.get_reslist_item()
        res = cur.resname

        check_indice = -1
        idx = 0
        for g in dat:
            for it in g.data:
                if s_eq(it.resname, res):
                    check_indice = idx
                    break
                idx += 1
            if check_indice > -1:
                break

        msg = _("media set edited")

        if check_indice < 0:
            self.cmd_on_stop(from_user = True)
            self.unload_media()

            self.reslist = dat
            self.media_indice = 0
        else:
            self.reslist = dat
            self.media_indice = check_indice

            ln, sz = self.check_set_media_meta(True)
            dn, med, des, com, err, lth = self.get_reslist_item_tup()

            msg = _T(des or dn or med)

            if st == wx.media.MEDIASTATE_PLAYING:
                msg = _("Playing: {}").format(msg)
            elif st == wx.media.MEDIASTATE_PAUSED:
                msg = _("Paused: {}").format(msg)
            else:
                msg = _("Current: {}").format(msg)

        self.set_tb_combos()
        self.set_statusbar(msg, 0)

        self.mpris2_signal_emit(_T("Metadata"))
        self.mpris_sendsignal_check()

        return True

    def dialog_save_group(self, indice = None):
        grp = self.get_res_group_current()
        if not grp:
            return False

        if self.dialog_savegroup == None:
            self.dialog_savegroup = wx.FileDialog(
                    self,
                    _("Save Current Media Group as a Playlist v2"),
                    _T(""), _T(""),
                    _("Playlist v2 (*.pls)|*.pls|All Files (*)|*;*.*"),
                    wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT
                )

        dlg = self.dialog_savegroup

        if dlg.ShowModal() != wx.ID_OK:
            return False

        pth = _T(dlg.GetPath())
        # ensure .pls suffix
        nam, ext = os.path.splitext(pth)
        ext = _T(ext.lower()) if _in_msw else _T(ext)
        if not ext or ext != _T(".pls"):
            pth += _T(".pls")

        res = False
        fd = err = None

        try:
            fd = cv_open_w(pth)
            res = grp.write_file(fd, do_close = False)
            if not res:
                err = _("cannot save list")
        except (OSError, IOError) as s:
            err = _("O/S error saving {n}: {e}").format(n=pth, e=s)
        except Exception as s:
            err = _("error saving {n}: {e}").format(n=pth, e=s)
        except:
            err = _("exception: error saving '{}'").format(pth)

        if fd:
            fd.close()

        if err:
            wx.MessageBox(err, _("Error"), wx.OK|wx.ICON_ERROR)
            return False

        return res

    def dialog_save_set(self, indice = None):
        lst = self.reslist
        if len(lst) < 1:
            return False

        if self.dialog_saveset == None:
            d = wx.GetHomeDir()
            #d = wx.GetApp().get_config_dir()
            self.dialog_saveset = wx.DirDialog(
                    self,
                    _("Choose Media Group Set Directory"),
                    d, wx.DD_DEFAULT_STYLE
                )

        dlg = self.dialog_saveset

        if dlg.ShowModal() != wx.ID_OK:
            return False

        pth = dlg.GetPath()
        res = False
        err = None

        try:
            res = wr_groups(lst, pth) #, namebase = _T("group-"))
            if not res:
                err = _("cannot save set {}").format(pth)
        except (OSError, IOError) as s:
            err = _("O/S error saving in {n}: {e}").format(n=pth, e=s)
        except Exception as s:
            err = _("error saving in {n}: {e}").format(n=pth, e=s)
        except:
            err = _("exception: error saving in '{}'").format(pth)

        if err:
            wx.MessageBox(err, _("Error"), wx.OK|wx.ICON_ERROR)
            return False

        return res

    def dialog_open_file(self, append = True, play = True):
        if self.dialog_file == None:
            self.dialog_file = wx.FileDialog(
                    self,
                    _("Select A/V Files"),
                    _T(""), _T(""), _T("*"),
                    wx.FD_OPEN|wx.FD_MULTIPLE|wx.FD_FILE_MUST_EXIST
                )

        dlg = self.dialog_file

        if dlg.ShowModal() != wx.ID_OK:
            return

        reslist, errs = self.do_arg_list(dlg.GetPaths(),
                                         append = append,
                                         recurse = False,
                                         play = play)

        self.prdbg(_T("dialog_open_file: errs == '{}'").format(errs))

    def dialog_open_dirs(self,
                        append = True, play = True, recurse = False):
        if self.dialog_dirs == None:
            self.dialog_dirs = wx.DirDialog(
                self, _("Select Directory/Folder"),
                wx.EmptyString, wx.DD_DIR_MUST_EXIST
            )

        dlg = self.dialog_dirs

        if dlg.ShowModal() != wx.ID_OK:
            return

        reslist, errs = self.do_arg_list([dlg.GetPath()],
                                         append = append,
                                         recurse = recurse,
                                         play = play)

        self.prdbg(_T("dialog_open_dirs: errs == '{}'").format(errs))

    def dialog_open_uri(self, append = True, play = True):
        msg = _("Enter a URL for a resource such as a media "
                "file or playlist")
        tit = _("Enter URL")
        dft = wx.EmptyString

        res = wx.GetTextFromUser(msg, tit, dft, self)

        if not res:
            return

        res = res.strip()
        if not re.search(_T(r'^([a-zA-Z0-9]+)://.*/.*$'), res):
            self.prdbg(_T("BAD URL entered: '{}'").format(res))
            return

        reslist, errs = self.do_arg_list([res],
                                         append = append,
                                         recurse = False,
                                         play = play)

        self.prdbg(_T("dialog_open_uri: errs == '{}'").format(errs))

    def on_cbox(self, event):
        # For MSW an applicatiom ComboCtrl w/ ListBox dropdwon is used,
        # and the event is setup so that event.IsSelection() is True;
        # elsewhere wxChoice control is used and event.IsSelection()
        # does not return True
        if _in_msw and not event.IsSelection():
            return

        ix = self.media_indice
        gr, ir = self.get_res_group_with_index(ix)
        if not gr:
            return
        ig = self.reslist.index(gr)
        gix = self.cbox_group.GetSelection() or 0
        rix = self.cbox_resrc.GetSelection() or 0

        if gix == ig and rix == ir:
            return # no change
        elif gix != ig:
            self.media_indice = 0
            for i in range(gix):
                self.media_indice += self.reslist[i].get_len()
            self.set_tb_combos(do_group = False, do_resrc = True)
        else:
            ix = 0
            for i in range(ig):
                ix += self.reslist[i].get_len()
            self.media_indice = ix + rix

        if self.media_indice > 0:
            self.media_indice -= 1
            self.cmd_on_next(from_user = True)
        else:
            self.media_indice += 1
            self.cmd_on_prev(from_user = True)

    def on_menu(self, event):
        i = event.GetId()

        if False:
            pass
        # File menu
        ## opens
        elif i == self.mfile_quit:
            self.on_quit(event)
        elif i == self.mfile_openfile:
            self.dialog_open_file()
            self.metadata_check()
        elif i == self.mfile_opendir:
            self.dialog_open_dirs()
            self.metadata_check()
        elif i == self.mfile_opendir_recurse:
            self.dialog_open_dirs(recurse = True)
            self.metadata_check()
        elif i == self.mfile_openurl:
            self.dialog_open_uri()
            self.metadata_check()
        ## saves
        elif i == self.mfile_savegrp:
            self.dialog_save_group()
        elif i == self.mfile_saveset:
            self.dialog_save_set()
        # Edit menu
        ## regrets
        elif i == self.medit_undo:
            self.do_undo()
            self.metadata_check()
        elif i == self.medit_redo:
            self.do_redo()
            self.metadata_check()
        ## set edit dialog
        elif i == self.medit_editor:
            self.dialog_set_editor()
            self.metadata_check()
        ## set title tags on group items
        elif i == self.medit_grtags:
            self.do_group_items_desc_from_tags()
        ## deletes
        elif i == self.medit_delegrp:
            self.delete_group()
            self.metadata_check()
        elif i == self.medit_deleset:
            self.delete_set()
            self.metadata_check()
        # Controls menu
        elif i == self.mctrl_loop:
            b = self.loop_track
            self.loop_track = self.mctrl.IsChecked(self.mctrl_loop)
            if b != self.loop_track:
                self.mpris2_signal_emit(_T("LoopStatus"))
        elif i == self.mctrl_advance:
            self.adv_track = self.mctrl.IsChecked(self.mctrl_advance)
        elif i == self.mctrl_play:
            self.do_command_button(self.id_play)
        elif i == self.mctrl_pause:
            self.do_command_button(self.id_play)
        elif i == self.mctrl_stop:
            self.do_command_button(self.id_stop)
        elif i == self.mctrl_next:
            self.do_command_button(self.id_next)
            self.metadata_check()
        elif i == self.mctrl_previous:
            self.do_command_button(self.id_prev)
            self.metadata_check()
        elif i == self.mctrl_next_grp:
            self.cmd_next_grp()
            self.metadata_check()
        elif i == self.mctrl_previous_grp:
            self.cmd_prev_grp()
            self.metadata_check()
        elif i == self.mctrl_first_grp:
            self.cmd_first_grp()
            self.metadata_check()
        elif i == self.mctrl_last_grp:
            self.cmd_last_grp()
            self.metadata_check()
        # Options menu
        elif i == self.mopts_quitquery:
            t = self.mopts.IsChecked(self.mopts_quitquery)
            self.opt_quit_query = t
        elif i == self.mopts_trayicon:
            t = self.mopts.IsChecked(self.mopts_trayicon)
            self.opt_tray_icon = t
            self.set_taskbar_object()
        elif i == self.mopts_notifymsg:
            t = self.mopts.IsChecked(self.mopts_notifymsg)
            self.opt_notifymsg = t
        elif i == self.mopts_proxy:
            t = self.mopts.IsChecked(self.mopts_proxy)
            self.can_use_proxy = t
        elif i == self.mopts_themeok:
            t = self.mopts.IsChecked(self.mopts_themeok)
            self.theme_support = t
        # Help menu
        elif i == self.mhelp_ckver:
            self.do_version_dialog()
        elif i == self.mhelp_help:
            pass
        elif i == self.mhelp_about:
            self.do_about_dialog()


    def on_char(self, event):
        self.on_key(event)

    def on_key(self, event):
        t = event.GetEventType()

        if t == wx.wxEVT_KEY_DOWN:
            self.handle_key_down(self, event)
        elif t == wx.wxEVT_KEY_UP:
            self.handle_key_up(self, event)
        elif t == wx.wxEVT_CHAR:
            self.handle_key_char(self, event)
        else:
            event.Skip()

    def focus_medi_opt(self, force = False):
        if not self.medi:
            return

        try:
            f = self.FindFocus()
            if f is self.cbox_group or f is self.cbox_resrc:
                return
        except AttributeError:
            pass

        #if _in_msw and not force:
        #    return

        self.medi.SetFocus()
        pass

    def show_wnd_id(self, ID, show = True):
        obj = self.get_obj_by_id(ID)
        if obj:
            return self.show_wnd_obj(obj, show)

        return False

    def show_wnd_obj(self, obj, show = True):
        r = False

        if obj not in self.hiders.values():
            return False

        szr = self.backpanel.GetSizer()
        r = szr.Show(obj, show, True)

        if r:
            szr.Layout()

        # try to keep focus on media control
        self.focus_medi_opt()

        return r

    def handle_key_char(self, recobj, event):
        kc = event.GetKeyCode()

        if kc == ord('<'):
            self.do_command_button(self.id_prev)
            return
        elif kc == ord('>'):
            self.do_command_button(self.id_next)
            return
        elif kc == ord('V'):
            self.dec_volume()
        elif kc == ord('v'):
            self.inc_volume()
        elif kc == ord('s'):
            if self.is_fullscreen():
                self.medi_tick = -1
                self.show_wnd_obj(self.hiders["vszr"], True)
                self.SetCursor(select_cursor(wx.CURSOR_DEFAULT))
        elif kc == ord('h'):
            if self.is_fullscreen():
                self.medi_tick = -1
                self.show_wnd_obj(self.hiders["vszr"], False)
                self.SetCursor(select_cursor(wx.CURSOR_BLANK))
        else:
            event.Skip()


    def handle_key_down(self, recobj, event):
        kc = event.GetKeyCode()

        if kc == wx.WXK_LEFT:
            self.do_seek_back()
        elif kc == wx.WXK_RIGHT:
            self.do_seek_forward()
        elif kc == wx.WXK_HOME or kc == wx.WXK_END:
            pass
        elif kc == wx.WXK_DOWN or kc == wx.WXK_UP:
            pass
        elif kc == wx.WXK_PAGEUP or kc == wx.WXK_PAGEDOWN:
            pass
        elif kc == wx.WXK_F11 or kc == wx.WXK_ESCAPE:
            pass
        elif kc == wx.WXK_SPACE:
            pass
        else:
            # wx on Unix does not define these -- MSW only?
            try:
                if kc == wx.WXK_VOLUME_DOWN:
                    self.dec_volume()
                    return
                elif kc == wx.WXK_VOLUME_UP:
                    self.inc_volume()
                    return
                #elif kc == wx.WXK_VOLUME_MUTE:
                #    return
            except AttributeError:
                pass

            event.Skip()

    def handle_key_up(self, recobj, event):
        kc = event.GetKeyCode()

        if kc == wx.WXK_F11:
            self.do_fullscreen(False) # toggle
        elif kc == wx.WXK_ESCAPE:
            if self.is_fullscreen():
                self.do_fullscreen(True) # un-fullscreen
        elif kc == wx.WXK_SPACE:
            self.do_command_button(self.id_play)
        elif kc == wx.WXK_PAGEUP:
            self.cmd_prev_grp()
        elif kc == wx.WXK_PAGEDOWN:
            self.cmd_next_grp()
        elif kc == wx.WXK_HOME:
            self.cmd_first_grp()
        elif kc == wx.WXK_END:
            self.cmd_last_grp()
        elif kc == wx.WXK_LEFT or kc == wx.WXK_RIGHT:
            pass
        elif kc == wx.WXK_DOWN or kc == wx.WXK_UP:
            pass
        else:
            # wx on Unix does not define these -- MSW only?
            try:
                if not _in_msw or not self.register_hotkey_done:
                    if kc == wx.WXK_MEDIA_NEXT_TRACK:
                        self.do_command_button(self.id_next)
                        return
                    elif kc == wx.WXK_MEDIA_PREV_TRACK:
                        self.do_command_button(self.id_prev)
                        return
                    elif kc == wx.WXK_MEDIA_STOP:
                        self.do_command_button(self.id_stop)
                        return
                    elif kc == wx.WXK_MEDIA_PLAY_PAUSE:
                        self.do_command_button(self.id_play)
                        return
            except AttributeError:
                pass

            event.Skip()

    def err_msg(self, msg):
        wx.GetApp().err_msg(msg)

    # bad hack: it has historically happened, and continues to happen
    # on MSW (7) and GTK, that some interface updates don't appear
    # without being forced, e.g. by resizing; wx 2.8 docs say that
    # if using sizers, wxWindow::Layout() should be used, but this
    # hack proves effective regardless
    def force_hack(self, use_hack = False, sz = None, force = False):
        if False and use_hack:
            if not sz:
                sz = self.GetSize()

            sz2 = wx.Size((sz.width+1, sz.height+1))
            self.SetSize(sz2)
            ev = wx.SizeEvent(sz, self.GetId())
            wx.CallAfter(wx.PostEvent, self, ev)
        elif force:
            self.Layout()

    def get_obj_by_id(self, the_id):
        for ID, obj in self.ctl_data:
            if ID == the_id:
                return obj
        return None

    def get_obj_by_id(self, the_id):
        for ID, obj in self.ctl_data:
            if ID == the_id:
                return obj
        return None

    def get_play_button(self):
        return self.get_obj_by_id(self.id_play)

    def set_play_label(self):
        self.get_play_button().SetLabel(self.label_play_on)
        self.mctrl.Enable(self.mctrl_play, True)
        self.mctrl.Enable(self.mctrl_pause, False)
        self.mctrl.Enable(self.mctrl_stop, True)

    def set_pause_label(self):
        self.get_play_button().SetLabel(self.label_play_off)
        self.mctrl.Enable(self.mctrl_play, False)
        self.mctrl.Enable(self.mctrl_pause, True)
        self.mctrl.Enable(self.mctrl_stop, True)

    def set_loop_track(self, do_loop = None, force_signal = False):
        if do_loop != None:
            self.loop_track = True if do_loop else False

        b = self.mctrl.IsChecked(self.mctrl_loop)
        if b != self.loop_track:
            self.mctrl.Check(self.mctrl_loop, self.loop_track)
            force_signal = True

        if force_signal:
            self.mpris2_signal_emit(_T("LoopStatus"))

    # see comment in ctor, where this is Bind()ed
    def on_iconize_event(self, event):
        self.do_tb2_size(None)
        # if restored from minimized state:
        if not event.IsIconized():
            if _in_gtk:
                wx.CallAfter(self.Layout)
        else:
            # record windowed size
            self.window_size = sz = self.GetSize()
            self.window_pos  = pt = self.GetPosition()
            self.err_msg(_T("On Minimize {} at {}").format(
                (sz.width, sz.height), (pt.x, pt.y)))

        self.force_hack(use_hack = True)

    # see comment in ctor, where this is Bind()ed
    def on_maximize_event(self, event):
        self.do_tb2_size(None)
        # if restored from minimized state:
        if not self.IsMaximized():
            # record windowed size
            self.window_size = sz = self.GetSize()
            self.window_pos  = pt = self.GetPosition()
            self.err_msg(_T("On Maximize {} at {}").format(
                (sz.width, sz.height), (pt.x, pt.y)))

        self.force_hack(use_hack = True)

    def on_sys_color(self, event):
        f = lambda wnd: self._color_proc_per_child(wnd)
        if False:
            invoke_proc_for_window_children(self, f)
            self.color_hacks()
        else:
            wx.CallAfter(invoke_proc_for_window_children, self, f)
            wx.CallAfter(self.color_hacks)

        if self.theme_support:
            self.Refresh(True)
        else:
            event.Skip()

    def _color_proc_per_child(self, wnd):
        wnd.SetThemeEnabled(self.theme_support)

        if not self.theme_support:
            return

        try:
            wnd._hack_on_color()
        except AttributeError:
            try:
                wnd.SetOwnForegroundColour(wx.NullColour)
            except:
                wnd.SetForegroundColour(wx.NullColour)
            try:
                wnd.SetOwnBackgroundColour(wx.NullColour)
            except:
                wnd.SetBackgroundColour(wx.NullColour)

    def on_idle(self, event):
        if self.do_setwname_done == False:
            self.do_setwname_done = True
            self.do_setwname()

        self.on_idle_menu_update(event)
        self.player_panel.do_idle(event)

    def on_idle_menu_update(self, event):
        if self.undo_redo.undo_length():
            # activate Undo menu
            self.medit.Enable(self.medit_undo, True)
            self.toolbar.EnableTool(self.medit_undo, True)
        else:
            self.medit.Enable(self.medit_undo, False)
            self.toolbar.EnableTool(self.medit_undo, False)
        if self.undo_redo.redo_length():
            # activate Redo menu
            self.medit.Enable(self.medit_redo, True)
            self.toolbar.EnableTool(self.medit_redo, True)
        else:
            self.medit.Enable(self.medit_redo, False)
            self.toolbar.EnableTool(self.medit_redo, False)

        butid = [
            self.id_play, self.id_prev, self.id_next, self.id_stop]

        if self.reslist and self.medi:
            # activate save menus
            self.mfile.Enable(self.mfile_savegrp, True)
            self.mfile.Enable(self.mfile_saveset, True)
            # activate edit menus
            self.medit.Enable(self.medit_delegrp, True)
            self.medit.Enable(self.medit_deleset, True)

            # {,de}activate control menus --
            # note play/pause is handled elswhere
            st = self.get_medi_state()
            # track items
            if st == wx.media.MEDIASTATE_PLAYING:
                self.mctrl.Enable(self.mctrl_play, False)
                self.mctrl.Enable(self.mctrl_pause, True)
                self.mctrl.Enable(self.mctrl_stop, True)
            elif st == wx.media.MEDIASTATE_PAUSED:
                self.mctrl.Enable(self.mctrl_play, True)
                self.mctrl.Enable(self.mctrl_pause, False)
                self.mctrl.Enable(self.mctrl_stop, True)
            elif st == wx.media.MEDIASTATE_STOPPED:
                self.mctrl.Enable(self.mctrl_play, True)
                self.mctrl.Enable(self.mctrl_pause, False)
                self.mctrl.Enable(self.mctrl_stop, False)
                self.get_obj_by_id(self.id_stop).Enable(False)
                # NOTE: remove from butid or infinite loop!
                del butid[butid.index(self.id_stop)]
            else:
                self.prdbg(_T("IDLE: OTHER STATE {}").format(st))
                self.mctrl.Enable(self.mctrl_play, False)
                self.mctrl.Enable(self.mctrl_pause, False)
                self.mctrl.Enable(self.mctrl_stop, False)
                self.get_obj_by_id(self.id_stop).Enable(False)
                del butid[butid.index(self.id_stop)]

            l = self.get_reslist_len()
            if l <= 1:
                self.mctrl.Enable(self.mctrl_next, False)
                self.mctrl.Enable(self.mctrl_previous, False)
                self.get_obj_by_id(self.id_next).Enable(False)
                del butid[butid.index(self.id_next)]
                self.get_obj_by_id(self.id_prev).Enable(False)
                del butid[butid.index(self.id_prev)]
            elif self.media_indice <= 0:
                self.mctrl.Enable(self.mctrl_next, True)
                self.mctrl.Enable(self.mctrl_previous, False)
                self.get_obj_by_id(self.id_prev).Enable(False)
                del butid[butid.index(self.id_prev)]
            elif self.media_indice >= (l - 1):
                self.mctrl.Enable(self.mctrl_next, False)
                self.mctrl.Enable(self.mctrl_previous, True)
                self.get_obj_by_id(self.id_next).Enable(False)
                del butid[butid.index(self.id_next)]
            else:
                self.mctrl.Enable(self.mctrl_next, True)
                self.mctrl.Enable(self.mctrl_previous, True)

            l = self.get_res_group_len()
            g = self.get_res_group_current()
            gi = self.reslist.index(g)
            # group items
            if l <= 1:
                self.mctrl.Enable(self.mctrl_next_grp, False)
                self.mctrl.Enable(self.mctrl_previous_grp, False)
                self.mctrl.Enable(self.mctrl_last_grp, False)
                self.mctrl.Enable(self.mctrl_first_grp, False)
                self.toolbar.EnableTool(self.mctrl_next_grp, False)
                self.toolbar.EnableTool(self.mctrl_previous_grp, False)
            elif gi <= 0:
                self.mctrl.Enable(self.mctrl_next_grp, True)
                self.mctrl.Enable(self.mctrl_previous_grp, False)
                self.mctrl.Enable(self.mctrl_last_grp, True)
                self.mctrl.Enable(self.mctrl_first_grp, False)
                self.toolbar.EnableTool(self.mctrl_next_grp, True)
                self.toolbar.EnableTool(self.mctrl_previous_grp, False)
            elif gi >= (l - 1):
                self.mctrl.Enable(self.mctrl_next_grp, False)
                self.mctrl.Enable(self.mctrl_previous_grp, True)
                self.mctrl.Enable(self.mctrl_last_grp, False)
                self.mctrl.Enable(self.mctrl_first_grp, True)
                self.toolbar.EnableTool(self.mctrl_next_grp, False)
                self.toolbar.EnableTool(self.mctrl_previous_grp, True)
            else:
                self.mctrl.Enable(self.mctrl_next_grp, True)
                self.mctrl.Enable(self.mctrl_previous_grp, True)
                self.mctrl.Enable(self.mctrl_last_grp, True)
                self.mctrl.Enable(self.mctrl_first_grp, True)
                self.toolbar.EnableTool(self.mctrl_next_grp, True)
                self.toolbar.EnableTool(self.mctrl_previous_grp, True)

            # buttons
            for bi in butid:
                self.get_obj_by_id(bi).Enable(True)
        else:
            # disable saves
            self.mfile.Enable(self.mfile_savegrp, False)
            self.mfile.Enable(self.mfile_saveset, False)
            # disable edit->deletes
            self.medit.Enable(self.medit_delegrp, False)
            self.medit.Enable(self.medit_deleset, False)
            # disable buttons
            for bi in butid:
                self.get_obj_by_id(bi).Enable(False)
            # disable control menu items
            for mi in self.mctrl.GetMenuItems():
                mi.Enable(False)

    def on_media_finish(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_FINISHED"))

        self.set_medi_state(wx.media.MEDIASTATE_STOPPED)

        dn, med, des, com, err, lth = self.get_reslist_item_tup()

        nm = _T(des or dn or med)
        self.set_statusbar(
            _("Finished '{}'").format(nm), 0, notify = True)
        self.set_statusbar(_T("  "), 1)

        self.set_play_label()
        self.pause_ticks = -1

        if self.loop_track:
            wx.CallAfter(self.cmd_on_play)
            return

        self.unload_media()
        self.in_play = False
        self.in_stop = False

        if self.adv_track:
            self.cmd_on_next()


    def on_media_state(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_STATECHANGED"))

        ln, sz = self.check_set_media_meta()
        if ln == 0:
            ln, sz = self.check_set_media_meta(True)
            if ln < 1:
                wx.CallAfter(self.check_set_media_meta, True)

        if self.getdbg():
            st = self.medi.GetState()
            if st == wx.media.MEDIASTATE_PLAYING:
                m = "MEDIASTATE_PLAYING"
            elif st == wx.media.MEDIASTATE_PAUSED:
                m = "MEDIASTATE_PAUSED"
            elif st == wx.media.MEDIASTATE_STOPPED:
                m = "MEDIASTATE_STOPPED"
            else:
                m = "STATE UNKNOWN: value {}".format(st)
            self.prdbg(_T("CURRENT STATE: {}").format(_T(m)))
            ln = self.get_time_str(tm = ln, wm = True)
            self.prdbg(_T("Media length: {}").format(ln))
            self.prdbg(_T("Media size: {}x{} (chg state)").format(
                            sz.width, sz.height))

        self.mpris2_signal_emit(_T("PlaybackStatus"))

    def on_media_play(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_PLAY"))

        self.set_medi_state(wx.media.MEDIASTATE_PLAYING)

        self.set_pause_label()
        self.in_play = True
        self.in_stop = False
        self.load_ok = True

        dn, med, des, com, err, lth = self.get_reslist_item_tup()
        nm = _T(des or dn or med)

        # pause hack -- at least w/ gstreamer, this pause
        # call must happen before the Seek() (below), else
        # the pause event might not be delivered, and we do
        # not know our state
        if self.seek_and_pause_hack > 0:
            self.medi.Pause()

        if self.seek_and_play_hack >= 0:
            seek_pos = self.seek_and_play_hack
            self.seek_and_play_hack = -1
            if seek_pos > 0:
                self.medi.Seek(seek_pos)
                self.pos_seek_paused = -200
            self.prdbg(_T("EVT_MEDIA_PLAY - seek_and_play_hack"))

            if self.seek_and_pause_hack > 0:
                seek_op = self.seek_and_pause_hack
                self.seek_and_pause_hack = 0
                self.prdbg(
                 _T("-- seek_and_pause_hack == {} ({})").format(
                 "STOP" if (seek_op == 2) else "pause", seek_op)
                 )

                # possibly pause, but only if the seek position was
                # not zero, for if it was the resourse is probably
                # an unbounded stream and pausing for more than a
                # couple of seconds might (gstreamer) send an unwanted
                # stop event; also, there would be little reason not
                # to simply stop since position needn't be preserved
                if seek_op == 1 and seek_pos > 0:
                    #XXX commented pause, see '# pause hack' above
                    #self.medi_pause()
                    #wx.CallAfter(self.cmd_on_pause, from_user = True)
                    self.prdbg(_T("HACK: PAUSED pos {}").format(
                                                seek_pos))
                elif seek_op == 2 or seek_pos <= 0:
                    self.in_stop = True
                    self.in_play = False
                    wx.CallAfter(self.cmd_on_stop, from_user = True)
                    self.prdbg(_T("HACK: STOPPED"))

                self.set_statusbar(_("Ready: '{}'").format(nm), 0)
                return

        ln, sz = self.check_set_media_meta()
        if sz.width == 0 or sz.height == 0 or ln == 0:
            ln, sz = self.check_set_media_meta(True)
            if ln < 1:
                wx.CallAfter(self.check_set_media_meta, True)

        self.set_statusbar(
            _("Playing '{}'").format(nm), 0, notify = True)
        self.set_statusbar(self.get_time_str(tm = ln), 1)

        wx.CallAfter(self.with_media_loaded)

    def on_media_pause(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_PAUSE"))

        self.set_medi_state(wx.media.MEDIASTATE_PAUSED)

        self.set_play_label()

        ln, sz = self.check_set_media_meta()
        if sz.width == 0 or sz.height == 0 or ln == 0:
            ln, sz = self.check_set_media_meta(True)
            if ln < 1:
                wx.CallAfter(self.check_set_media_meta, True)
        self.slider_setup()

        dn, med, des, com, err, lth = self.get_reslist_item_tup()

        nm = _T(des or dn or med)
        self.set_statusbar(
            _("Paused '{}'").format(nm), 0, notify = True)
        tm = self.media_meta[0]
        self.set_statusbar(self.get_time_str(tm = tm), 1)

        # pause duration limit hack
        if self.media_current_is_uri:
            # contains length, size in tuple (l, wxSize)
            stream = self.media_meta[0] == 0

            self.pause_ticks = self.get_secs()
            # long pause seek position, from MediaCtrl.Tell() --
            # 0 for streams
            self.pause_seek_pos = 0 if stream else self.medi.Tell()

            self.prdbg(_T("on_media_pause: pos == {}, ticks {}").format(
                            self.pause_seek_pos, self.pause_ticks))


    def on_media_stop(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_STOP"))

        self.set_medi_state(wx.media.MEDIASTATE_STOPPED)

        if not self.in_stop:
            self.prdbg(_T(
                "on_media_stop: not self.in_stop -- in_play {}").format(
                self.in_play))
            event.Veto()
            event.Skip()
            if self.in_play:
                if self.pause_ticks == -2:
                    # MSW, spurious stop event
                    self.prdbg(_T("on_media_stop: MSW stop; ticks -2"))
                    self.pause_ticks = -1
            return

        # pause duration limit hack invalid now
        self.pause_ticks = -1

        # should status msg show notification message?
        #try:
        #    nmsg = True if self.pending_notification is None else False
        #except:
        #    nmsg = True
        # No, with simplistic notification daemons (e.g. notify-osd,
        # Ubuntu) we are putting up too many, with each displayed
        # too long making a backlog -- so no notify for stop
        nmsg = False

        # TODO: cannot use current index in a message here, because
        # if a next/previous op led us here it has been adjusted
        # already and the message is wrong -- so the todo is:
        # fix this.
        if False:
            dn, med, des, com, err, lth = self.get_reslist_item_tup()

            nm = _T(des or dn or med)
            self.prdbg(_T("on_media_stop: user stop {}").format(nm))

            self.set_statusbar(
                _("Stopped '{}'").format(des or med), 0, notify=nmsg)
        else:
            self.prdbg(_T("on_media_stop: user stop medium"))
            self.set_statusbar(_("Stopped medium"), 0, notify=nmsg)

        self.set_statusbar(_T("  "), 1)

        self.in_play = False
        self.in_stop = True
        self.set_play_label()

        # at least w/ gtk/gstreamer stop(), with or without seek(0),
        # will not work as expected[*] with an unbounded stream, but
        # instead on play() will play buffered data no matter how old
        # until exhausted, then issue a 'finished' event
        # [*] expectation is that on stop() will discard buffer and
        # on play() will restart the unbounded stream as if first
        # connecting -- behavior with bounded media works as
        # expected since seek(0) is effective and subsequent play()
        # is from the start;
        # so . . .
        if self.medi.Length() > 0:
            # bounded, seek to 0 (start)
            self.medi.Seek(0)
            self.mpris2_signal_emit(_T("Seeked"))
        else:
            # unbounded, force backend to disassociate from current
            # resource; if a play() op follows the resource will be
            # loaded again, fresh and new and shiny -- note force =
            # True; else, only flags are set but backend is not
            # forced to unload (which is another hack)
            self.unload_media(force = False)
        self.pos_sld.SetValue(0)

    # old wxpython sample comment says that MSW backends do not
    # post loaded event -- I have not observed that with MSW 7 and
    # wxwidgets 3.x
    def on_media_loaded(self, event):
        self.prdbg(_T("Media event: EVT_MEDIA_LOADED"))

        self.set_medi_state(wx.media.MEDIASTATE_STOPPED)
        self.canseek = None
        self.lastlen = None

        call_me = self.load_func
        self.load_func = None

        ln, sz = self.check_set_media_meta()
        if sz.width == 0 or sz.height == 0 or ln == 0:
            ln, sz = self.check_set_media_meta(True)
        dn, med, des, com, err, lth = self.get_reslist_item_tup()

        nm = _T(des or dn or med)
        self.set_statusbar(_("Loaded resource '{}'").format(nm), 0)

        # pause duration limit hack media (re)load? then seek and play
        if self.pause_ticks == 0:
            # MSW spurious stop event: will note -2 and refrain
            # from issuing an extra play() -- this is fragile --
            # do all MSW backends always send spurious stop event?
            self.pause_ticks = -2 if _in_msw else -1
            self.prdbg(_T("loaded, duration hack, SEEK({})").format(
                        self.pause_seek_pos))

            self._seek_and_play(whence = self.pause_seek_pos)
        else:
            self.pause_ticks = -1
            self.metadata_check()
            wx.CallAfter(self.with_media_loaded, call_me = call_me)

    def with_media_loaded(self, event = None, call_me = None):
        ln, sz = self.check_set_media_meta()
        if sz.width == 0 or sz.height == 0 or ln == 0:
            ln, sz = self.check_set_media_meta(True)

        self.prdbg(_T("Media length: {}").format(
                        self.get_time_str(tm = ln, wm = True)))
        self.prdbg(_T("Media size: {}x{} (in_play {})").format(
                        sz.width, sz.height, self.in_play))

        self.do_volume()

        if self.pos_seek_paused <= 0:
            self.slider_setup()

        if ln > 0:
            self.set_statusbar(self.get_time_str(tm = ln), 1)

        if call_me:
            wx.CallAfter(call_me)
        elif not self.in_play:
            self.medi_pause()

            self.prdbg(_T("with_media_loaded: call after Play()"))
            wx.CallAfter(self.medi.Play)
            self.focus_medi_opt()

        self.mpris2_signal_emit(_T("Metadata"))
        self.mpris2_signal_emit(_T("CanSeek"))
        self.mpris_sendsignal_check(force=True)

    def slider_setup(self, pos = None):
        ln = self.medi.Length()
        if not ln and pos == None:
            pos = 0
        psf = float(self.pos_mul)
        rng = int(psf * ln + 0.5)
        tel = int(psf * self.medi.Tell() + 0.5)
        cur = tel if (pos == None) else pos
        self.pos_sld.SetRange(0, rng)
        self.pos_sld.SetValue(cur)
        if _in_msw:
            # MSW: if range has increased so that another decimal
            # digit is required, the number is clipped -- trying
            # to find a workaround here . . .
            if False:
                self.pos_sld.Layout()
                w, h = self.pos_sld.GetSize()
                self.pos_sld.SetSize((w - 1, h - 1))
                self.pos_sld.Refresh()
                self.pos_sld.SetSize((w, h))
                self.pos_sld.Refresh(True)
            else:
                self.pos_sld.SendSizeEvent()
                self.pos_sld.Layout()
                self.pos_sld.Refresh(True)

        if ln > 0:
            self.set_statusbar(self.get_time_str(tm = ln), 1)

        return ln

    def unload_media(self, force = False):
        self.load_ok = False

        if not self.medi:
            return False

        self.media_meta = (0, wx.Size(0, 0))

        if force:
            self.set_medi_state("unloaded force")
            # MS seems to have trouble with 'nul', OTOH gstreamer
            # (GTK) seems to ignore empty string
            dn = _T('') if _in_msw else os.devnull
            #dn = _T('')

            ret = bool(self.medi.Load(dn))
            #ret = False if _in_gtk else bool(self.medi.Load(dn))

            self.msg_grep = None
            return ret
        else:
            self.set_medi_state("unloaded easy")
            return True

    def load_media(self, med = None):
        dn, med, des, com, err, lth = self.get_reslist_item_tup()

        if not med:
            return False

        s = med
        if not s:
            return False

        ret = False

        r = re.match(_T(r'^([A-Za-z]+)://.*/.*$'), _T(s))
        if r:
            # URI form
            self.media_current_is_uri = True
            # TODO: user specified proxy(s) for protocol set(s)
            prx = None
            try:
                prx = self.proxies[r.group(1).lower()]
            except:
                prx = None

            # load with proxy has been failing, silently
            if prx and self.can_use_proxy:
                ret = bool(self.medi.LoadURIWithProxy(s, prx))
            else:
                ret = bool(self.medi.LoadURI(s))
        else:
            self.media_current_is_uri = False
            # assume local file
            # wxPython bug: tries to decode arg with utf-8 codec,
            # ignoring that, at least on Unix, fs paths/names are
            # just bytes; therefore exception is raised when name
            # is iso8859-* -- try conversion, but that will almost
            # certainly fail to find fs resource, even if exception
            # is quashed
            failed = True
            #nl = [s, _T(s)]
            nl = [s]
            for i, v in enumerate(nl):
                try:
                    t = bool(self.medi.Load(v))
                    if t:
                        failed = False
                        break
                except Exception as e:
                    self.prdbg(_T(
                        "'{}' on load {} of '{}' due to charset bug"
                        ).format(e, i, _T(v)))
                except:
                    self.prdbg(_T(
                        "fail on load {} of '{}' due to charset bug"
                        ).format(i, _T(v)))
            ret = not failed

        if self.msg_grep:
            self.err_msg(_T("IN load_media: {}").format(self.msg_grep))
            self.load_ok = False
            self.msg_grep = None
        else:
            self.load_ok = ret

        if self.load_ok:
            wx.CallAfter(self.check_set_media_meta, True)

        return self.load_ok

    def check_set_media_meta(self, do_set = False, only_len = False):
        if not (self.medi and self.load_ok):
            return (0, wx.Size(0, 0))

        if do_set:
            if not only_len:
                self.medi.SetInitialSize()
                ln = self.medi.Length()
                sz = self.medi.GetBestSize()
            else:
                ln = self.medi.Length()
                sz = self.media_meta[1]

            self.media_meta = (ln, sz)

            it = self.get_reslist_item()
            if it:
                it.length = int(ln) if (ln > 0) else -1
                it.comment = _T("{}x{}").format(sz.width, sz.height)

            self.player_panel.set_meta(sz, ln)
            if not only_len:
                self.player_panel.do_new_size()

        return self.media_meta

    def on_position(self, event):
        if not self.medi:
            return

        if self.in_play:
            pval = 2
            if isinstance(event, int):
                pval = event

            if self.pos_seek_state == None:
                st = self.get_medi_state()
                if st == wx.media.MEDIASTATE_PLAYING:
                    self.pos_seek_state = st
                    self.medi.Pause()
            self.pos_seek_paused = pval

    # on_volume is only called when slider widget is manipulated by
    # user, not when slider.SetValue() is used, so there is no loop
    # entered when self.do_volume() uses slider.SetValue()
    def on_volume(self, event):
        self.do_volume(event.GetPosition())
        self.focus_medi_opt()


    def do_mouse_tick_check(self):
        prec = self.player_panel.GetScreenRect()
        mpos = wx.GetMousePosition()
        x, y = self.fs_mouse_pos

        isin = prec.Contains(mpos)

        if isin:
            self.medi_has_mouse = True
            if x != mpos.x or y != mpos.y:
                self.medi_tick = self.medi_tick_span

        else:
            self.medi_has_mouse = False
            self.medi_tick = 0

        self.fs_mouse_pos = (mpos.x, mpos.y)


    def do_fullscreen_label(self, on = False):
        btn = self.get_obj_by_id(self.id_fullscreen)

        if on:
            btn.SetLabel(self.label_fullscreen_on)
        else:
            btn.SetLabel(self.label_fullscreen_off)

        btn.SetMinSize(btn.GetBestSize())
        self.btn_panel.get_sizer().Layout()

    def do_fullscreen(self, off = False):
        # if not off, then toggle, else set off
        if off == False:
            b = self.is_fullscreen()
            if not b:
                # Did go fullscreen, so make sure we are at top of
                # z-order -- we probably already are if we're here
                # from a button or menu; but might not be if this
                # is initiated programmatically, e.g. MPRIS
                self.Raise()
                self.do_fullscreen_label(False)
                # let it show at 1st, ticker will hide
                #self.show_wnd_obj(self.hiders["vszr"], False)
                self.toolbar2.Show(False)
                self.medi_tick = self.medi_tick_span


            def _aft(self, b):
                self.ShowFullScreen(not b)
                if b:
                    self.do_fullscreen_label(True)
                    self.show_wnd_obj(self.hiders["vszr"], True)
                    self.toolbar2.Show(True)
                    self.Layout()
                    self.SetCursor(select_cursor(wx.CURSOR_DEFAULT))
                    self.medi_tick = 0
                else:
                    # Did go fullscreen, so make sure we are at top of
                    # z-order -- we probably already are if we're here
                    # from a button or menu; but might not be if this
                    # is initiated programmatically, e.g. MPRIS
                    wx.CallAfter(self.Raise)


            wx.CallAfter(_aft, self, b)
            wx.GetApp().do_screensave(b)
            self.mpris2_signal_emit(_T("Fullscreen"))
        elif off == True:
            if self.is_fullscreen():
                self.ShowFullScreen(False)
                self.do_fullscreen_label(True)
                self.show_wnd_obj(self.hiders["vszr"], True)
                self.toolbar2.Show(True)
                self.Layout()
                self.SetCursor(select_cursor(wx.CURSOR_DEFAULT))
                self.medi_tick = 0
                wx.GetApp().do_screensave(True)
                self.mpris2_signal_emit(_T("Fullscreen"))

    def do_group_items_desc_from_tags(self, grp = None):
        if grp == None:
            grp = self.get_res_group_current()

        if not grp:
            return False

        tlst, tcnt = get_tags_for_avitems(grp.data)

        if not tcnt:
            return False

        self.push_undo()

        alst = []
        cnt  = 0
        tlen = max(2, len(str(len(tlst))))
        na   = _("[not tagged]")

        for i, t in enumerate(tlst):
            if not t:
                if not na in alst:
                    alst.append(na)
                continue
            laa = []
            ta = t.artist
            if ta:
                laa.append(ta)
            ta = t.album
            if ta:
                laa.append(ta)
            if laa:
                aa = _T(": ").join(laa)
                if not aa in alst:
                    alst.append(aa)
            tit = t.processed_title(tlen)
            if tit:
                grp.data[i].desc = tit
                cnt += 1

        if not cnt:
            return False

        if alst:
            grp.desc = _T(" -- ").join(alst)

        self.set_tb_combos()
        self.mpris2_signal_emit(_T("Metadata"))

        return True


    def push_undo(self, do_copy = True):
        self.push_undoredo(is_redo = False, do_copy = do_copy)

    def push_redo(self, do_copy = True):
        self.push_undoredo(is_redo = True, do_copy = do_copy)

    def push_undoredo(self, is_redo = False, do_copy = True):
        it = UndoItem(self.reslist)
        it.media_indice = self.media_indice
        it.group_indice = self.group_indice
        it.media_state  = self.get_medi_state()
        it.media_len    = self.medi.Length()
        it.media_pos    = 0 if (it.media_len < 1) else self.medi.Tell()

        if is_redo:
            self.undo_redo.push_redo(it)
        else:
            self.undo_redo.push_undo(it)

    def cancel_undo(self, count = 1):
        while count > 0:
            count -= 1
            self.undo_redo.pop_undo()

    def cancel_redo(self, count = 1):
        while count > 0:
            count -= 1
            self.undo_redo.pop_redo()

    def do_undo(self):
        self.push_redo(do_copy = False)
        self.do_undoredo_item(self.undo_redo.pop_undo())

    def do_redo(self):
        self.push_undo(do_copy = False)
        self.do_undoredo_item(self.undo_redo.pop_redo())

    def do_undoredo_item(self, it):
        if not it:
            return

        self.cmd_on_stop(from_user = True)
        self.unload_media()

        self.reslist = it.data
        self.media_indice = it.media_indice
        self.group_indice = it.group_indice
        self.set_tb_combos()

        st = it.media_state

        if st == wx.media.MEDIASTATE_PLAYING:
            self.load_func = lambda: self._seek_and_play(it.media_pos)
        elif st == wx.media.MEDIASTATE_PAUSED:
            self.load_func = lambda: self._seek_and_pause(it.media_pos)
        else:
            self.load_func = lambda: self._seek_and_stop(it.media_pos)

        self.load_media()

    def delete_group(self, group_index = None):
        if not self.reslist:
            return

        self.push_undo(do_copy = True)

        self.cmd_on_stop(from_user = True)
        self.unload_media(force = False)

        def _sub_del_grp(self, do_play):
            l = 0
            indice = self.media_indice
            for i, g in enumerate(self.reslist):
                gl = g.get_len() + l
                if indice < gl:
                    if i > 0 and (i + 1) == len(self.reslist):
                        l -= self.reslist[-2].get_len()
                    self.media_indice = l
                    del self.reslist[i]
                    self.load_media()
                    if do_play:
                        wx.CallAfter(self.cmd_on_play)
                    break
                l = gl
            self.set_tb_combos()

            self.mpris2_signal_emit(_T("Metadata"))
            self.mpris_sendsignal_check()

        wx.CallAfter(_sub_del_grp, self, self.in_play)

    def delete_set(self):
        if not self.reslist:
            return

        self.push_undo(do_copy = False)

        self.cmd_on_stop(from_user = True)
        self.unload_media(force = False)

        self.reslist = []
        self.media_indice = 0
        self.set_tb_combos()

    def do_seek_back(self):
        self.do_seek_millisecs(-1000)

    def do_seek_forward(self):
        self.do_seek_millisecs(1000)

    def do_seek_millisecs(self, ms, whence = wx.FromCurrent):
        # 'whence' may be wx.FromStart, wx.FromCurrent, or wx.FromEnd
        try:
            if ms >= 0:
                cur = self.pos_sld.GetValue()
                off = long(float(self.pos_mul) * ms + 0.5)
                self.pos_sld.SetValue(cur + off)
                self.on_position(None)
            self.medi.Seek(ms, whence)
            #if ms < 0:
            #    cur = self.pos_sld.GetValue()
            #    off = long(float(self.pos_mul) * ms + 0.5)
            #    self.pos_sld.SetValue(cur + off)
            #    self.on_position(None)
        except:
            pass

    def do_volume(self, val = None):
        if val == None:
            val = self.vol_cur

        val = max(self.vol_min, min(self.vol_max, val))

        if self.medi:
            d = float(self.vol_max - self.vol_min)
            v = float(val - self.vol_min) / d
            self.medi.SetVolume(v)
            self.mpris2_signal_emit(_T("Volume"))
            if self.in_play:
                val = self.medi.GetVolume()
                val = int(math.floor(val * d + 0.5)) + self.vol_min

        self.vol_sld.SetValue(val)
        self.vol_cur = val

    def inc_volume(self, val = 5):
        ov = self.vol_sld.GetValue()
        m = self.vol_sld.GetMax()
        v = min(m, ov + val)

        if v != ov:
            self.vol_sld.SetValue(v)
            self.do_volume(v)

    def dec_volume(self, val = 5):
        ov = self.vol_sld.GetValue()
        m = self.vol_sld.GetMin()
        v = max(m, ov - val)

        if v != ov:
            self.vol_sld.SetValue(v)
            self.do_volume(v)


    def do_taskbar_click(self, event = None):
        ismin = self.IsIconized()
        ismax = self.IsMaximized()

        if ismin:
            self.Iconize(False)

        if ismax:
            self.Maximize(False)

        self.Raise()

    def do_filter_msg(self, lvl, msg, evt_time, inverse):
        # TODO: more testing here -- this won't help unless
        # very specific message can be identified; so far it
        # seems that the hoped for messages are not produced,
        # but test more as various bad inputs are found
        if False and lvl == wx.LOG_Error:
            # in spite of the word 'playback', this message is seen
            # when wxMediaCtrl.Load*() fails (even though it might
            # return True!)
            ms  = _T("Media playback error:")
            mt  =  _("Media playback error:")
            mst = _T(msg)
            if msg[:len(mt)] == mt or msg[:len(ms)] == ms:
                self.msg_grep = msg
                self.err_msg(
                    "FRAME do_filter_msg, time {} - msg '{}'".format(
                        evt_time, msg))

    def do_command_button(self, button_id):
        btn = self.get_obj_by_id(button_id)

        if not btn:
            return

        ev = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, button_id)
        wx.PostEvent(btn, ev)

    # play must function as a toggle . . .
    def on_play(self, event):
        # pause duration limit hack
        if self.pause_ticks >= 0:
            tdiff = self.get_secs() - self.pause_ticks
            if tdiff >= self.pause_ticks_interval:
                self.pause_ticks = 0 # expired: tested in stop event
                self.prdbg(_T("on_media_play: pause_ticks == 0"))
                # if medium is an unbounded stream then stop and restart
                if self.medi.Length() < 1:
                    self.prdbg(_T("on_media_play: tick expire stop"))
                    #self.medi.Stop()
                    self.cmd_on_stop()
                    self.unload_media(force = False)
                    self.load_media()
                    return
            else:
                self.pause_ticks = -1 # reset: played in time

        self.cmd_on_play(from_user = True, event = event)

    def cmd_on_play(self, from_user = False, event = None):
        dn, med, des, com, err, lth = self.get_reslist_item_tup()
        res = _T(des or dn or med)

        s0 = _("Playing '{}'").format(res) if med else _(
                "No file or URL resource to play!")

        self.set_statusbar(s0, 0)
        self.set_statusbar(_T("  "), 1)

        if not med:
            return

        self.in_stop = False

        # this block does not actually play/pause because
        # resource has not been loaded yet; moreover the boolean
        # returned from Load() does not guarantee tha media is
        # in fact loadable/playable (but False is bad),
        # so play is not called here but in the load event handler
        if not self.load_ok:
            self.in_play = False

            # hack: it happens that retries after interval can work
            numtry = 7 if self.media_current_is_uri else 2
            intrvl = 100
            itrmul = 2
            while True:
                self.load_media()
                if self.load_ok:
                    break
                numtry -= 1
                if not numtry:
                    break
                self.err_msg(
                    _T("Load {m} failed, retry after {ms}ms").format(
                    m = res, ms = intrvl))
                wx.MilliSleep(intrvl)
                intrvl *= itrmul

            self.player_panel.load_ok = self.load_ok

            if not self.load_ok:
                s0 = _("Failed loading '{}'").format(res)
                s1 = _("failure")
                self.err_msg(s0)
            else:
                s0 = _("Loading '{}' ({})").format(res, _T(med))
                s1 = _("waiting . . .")
                self.prdbg(_T("Success loading '{}'").format(res))

            self.set_statusbar(s0, 0)
            self.set_statusbar(s1, 1)
            return

        # the remainder is a play pause toggle, reached if the media
        # was already loaded
        b = False
        er = _("Failed playing '{}'")
        st = self.get_medi_state()
        if st == wx.media.MEDIASTATE_PLAYING:
            b = self.medi_pause()
            if b:
                s0 = _("Paused in '{}'").format(res)
                s1 = _("waiting . . .")
            else:
                s0 = _("Failure pausing '{}'").format(res)
                s1 = _("pause fail")
                er = _("Failed pausing '{}'")
            self.prdbg(_T("Pause({}) returned {}").format(res, b))
        else:
            b = self.medi.Play()
            if b:
                s0 = _("Playing '{}'").format(res)
                s1 = _("waiting . . .")
            else:
                s0 = _("Failure playing '{}'").format(res)
                s1 = _("play fail")
            self.prdbg(_T("Play({}) returned {}").format(res, b))

        self.set_statusbar(s0, 0)
        self.set_statusbar(s1, 1)

        if not b:
            self.err_msg(er.format(_T(med)))

        # try to keep focus on media control
        self.focus_medi_opt()

    # . . . but pause must only pause
    def on_pause(self, event):
        self.cmd_on_pause(from_user = True, event = event)

    def cmd_on_pause(self, from_user = False, event = None):
        if not self.load_ok:
            return

        st = self.get_medi_state()
        if st == wx.media.MEDIASTATE_PLAYING:
            self.medi.Pause()

        self.set_play_label()

        self.slider_setup()

        # try to keep focus on media control
        self.focus_medi_opt()

    def on_prev(self, event):
        self.cmd_on_prev(from_user = True, event = event)

    def get_can_do_prev(self):
        return False if self.get_prev_index() is None else True

    def get_prev_index(self):
        l = self.get_reslist_len()
        if not l:
            return None

        ixnew = max(0, self.media_indice - 1)

        if ixnew == self.media_indice:
            return None

        return ixnew

    def cmd_on_prev(self, from_user = False, event = None):
        ixnew = self.get_prev_index()

        if ixnew == None:
            return False

        self.media_indice = ixnew
        self.set_tb_combos()

        st = self.get_medi_state()
        if (st == wx.media.MEDIASTATE_PLAYING or
            st == wx.media.MEDIASTATE_PAUSED):
            wx.CallAfter(self._unload_and_play)
        else:
            self.unload_media()
            wx.CallAfter(self.cmd_on_play)

        return True

    def cmd_first_grp(self):
        gcur = self.get_res_group_current()
        g, i = self.get_first_res_group_with_index()
        if i == None or g == gcur:
            return
        self.media_indice = i + 1
        self.do_command_button(self.id_prev)

    def cmd_prev_grp(self):
        gcur = self.get_res_group_current()
        g, i = self.get_prev_res_group_with_index()
        if i == None or g == gcur:
            return
        self.media_indice = i + 1
        self.do_command_button(self.id_prev)

    def on_next(self, event):
        self.cmd_on_next(from_user = True, event = event)

    def get_can_do_next(self):
        return False if self.get_next_index() is None else True

    def get_next_index(self):
        l = self.get_reslist_len()
        if not l:
            return None

        ixnew = min(l - 1, self.media_indice + 1)

        if ixnew == self.media_indice:
            return None

        return ixnew

    def cmd_on_next(self, from_user = False, event = None):
        ixnew = self.get_next_index()

        if ixnew == None:
            return False

        self.media_indice = ixnew
        self.set_tb_combos()

        st = self.get_medi_state()
        if (st == wx.media.MEDIASTATE_PLAYING or
            st == wx.media.MEDIASTATE_PAUSED):
            wx.CallAfter(self._unload_and_play)
        else:
            self.unload_media()
            wx.CallAfter(self.cmd_on_play)

        return True

    def cmd_last_grp(self):
        gcur = self.get_res_group_current()
        g, i = self.get_last_res_group_with_index()
        if i == None or g == gcur:
            return
        self.media_indice = i - 1
        self.do_command_button(self.id_next)

    def cmd_next_grp(self):
        gcur = self.get_res_group_current()
        g, i = self.get_next_res_group_with_index()
        if i == None or g == gcur:
            return
        self.media_indice = i - 1
        self.do_command_button(self.id_next)

    #delayed set of actions
    def _seek_and_stop(self, whence = 0, from_user = False):
        self.seek_and_pause_hack = 2
        self._seek_and_play(whence = whence, from_user = from_user)

    #delayed set of actions
    def _seek_and_pause(self, whence = 0, from_user = False):
        self.seek_and_pause_hack = 1
        self._seek_and_play(whence = whence, from_user = from_user)

    #delayed set of actions
    def _seek_and_play(self, whence = 0, from_user = False):
        def _sub_seek_and_play(obj, s2, u):
            self.seek_and_play_hack = s2
            self.in_play = True
            obj.cmd_on_play(from_user = u)

        wx.CallAfter(_sub_seek_and_play, self, whence, from_user)

    #delayed set of actions
    def _unload_and_play(self):
        def _sub_unload_and_play(obj):
            obj.load_ok = False
            obj.cmd_on_play()

        #self.prdbg(_T("IN _unload_and_play()"))
        self.medi.Stop()
        self.unload_media(force = False)
        self.in_stop = True
        self.in_play = False
        self.set_play_label()
        wx.CallAfter(_sub_unload_and_play, self)

    def on_stop(self, event):
        self.cmd_on_stop(from_user = True, event = event)

    def cmd_on_stop(self, from_user = False, event = None):
        if not self.load_ok:
            return

        if from_user:
            self.in_stop = True
            self.in_play = False
            self.set_play_label()

        st = self.get_medi_state()
        if st != wx.media.MEDIASTATE_STOPPED:
            self.medi.Stop()

        # try to keep focus on media control
        self.focus_medi_opt()

    def do_setwname(self):
        if self.tittime > 0:
            return

        self.tittime = 2

        t = self.GetTitle()
        self.orig_title = t

        m = _T("{p} {t}").format(p=os.getpid(), t=t)
        self.tmp_title = m
        self.SetTitle(m)

    if _in_msw:
        def register_ms_hotkeys(self, reg = True):
            if self.register_hotkey_done and reg:
                return

            if reg:
                # no return check: they work, or they don't
                self.RegisterHotKey(
                    self.hotk_id_play, 0, self.msvk_id_play)
                self.RegisterHotKey(
                    self.hotk_id_stop, 0, self.msvk_id_stop)
                self.RegisterHotKey(
                    self.hotk_id_next, 0, self.msvk_id_next)
                self.RegisterHotKey(
                    self.hotk_id_prev, 0, self.msvk_id_prev)
            else:
                self.UnregisterHotKey(self.hotk_id_play)
                self.UnregisterHotKey(self.hotk_id_stop)
                self.UnregisterHotKey(self.hotk_id_next)
                self.UnregisterHotKey(self.hotk_id_prev)

            self.register_hotkey_done = reg
    else: #msw
        def register_ms_hotkeys(self, reg = True):
            self.register_hotkey_done = True

    def xhelper_ready(self, xhelper):
        self.xhelper = xhelper
        self.do_setwname_done = False

        self.mpris = (self.xhelper.get_mpris_pipe_obj() != None)
        if self.mpris and wx.GetApp().should_do_mpris():
            self.xhelper.mpris_on()

    def do_time_medi(self, timer):
        t = self.medi_tick

        if t <= 0:
            self.do_mouse_tick_check()
            t = self.medi_tick

        if t < 0:
            return

        self.medi_tick -= 1

        back = self.backpanel

        if t == self.medi_tick_span or not self.medi_has_mouse:
            if self.is_fullscreen():
                self.show_wnd_obj(self.hiders["vszr"], True)

            self.SetCursor(select_cursor(wx.CURSOR_DEFAULT))
        elif t == 0:
            if self.is_fullscreen():
                self.show_wnd_obj(self.hiders["vszr"], False)

            self.SetCursor(select_cursor(wx.CURSOR_BLANK))


    def mpris_seek_method(self, val, is_seek = False):
        if not self.load_ok:
            return

        ln = self.medi.Length()
        if ln < 1:
            return

        v = long(val) / 1000 # value from MPRIS2 is in usecs
        if is_seek:
            # this was MPRIS2.Playlist Seek method, not SetPosition
            v += ln
        v = min(ln, max(0, v))
        do_seek = (self.mpris_seek < 0)
        self.mpris_seek = v

        if True or self.pos_seek_paused <= 0:
            cur = long(float(self.pos_mul) * v + 0.5)
            self.pos_sld.SetValue(cur)
            self.on_position(None)
            if do_seek:
                self.medi.Seek(v)

    def do_timep(self, timer):
        # at some interval, do config save as needed
        if timer:
            try:
                # this count is not set in init; hence, the try block
                cnt = self.autosave_count
                self.autosave_count += 1
                itv = timer.GetInterval() or 1000
                sec = 30000 / itv # 30 secs adjusted for interval
                m = cnt % sec
                if m == 0:
                    self.save_config_and_state()
            except:
                # add this member
                self.autosave_count = 1
        else:
            #self.err_msg(_T("do_timep: NO event"))
            pass

        # test a member that does not exist _unless_
        # the App object sets it, which means close up
        # shop (e.g. exit signal was caught)
        try:
            if self._quit_signal != 0:
                b = False if (self._quit_signal < -1) else True
                self._quit_signal = 0
                wx.CallAfter(self.Close, b)
                self.prdbg("SIGNAL NUMBER {}".format(self._quit_signal))
        except AttributeError:
            self._quit_signal = 0
        except:
            pass

        # show notification popup messages
        wx.CallAfter(self._show_notification_message)

        if self.pos_seek_paused <= 0:
            # unfortunately, it proves necessary to call
            # check_set_media_meta(True) and slider_setup()
            # repeatedly at this interval due to the fact that
            # the backend must estimate media length for some
            # formats (think vbr mp3), and it cannot reliably be
            # determined when the backend is ready to provide
            # a non-zero value (much less an accurate value, as
            # the media.Length() changes over the course of
            # playing as it converges on accuracy); note also
            # that the test for zero Length() is the only means
            # of detecting whether a stream is bounded or not,
            # so false 0 values are really intolerable -- sadly,
            # for the most part in most formats these repeated
            # calls are a waste
            ln, sz = self.check_set_media_meta(True, True)
            self.slider_setup()

            bounded = (not ln < 1)
            if self.medi and self.load_ok:
                ms = self.medi.Tell()
                if bounded:
                    if self.mpris_seek >= 0:
                        ms = self.mpris_seek
                    cur = long(float(self.pos_mul) * ms + 0.5)
                    self.pos_sld.SetValue(cur)
                elif self.in_play:
                    self.set_statusbar(self.get_time_str(tm = ms), 1)
            self.focus_medi_opt()
            if self.pos_seek_paused == -200:
                self.pos_seek_paused = 2
        else:
            self.pos_seek_paused -= 1
            if self.pos_seek_paused == 0:
                if self.pos_seek_state == wx.media.MEDIASTATE_PLAYING:
                    self.medi.Play()
                self.pos_seek_state = None

                self.mpris2_signal_emit(_T("Seeked"))
                self.mpris_seek = -1
                #XXX this might be an oppotune time for:
                #self.config_wr()
            else:
                def _sk_mse(self, v, sig):
                    self.medi.Seek(v)
                    wx.CallAfter(self.mpris2_signal_emit, sig)
                v = self.pos_sld.GetValue()
                v = long(
                    float(v - self.pos_sld.GetMin()) / self.pos_mul)
                wx.CallAfter(_sk_mse, self, v, _T("Seeked"))
                #wx.CallAfter(self.medi.Seek, v)

        if self.tittime > 0:
            if self.tittime == 3:
                self.prdbg(_T("do_timep {}").format(self.tittime))
            elif self.tittime == 2:
                wx.GetApp().do_setwname(self.tmp_title)
                self.prdbg(_T("do_timep {}").format(self.tittime))
            elif self.tittime == 1:
                self.SetTitle(self.orig_title)
                self.prdbg(_T("do_timep {}").format(self.tittime))

            self.tittime -= 1

        if _in_xws:
            # timer checks for state changes for mpris2
            self.mpris_sendsignal_check()


    def get_medi_state(self):
        # Incredibly, under msw self.medi.GetState() will return
        # *incorrect values* for some but not all unbounded streams,
        # although not consistently. Sigh. Event delivery appears
        # to be more reliable, so set state in event handlers, and
        # use self.get_medi_state() wherever self.medi.GetState()
        # had been used.
        # msw only for now.
        #XXX testing only (maybe): use self.medi_state unconditionally
        return self.medi_state
        #return self.medi_state if _in_msw else self.medi.GetState()

    def set_medi_state(self, state):
        self.medi_state = state

    def get_playback_state_string(self):
        st = self.get_medi_state()
        if st == wx.media.MEDIASTATE_PLAYING:
            return _T("Playing")
        elif st == wx.media.MEDIASTATE_PAUSED:
            return _T("Paused")
        else:
            return _T("Stopped")

    def medi_pause(self):
        # see comment at get_medi_state -- in addition to that pause
        # might become ineffectve
        #XXX testing only (maybe): use workaround unconditionally
        if True or _in_msw:
            st = self.get_medi_state()
            ub = (self.medi.Length() < 1)
            if ub and st == wx.media.MEDIASTATE_PLAYING:
                if st != self.medi.GetState():
                    self.prdbg(_T("medi_pause: MEDI.GetState() bug!!!"))
                    # stop
                    wx.CallAfter(self.do_command_button, self.id_stop)
                    return True

        return self.medi.Pause()

    def get_identity(self):
        t = wx.GetApp().get_prog_name()
        m = _T("{n} {v}").format(n = t, v = version_string)
        return m

    def get_reslist(self):
        return self.reslist

    def get_config(self):
        try:
            return self.config
        except AttributeError:
            self.config = wx.GetApp().get_config()
        return self.config

    def config_rd(self, config = None):
        if not config:
            config = self.get_config()
        if not config:
            return

        self.opt_quit_query = config.ReadBool(
                             _T("do_quitquery"), self.opt_quit_query)
        self.opt_tray_icon  = config.ReadBool(
                             _T("use_trayicon"), self.opt_tray_icon)
        self.opt_notifymsg  = config.ReadBool(
                             _T("use_notifymsg"), self.opt_notifymsg)
        self.can_use_proxy  = config.ReadBool(
                             _T("use_proxy"), self.can_use_proxy)

        vmap = {
            _T("resource_index") : 0,     # self.media_indice
            _T("group_index")    : 0,     # group index in self.reslist
            _T("group_desc")     : _T(""),# current AVGroup.desc
            _T("volume")         : 50,    # volume on quit,  0-100
            _T("current_pos")    : -1,    # media.Tell() if bounded
            _T("playing")        : False, # was playing on quit
            _T("loop_play")      : False, # loop current track menu opt
            _T("auto_advance")   : True,  # on track end advance to next
            _T("theme_support")  : True,  # employ theme support
            _T("res_restart")    : True   # on start resume last state
        }

        for k in vmap.keys():
            v = vmap[k]
            if isinstance(v, bool):
                vmap[k] = config.ReadBool(k, v)
            elif isinstance(v, float):
                vmap[k] = config.ReadDouble(k, v)
            elif isinstance(v, int):
                vmap[k] = config.ReadInt(k, v)
            else:
                vmap[k] = config.Read(k, v)

        return vmap


    def config_wr(self, config = None, flush = False):
        if not config:
            config = self.get_config()
        if not config:
            return

        grp, gi = self.get_res_group_with_index(self.media_indice)
        config.WriteInt(_T("resource_index"), self.media_indice)
        gi = self.reslist.index(grp) if grp else 0
        config.WriteInt(_T("group_index"), gi)
        gdesc = grp.desc if (grp and grp.has_unique_desc()) else _T("")
        config.Write(_T("group_desc"), gdesc)
        config.WriteInt(_T("volume"), self.vol_cur)
        st = self.get_medi_state()
        cur = self.medi.Length()
        if (st == wx.media.MEDIASTATE_PLAYING or
            st == wx.media.MEDIASTATE_PAUSED) and cur > 0:
            cur = int(float(self.pos_mul) * self.medi.Tell() + 0.5)
        else:
            cur = -1
        config.WriteInt(_T("current_pos"), cur)
        cur = True if (st == wx.media.MEDIASTATE_PLAYING) else False
        config.WriteBool(_T("playing"), cur)
        cur = self.mctrl.IsChecked(self.mctrl_loop)
        config.WriteBool(_T("loop_play"), cur)
        cur = self.mctrl.IsChecked(self.mctrl_advance)
        config.WriteBool(_T("auto_advance"), cur)
        cur = self.mopts.IsChecked(self.mopts_quitquery)
        config.WriteBool(_T("do_quitquery"), cur)
        cur = self.mopts.IsChecked(self.mopts_trayicon)
        config.WriteBool(_T("use_trayicon"), cur)
        cur = self.mopts.IsChecked(self.mopts_notifymsg)
        config.WriteBool(_T("use_notifymsg"), cur)
        if False:
            cur = self.mopts.IsChecked(self.mopts_proxy)
        else:
            cur = self.can_use_proxy
        config.WriteBool(_T("use_proxy"), cur)
        # theme support: option has no effect in GTK or MSW
        if False:
            cur = self.mopts.IsChecked(self.mopts_themeok)
        else:
            cur = self.theme_support
        config.WriteBool(_T("theme_support"), cur)

        mn = True if self.IsIconized() else False
        config.WriteBool(_T("iconized"),  mn)
        mx = True if self.IsMaximized() else False
        config.WriteBool(_T("maximized"), mx)

        w, h = self.GetSize()
        x, y = self.GetPosition()
        if mn or mx:
            w = self.window_size.width
            h = self.window_size.height
            x = self.window_pos.x
            y = self.window_pos.y
        config.WriteInt(_T("x"), max(x, 0))
        config.WriteInt(_T("y"), max(y, 0))
        config.WriteInt(_T("w"), w)
        config.WriteInt(_T("h"), h)

        self.prdbg(
            _T("config_wr: iconized: {} -- maximized: {}\n"
               "\tposition {} -- size {}").format(
                                            mn, mx, (x, y), (w, h)))

        if flush:
            config.Flush()

    def save_config_and_state(self):
        # use the app class save state method (which calls
        # methods of this class) so that the app may handle
        # its state too
        # use callafter proc so that this may be used in
        # event handlers
        def _real_save_config_and_state(app):
            app.save_self_state()

        wx.CallAfter(_real_save_config_and_state, wx.GetApp())

    def on_quit(self, event):
        self.cmd_on_quit(from_user = True, event = event)

    def cmd_on_quit(self, from_user = False, event = None):
        self.Close(False)

    def on_close(self, event):
        wx.GetApp().set_reslist(self.reslist)

        def _oncl_xitproc():
            self.register_ms_hotkeys(False)
            st = self.get_medi_state()
            if self.load_ok and (
                    st == wx.media.MEDIASTATE_PLAYING or
                    st == wx.media.MEDIASTATE_PAUSED
                    ):
                self.cmd_on_stop()
            self.unload_media(True)
            self.main_timer.Stop()
            self.del_taskbar_object()
            self.Destroy()

        if event.CanVeto():
            self.config_wr(flush = True)

            if self.opt_quit_query:
                rs = wx.MessageBox(
                    _("Do you really want to quit?"),
                    _("Confirm Quit"),
                    wx.YES_NO | wx.ICON_QUESTION, self)

                if rs != wx.YES:
                    event.Veto(True)
                    self.prdbg(_T("DID Veto 1"))
                    return

            #self.Show(False)

            if wx.GetApp().test_exit():
                _oncl_xitproc()
            else:
                event.Veto(True)
                self.prdbg(_T("DID Veto 2"))
        else:
            wx.GetApp().test_exit()
            _oncl_xitproc()
            self.prdbg(_T("DID Destroy"))

    def on_destroy(self, event):
        self.prdbg(_T("CLOSE in on_destroy"))
        self.Close(True)

    def on_fullscreen(self, event):
        self.cmd_on_fullscreen(from_user = True, event = event)

    def cmd_on_fullscreen(self, from_user = False, event = None):
        if not from_user or (event.GetId() == self.id_fullscreen):
            self.do_fullscreen()

    def on_tb2_size(self, event):
        self.do_tb2_size(None)

    def on_show(self, event):
        if not (isinstance(event, wx.ShowEvent)): #and event.GetShow()):
            return

        if _in_msw:
            self.register_ms_hotkeys()

        self.focus_medi_opt()
        self.force_hack(use_hack = True)

    def on_wx_timer(self, event):
        self.cmd_on_wx_timer(from_user = False, event = event)

    def cmd_on_wx_timer(self, from_user = True, event = None):
        iv = event.GetTimer() if (event and not from_user) else None
        self.do_timep(iv)
        self.do_time_medi(iv)

    if _in_msw:
        def on_ms_hotkey(self, event):
            kid = event.GetId()

            if kid == self.hotk_id_play:
                self.do_command_button(self.id_play)
            elif kid == self.hotk_id_pause:
                self.do_command_button(self.id_play)
            elif kid == self.hotk_id_stop:
                self.do_command_button(self.id_stop)
            elif kid == self.hotk_id_next:
                self.do_command_button(self.id_next)
            elif kid == self.hotk_id_prev:
                self.do_command_button(self.id_prev)

    def coproc_queue_get(self):
        if not _in_xws:
            return None

        fifo = self.coproc_fifo
        try:
            r = fifo.get(block = False, timeout = -1)
            fifo.task_done()
            return r
        except q_fifo_empty:
            return None

        return None

    def put_coproc_queue(self, dat = None, discardold = True):
        if not _in_xws:
            return

        self.err_msg('ENTER put_coproc_queue')
        cnt = 0
        fifo = self.coproc_fifo
        while True:
            cnt += 1
            try:
                fifo.put(dat, block = False, timeout = -1)
                break
            except q_fifo_full:
                if discardold:
                    t = fifo.get(block = False, timeout = -1)
                    fifo.task_done()
                    m = _T("put_coproc_queue: FULL: lose old {} [{}]")
                    self.err_msg(m.format(t, cnt))
                else:
                    m = _T("put_coproc_queue: FULL: lose new {} [{}]")
                    self.err_msg(m.format(dat, cnt))
                    break

    def mpris2_signal_emit(self, signal):
        if _in_xws and wx.GetApp().should_do_mpris():
            if not self.mpris:
                return False
            self._x_mpris2_signal_emit(signal)
            return True
        return False

    if _in_xws:
        def _x_mpris2_signal_emit(self, signal):
            if True:
                self.put_coproc_queue(signal)
                self._x_core_mpris2_signal_emit()

        def _x_core_mpris2_signal_emit(self):
            iotup = wx.GetApp().get_mpris2_signal_io()
            if iotup == None:
                return False

            io_ch, io_ctrl = iotup
            if io_ch == None or io_ctrl == None:
                return False

            rd_ch, wr_ch     = io_ch.get_fds()
            rd_ctrl, wr_ctrl = io_ctrl.get_fds()

            ret = True
            fl_wr_ch = fcntl.fcntl(wr_ch, fcntl.F_GETFL)
            if not (fl_wr_ch & os.O_NONBLOCK):
                fcntl.fcntl(wr_ch, fcntl.F_SETFL,
                            fl_wr_ch | os.O_NONBLOCK)

            # tell coproc to set available signal flag
            try:
                fd_write(wr_ch, _T("mpris:signal\n"))
            except (IOError, OSError) as e:
                if e.errno == errno.EAGAIN:
                    self.err_msg(_T("signal_emit: WOULD BLOCK"))
                else:
                    self.err_msg(
                        _T("signal_emit: IO fail '{}'").format(
                            e.strerror))
                ret = False

            if not (fl_wr_ch & os.O_NONBLOCK):
                fcntl.fcntl(wr_ch, fcntl.F_SETFL, fl_wr_ch)

            return ret


    def on_chmsg(self, event):
        t, dat = event.get_content()

        if t == _T("M"):
            if not _in_xws:
                return

            try:
                n = self.mpriscallcnt
                self.mpriscallcnt += 1
            except AttributeError:
                self.mpriscallcnt = 1
                n = 0
            self.err_msg(_T("MPRIS call #{}").format(n))

            if not self.mpris:
                self.err_msg(_T("MPRIS call after mpris error"))
                return

            # the mpris2 handler does not handle exceptions:
            # it's expected that there will only be IO errors
            # on the pipes if helper proc fails (killed, etc.)
            # - any others are internal errors needing debugging -
            # an exception caught here should not be fatal, but
            # MPRIS2 functionality will be kaput
            emsg = None
            try:
                tmh = MPRIS2Handler(self, dat)
                tmh.go()
            except (IOError, OSError) as e:
                emsg = _T(
                    "MPRIS event handling (on_chmsg) error '{}'"
                    ).format(e.strerror)
            except:
                emsg = _T(
                    "MPRIS event handling (on_chmsg) internal error")

            if emsg:
                self.mpris = None
                self.err_msg(emsg)
                try:
                    self.xhelper.mpris_off()
                except:
                    pass

            return

        if t != _T('1'):
            self.prdbg(_T("MSG NOT STDOUT '{}'").format(
                                                _T(dat.rstrip())))
            return

        p = _T("Audio")
        q = _T("dbus:")
        l = len(p)
        pfx = dat[0:l]
        if pfx != p and pfx != q:
            self.prdbg(_T("CHILD STDOUT '{}'").format(_T(dat.rstrip())))
            return

        c = dat[l:].rstrip().lower()

        # might not get pause, if play is a toggle -- see handlers
        if c == _T("play"):
            self.do_command_button(self.id_play)
        elif c == _T("prev") or c == _T("previous"):
            self.do_command_button(self.id_prev)
        elif c == _T("next"):
            self.do_command_button(self.id_next)
        elif c == _T("stop"):
            self.do_command_button(self.id_stop)
        elif c == _T("pause"):
            self.do_command_button(self.id_play)


# The program licence, encoded as:
# CHUNK = 64
# buf = base64.b64encode(zlib.compress(f_in.read(), 9))
# while buf:
#   f_out.write(buf[:CHUNK] + "\n")
#   buf = buf[CHUNK:]
licence_data = """
eNqdXFtz4zayfg7q/AiUX8au4ijx5OwlcSpVsi2PtWvLjiTPxG9LSZDFHYrUEqQ9
+venv24ABHWZ5GxqsxObZKPR6MvXF8x332n65+PoSX8cjAbj/p1+fLq8G15p+ncw
mgzUd/wC/fPJVDYrC/0h0f9oCqPPf/rpXCl9VW62VfayqvXp1Rn98u8/JfxI31TG
6Em5rN/SyuibsikWaU0EEj0s5j3FNP/yk56a9SY3+jFP5ybRkyarjf7xxx8SfVna
Gm/f97X+4cP5+fn78x9/+JvWT5O+0oNXU21L4iKzemOqdVbXZqHrUs+JHZ0WC73I
bF1ls4bI0bszWnqNh5mxSpdLXa/oyzybm8IavSjnzdoUdaLpfT1fpcVLVrzorAb5
oqx1muflm1n0FImD5fFYmXQ9yw0JQE9XxlOyellWek2ca+t3jn8XxmYvhXBYp1/o
l2/pVm/LplJLEtOiXOOJXfH7xDyzQJure1pfbonvoq5SS/zVtBYflilMleb6sZnR
0urObYTYzYraFAtZ6qVJq5R+NryU/tZSeKY8z+/f0ytr8Gkbeg2Lhu3QEniXN0pi
IR6tbizpRg+SyKzqsqY9a+lmk5PwsTjLh8/AdLVEtVryzkYSLHg3abHVJX1T6U1V
vlTpWr+tSlBu6lVZWZLSmvSA3lSNleMjlk4n5dq4z45pZGdz85LUhcQ32yov7Lts
VqXVVh/ZWVbY2qSL3pnWz2Wj52nBm91qYYZF7zi2dIJl2YPWfF6ZQr+RYDcm/QJp
sFQ9JwkegaPKLE1VYTskAXeACXRSbSpan3b4QOQPc2b3dC8+07SGVqhV+ionHGlH
ZDtiMnv86VOnO9ULq4JieyI1eKWldbYEaf2W2dVZEpaivcxN9goiTTUH6QWdTMUC
ezFka7XyH5LS0o/Rp3jHaWpHG+lzUj5NPM6FSxApdGHehF8v9wtRIk/uS1G+BbqL
EjQtKJOcLZ/OtMSntZnXYjrs4SyfSmEiWVYGkppDi6yQJ2HMsoUiZYV7gjBNwabu
FhFKYBwqbb/IoxKnUsFwK96gvNVTU/mmswqZtM3TmonPTVWntGF6Y0MPs1mWZ3Xm
/BAoi0TVwRONJZmAIyf+dbnIllBfFsUNPTBfU3jpxL9xkJxt5iudepGTrFYGZqfo
pzrjHbPP0EtDhHidhvzAS+b0j7QjI1IFCQd+pZUCyxVmpKGrPbEy/nZHnemTLRtY
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
DvxdF+rw33WxX9r8P3d/dKk=
"""

# ----------------------------------------------------------------------
wxmav_16 = PyEmbeddedImage("""
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlw
SFlzAAAHYgAAB2IBOHqZ2wAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoA
AAKOSURBVDiNnZJLaBNRFIbPnbmTzCRNmlfTl7RJSVvE0qZYS7U+CC6kKuLGhboogm5cdCFY
FFFw4wNEkC7sQtCVC0F8YFVaDbQG0aotahFCba1tajSdPCbJzGRmMve6q4ILId/2/P+3+Q+6
eeXsSodHNqACPqftFtzplnNbwgs1lQj4T0ERWzBVAKhUiQAjomIWEQUAUCUCKwYFcwwjL2ab
OZ9d1J0W2UyrLk4qVeMW93cVACCRr7eWKYsErkQoYaCuKqUDAEiaA/9Q6wHPZDuFG9PH+w+2
P/tycvPt+cHHI7sNwrLPDx95+irR5z0TPddPCUL7Q+Pxd8nuhgeHjk2UCUYnxq5FanEmw8zL
IVuTczX18ecmz8Wp4XYbpyobqpOptOJRL8WGeg6EJmYBACzYLP6Saxz5kku5HBtqKeh2fKr1
ToxZLDS7u2vn4rIh4KIugJMvZAPOlcRw9HyfZlpZG1fMWbGupRUnAFAYnT3aNL60q+P01tEn
Pl4SmVXV72/zfV0c7Lo3dmHH9UfLUqNfVL14IRdoHAi9eGlQi1JjTye/SUGPR8inHsYHdkYC
r6cigVicxzSH7o/cuhppn5Kc0Z56tNTsTa62Buwyy1nKAEKJZQEANME0dGyC7tDUjE9Wghvf
z6M90YS55tKR2Ttzl0k0hGmZtazvU11Mk665ORpMiCA5eEb0OtGHjjCovOPPhoZK2uJvMMWG
SHltDQjDrR95LYuEkkgR5KFKLpKC3WBtpTVAoK5nOEOjGNLImNy3DRG7n0z21qHlBhdk3E5G
FaygYQs1WRYhoMCRMmCjDHZZIT4xjwLJnLn9bYphII306b1hRKi/kk+kmIhMJcW/wYTFRQZ0
7v/RfyEmW/wNCi4jLhj6TdwAAAAASUVORK5CYII=
""")
getwxmav_16Data = wxmav_16.GetData
getwxmav_16Image = wxmav_16.GetImage
getwxmav_16Bitmap = wxmav_16.GetBitmap
getwxmav_16Icon = wxmav_16.GetIcon

# ----------------------------------------------------------------------
wxmav_24 = PyEmbeddedImage("""
iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlw
SFlzAAALEwAACxMBAJqcGAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoA
AARzSURBVEiJzVRbbFRVFF3n3HNn6LynM2VmOm0ZWsqbPhCISCEUiWBCIjExIfGdQFQSwwcx
ooGAkZgYEiMmfpgQv/gAjT+IEArUQHhTTGkprQVaOsyrM51p53bmzuvec/xQiNpBjZbE87n3
XmvtvXP2Ivs/2jNulzWBJ/AUTZaZmen6W+tvSr/FyHQKHOpsVRkjvCD+wCumTUQmus5kijwh
nD+iF9M3BaMcjEHPA0R7GCQEwDSJyBSUyYzmIFCakhX/fVUGyhmTiZYDUJySJQQg/3SS8mWM
cAMzUKIeuLI9cD/tty7z9ibeaD4SBIBjP2/0dtxf7ZclnX/27N5uQgU0LpFdnbubUjnnDCMr
aK8s+W7oSN8Ls5ur+pNblx4eeUh8NfyU4/CtF+v1bLFAJaKpp+61z7oRbfEdv7O+jgBqSKkW
n3dtbboRbfFFJj0VEoVKQdQDl98NXHywomYgOcfdHVvsVfJWvSvS4usYXuOnICoFUTMFS/GT
CzuabkSavQtsfRE6rteSTMlkrLOHE5GM1x7Jevnuc+8vraoYTwPALHsoLgSyZ4bbrN8Prl/g
s8RSy3w9QwAwmnWTGSxfjGS8dlUzFITg6r7zOxfFVZd1Y0PnrVbHzRE6nG2wAMCG+h97jFKp
uKvzw2dCSrVzTd2l2wAw3zkUHs1W6p9e3t4mEc4/WPXFmbmVd8MA0JtY6KyxRUd1LtFr4ZaK
Y4MbXJdCy+f6LKOJXSu/vMSEUGlQrXcAwPLq7uGAIxgcTDbUvdl89HQw7TcBQJPndvC9s3vX
KgWbxWLMTB7ufWn+1fDSGgC4kwx46h3BEACcC672Huza1i5RXtqz+uBxIytmZMozNJb3VBml
Qn5J1UDk+caz1zY1dpx+efG3N4fTdVUGqVQ4c7+tejDV0OAxJyJNnv4+I8tnfNZYlFGtNKa6
XAH7SBgATt5buzJbNJk3zztxutXTHRLgqlESWUYI1Ra67/ZQiPyW+cf6APQBBFxQPsc53N8T
XxAIWEN39i869EMjS+ZAdAGzqm0vmWlCdbmdFcr4TFMyDAA+Szy6c8VXFymIAAATE4L0fv32
O/OWjBhJ/xwbPf90HXlQ7UbCVUlSzkpMmuzQZAM4eWiGf/rovARJKwq7MoHK8RS8yaSYHUzw
9gtBURPLhQZqNZJ87eg+5/XW58iYy1eWhHJNeBMheMcS3KKoAIC0zUKjHg+Ju/3lrkwAArXh
IWXd+VNEcyeuSAa9ovyFAnzzqRP6698MgEy1DunjHW30p+blj8PqxvwDUnz16DbWt3Ajxm1V
5YqIJDTuj43AFx+DOZsHlwgUswkRj4fEZtaUt3cihDce0tZdPU6KHVuWCafiJ7fm2sj1Fh/i
bjtNOuyYtNmJarSA0/L7fzQGLwlzdhL2yTR3TiiiNpYSq7qiqA3nyIR1lOSvbGqUoM9+LAGn
hIw5ZKgWCVkzg1wSMOR0mHK6mJmaapK/hzIWZH/ZHQBQLn4lSv1taVn4v0L9nwSYETmlKM2I
PAlyDRPpXwBWW/ifn2GhwQAAAABJRU5ErkJggg==
""")
getwxmav_24Data = wxmav_24.GetData
getwxmav_24Image = wxmav_24.GetImage
getwxmav_24Bitmap = wxmav_24.GetBitmap
getwxmav_24Icon = wxmav_24.GetIcon

# ----------------------------------------------------------------------
wxmav_32 = PyEmbeddedImage("""
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
jBQAAAAASUVORK5CYII=
""")
getwxmav_32Data = wxmav_32.GetData
getwxmav_32Image = wxmav_32.GetImage
getwxmav_32Bitmap = wxmav_32.GetBitmap
getwxmav_32Icon = wxmav_32.GetIcon

# ----------------------------------------------------------------------
wxmav_48 = PyEmbeddedImage("""
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
""")
getwxmav_48Data = wxmav_48.GetData
getwxmav_48Image = wxmav_48.GetImage
getwxmav_48Bitmap = wxmav_48.GetBitmap
getwxmav_48Icon = wxmav_48.GetIcon

# ----------------------------------------------------------------------
wxmav_64 = PyEmbeddedImage("""
iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlw
SFlzAAAdhwAAHYcBj+XxZQAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoA
AA8ISURBVHic7Vt7cJzVdf+d+3370mtXq9XqZVmSLVk2fr+wsQ0BAhM7JC1M0qYlhQT+6GNo
QlsopcAYl9KQaYZpp5k8mg6hZTLQgaakYAjJYMc2GIwf+CFkWX7o/V6tpNXuah/fvff0j9VK
q5VkYxDYxvxm7uzud+6537nnO+fcc+53l7Zv374TwFZ8TAghPu4QlwInTSHEFoMUBOFjzkDN
jUifEpjBlhZ1JgDLJOLNJcP6Wl/4yprFR0RzKFf8utsrJJNlArAMUlxfEJOiMpC8hHLRp3Wj
eqHM33R77FqTNAFIIUgTgUF8VVgABAmDwERkmcxsCWgtUk4sL7VsnxIMkxQzG5YJQBoETWDN
fHUogAimEEJPWIAB1ri8LOATjgesbcQpFyAiSxC0EBNK+MyDGSpl8ZxSgCmgCdBEfLlYwCcK
hlaGgUkXALQisAKLq0IBEFBG2gIAyHELuJxiQDbmOCaQMoh1xjIIJQSumhgAZiXAWmstU0Ew
PfkrMgZ8BOMgUoYYjwFEZBnQSoAV9GXrAucBXzwLsRIERTReCwiCIkCBrhgFfNyYoAyoVBBk
ZklgRUQKoKsiBhCRMgSpSRcgKJBWwJUYAz4CUg99Yhm0TMEKIMVXZBC8GFD6Q5qCZHoZlAKQ
AMuD3WtzGwOL3Nls68uPDy3znYrMNmwo4Tb/t3lr+Uy0u5b/T6dJatZI1Rme5/zxkbtrM+VL
o66wZfTeVf/dcTJQl/de9xpvJi3XPib/8JpXe8D8oeLBa2dv9QeiRQ4AMONmTuuQK+9sxF09
XguwYkA91/D1miO9K6dNpGmwtuOfv/iPx2cb/In9f7X8nc71ldnXPc5Q7J6VL7TOxqfYoMf2
/u2K08GFvpnoDQOLx+5d+Xxrf6TY9rOjdy3LpAmh9Vdrf9vjssUuaLVvd270/tP++9cw0xRl
VTkPtwtmtsT4stA6XOWZaYCTg4uLACFnajvPbPPNNHkAqHF3DM/GBwj5gwP31c42eQAIjnlz
ukbLzWsrjgcE9BQr0lqIYwPLc843PiDkaMKDp/Z/d3X25CucnWPL814/LFKJEMmBpIeG4p6c
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
""")
getwxmav_64Data = wxmav_64.GetData
getwxmav_64Image = wxmav_64.GetImage
getwxmav_64Bitmap = wxmav_64.GetBitmap
getwxmav_64Icon = wxmav_64.GetIcon

if __name__ == '__main__':
    wxmav_main()
