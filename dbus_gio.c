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

/* signal handler for specified quit signal,
 * (system signal, not glib)
 */
volatile sig_atomic_t got_quit_signal = 0;
static void
handle_quit_signal(int s);
/* signal handler for glib signals */
static void
on_glib_signal(GDBusProxy *proxy,
               gchar      *sender_name,
               gchar      *signal_name,
               GVariant   *parameters,
               gpointer    user_data);
/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const char *prog);


/* EXTERNAL:
 * start (fork) coprocess to handle glib2 gio loop for
 * dbus signals (e.g., keys that some X desktop envs grab
 * and dole out through dbus)
 */
int
start_dbus_gio_proc(const dbus_proc_in *in, dbus_proc_out *out)
{
    int p[2] = {-1, -1};
    int dn, fd_wr;
    size_t i;

    out->fd_rd = -1;

    dn = open("/dev/null", O_RDONLY);
    if ( dn < 0 ) {
        out->err_no = errno;
        return -1;
    }

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

        if ( p[0] > 0 ) {
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
    _exit(1);
}

/* signal handler for glib signals */
static void
on_glib_signal(GDBusProxy *proxy,
               gchar      *sender_name,
               gchar      *signal_name,
               GVariant   *parameters,
               gpointer    user_data)
{
    gchar *param_str;
    size_t len;
    ssize_t wret, tot = 0;
    int   fd = (int)(ptrdiff_t)user_data;

    param_str = g_variant_print(parameters, TRUE);
    len = strlen(param_str);

    /* g_print("%s: %s\n", signal_name, param_str); */
    for (;;) {
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
        } else {
            break;
        }
    }

    g_free(param_str);
}

/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const char *prog)
{
    GDBusProxy      *proxy;
    GDBusProxyFlags flags;
    GMainLoop       *loop = NULL;
    GError          *error = NULL;

    int dt_idx = -1;
    int outfd = 1; /* standard output */

    loop = g_main_loop_new(NULL, FALSE);

    proxy = g_dbus_proxy_new_for_bus_sync(G_BUS_TYPE_SESSION,
        flags,
        NULL, /* GDBusInterfaceInfo */
        "org.xfce.SettingsDaemon",
        "/org/xfce/SettingsDaemon/MediaKeys",
        "org.xfce.SettingsDaemon.MediaKeys",
        NULL, /* GCancellable */
        &error);

    if ( error ) {
        if ( prog ) {
            fprintf(stderr, "%s: failed proxy 'xfce'\n",
                prog);
        }

        error = NULL;
        proxy = g_dbus_proxy_new_for_bus_sync(G_BUS_TYPE_SESSION,
            flags,
            NULL, /* GDBusInterfaceInfo */
            "org.mate.SettingsDaemon",
            "/org/mate/SettingsDaemon/MediaKeys",
            "org.mate.SettingsDaemon.MediaKeys",
            NULL, /* GCancellable */
            &error);

        if ( error ) {
            if ( prog ) {
                fprintf(stderr, "%s: failed proxy 'mate'\n",
                    prog);
            }

            error = NULL;
            proxy = g_dbus_proxy_new_for_bus_sync(G_BUS_TYPE_SESSION,
                flags,
                NULL, /* GDBusInterfaceInfo */
                "org.gnome.SettingsDaemon",
                "/org/gnome/SettingsDaemon/MediaKeys",
                "org.gnome.SettingsDaemon.MediaKeys",
                NULL, /* GCancellable */
                &error);

            if ( error ) {
                if ( prog ) {
                    fprintf(stderr, "%s: failed gnome dbus, exiting\n",
                        prog);
                }
                _exit(1);
            } else {
                dt_idx = 2;
            }
        } else {
            dt_idx = 2;
        }
    } else {
        dt_idx = 1;
    }

    g_signal_connect(proxy, "g-signal",
                    G_CALLBACK(on_glib_signal),
                    (gpointer)(ptrdiff_t)outfd);

    g_dbus_proxy_call(proxy, "GrabMediaPlayerKeys",
          g_variant_new("(su)", "wxmav", 0),
          G_DBUS_CALL_FLAGS_NO_AUTO_START,
          -1,
          NULL, NULL, NULL);

    g_main_loop_run(loop);

    /* out: (Release may not be necessary) */
    g_dbus_proxy_call(proxy, "ReleaseMediaPlayerKeys",
               g_variant_new("(s)", "ExampleCCode"),
               G_DBUS_CALL_FLAGS_NO_AUTO_START,
               -1,
               NULL, NULL, NULL);

    if ( proxy != NULL ) {
        g_object_unref(proxy);
    }

    if ( loop != NULL ) {
        g_main_loop_unref(loop);
    }

    switch ( dt_idx ) {
    case 1:
        g_free("org.xfce.SettingsDaemon");
        g_free("/org/xfce/SettingsDaemon/MediaKeys");
        g_free("org.xfce.SettingsDaemon.MediaKeys");
    case 2:
        g_free("org.mate.SettingsDaemon");
        g_free("/org/mate/SettingsDaemon/MediaKeys");
        g_free("org.mate.SettingsDaemon.MediaKeys");
    case 3:
        g_free("org.gnome.SettingsDaemon");
        g_free("/org/gnome/SettingsDaemon/MediaKeys");
        g_free("org.gnome.SettingsDaemon.MediaKeys");
    }

    return 0;
}

