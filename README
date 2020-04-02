# (WX) M A/V (Player)

## __wxmav__

This, __wxmav__, is an Audio/Visual media file and stream player.

There are many player applications for audio, video, or both,
and wxmav is not an attempt to be better than the others in
any sense but one: to suit the author's preferences.  This is
very much a 'scratch your own itch' program.  It is a qualified
success at satisfying the author.

This is a front end to the media widget in the __wxWidgets__
library, which is used via __wxPython__ as the bulk of the program
is written in the __Python__ language. For Unix systems there is
a small helper program in __C__, and a __MPRIS2__ control program for
the command line (in python); these do not apply to MS__Windows__
(and there has been no development on Apple systems, which
would without doubt require more work on the code as it stands).

Features:

* A traditional, and plain, user interface, which is hopefully
intuitive and easy.  While playing audio, the video window remains
blank (unless the system's underlying media backend presents a
graphical display, unrequested, as MSWindows might).  Presumably,
the application interface is only of interest while viewing video
(which might be in full screen mode), and would be mostly ignored
while listening to audio media.  As for video, the plain interface
might reduce distraction.

* Runtime (user's) data is saved in PLS 'playlist' files -- and
sets of playlists (or "groups" as referred to in wxmav) are
saved in directories.  (It is important to the author that data
be saved in a simple text format so that they may be easily
processed with command line tools, or edited by hand.)  One
non-standard feature is added to the PLS format: descriptions
in the typical form of a comment, starting with '#'.  Other
programs might or might not ignore these lines and parse the
files; at least, the __vlc__ player does.

* Adding files or playlists is accomplished through traditional
menus invoking file/directory selection dialogs; or, through
drag-and-drop from file managers, web browser URLs, and possibly
selected text from editors and such (depending, of course, on
that program).  On Unix, media may be played from the command line
with the MPRIS2 control program (named "__wxmav_control__").

* Selection from loaded data is through drop down lists: a list
at the top left presents the groups (playlists), and at the
right presents the items within the current group.  The groups
and their items may be reordered and edited with a "Media Set
Editor" window, which is invoked from the Edit menu.  (This
editor is a weak point presently, and may be improved.)

* Current loaded data (playlists) are saved when the program
is cleanly terminated; also, the data is automatically saved at
intervals to guard against unexpected/unhandled termination.
At start-up, the last saved data set is automatically loaded.

Misfeatures:

* When playing of sets tracks, on advancing from one to the next,
there will be a small gap of silence.  This should not matter
with discrete tracks, but in cases where the tracks constitute
unbroken sound, the gap will be noticeable.  This is a consequence
of being a front-end which uses a media widget with a limited
scope.  There is no way to present the backend media player
with a set of tracks that it may arrange to play without gaps.

* For similar reasons, this program cannot make use of info
tags that might be available in remote streams.  The media
backend might provide access to such at a lower level, but the
wxWidgets media control does not.

* DVD video discs, or CD audio discs, or similar cannot be played.
The backend might play these, but the media control does not
provide for that.

* Presently, there is no documentation (other than some 'tool-tips'),
but hopefully the program is easy learn through discovery.

Wayland (GNU/Linux systems):

If your system uses Wayland (e.g. Fedora) then videos might open a
new undecorated window rather than displaying in the main window,
as expected.  This is probably due to wxWidgets (e.g. using GTK)
not yet implementing The New Way of Things™ (wx 3.0).

Your system might provide way to use Good Ol' X, if you're inclined.
For example in Fedora set WaylandEnable=false in /etc/gdm/custom.conf
and reboot.

Author: Ed Hynan, ehynan@gmail.com

