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


#include <errno.h>
#include <fcntl.h>
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

#include <gio/gio.h>

#include "dbus_gio.h"

#ifndef EWOULDBLOCK
#define EWOULDBLOCK EAGAIN
#endif

#undef A_SIZE
#define A_SIZE(a) (sizeof(a) / sizeof((a)[0]))

/* signal handler for specified quit signal,
 * (system signal, not glib)
 */
volatile sig_atomic_t got_quit_signal = 0;
static void
handle_quit_signal(int s);
/* signal handler for glib (app arbitrary) quit signals */
int glib_quit_signal = SIGTERM;
static void
on_glib_quit_signal(gpointer user_data);
/* signal handler for glib signals (i.e., callback) */
static void
on_glib_signal(GDBusProxy *proxy,
               gchar      *sender_name,
               gchar      *signal_name,
               GVariant   *parameters,
               gpointer    user_data);
/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const char *prog);


/* EXTERNAL API:
 * start (fork) coprocess to handle glib2 gio loop for
 * dbus signals (e.g., keys that some X desktop envs grab
 * and dole out through dbus)
 */
int
start_dbus_gio_proc(const dbus_proc_in *in, dbus_proc_out *out)
{
    int    p[2] = {-1, -1};
    int    dn, fd_wr;
    size_t i;

    out->fd_rd = -1;

    dn = open("/dev/null", O_RDONLY);
    if ( dn < 0 ) {
        out->err_no = errno;
        return -1;
    }

    /* pipe write end may be set by caller,
     * but if it is not, pipe is made here
     */
    if ( in->fd_wr < 0 ) {
        int s;

        if ( (s = pipe(p)) != 0 ) {
            out->err_no = errno;
            close(dn);
            return -1;
        }

        out->fd_rd = p[0];
        fd_wr = p[1];
    } else {
        fd_wr = in->fd_wr;
    }

    out->proc_pid = fork();
    if ( out->proc_pid > 0 ) {
        out->err_no = 0;
        close(dn);
        return 0;
    } else if ( out->proc_pid < 0 ) {
        out->err_no = errno;

        if ( p[0] >= 0 || p[1] >= 0 ) {
            close(p[0]);
            close(p[1]);
            out->fd_rd = -1;
        }

        close(dn);
        return -1;
    }

    /* fork succeeded, child here */
    for ( i = 0; i < in->num_sig; i++ ) {
        signal(in->def_sig[i], SIG_DFL);
    }

    if ( in->quit_sig == SIGTERM ) {
        glib_quit_signal = SIGINT;
    }

    if ( in->quit_sig > 0 ) {
        signal(in->quit_sig, handle_quit_signal);
    }

    if ( fd_wr == 0 && (fd_wr = dup2(fd_wr, 1)) == -1 ) {
        if ( in->progname != NULL ) {
            fprintf(stderr,
              "%s: failed to dup input fd to 1; '%s'\n",
              in->progname, strerror(errno));
        }
        _exit(1);
    }

    if ( dn != 0 && dup2(dn, 0) == -1 ) {
        if ( in->progname != NULL ) {
            fprintf(stderr,
              "%s: failed to dup /dev/null to 0; '%s'\n",
              in->progname, strerror(errno));
        }
        _exit(1);
    }
    if ( dn != 0 ) {
        close(dn);
    }

    if ( fd_wr != 1 && dup2(fd_wr, 1) == -1 ) {
        if ( in->progname != NULL ) {
            fprintf(stderr,
              "%s: failed to dup input fd to 1; '%s'\n",
              in->progname, strerror(errno));
        }
        _exit(1);
    }
    if ( fd_wr != 1 ) {
        close(fd_wr);
    }

    _exit(dbus_gio_main(in->progname));
}

static void
handle_quit_signal(int s)
{
    /* for form, or future */
    got_quit_signal = s;

    /* this is working with on_glib_quit_signal() below */
    kill(getpid(), glib_quit_signal);
    /* need to exit unless it is possible to
     * interrupt the glib main loop
     * _exit(1); */
}

const gchar *signal_wanted = "MediaPlayerKeyPressed";

/* signal handler for glib (app arbitrary) quit signals */
static void
on_glib_quit_signal(gpointer user_data)
{
    GMainLoop *loop = (GMainLoop *)user_data;
    g_main_loop_quit(loop);
}

/* signal handler for glib signals */
static void
on_glib_signal(GDBusProxy *proxy,
               gchar      *sender_name,
               gchar      *signal_name,
               GVariant   *params,
               gpointer    user_data)
{
    size_t  len;
    ssize_t wret, tot;
    gchar   *param_str = NULL;
    int     fd = (int)(ptrdiff_t)user_data;

    if ( strcasecmp(signal_wanted, signal_name) ) {
        return;
    }

    g_variant_get_child(params, 1, "s", &param_str);

    if ( param_str == NULL ) {
        return;
    }

    len = strlen(param_str);

    for ( tot = 0;; ) {
        wret = write(fd, param_str + tot, len - tot);
        if ( wret < 0 ) {
            if ( errno != EINTR ) {
                continue;
            }
            /* fatal */
            _exit(1);
        }

        tot += wret;
        if ( tot < len ) {
            if ( errno == EAGAIN || errno == EWOULDBLOCK ) {
                /* sleep(1); */
                poll(NULL, 0, 500);
                continue;
            } else {
                _exit(1);
            }
        }

        break;
    }

    /*
     * glib headers do not document whether an alloc'd string is
     * returned by g_variant_get_child, but that makes the most
     * sense, particularly since that funk takes a format arg.
     * TODO: find docs and confirm.
     * UPDATE: docs at glib site,
     *     https://developer.gnome.org/glib/stable/glib-GVariant.html
     * do not say that return should be g_free()'d.
     * UPDATE: docs at
     *     https://developer.gnome.org/glib/stable/
     *      gvariant-format-strings.html
     * state that g_variant_get with format "s" returns alloc'd
     * string that should be g_free()'d (g_variant_get_child
     * uses g_variant_get)
     */
    g_free(param_str);
}

#define _PUT_DBUS_PATH_ETC(v) { \
     "org." v ".SettingsDaemon", \
    "/org/" v "/SettingsDaemon/MediaKeys", \
     "org." v ".SettingsDaemon.MediaKeys", \
            v \
    }
struct {
    const gchar *m1;
    const gchar *m2;
    const gchar *m3;
    const  char *nm;
} path_attempts[] = {
    _PUT_DBUS_PATH_ETC("freedesktop"), /* found in xdg-screensaver */
    _PUT_DBUS_PATH_ETC("xfce"),        /* just a guess */
    _PUT_DBUS_PATH_ETC("unity"),       /* just a guess */
    _PUT_DBUS_PATH_ETC("mate"),        /* found in xdg-screensaver */
    _PUT_DBUS_PATH_ETC("cinnamon"),    /* found in xdg-screensaver */
    _PUT_DBUS_PATH_ETC("gnome")        /* found in xdg-screensaver */
};

GDBusProxy *proxy_all[A_SIZE(path_attempts)];

/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const char *prog)
{
    size_t          i;
    GDBusProxy      *proxy;
    GDBusProxyFlags flags  = 0;
    GMainLoop       *loop  = NULL;
    GError          *error = NULL;
    int             outfd  = 1; /* standard output */

    loop = g_main_loop_new(NULL, FALSE);
    if ( loop == NULL ) {
        return 1;
    }

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        error = NULL;

        proxy = g_dbus_proxy_new_for_bus_sync(G_BUS_TYPE_SESSION,
            flags,
            NULL, /* GDBusInterfaceInfo */
            path_attempts[i].m1,
            path_attempts[i].m2,
            path_attempts[i].m3,
            NULL, /* GCancellable */
            &error);

        if ( error || proxy == NULL ) {
            if ( prog != NULL ) {
                fprintf(stderr, "%s: failed proxy for '%s'\n",
                        prog, path_attempts[i].nm);
            }
            proxy_all[i] = NULL;
            continue;
        }

        proxy_all[i] = proxy;

        g_signal_connect(proxy, "g-signal",
                         G_CALLBACK(on_glib_signal),
                         (gpointer)(ptrdiff_t)outfd);

        g_dbus_proxy_call(proxy, "GrabMediaPlayerKeys",
                          g_variant_new("(su)", "wxmav", 0),
                          G_DBUS_CALL_FLAGS_NO_AUTO_START,
                          -1, NULL, NULL, NULL);
    }

    g_unix_signal_add(glib_quit_signal, on_glib_quit_signal,
                      (gpointer)loop);

    g_main_loop_run(loop);

    g_main_loop_unref(loop);

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        proxy = proxy_all[i];

        if ( proxy == NULL ) {
            continue;
        }

        g_dbus_proxy_call(proxy, "ReleaseMediaPlayerKeys",
                          g_variant_new("(su)", "wxmav", 0),
                          G_DBUS_CALL_FLAGS_NO_AUTO_START,
                          -1, NULL, NULL, NULL);

        g_object_unref(proxy);
    }

    return 0;
}

