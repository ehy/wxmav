/*
 * Copyright (C) 2017 Ed Hynan <edhynan@gmail.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
 * MA 02110-1301, USA.
 */

#ifdef HAVE_CONFIG_H
#   include "config.h"
#endif

#if HAVE_X11_EXTENSIONS_DPMS_H && ! defined(HAVE_XEXT)
#   define HAVE_XEXT 1
#endif
#if HAVE_X11_EXTENSIONS_SCRNSAVER_H && ! defined(HAVE_XSSAVEREXT)
#   define HAVE_XSSAVEREXT 1
#endif

#if ! HAVE_XEXT
#   warning "Building without DPMI functionality in libXext"
#endif

/* use -lXss for this: */
#if ! HAVE_XSSAVEREXT
#   warning "Building without X screen saver functionality in libXss"
#endif

#include <errno.h>
#if HAVE_GETOPT_H
#include <getopt.h>
#else
#include "gngetopt.h"
#endif
#include <limits.h>
#include <locale.h>
#include <poll.h>
#include <signal.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <X11/X.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <X11/XF86keysym.h>
#if HAVE_XEXT && HAVE_X11_EXTENSIONS_DPMS_H
#include <X11/extensions/dpms.h>
#endif
#if HAVE_XSSAVEREXT && HAVE_X11_EXTENSIONS_SCRNSAVER_H
#include <X11/extensions/scrnsaver.h>
#endif

/* if configure found glib dbus io support: */
#if HAVE_GIO20
#include "dbus_gio.h"
#endif

/* XDG command line utility for controlling
 * screensaver -- if system has this but with
 * another name, define this!
 */
#ifndef XDG_SCREENSAVER
#define XDG_SCREENSAVER "xdg-screensaver"
#endif

/* by invocation option, try xautolock -{dis,en}able
 */
#ifndef XAUTOLOCK
#define XAUTOLOCK "xautolock"
#endif

/* by invocation option, try xscreensaver
 */
#ifndef XSCREENSAVER
#define XSCREENSAVER "xscreensaver-command"
#endif

#undef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#undef MAX
#define MAX(a, b) ((a) > (b) ? (a) : (b))

#define A_SIZE(a) (sizeof(a) / sizeof((a)[0]))

#if defined(_POSIX_PIPE_BUF)
#    define MAX_RW_SIZE     _POSIX_PIPE_BUF
#elif defined(PIPE_BUF)
#    define MAX_RW_SIZE     PIPE_BUF
#else
#    warning "PIPE_BUF macro not found -- just guessing"
    /* conservative (hopefully) guess */
#    define MAX_RW_SIZE     128
#endif

#ifndef WANTED_RW_SIZE
#    define WANTED_RW_SIZE  128
#endif

#if (WANTED_RW_SIZE > MAX_RW_SIZE)
#    undef WANTED_RW_SIZE
#    define WANTED_RW_SIZE  MAX_RW_SIZE
#endif

/* buffer size to build a write
 */
#define MAX_LINEOUT_SIZE   WANTED_RW_SIZE
/* buffer size to receive a read
 */
#define MAX_LINEIN_SIZE    WANTED_RW_SIZE

# if defined(HAVE_CONFIG_H) && defined(VERSION)
#   define PROGRAM_VERSION VERSION
#else
#   define PROGRAM_VERSION "1.0"
#endif
#ifndef PROGRAM_DEFNAME
#    define PROGRAM_DEFNAME "x-key-ss-helper"
#endif /* PROGRAM_DEFNAME */

const char *prog = PROGRAM_DEFNAME;

#define TERMINATE_CHARBUF(buf, contentlen) do { \
        buf[MIN(contentlen, sizeof(buf) - 1)] = '\0'; \
    } while (0)

#define KEY_SETUP(dsp, wnd) \
    do_key_grabs(dsp, wnd); \
    XSelectInput(dsp, wnd, KeyPressMask | KeyReleaseMask);
#define KEY_SETDOWN(dsp, wnd) \
    XSelectInput(dsp, wnd, 0); \
    do_key_ungrabs(dsp, wnd);

static void
setup_prog(const char *av0);
static void
usage(void);
static void
print_version(void);
static void
common_signal_handler(int sig);
static const char *
handle_key(int type, XKeyEvent *xkey);
static void
do_key_grabs(Display *dpy, Window w);
static void
do_key_ungrabs(Display *dpy, Window w);
static Bool
write_grabs(int fd);
static int
x_error_proc(Display *dpy, XErrorEvent *err);
ssize_t
input_line(int fd, char *buf, size_t buf_sz);
int
client_input(int fd);
ssize_t
client_output(int fd, const void *buf, size_t buf_sz);
ssize_t
client_output_str(int fd, const char *str);
Bool
grab_new_window(Display *dpy, Window *pwold, Window wnew);
Bool
input_and_reply(Display *dpy, Window *pw,
                int client_in, int client_out);
Bool
dbus_proc_relay(int dbus_fd, int client_out);
Bool
dbus_proc_relay_write(int client_out, char *msgbuf);
Window
window_by_name(Display *dpy, Window top, const char *name);
/* system(3) with result message */
int
do_system_call(const char *buf);
/* screensaver diddlers */
#if HAVE_XEXT
void
_DPMI_off(Display *dpy);
void
_DPMI_on(void);
#endif
void
_ssave_off(Display *dpy);
void
_ssave_on(void);
/* X screensaver methods likely fail in complex desktop systems
 * that each do things their own idiosyncratic ways -- XDG
 * has tackled the problem with a script 'xdg-screensaver'
 * that jumps through hoops to detect its context and do something
 * useful, BUT its {dis,en}able commands require a Window ID
 * argument, so using program must first have set that in
 * client_name.wid with "setwname" message
 */
int
_xdg_ssave(Bool disable);
/* the following two are used herein to try to control
 * the screensaver; the protos _DPMI*, _ssave*, and _xdg*
 * above are only for use within the two following procedures
 */
void
ssave_disable(Display *dpy);
void
ssave_enable(void);

/* by invocation option, try xautolock -{dis,en}able
 */
int
_xautolock(Bool disable);
Bool try_xautolock = False;

/* by invocation option, try xscreensaver -{dis,en}able
 */
int
_xscreensaver(Bool disable);
Bool try_xscreensaver = False;

struct {
    Window    wid;
    char      buf[MAX_LINEIN_SIZE];
} client_name = { 0, { '\0' } };

volatile sig_atomic_t got_common_signal = 0;

int common_signals[] = {
    SIGHUP, SIGINT, /* leave this alone: SIGQUIT, */
    SIGTERM,
    /* SIGPIPE, client gone, but does Xlib want this? */
    SIGTERM, SIGUSR1, SIGUSR2
};

/* for pipe-write-in-signal-handler hack */
int sigpipe[] = { -1, -1 };
#define PIPE_RFD_INDEX 0
#define PIPE_WFD_INDEX 1
#define PIPE_RFD sigpipe[PIPE_RFD_INDEX]
#define PIPE_WFD sigpipe[PIPE_WFD_INDEX]

static void
common_signal_handler(int sig)
{
    got_common_signal = sig;

    if ( PIPE_WFD >= 0 ) {
        /* assign return for some noisy recent compilers */
        sig = (int)write(PIPE_WFD, &sig, sizeof(sig));
    }
}

static int
x_error_proc(Display *dpy, XErrorEvent *err)
{
    char buf[MAX_LINEIN_SIZE];
    int l;

    l = XGetErrorText(dpy, (int)err->error_code, buf, sizeof(buf) - 1);

    /* manpage for XGetErrorText does not describe possible
     * failure return values, in fact it does not describe
     * the int returned at all, so as a matter of guesswork:
     */
    if ( l < 0 ) {
        l = snprintf(buf, sizeof(buf),
                    "X error code %u",
                    (unsigned int)err->error_code);

        TERMINATE_CHARBUF(buf, l);
    } else {
        /* this sucks */
        buf[sizeof(buf) - 1] = '\0';
    }

    /* X docs say "the returned value is ignored." */
    return fprintf(stderr, "%s: got X error: %s\n", prog, buf);
}

#define _KEY_DATA(k) { k, -1, 0, #k, False }
static struct {
    KeySym           ksym;
    int              kcode;
    unsigned int     kmod;
    const char       *ssym;
    Bool             got_grab;
} key_data[] = {
    _KEY_DATA(XF86XK_AudioPlay),
    _KEY_DATA(XF86XK_AudioPause),
    _KEY_DATA(XF86XK_AudioStop),
    _KEY_DATA(XF86XK_AudioPrev),
    _KEY_DATA(XF86XK_AudioNext),
    _KEY_DATA(XF86XK_AudioRewind),
    _KEY_DATA(XF86XK_AudioForward),
    _KEY_DATA(XF86XK_AudioRepeat),
    _KEY_DATA(XF86XK_AudioRandomPlay),
    _KEY_DATA(XF86XK_AudioCycleTrack)
};

const size_t ssym_off = sizeof("XF86XK");
#define _KEYNAME(kdat) ((kdat).ssym + ssym_off)

static const char *
handle_key(int type, XKeyEvent *xkey)
{
    if ( ! ( type == KeyPress || type == KeyRelease ) ) {
        return NULL;
    }

    if ( type == KeyRelease ) {
        KeySym ksym;
        int i;

        ksym = XLookupKeysym(xkey, 0);

        for ( i = 0; i < A_SIZE(key_data); i++ ) {
            if ( key_data[i].ksym == ksym ) {
                return _KEYNAME(key_data[i]);
            }
        }
    }

    return NULL;
}

static void
do_key_grabs(Display *dpy, Window w)
{
    int i;
    unsigned int mk = AnyModifier;

    for ( i = 0; i < A_SIZE(key_data); i++ ) {
        int kc, r;
        KeySym ksym = key_data[i].ksym;

        kc = XKeysymToKeycode(dpy, ksym);

        if ( kc == 0 ) {
            #if _DEBUG
            fprintf(stderr,
                "%s: failed to get keycode for '%s' (keysym 0x%lx)\n",
                prog, _KEYNAME(key_data[i]), (unsigned long)ksym);
            #endif
            key_data[i].got_grab = False;
            continue;
        }

        key_data[i].kcode = kc;
        key_data[i].kmod  = mk;

        /* manual for XGrabKey states int return in prototype,
         * but does not specify the actual returns; from observation
         * the returns appear to be X defined 'Bool' --
         * True(1) of False(0) -- but test for int constants since
         * Bool is not stated
         */
        r = XGrabKey(dpy, kc, mk, w, True,
                GrabModeAsync, GrabModeAsync);

        if ( r == 0 ) {
            /* there has been no 0 returned in all testing! */
            key_data[i].got_grab = False;
            fprintf(stderr,
                "%s: failed to grab '%s' (keycode %d)\n",
                prog, _KEYNAME(key_data[i]), kc);
        } else {
            /* unfortunately, 'True' return happens even if
             * the error handler was called and the events
             * will never be delivered -- what to do?
             */
            key_data[i].got_grab = True;
        }
    }
}

static void
do_key_ungrabs(Display *dpy, Window w)
{
    int i;

    for ( i = 0; i < A_SIZE(key_data); i++ ) {
        if ( key_data[i].got_grab != True ) {
            continue;
        }

        XUngrabKey(dpy,
                   key_data[i].kcode,
                   key_data[i].kmod,
                   w);

        key_data[i].got_grab = False;
    }
}

Bool
grab_new_window(Display *dpy, Window *pwold, Window wnew)
{
    Window w;

    w = *pwold;
    KEY_SETDOWN(dpy, w);
    w = wnew;
    KEY_SETUP(dpy, w);
    *pwold = w;

    return True;
}

static Bool
write_grabs(int fd)
{
    char buf[MAX_LINEOUT_SIZE];
    int i;

    for ( i = 0; i < A_SIZE(key_data); i++ ) {
        int l;

        l = snprintf(buf, sizeof(buf), "%c:%s\n",
                key_data[i].got_grab == True ? 'Y' : 'N',
                _KEYNAME(key_data[i]));

        TERMINATE_CHARBUF(buf, l);

        if ( client_output_str(fd, buf) < 0 ) {
            return False;
        }
    }

    return True;
}

ssize_t
input_line(int fd, char *buf, size_t buf_sz)
{
    char     *p;
    ssize_t  res;

    for (;;) {
        res = read(fd, buf, buf_sz);

        if ( res < 0 ) {
            if ( got_common_signal || errno != EINTR ) {
                return res;
            }
        } else {
            break;
        }
    }

    res = MIN(res, buf_sz - 1);
    buf[res] = '\0';

    while ( res > 0 && buf[res - 1] == '\n' ) {
        buf[--res] = '\0';
    }

    return res;
}

#ifndef EWOULDBLOCK
#define EWOULDBLOCK EAGAIN
#endif

ssize_t
client_output(int fd, const void *buf, size_t buf_sz)
{
    ssize_t  res, cnt;

    for ( res = 0; res < buf_sz; res += cnt ) {
        size_t nwr = buf_sz - res;

        cnt = write(fd, (char *)buf + res, nwr);

        if ( cnt < 0 ) {
            if ( got_common_signal || errno != EINTR ) {
                return cnt;
            }

            cnt = 0;
        } else if ( cnt < nwr ) {
            if ( errno == EAGAIN || errno == EWOULDBLOCK ) {
                /* sleep(1); */
                poll(NULL, 0, 500);
            } else {
                return cnt - nwr;
            }
        }
    }

    return res;
}

ssize_t
client_output_str(int fd, const char *str)
{
    return client_output(fd, str, strlen(str));
}

/* request strings */
#define _QUITMSG  "quit"
#define _QUERYMSG "query"
#define _WNAMEMSG "wname"
#define _WROOTMSG "wroot"
#define _MAXLNMSG "linemax"
#define _SS_ONMSG "ssaver_on"
#define _SSOFFMSG "ssaver_off"
#define _SNAMEMSG "setwname"
/* request returns */
#define GOT_RDERR         -1
#define GOT_NOISE          0
#define GOT_QUITMSG        1
#define GOT_QUERYMSG       2
#define GOT_WNAMEMSG       4
#define GOT_WROOTMSG       8
#define GOT_MAXLNMSG       16
#define GOT_SS_ONMSG       32
#define GOT_SSOFFMSG       64
#define GOT_SNAMEMSG       128
int
client_input(int fd)
{
    char buf[MAX_LINEIN_SIZE];
    int  res;

    if ( input_line(fd, buf, sizeof(buf)) < 0 ) {
        return GOT_RDERR;
    }

    res = strcasecmp(buf, _QUITMSG);
    if ( res == 0 ) {
        return GOT_QUITMSG;
    }

    res = strcasecmp(buf, _QUERYMSG);
    if ( res == 0 ) {
        return GOT_QUERYMSG;
    }

    res = strcasecmp(buf, _WNAMEMSG);
    if ( res == 0 ) {
        return GOT_WNAMEMSG;
    }

    res = strcasecmp(buf, _WROOTMSG);
    if ( res == 0 ) {
        return GOT_WROOTMSG;
    }

    res = strcasecmp(buf, _MAXLNMSG);
    if ( res == 0 ) {
        return GOT_MAXLNMSG;
    }

    res = strcasecmp(buf, _SS_ONMSG);
    if ( res == 0 ) {
        return GOT_SS_ONMSG;
    }

    res = strcasecmp(buf, _SSOFFMSG);
    if ( res == 0 ) {
        return GOT_SSOFFMSG;
    }

    res = strcasecmp(buf, _SNAMEMSG);
    if ( res == 0 ) {
        return GOT_SNAMEMSG;
    }

    /* unexpected or empty input is ignored */
    return GOT_NOISE;
}

Bool
dbus_proc_relay(int dbus_fd, int client_out)
{
    char buf[MAX_LINEIN_SIZE];

    if ( input_line(dbus_fd, buf, sizeof(buf)) < 0 ) {
        return False;
    }

    return dbus_proc_relay_write(client_out, buf);
}

Bool
dbus_proc_relay_write(int client_out, char *msgbuf)
{
    char buf[MAX_LINEIN_SIZE];
    int  l;

    l = snprintf(buf, sizeof(buf), "dbus:%s\n", msgbuf);

    TERMINATE_CHARBUF(buf, l);

    return client_output_str(client_out, buf) > 0 ? True : False;
}

Bool
input_and_reply(Display *dpy, Window *pw,
                int client_in, int client_out)
{
    char buf[64];
    const char *msg = NULL;
    int imsg = client_input(client_in);

    if ( imsg == GOT_QUITMSG || imsg == GOT_RDERR ) {
        return False;
    } else if ( imsg == GOT_QUERYMSG ) {
        return write_grabs(client_out);
    } else if ( imsg == GOT_MAXLNMSG ) {
        int l = MAX_LINEIN_SIZE;

        l = snprintf(buf, sizeof(buf), "Y:%d\n", l);

        TERMINATE_CHARBUF(buf, l);

        msg = buf;
    } else if ( imsg == GOT_WNAMEMSG ) {
        Window wnew = client_name.wid;

        if ( wnew && grab_new_window(dpy, pw, wnew) ) {
            msg = "Y:" _WNAMEMSG "\n";
        } else {
            fprintf(stderr,
                "%s: cannot find window; use '" _SNAMEMSG "'\n", prog);
            msg = "N:" _WNAMEMSG "\n";
        }
    } else if ( imsg == GOT_SNAMEMSG ) {
        char  *pbuf = client_name.buf;
        size_t  bsz = sizeof(client_name.buf);
        ssize_t res = input_line(client_in, pbuf, bsz);

        if ( res < 0 ) {
            return False;
        }

        if ( res < 1 ) {
            fprintf(stderr, "%s: read empty window name\n", prog);
            msg = "N:" _SNAMEMSG "\n";
        } else {
            Window wnew;

            wnew = RootWindow(dpy, 0);
            wnew = window_by_name(dpy, wnew, pbuf);

            if ( wnew ) {
                client_name.wid = wnew;
                msg = "Y:" _SNAMEMSG "\n";
            } else {
                fprintf(stderr,
                    "%s: cannot find window with name '%s'\n",
                    prog, pbuf);
                msg = "N:" _SNAMEMSG "\n";
            }
        }

#       if _DEBUG
        fprintf(stderr, "%s: handling set wname: '%s' -- %s\n",
                        prog, pbuf, msg);
#       endif
    } else if ( imsg == GOT_WROOTMSG ) {
        Window wnew = RootWindow(dpy, 0);

        if ( wnew && grab_new_window(dpy, pw, wnew) ) {
            msg = "Y:" _WROOTMSG "\n";
        } else {
            fprintf(stderr,
                "%s: cannot get root window\n", prog);
            msg = "N:" _WROOTMSG "\n";
        }
    } else if ( imsg == GOT_SSOFFMSG ) {
        ssave_disable(dpy);
        msg = "Y:" _SSOFFMSG "\n";
    } else if ( imsg == GOT_SS_ONMSG ) {
        ssave_enable();
        msg = "Y:" _SS_ONMSG "\n";
    }

    if ( msg != NULL && client_output_str(client_out, msg) < 0 ) {
        fprintf(stderr, "%s: error on client write '%s'\n",
            prog, msg);
        return False;
    }

    return True;
}

static void
print_version(void)
{
    fprintf(stderr,
    "\nThis is %s (%s), version %s.\n"
    "\n"
    "%s is licensed under the GNU General Public License,\n"
    "version 2 or greater; see the source code for details.\n"
    "\n",
    prog, PROGRAM_DEFNAME, PROGRAM_VERSION, prog);
}

static void
usage(void)
{
    fprintf(stderr,
    "\nUsage: %s [options]\n"
    "\n"
    "  --display\n"
    "   -d       X display string; default is from environment\n"
    "\n"
    "  --name\n"
    "   -n       name of X Window to grab keys from;"
                 " default is root window\n"
    "\n"
    "  --window\n"
    "   -w       X Window identifier to grab keys from;"
                 " default is root window\n"
    "\n"
    "  --xautolock\n"
    "   -a       try invoking " XAUTOLOCK " screen saver suspend\n"
    "\n"
    "  --xscreensaver\n"
    "   -s       try invoking " XSCREENSAVER " screen saver suspend\n"
    "\n"
    "  --version\n"
    "   -v       print version and licence info on standard error\n"
    "\n"
    "  --help\n"
    "   -h       print usage text (this) on standard error\n"
    "\n"
    "This is not a user program; this is a helper for application\n"
    "programs that want multimedia keys, but which might not be able\n"
    "to obtain them from their language or libraries.  Interactive\n"
    "use is only useful for testing and debugging."
    "\n\n",
    prog);
}

static void
setup_prog(const char *av0)
{
    const char *p;

    if ( ! av0 || ! *av0 ) {
        return;
    }

    p = strrchr(av0, '/');

    if ( p && p[1] ) {
        prog = ++p;
    } else {
        prog = av0;
    }
}

Window
window_by_name(Display *dpy, Window top, const char *name)
{
    Window wroot, wparent, ret = 0;
    Window *wp = NULL;
    char   *nm = NULL;
    Status st;
    unsigned int i, nwp;

    st = XFetchName(dpy, top, &nm);

    if ( st == 0 ) {
        nm = NULL;
    } else if ( nm != NULL ) {
        if ( strcmp(name, nm) == 0 ) {
            XFree(nm);
            return top;
        }
    }

    if ( nm != NULL ) {
        XFree(nm);
    }

    st = XQueryTree(dpy, top, &wroot, &wparent, &wp, &nwp);

    if ( st == 0 || wp == NULL ) {
        return 0;
    }

    for ( i = 0; i < nwp; i++ ) {
        if ( (ret = window_by_name(dpy, wp[i], name)) != 0 ) {
            break;
        }
    }

    if ( wp != NULL ) {
        XFree(wp);
    }

    return ret;
}

#if HAVE_XEXT
struct {
    Display   *display;
    CARD16    power_level;
    BOOL      state;
} DPMIstate = { NULL, 0, False };

void
_DPMI_off(Display *dpy)
{
    Status stat;

    if ( DPMIstate.display != NULL ) {
        return;
    }

    stat = DPMSInfo(dpy, &DPMIstate.power_level, &DPMIstate.state);
    if ( stat != True ) {
        return;
    }

    DPMIstate.display = dpy;

    if ( DPMIstate.state == True ) {
        DPMSDisable(dpy);
    }
}

void
_DPMI_on(void)
{
    if ( DPMIstate.display == NULL ) {
        return;
    }

    if ( DPMIstate.state == True ) {
        DPMSEnable(DPMIstate.display);
    }

    DPMIstate.display = NULL;
    DPMIstate.state = False;
}
#endif

struct {
    Display   *display;
    int       timeout, interval, blanking, exposures;
} ssavestate = { NULL, 0, 0, 0, 0 };

void
_ssave_off(Display *dpy)
{
    int stat;

    if ( ssavestate.display != NULL ) {
        return;
    }

    stat = XGetScreenSaver(dpy,
                           &ssavestate.timeout,
                           &ssavestate.interval,
                           &ssavestate.blanking,
                           &ssavestate.exposures);

    if ( stat == BadValue ) {
#    if _DEBUG
        fprintf(stderr, "%s: failed getting screensaver info\n", prog);
#    endif
        return;
    }

    ssavestate.display = dpy;

    if ( ssavestate.timeout != 0 ) {
        XSetScreenSaver(dpy,
                        0,
                        ssavestate.interval,
                        ssavestate.blanking,
                        ssavestate.exposures);
#        if _DEBUG
        fprintf(stderr, "%s: done setting screensaver off, "
                        "timeout was %d\n",
                        prog, ssavestate.timeout);
#        endif
    } else {
        fprintf(stderr, "%s: screensaver already off: "
                        "timeout was %d\n",
                        prog, ssavestate.timeout);
    }
}

void
_ssave_on(void)
{
    Display *dpy;
    int stat, tout;

    if ( ssavestate.display == NULL ) {
        return;
    }

    dpy = ssavestate.display;

    ssavestate.display = NULL;

    stat = XGetScreenSaver(dpy,
                           &tout,
                           &ssavestate.interval,
                           &ssavestate.blanking,
                           &ssavestate.exposures);

    if ( stat == BadValue ) {
        return;
    }

    if ( tout == 0 ) {
        XSetScreenSaver(dpy,
                        ssavestate.timeout,
                        ssavestate.interval,
                        ssavestate.blanking,
                        ssavestate.exposures);
    }
}

/* for system(3), used below */
#define _SH_REDIR ">/dev/null 2>/dev/null </dev/null"
/* 64 bit decimal with sign can be 20 chars -- so lets use 32 */
#define _FMT_BUF_PAD 32

/* X screensaver methods likely fail in complex desktop systems
 * that each do things their own idiosyncratic ways -- XDG
 * has tackled the problem with a scipt 'xdg-screensaver'
 * that jumps through hoops to detect its context and do something
 * useful, BUT its {dis,en}able commands require a Window ID
 * argument, so using program must first have set that in
 * client_name.wid with "setwname" message
 */
int
_xdg_ssave(Bool disable)
{
    static const char xdgprog[] = XDG_SCREENSAVER;
    static const char xdgoff[]  = "suspend";
    static const char xdgon[]   = "resume";

#undef _BUF_TMP_SZ
#define _BUF_TMP_SZ \
    (sizeof(xdgprog)+sizeof(xdgoff)+sizeof(_SH_REDIR)+_FMT_BUF_PAD)

    int l;
    char buf[_BUF_TMP_SZ];

    if ( ! client_name.wid ) {
        return -1;
    }

    l = snprintf(buf, sizeof(buf),
                 "%s %s %lu " _SH_REDIR,
                 xdgprog,
                 disable == True ? xdgoff : xdgon,
                 (unsigned long)client_name.wid);

    TERMINATE_CHARBUF(buf, l);

    return do_system_call(buf);
}

int
_xautolock(Bool disable)
{
    static const char xpr[] = XAUTOLOCK;
    static const char en[]  = "-enable";
    static const char dis[] = "-disable";
    static int execstatus = 0;

#undef _BUF_TMP_SZ
#define _BUF_TMP_SZ \
    (sizeof(xpr)+sizeof(dis)+sizeof(_SH_REDIR)+_FMT_BUF_PAD)

    int l;
    char buf[_BUF_TMP_SZ];

    if ( try_xautolock != True ) {
        return -1;
    }

    if ( execstatus < 0 ) {
        return execstatus;
    }

    l = snprintf(buf, sizeof(buf),
                 "%s %s " _SH_REDIR,
                 xpr, disable == True ? dis : en);

    TERMINATE_CHARBUF(buf, l);

    execstatus = do_system_call(buf);

    return execstatus;
}

pid_t _child_xscreensaver_pid = 0;

int
_child_xscreensaver(void)
{
    static const char cmd[] = XSCREENSAVER " -deactivate " _SH_REDIR;

    int i;

    if ( try_xscreensaver != True || _child_xscreensaver_pid != 0 ) {
        return -1;
    }

    _child_xscreensaver_pid = fork();

    if ( _child_xscreensaver_pid > 0 ) {
        /* parent: sleep briefly and wait nohang as a quick check */
        pid_t p;

        sleep(1);
        p = waitpid(_child_xscreensaver_pid, &i, WNOHANG);

        /* if child exited already, don't check status, it's error */
        if ( p ) {
            _child_xscreensaver_pid = -1;
        }

        return _child_xscreensaver_pid;
    } else if ( _child_xscreensaver_pid < 0 ) {
        /* ev'ybody wanna fork */
        return -1;
    }

    /* child: disable, sleep, do it again */
#ifndef XSCREENSAVER_SECS_SLEEP
#define XSCREENSAVER_SECS_SLEEP (60 * 2)
#endif

    /* make sure of signals -- we're OK with defaults */
    for ( i = 0; i < A_SIZE(common_signals); i++ ) {
        signal(common_signals[i], SIG_DFL);
    }

    for (;;) {
        i = do_system_call(cmd);

        /* xscreensaver-command manual is explicit about status */
        if ( i ) {
            i = 13;
            break;
        }

        sleep(XSCREENSAVER_SECS_SLEEP);
    }

    _exit(i);
    /* not reached */
    return i;
}

int
_xscreensaver(Bool disable)
{
    pid_t p;
    int st;

    if ( try_xscreensaver != True ) {
        return -1;
    }

    if ( disable == True && _child_xscreensaver_pid != 0 ) {
        return -1;
    } else if ( disable == False && _child_xscreensaver_pid <= 0 ) {
        return -1;
    }

    if ( disable == True ) {
        return _child_xscreensaver();
    }

    /* enable: end child proc */
    p = waitpid(_child_xscreensaver_pid, &st, WNOHANG);
    if ( ! p ) {
        st = kill(_child_xscreensaver_pid, SIGINT);
        if ( st ) {
            /* give up -- leave pid for retry */
            return -1;
        }

        p = waitpid(_child_xscreensaver_pid, &st, 0);
        if ( ! p ) {
            /* gone already */
            return -1;
        }
    }

    if ( WIFSIGNALED(st) ) {
        /* good, we killed */
        _child_xscreensaver_pid = 0;
        return 0;
    }

    if ( ! WIFEXITED(st) ) {
        /* WTF -- leave pid for retry */
        return -1;
    }

    return WEXITSTATUS(st);
}

int
do_system_call(const char *buf)
{
    int i = system(buf);

    if ( i == -1 ) {
        fprintf(stderr, "%s: '%s' not executable\n", prog, buf);
    } else if ( WIFSIGNALED(i) ) {
        int s = WTERMSIG(i);

        i = WEXITSTATUS(i);
        fprintf(stderr,
            "%s: status %d, terminated by signal %d, for '%s'\n",
            prog, i, s, buf);
    } else if ( WIFEXITED(i) ) {
        i = WEXITSTATUS(i);
        fprintf(stderr, "%s: status %d for '%s'\n", prog, i, buf);
    } else {
        fprintf(stderr, "%s: abnormal termination '%s'\n", prog, buf);
        i = -1;
    }

    return i;
}

int _xdg_ok = -1;
#if HAVE_XSSAVEREXT
int _xssave = -1;
Display *_xssave_dpy = NULL;
#endif

Bool did_ssave_disable = False;

void
ssave_enable(void)
{
    if ( did_ssave_disable == False ) {
        return;
    }

    did_ssave_disable = False;

    /* NOTE: test >= rather than equality because xdg-screensaver
     * might leave a subshell running even if fail status is reported,
     * and we do want to stop that subshell, especially since this
     * program's parent process might start a new process group
     * and wait on the group, which could be a long wait . . .
     */
    if ( _xdg_ok >= 0 ) {
        _xdg_ok = _xdg_ssave(False);
    }

    /* do these regardles of _xdg_ok since its status lies */
    _xautolock(False);
    _xscreensaver(False);

    if ( _xdg_ok ) {
#if HAVE_XSSAVEREXT
        if ( _xssave_dpy != NULL ) {
            XScreenSaverSuspend(_xssave_dpy, False);
            _xssave_dpy = NULL;
        }
#endif
        _ssave_on();
    }
#if HAVE_XEXT
    _DPMI_on();
#endif
}

void
ssave_disable(Display *dpy)
{
    if ( did_ssave_disable == True ) {
        return;
    }

    did_ssave_disable = True;

    _xdg_ok = _xdg_ssave(True);

    /* do these regardles of _xdg_ok since its status lies */
    _xautolock(True);
    _xscreensaver(True);

    if ( _xdg_ok ) {
#if HAVE_XSSAVEREXT
        int evt, err;

        if ( XScreenSaverQueryExtension(dpy, &evt, &err) == True ) {
            XScreenSaverSuspend(dpy, True);
            _xssave_dpy = dpy;
            fprintf(stderr, "%s: Xss query true (%d, %d)\n",
                prog, evt, err);
        }
#endif
        _ssave_off(dpy);
    }
#if HAVE_XEXT
    _DPMI_off(dpy);
#endif
}

/*
 * put struct pollfd array on heap, plus
 * counts --
 * UPDATE THIS if fd usage changes!
 *
 * currently polled:
 * - client in
 * - client out
 * - X connection descriptor
 * - signal pipe hack read end
 * - dbus handler coprocess (when available)
 */
#define _POLL_FD_CNT 5
#define DBUS_PROC_POLL_IDX 4
struct pollfd poll_fds[_POLL_FD_CNT];
nfds_t poll_fds_idx;

#define ADD_POLL_RD(desc) do { \
        poll_fds[poll_fds_idx].fd = desc; \
        poll_fds[poll_fds_idx].events = POLLIN; \
        ++poll_fds_idx; \
    } while (0)

#define ADD_POLL_WR(desc) do { \
        poll_fds[poll_fds_idx].fd = desc; \
        poll_fds[poll_fds_idx].events = POLLOUT; \
        ++poll_fds_idx; \
    } while (0)

#define DO_POLL_NOW(retval, timval) do { \
        retval = poll(poll_fds, poll_fds_idx, timval); \
    } while (0)

void
init_poll_data(void)
{
    size_t i;
    for ( i = 0; i < A_SIZE(poll_fds); i++ ) {
        poll_fds[i].fd      = -1;
        poll_fds[i].events  = 0;
        poll_fds[i].revents = 0;
    }
    poll_fds_idx = 0;
}
/* check poll data for POLLHUP or POLLERR in revents;
 * return zero if not found, else array index + 1
 */
int
check_poll_data_error(void)
{
#   define _REVENTS_ERR (POLLERR|POLLHUP|POLLNVAL)
    size_t i;
    for ( i = 0; i < A_SIZE(poll_fds); i++ ) {
        if ( poll_fds[i].fd < 0 ) {
            continue;
        }
        if ( poll_fds[i].revents & _REVENTS_ERR ) {
            return (int)i + 1;
        }
    }
    return 0;
}


/* these are associated with macro HAVE_GIO20,
 * but define them for unconditional use
 */
int dbus_proc_status = -1;
int dbus_fd = -1;
#if HAVE_GIO20
dbus_proc_out dbus_out;
dbus_proc_in  dbus_in;
#ifndef DBUS_PROC_QUIT_SIG
#define DBUS_PROC_QUIT_SIG SIGINT
#endif
#endif /* HAVE_GIO20 */

static int
do_dbus_proc(void)
{
#if HAVE_GIO20
    dbus_in.quit_sig = DBUS_PROC_QUIT_SIG;
    dbus_in.def_sig  = common_signals;
    dbus_in.num_sig  = A_SIZE(common_signals);
    dbus_in.fd_wr    = -1;
    dbus_in.progname = prog;

    dbus_proc_status = start_dbus_gio_proc(&dbus_in, &dbus_out);
    /* assignment will be -1 on error, check not needed */
    dbus_fd = dbus_out.fd_rd;
#endif /* HAVE_GIO20 */

    return dbus_proc_status;
}

static int
collect_dbus_proc(void)
{
#if HAVE_GIO20
    int p, st;

    if ( dbus_fd >= 0 ) {
        close(dbus_fd);
    }

    if ( dbus_proc_status ) {
        return 1;
    }

    p = waitpid(dbus_out.proc_pid, &st, WNOHANG);
    if ( ! p ) {
        st = kill(dbus_out.proc_pid, DBUS_PROC_QUIT_SIG);
        if ( st ) {
            /* give up */
            return 1;
        }

        p = waitpid(dbus_out.proc_pid, &st, 0);
        if ( ! p ) {
            /* gone already */
            return 1;
        }
    }

    if ( WIFSIGNALED(st) ) {
        /* OK */
        return WTERMSIG(st);
    }

    if ( ! WIFEXITED(st) ) {
        /* WTF */
        return 1;
    }

    return WEXITSTATUS(st);
#else  /* HAVE_GIO20 */

    return 1;
#endif /* HAVE_GIO20 */
}


int
main(int argc, char **argv)
{
    Display           *dpy;
    Window            w;
    XEvent            ev;
    int               client_in, client_out;
    int               c, dpy_fd, poll_err_fd;
    const char        *display = NULL, *byname = NULL;
    int               (*orig_err)(Display *, XErrorEvent *);

    static const char opt_str[] = "d:w:n:ashv";
    static struct option opts[] = {
        { "display",      1, NULL, 'd' },
        { "window",       1, NULL, 'w' },
        { "name",         1, NULL, 'n' },
        { "xautolock",    0, NULL, 'a' },
        { "xscreensaver", 0, NULL, 's' },
        { "help",         0, NULL, 'h' },
        { "version",      0, NULL, 'v' },
        { 0,              0, NULL, 0 }
    };

#   if HAVE_SETLOCALE
    /* all IO in ascii, except perhaps window titles,
     * which are only be subject to byte-wise comparison
     */
    setlocale(LC_ALL, "C");
#   endif

#    if ! _DEBUG
    /* this program does not (intentionally) use the inherited
     * working directory, and it might possibly be useful to
     * get out of the way -- of course we don't dump core ;)
     * -- no result check, but assign return for some noisy
     * recent compilers
     */
    c = chdir("/");
#    endif

    setup_prog(argv[0]);

    w = 0;

    while ((c = getopt_long(argc, argv, opt_str, opts, NULL)) != -1) {
        switch (c) {
        case 'd':
            display = optarg;
            break;
        case 'n':
            byname = optarg;
            w = 0;
            break;
        case 'w': {
                char *ep = NULL;
                unsigned long ul = 0;

                errno = 0;
                ul = strtoul(optarg, &ep, 0);

                if ( errno || (ep != NULL && *ep) ) {
                    fprintf(stderr,
                        "%s: bad -w,--window argument '%s'\n",
                        prog, optarg);
                    usage();
                    exit(1);
                }

                byname = NULL;
                w = (Window)ul;
            }
            break;
        case 'a':
            try_xautolock = True;
            break;
        case 's':
            try_xscreensaver = True;
            break;
        case 'v':
            print_version();
            exit(0);
            break;
        case 'h':
        /* fall through */
        default:
            usage();
            exit(1);
            break;
        }
    }

    c = pipe(sigpipe);
    if ( c ) {
        fprintf(stderr,
            "%s: error '%s' from pipe()\n",
            prog, strerror(errno));
        exit(1);
    }

    dpy = XOpenDisplay(display);
    if ( !dpy ) {
        fprintf(stderr,
            "%s: XOpenDisplay '%s' failed\n",
            prog, XDisplayName(display));
        exit(1);
    }

    client_in  = STDIN_FILENO;
    client_out = STDOUT_FILENO;

    for ( c = 0; c < A_SIZE(common_signals); c++ ) {
        signal(common_signals[c], common_signal_handler);
    }

    /* setup error handler or KeyGrab() might be fatal */
    orig_err = XSetErrorHandler(x_error_proc);

    if ( w == 0 ) {
        w = RootWindow(dpy, 0);
        if ( byname != NULL ) {
            if ( (w = window_by_name(dpy, w, byname)) == 0 ) {
                fprintf(stderr,
                    "%s: cannot find window with name '%s'\n",
                    prog, byname);
                usage();
                exit(1);
            }
            #if _DEBUG
            fprintf(stderr, "%s: found window %#lx with name '%s'\n",
                prog, (unsigned long)w, byname);
            #endif
        }
    }

    KEY_SETUP(dpy, w);

    c = do_dbus_proc();

    for (;;) {
        const char *key_str = NULL;
        Bool got_one = False;

        if ( got_common_signal ) {
            break;
        }

        if ( XPending(dpy) ) {
            got_one = True;

            XNextEvent(dpy, &ev);

            switch ( ev.type ) {
            case KeyPress:
                /* fall through */
            case KeyRelease:
                key_str = handle_key(ev.type, &ev.xkey);
                #if _DEBUG
                fprintf(stderr, "%s: got key '%s'\n",
                     prog, key_str ? key_str : "[unknown]");
                #endif
                break;
            default:
                break;
            }
        }

        init_poll_data();
        ADD_POLL_RD(client_in);
        ADD_POLL_RD(PIPE_RFD);
        ADD_POLL_RD(-1);
        ADD_POLL_WR(client_out);
        ADD_POLL_RD(dbus_fd); /* might be -1, which is OK */
        DO_POLL_NOW(c, 0);

        if ( got_common_signal ) {
            break;
        }
        if ( (poll_err_fd = check_poll_data_error()) != 0 ) {
            poll_err_fd--;
            if ( poll_err_fd == dbus_fd ) {
                close(dbus_fd);
                dbus_fd = -1;
                fprintf(stderr, "%s: error dbus coprocess\n", prog);
            } else {
                break;
            }
        }

        if ( c > 0 && poll_fds[DBUS_PROC_POLL_IDX].revents & POLLIN ) {
            if ( ! dbus_proc_relay(dbus_fd, client_out) ) {
                break;
            }
        }

        if ( c > 0 && (poll_fds[0].revents & POLLIN) ) {
            if ( ! input_and_reply(dpy, &w, client_in, client_out) ) {
                break;
            }

            got_one = True;
        }

        if ( got_one == True && key_str == NULL ) {
            continue;
        }

        dpy_fd = ConnectionNumber(dpy);
        init_poll_data();
        ADD_POLL_RD(client_in);
        ADD_POLL_RD(PIPE_RFD);
        ADD_POLL_RD(dpy_fd);
        ADD_POLL_WR(key_str == NULL ? -1 : client_out);
        ADD_POLL_RD(dbus_fd); /* might be -1, which is OK */
        DO_POLL_NOW(c, -1);

        if ( got_common_signal ) {
            break;
        }
        if ( (poll_err_fd = check_poll_data_error()) != 0 ) {
            poll_err_fd--;
            if ( poll_err_fd == dbus_fd ) {
                close(dbus_fd);
                dbus_fd = -1;
                fprintf(stderr, "%s: error dbus coprocess\n", prog);
            } else {
                break;
            }
        }

        if ( c < 1 ) {
            continue;
        }

        if ( poll_fds[DBUS_PROC_POLL_IDX].revents & POLLIN ) {
            if ( ! dbus_proc_relay(dbus_fd, client_out) ) {
                break;
            }
        }

        if ( poll_fds[0].revents & POLLIN ) {
            if ( ! input_and_reply(dpy, &w, client_in, client_out) ) {
                break;
            }
        }

        if ( key_str != NULL && (poll_fds[3].revents & POLLOUT) ) {
            int l;
            char buf[MAX_LINEOUT_SIZE];

            l = snprintf(buf, sizeof(buf), "%s\n", key_str);
            TERMINATE_CHARBUF(buf, l);

            /* TODO error check */
            if ( client_output_str(client_out, buf) < 0 ) {
                fprintf(stderr, "%s: error on client write '%s'\n",
                    prog, buf);
                break;
            }
        }
    } /* end for (;;) */

    c = collect_dbus_proc();

    ssave_enable();
    XSetErrorHandler(orig_err);
    KEY_SETDOWN(dpy, w);
    XCloseDisplay(dpy);

    if ( got_common_signal ) {
        fprintf(stderr,
            "%s: exiting on signal %d\n",
            prog, (int)got_common_signal);
    }

    return 0;
}
