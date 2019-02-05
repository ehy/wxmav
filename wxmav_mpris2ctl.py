#
#  Copyright 2019 Ed Hynan <edhynan@gmail.com>
#
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
#

"""
Implementation of wxmav_control.

File:
    wxmav_mpris2ctl.py -  Imported by wrapper wxmav_control.
"""

#
# initial imports
#

from __future__ import print_function
import sys, os, argparse
from time import sleep

#
# 1st, some Utilities Lite (R)
#


##
# The name of the invoked program, without path.
progname = os.path.split(sys.argv[0])[1]

##
# Small set of encodings to try in handling non-UTF-8 text.
encoding_tuple_small = (
    "ascii", "utf_8", "latin_1", "cp1252"
)


def mkascii(v, repl=0x5F):
    """
    Make a bytes object of only ASCII codes, replacing as needed.

    A last effort to make a displayable string of chars.  This should
    really not be called, and is a matter of form and paranoia.

    Args:
        v:  A textual object (str, unicode, bytes) to process.
        repl: An integer code to replace butes > 127.

    Returns:
        A bytes object containing the result.
    """
    try:
        b = bytearray(os.fsencode(v))
    except:
        try:
            b = bytearray(bytes(v))
        except:
            b = bytearray(v.encode('latin1', 'strict'))

    for i in range(len(b)):
        if b[i] > 0x7F:
            b[i] = repl
    return b.decode('ascii', 'strict')


def mT(s, codeset=encoding_tuple_small):
    """
    Make a text bytes object that may be displayed without exception.

    An effort to make a displayable string of chars.  This might
    use codec conversion to any provided codec, using any of the
    error strategies 'strict', 'replace', or 'backslashreplace';
    or in the common case no value conversion, only conversion
    to bytes object.

    Args:
        s:  A textual object (str, unicode, bytes) to process.
        codeset: Iterable obj. with codec names.

    Returns:
        A bytes object containing the result.
    """
    meths = ( 'strict', 'replace', 'backslashreplace', )

    try:
        ss = os.fsencode(s)
    except AttributeError:
        ss = s

    for meth in meths:
        for c in codeset:
            try:
                ds = ss.decode(c, meth)
                es = ds.encode(c, meth)
                return ds
            except:
                pass

    return mkascii(s)


_PROG = mT(progname)
_EFMT = mT("{}: {}")

def prerr(msg):
    """
    Print to the standard error stream.

    Args:
        msg: A string to print.

    Returns:
        None.
    """
    print(msg, file=sys.stderr)

def errmsg(msg):
    """
    Print message prepended by program name to the standard error.

    Args:
        msg: A string to print.

    Returns:
        None.
    """
    prerr(_EFMT.format(_PROG, mT(msg)))

def errout(msg, code=1):
    """
    Print error message and exit.

    Args:
        msg: A string to print.
        code: Status code passed to exit().

    Returns:
        None.
    """
    errmsg(msg)
    sys.exit(code)

#
# final imports
#

try:
    from mpris2 import get_players_uri, Player, MediaPlayer2
except ImportError as e:
    errout("""
        Failed to import mpris2; try 'pip install --user mpris2;'
        it might be necessary to install the dbus package as well.
        The exception said \"{}\".""".format(e))


#
# global data
#

##
# A boolean to test for release specific differences.
py_v_is_3 = sys.version_info.major >= 3

##
# Object containing parsed arguments, from ArgumentParser.parse_args().
args_obj = None
##
# List of available MPRIS2 players, e.g. "org.mpris.MediaPlayer2.wxmav".
player_uri_all = []
##
# A player 'URI' (actually a bus name); one of player_uri_all.
player_uri = None
##
# The mpris2.player object (org.mpris.MediaPlayer2.Player)
player = None
##
# The mpris2.mediaplayer2 object (org.mpris.MediaPlayer2)
mplayer2 = None

##
# A tuple of MPRIS2 readable properties.
props_readable = (
    "CanQuit",
    "Fullscreen",
    "CanSetFullscreen",
    "CanRaise",
    "HasTrackList",
    "Identity",
    "DesktopEntry",
    "SupportedUriSchemes",
    "SupportedMimeTypes",
    "PlaybackStatus",
    "LoopStatus",
    "Rate",
    "Shuffle",
    "Metadata",
    "Volume",
    "Position",
    "MinimumRate",
    "MaximumRate",
    "CanGoNext",
    "CanGoPrevious",
    "CanPlay",
    "CanPause",
    "CanSeek",
    "CanControl",
)

##
# A tuple of MPRIS2 writable properties.
props_writable = (
    "Fullscreen",
    "LoopStatus",
    "Rate",
    "Shuffle",
    "Volume",
)

#
# global functions
#

def init_mpris2(prog='wxmav'):
    """
    Setup MPRIS2 package objects; make results global.

    Global results are placed in global variables
    'player_uri_all', 'player_uri', 'player', and 'mplayer2'.

    Args:
        prog: A string naming player to select.

    Returns:
        True if player is found else False.
    """
    global player_uri_all
    global player_uri
    global player
    global mplayer2

    player_uri_all = list(get_players_uri())
    u = "org.mpris.MediaPlayer2.{}".format(prog)
    if u in player_uri_all:
        player_uri = u
        player = Player(dbus_interface_info={'dbus_uri': u})
        mplayer2 = MediaPlayer2(dbus_interface_info={'dbus_uri': u})
        return True

    return False


def list_players():
    """
    Print the mpris2 players as found.

    Print short name suitable for use as player argument,
    and full uri in parenthesis.

    Returns:
        Integer number of players found.
    """
    c = 0
    pos = len("org.mpris.MediaPlayer2.")
    player_uris = get_players_uri()
    for uri in player_uris:
        c += 1
        print("{} ({})".format(uri[pos:], uri))

    return c

def invoke_method(meth, *args, **kwargs):
    """
    Call one MPRIS2 method.

    Args:
        meth: A string to select method to be called.
        args: Optional non-keyword arguments the method requires.

    Kwargs:
        kwargs: Optional keyword arguments the method may accept.

    Returns:
        True if the selector 'meth' is known; else False.
    """
    m = meth.lower()

    if m == 'play':
        player.Play(*args, **kwargs)
    elif m == 'pause':
        player.Pause(*args, **kwargs)
    elif m == 'playpause' or m == 'toggle':
        player.PlayPause(*args, **kwargs)
    elif m == 'stop':
        player.Stop(*args, **kwargs)
    elif m == 'previous' or m == 'prev':
        player.Previous(*args, **kwargs)
    elif m == 'next':
        player.Next(*args, **kwargs)
    elif m == 'setposition' or m == 'setpos':
        player.SetPosition(*args, **kwargs)
    elif m == 'seek':
        player.Seek(*args, **kwargs)
    elif m == 'openuri' or m == 'openurl':
        player.OpenUri(*args, **kwargs)
    elif m == 'raise':
        mplayer2.Raise(*args, **kwargs)
    elif m == 'quit':
        mplayer2.Quit(*args, **kwargs)
    else:
        return False

    return True

def invoke_easy_method(ao):
    """
    Call one MPRIS2 method, from options presented to user as 'easy'.

    A small set if MPRIS2 methods take arguments, and these might be
    difficult for user to specify as a positional argument; therefore
    an option '-C' presents an easier way for the user to specify
    the call.  The argument to that option is translated here, and
    invoke_method() is called.

    Args:
        ao: The parsed parameter object.

    Returns:
        Return from invoke_method(), or False for an error herein.
    """
    if not ao.cmd_easy:
        return True

    def _eo(v):
        """Print message 'v' with prefix and exit failure."""
        errout("malformed 'easy' (-C) argument: {}".format(v))


    if ao.cmd_easy[1] != ':':
        _eo(ao.cmd_easy)

    cmd = ao.cmd_easy[:1]
    arg = ao.cmd_easy[2:]

    if not arg:
        _eo(ao.cmd_easy)

    if cmd == 'S':
        try:
            i = int(float(arg) * 1e6) # arg must be in microsecs
        except ValueError:
            errmsg("-C S: arg must be signed decimal seconds")
            _eo(ao.cmd_easy)
        return invoke_method('seek', i)
    elif cmd == 'P':
        try:
            i = int(float(arg) * 1e6) # arg must be in microsecs
        except ValueError:
            errmsg("-C P: arg must be signed decimal seconds")
            _eo(ao.cmd_easy)
        try:
            p = dict(player.Metadata)['mpris:trackid']
        except:
            errmsg("-C P: cannot get Metadata['mpris:trackid']")
            return False
        return invoke_method('setposition', p, i)
    elif cmd == 'F':
        try:
            p = os.path.realpath(arg)
        except:
            errmsg("-C F: arg must be a valid filesystem path string")
            _eo(ao.cmd_easy)
        if not (os.path.isfile(p) or os.path.isdir(p)):
            m = "-C F: arg {} ({}) is not a regular file or dir ({})"
            errmsg(m.format(arg, p, 'trying anyway'))
        return invoke_method('openuri', 'file://{}'.format(p))
    else:
        errmsg("-C command '{}' is not known".format(cmd))
        return False

    return True


def invoke_method_list(methlist):
    """
    Call list of MPRIS2 methods, calling invoke_method() for each.

    If a list of methods should be invoked, such as those received from
    user as postional arguments, then call invoke_method() for each;
    parse arguments to the argument (method) where needed.

    Args:
        methlist: List containing the methods to call.

    Returns:
        Integer -1 if all methods are known, else index of bad method.
    """
    l = len(methlist)
    for i in range(l):
        meth = methlist[i]
        pos = meth.find('=')

        if pos > 0 and pos < len(meth):
            al = meth[(pos+1):]
            meth = meth[:pos]
            # Unfortunately, there is one mpris2 method, SetPosition,
            # that takes more than one arg (2), raising the problem of
            # how user may specify multiple args on command line.
            # simple splitting on, e.g. ',', is problematic because
            # the args that may occur are varied:
            # uri, dbus path, numeric.  Not to mention shell reserved
            # chars.
            # Although ugly, it's safer to refrain from trying to
            # split the arg unless required by the method
            t = meth.lower()
            if t == 'setpos' or t == 'setposition':
                # Since 1st arg is a dbus object path, the sep-char
                # problem remains.
                # try ' ' (space)
                args = al.split(' ')
            else:
                args = [al]
        else:
            args = []

        if not invoke_method(meth, *args):
            return i
        # wxmav currently needs time
        # before a second method will succeed
        if (i + 1) < l:
            sleep(5.0)

    return -1


def print_property(prop):
    """
    Print the current value of a MPRIS2 property.

    Args:
        prop: String name of the property to print.

    Returns:
        None.
    """
    # MediaPlayer2:
    if prop == "CanQuit":
        print("MediaPlayer2: {} == {}".format(
            "CanQuit", mplayer2.CanQuit))
    elif prop == "Fullscreen":
        print("MediaPlayer2: {} == {}".format(
            "Fullscreen", mplayer2.Fullscreen))
    elif prop == "CanSetFullscreen":
        print("MediaPlayer2: {} == {}".format(
            "CanSetFullscreen", mplayer2.CanSetFullscreen))
    elif prop == "CanRaise":
        print("MediaPlayer2: {} == {}".format(
            "CanRaise", mplayer2.CanRaise))
    elif prop == "HasTrackList":
        print("MediaPlayer2: {} == {}".format(
            "HasTrackList", mplayer2.HasTrackList))
    elif prop == "Identity":
        print(mT("MediaPlayer2: {} == {}").format(
            "Identity", mT(mplayer2.Identity)))
    elif prop == "DesktopEntry":
        print(mT("MediaPlayer2: {} == {}").format(
            "DesktopEntry", mT(mplayer2.DesktopEntry)))
    elif prop == "SupportedUriSchemes":
        l = list(mplayer2.SupportedUriSchemes)
        print(mT("MediaPlayer2: {} == {}").format(
            "SupportedUriSchemes", ", ".join([mT(i) for i in l])))
    elif prop == "SupportedMimeTypes":
        l = list(mplayer2.SupportedMimeTypes)
        print(mT("MediaPlayer2: {} == {}").format(
            "SupportedMimeTypes", ", ".join([mT(i) for i in l])))
    # Player:
    elif prop == "PlaybackStatus":
        print(mT("Player: {} == {}").format(
            "PlaybackStatus", mT(player.PlaybackStatus)))
    elif prop == "LoopStatus":
        print(mT("Player: {} == {}").format(
            "LoopStatus", mT(player.LoopStatus)))
    elif prop == "Rate":
        print("Player: {} == {}".format(
            "Rate", player.Rate))
    elif prop == "Shuffle":
        print("Player: {} == {}".format(
            "Shuffle", player.Shuffle))
    elif prop == "Metadata":
        m = dict(player.Metadata)
        print("Player: Metadata:")
        def _mdval(v):
            """Make arg 'v' displayable without exception."""
            try:
                return mT(str(v))
            except:
                try:
                    return mT(bytes(v))
                except:
                    return v
        for k in m.keys():
            if isinstance(m[k], list):
                s = mT(', ').join([_mdval(i) for i in m[k]])
                print(mT("  {} == {}").format(mT(k), s))
            else:
                print(mT("  {} == {}").format(mT(k), _mdval(m[k])))
    elif prop == "Volume":
        print("Player: {} == {}".format(
            "Volume", player.Volume))
    elif prop == "Position":
        print("Player: {} == {}".format(
            "Position", player.Position))
    elif prop == "MinimumRate":
        print("Player: {} == {}".format(
            "MinimumRate", player.MinimumRate))
    elif prop == "MaximumRate":
        print("Player: {} == {}".format(
            "MaximumRate", player.MaximumRate))
    elif prop == "CanGoNext":
        print("Player: {} == {}".format(
            "CanGoNext", player.CanGoNext))
    elif prop == "CanGoPrevious":
        print("Player: {} == {}".format(
            "CanGoPrevious", player.CanGoPrevious))
    elif prop == "CanPlay":
        print("Player: {} == {}".format(
            "CanPlay", player.CanPlay))
    elif prop == "CanPause":
        print("Player: {} == {}".format(
            "CanPause", player.CanPause))
    elif prop == "CanSeek":
        print("Player: {} == {}".format(
            "CanSeek", player.CanSeek))
    elif prop == "CanControl":
        print("Player: {} == {}".format(
            "CanControl", player.CanControl))



def print_properties_many(props):
    """
    Print each of an iterable set of properties.

    Invoke print_property() for each in the given set.

    Args:
        props: Iterable object with the property names for printing.

    Returns:
        None.
    """
    for p in props:
        print_property(p)


def print_properties_all():
    """
    Print all MPRIS2 (readable) properties.

    Returns:
        None.
    """
    print_properties_many(props_readable)

def print_properties_wr():
    """
    Print MPRIS2 writable properties.

    Returns:
        None.
    """
    print_properties_many(props_writable)


def do_property_wr_args(ao):
    """
    Set writable MPRIS properties.

    Using the parsed parameter object, prepared by get_options(),
    set those writable properties for which an argument was given.

    Args:
        ao: The parsed parameter object.

    Returns:
        None.
    """
    if ao.toggle_fullscr:
        print("Fullscreen original: {}".format(mplayer2.Fullscreen))
        mplayer2.Fullscreen = not mplayer2.Fullscreen
        print("Fullscreen now: {}".format(mplayer2.Fullscreen))

    if ao.loop != '':
        print("LoopStatus original: {}".format(player.LoopStatus))
        m = ao.loop.lower()
        if m == 'none':
            player.LoopStatus = "None"
        elif m == 'track':
            player.LoopStatus = "Track"
        elif m == 'playlist':
            player.LoopStatus = "PlayList"
        else:
            e = "LoopStatus '{}' is unknown".format(ao.loop)
            errout(e)
        print("LoopStatus now: {}".format(player.LoopStatus))

    if ao.rate > 0.0:
        print("Rate original: {}".format(player.Rate))
        player.Rate = ao.rate
        print("Rate now: {}".format(player.Rate))

    if ao.shuffle != '':
        print("Shuffle original: {}".format(player.Shuffle))
        m = ao.shuffle.lower()
        if m == 'true' or m == '1':
            player.Shuffle = True
        elif m == 'false' or m == '0':
            player.Shuffle = False
        else:
            e = "Shuffle '{}' is unknown".format(ao.loop)
            errout(e)
        print("Shuffle now: {}".format(player.Shuffle))

    if ao.vol != None:
        print("Volume original: {}".format(player.Volume))
        player.Volume = ao.vol
        print("Volume now: {}".format(player.Volume))


def get_options():
    """
    Get user options and arguments with argparse.ArgumentParser.

    Prepares a argparse.ArgumentParser object and assigned
    the result of parser.parse_args(sys.argv[1:]) in the
    global "args_obj".

    Returns:
        The argparse.ArgumentParser object.
    """
    global args_obj

    parser = argparse.ArgumentParser(
        description="""Control program for wxmav which, using the
        MPRIS2 specification, provides a command line means to
        play/pause, go previous/next, or stop; also, to set properties
        such as volume, window-showing, fullscreen.  A query option is
        provided which will show properties and metadata.""")
    parser.add_argument('args', metavar='method', type=str, nargs='*',
        help='''invoke method:
        play, pause, playpause (synonym: toggle), next,
        previous (synonym: prev), stop,
        seek=<signed integer offset in microseconds>,
        setposition="<trackid*> <unsigned integer in microseconds>"
        (synonym: setpos; *for trackid see
        "mpris:trackid" in metadata),
        openuri=<properly formed URI> (synonym: openurl),
        raise, quit''')
    parser.add_argument('-P', '--select-player', type=str,
        dest='player', default='wxmav', metavar='name',
        help='''select player to address: default "wxmav" --
        invoke the program with --list-players once, and use
        one of the short names as the argument to this option''')
    parser.add_argument('-l', '--list-players', action='store_const',
        const=True, dest='do_listplayers', default=False,
        help='list available players, and exit')
    parser.add_argument('-q', '--query', action='store_const',
        const=True, dest='do_query', default=False,
        help='query all properties and print')
    parser.add_argument('-w', '--wrprop-query', action='store_const',
        const=True, dest='do_wrquery', default=False,
        help='query writable properties and print')
    parser.add_argument('-F', '--fullscreen', action='store_const',
        const=True, dest='toggle_fullscr', default=False,
        help='toggle fullscreen mode')
    parser.add_argument('-L', '--set-loopstatus', type=str,
        dest='loop', default='', metavar='type',
        help='''set player loop mode to one of
        "None", "Track", or "Playlist"''')
    parser.add_argument('-R', '--set-rate', type=float,
        dest='rate', default=0.0, metavar='rate',
        help='''set playback rate (if supported) as
        this multiple; must be greater than 0.0
        and 1.0 is normal speed''')
    parser.add_argument('-S', '--set-shuffle', type=str,
        dest='shuffle', default='', metavar='bool',
        help='''set player shuffle mode: "true" or 1,
        or "false" or 0''')
    parser.add_argument('-V', '--set-volume', type=float,
        dest='vol', default=None, metavar='vol',
        help='''set volume from 0.0 to 1.0, or greater
        if the player supports that''')
    parser.add_argument('-C', '--cmd-easy', type=str,
        dest='cmd_easy', default='', metavar='<S|P|F>:arg',
        help='''"easy" form of the method commands that take arguments:
        "S" for Seek with argument in relative seconds,
        "P" for setPosition with argument in absolute seconds
        and using the current trackid,
        "F" for opening a local file --
        e.g. "-C S:-15"''')

    args_obj = parser.parse_args(sys.argv[1:])

    return parser


def mainproc():
    """
    Execute setup and main logic of the program.

    Returns:
        Small integer exit status code (0 on success).
    """
    parser = get_options()

    if args_obj.do_listplayers:
        return 0 if list_players() != 0 else 1

    if not init_mpris2(args_obj.player):
        e = "player '{}' was not found".format(args_obj.player)
        errout(e)

    do_property_wr_args(args_obj)

    if not invoke_easy_method(args_obj):
        e = "easy method '{}' failed".format(args_obj.cmd_easy)
        errout(e)

    i = invoke_method_list(args_obj.args)
    if i is not -1:
        e = "method '{}' is not known".format(args_obj.args[i])
        errout(e)

    if args_obj.do_query:
        print_properties_all()

    if args_obj.do_wrquery:
        print_properties_wr()

    return 0


if __name__ == '__main__':
    sys.exit(mainproc())

