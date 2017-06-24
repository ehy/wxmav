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
/* SIZE_MAX might be in limits.h (BSD), or in stdint.h */
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <gio/gio.h>
#include <glib-unix.h>

#include "x-aud-key-srv.h"
#include "dbus_gio.h"

#ifndef EAGAIN
#define EAGAIN EWOULDBLOCK
#endif

#ifndef SIZE_MAX
#define SIZE_MAX ULONG_MAX
#endif

/* token separator for multi-token lines */
#define _TSEPC ':'
#define _TSEPS ":"

/* signal handler for specified quit signal,
 * (system signal, not glib)
 */
static void
handle_quit_signal(int s);
/* signal handler for glib (app arbitrary) quit signals */
int glib_quit_signal = SIGTERM;
static gboolean
on_glib_quit_signal(gpointer user_data);
/* signal handler for glib signals (i.e., callback) */
static void
on_glib_signal(GDBusProxy *proxy,
               gchar      *sender_name,
               gchar      *signal_name,
               GVariant   *parameters,
               gpointer    user_data);
/* event on read end of client pipe */
static gboolean
on_mpris_fd_read(gint fd, GIOCondition condition, gpointer user_data);
/* read a line from a pipe, persistently until '\n' appears */
static ssize_t
read_line(char **buf, size_t *bs, FILE *fptr);\
/* remove trailing '\n' */
static int
unnl(char *p);
/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const dbus_proc_in *in);

/* MPRIS2 player control */
static int
start_mpris_service(void);
static void
stop_mpris_service(void);

/* global FILE for read end of client pipe */
FILE *mpris_rfp = NULL;
/* global FILE for writeing to client pipe */
FILE *mpris_wfp = NULL;

typedef struct _mpris_data_struct {
    /* glib items */
    GMainLoop         *loop;
    GDBusNodeInfo     *node_info;
    gint              bus_id;
    GDBusConnection   *connection;
    /* IO with client */
    char              *buf;
    size_t            bufsz;
    FILE              *fprd;
    FILE              *fpwr;
} mpris_data_struct;

mpris_data_struct mpris_data = {
    NULL, NULL, 0, NULL,
    NULL, 0, NULL, NULL
};


/* EXTERNAL API:
 * start (fork) coprocess to handle glib2 gio loop for
 * dbus signals (e.g., keys that some X desktop envs grab
 * and dole out through dbus)
 */
int
start_dbus_coproc(const dbus_proc_in *in,
                  dbus_proc_out *out,
                  char **av)
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
        if ( pipe(p) != 0 ) {
            out->err_no = errno;
            close(dn);
            return -1;
        }

        out->fd_rd = p[PIPE_RFD_INDEX];
        fd_wr      = p[PIPE_WFD_INDEX];
    } else {
        fd_wr = in->fd_wr;
    }

    /* fork child coprocess */
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
    p_exit = _exit;

    for ( i = 0; i < in->num_sig; i++ ) {
        signal(in->def_sig[i], SIG_DFL);
    }

    if ( in->quit_sig == SIGTERM ) {
        glib_quit_signal = SIGINT;
    }

    if ( in->quit_sig > 0 ) {
        signal(in->quit_sig, handle_quit_signal);
    }

    if ( av != NULL ) {
        const char *fmt = "%s:%ld coprocess";
        const char *prg = in->progname != NULL ? in->progname : prog;
        pid_t      ppid = getppid();
        size_t     mlen = strlen(av[0]) + 1;
        int        r;

        r = snprintf(av[0], mlen, fmt, prg, (long)ppid);
        av[0][mlen - 1] = '\0';
        if ( r < --mlen ) {
            memset(av[0] + r, '\0', mlen - r);
        }

        prog = av[0];
    } else if ( in->progname != NULL ) {
        prog = in->progname;
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

    _exit(dbus_gio_main(in));
}

static void
handle_quit_signal(int s)
{
    /* for form, or future */
    got_common_signal = s;

    /* this is working with on_glib_quit_signal() below */
    kill(getpid(), glib_quit_signal);
    /* need to exit unless it is possible to
     * interrupt the glib main loop
     * p_exit(1); */
}

/* signal handler for glib (app arbitrary) quit signals */
static gboolean
on_glib_quit_signal(gpointer user_data)
{
    GMainLoop *loop = (GMainLoop *)user_data;
    g_main_loop_quit(loop);
    return TRUE;
}

const gchar *signal_wanted = "MediaPlayerKeyPressed";

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
    if ( client_output(fd, param_str, len) != len ) {
        p_exit(1);
    }

    /*
     * docs at
     *     https://developer.gnome.org/glib/stable/
     *      gvariant-format-strings.html
     * state that g_variant_get with format "s" returns alloc'd
     * string that should be g_free()'d (g_variant_get_child
     * uses g_variant_get)
     */
    g_free(param_str);
}

typedef struct _dbus_path_etc {
    const gchar *well_known_name; /*  org.foo.BarDaemon */
    const gchar *object_path;     /* /org/foo/BarDaemon/BazBits */
    const gchar *interface;       /*  org.foo.BarDaemon.BazBits */
    const  char *domain_name;     /*      foo */
} dbus_path_etc;
#define _PUT_DBUS_PATH_ETC(v) { \
     "org." v ".SettingsDaemon", \
    "/org/" v "/SettingsDaemon/MediaKeys", \
     "org." v ".SettingsDaemon.MediaKeys", \
            v \
    }
dbus_path_etc path_attempts[] = {
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
dbus_gio_main(const dbus_proc_in *in)
{
    size_t          i;
    GDBusProxy      *proxy;
    GDBusProxyFlags flags  = 0;
    GMainLoop       *loop  = NULL;
    GError          *error = NULL;
    int             rmpris = 0;
    int             outfd  = 1; /* standard output */
    const char      *prg   = in->progname ? prog : NULL;

    loop = g_main_loop_new(NULL, FALSE);
    if ( loop == NULL ) {
        return 1;
    }

    mpris_data.loop = loop;

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        const char *nm = path_attempts[i].domain_name;

        error = NULL;
        proxy = g_dbus_proxy_new_for_bus_sync(G_BUS_TYPE_SESSION,
            flags,
            NULL, /* GDBusInterfaceInfo */
            path_attempts[i].well_known_name,
            path_attempts[i].object_path,
            path_attempts[i].interface,
            NULL, /* GCancellable */
            &error);

        if ( error != NULL || proxy == NULL ) {
            if ( prg != NULL ) {
                fprintf(stderr, "%s: failed proxy for '%s'\n",
                        prg, nm);
            }
            proxy_all[i] = NULL;
            continue;
        }

        proxy_all[i] = proxy;

        g_signal_connect(proxy, "g-signal",
                         G_CALLBACK(on_glib_signal),
                         (gpointer)(ptrdiff_t)outfd);

        g_dbus_proxy_call(proxy, "GrabMediaPlayerKeys",
                          g_variant_new("(su)", in->app_name, 0),
                          G_DBUS_CALL_FLAGS_NO_AUTO_START,
                          -1, NULL, NULL, NULL);
    }

    g_unix_signal_add(glib_quit_signal, on_glib_quit_signal,
                      (gpointer)loop);

    if ( mpris_fd_read >= 0 && mpris_fd_write >= 0 ) {
        if ( (mpris_rfp = fdopen(mpris_fd_read, "r")) == NULL ) {
            perror("fdopen(mpris_fd_read, \"r\") (MPRIS2 coproc)");
            p_exit(1);
        }

        mpris_data.fprd = mpris_rfp;

        if ( (mpris_wfp = fdopen(mpris_fd_write, "w")) == NULL ) {
            perror("fdopen(mpris_fd_write, \"w\") (MPRIS2 coproc)");
            fclose(mpris_rfp);
            close(mpris_fd_write);
            p_exit(1);
        }

        mpris_data.fpwr = mpris_wfp;

        /* NOTE: start with line buffering writes, full buffering
         * with fflush() might be needed eventually, so use fflush
         * after all line writes; then if multi-line writes are needed
         * just change this.
         */
        setvbuf(mpris_wfp, NULL, _IOLBF, 0);

        g_unix_fd_add(mpris_fd_read,
                      G_IO_IN|G_IO_PRI|G_IO_ERR|G_IO_HUP|G_IO_NVAL,
                      on_mpris_fd_read,
                      (gpointer)&mpris_data);
    }

    g_main_loop_run(loop);

    g_main_loop_unref(loop);

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        proxy = proxy_all[i];

        if ( proxy == NULL ) {
            continue;
        }

        g_dbus_proxy_call(proxy, "ReleaseMediaPlayerKeys",
                          g_variant_new("(s)", in->app_name),
                          G_DBUS_CALL_FLAGS_NO_AUTO_START,
                          -1, NULL, NULL, NULL);

        g_object_unref(proxy);
    }

    /* ensure MPRIS2 support is stopped */
    stop_mpris_service();

    /* if got quit signal (got_common_signal), reraise */
    if ( got_common_signal ) {
        if ( prg != NULL ) {
            fprintf(stderr,
                "%s (dbus coproc): caught and re-raising signal %d\n",
                prg, (int)got_common_signal);
        }
        signal((int)got_common_signal, SIG_DFL);
        raise((int)got_common_signal);
    }

    if ( prg != NULL ) {
        fprintf(stderr,
            "%s (dbus coproc): return from main (exit)\n", prg);
    }

    return 0;
}


/**********************************************************************/
/*                    Section for MPRIS2 code                         */
/**********************************************************************/

/* XML (blech) description of top node and children,
 * gets passed to g_dbus_node_info_new_for_xml() to
 * buy a GDBusNodeInfo *
 */
static const char mpris_node_xml[];

/*
#define BUS_NAME "org.mpris.MediaPlayer2.<name>"
#define OBJECT_NAME "/org/mpris/MediaPlayer2"
#define PLAYER_INTERFACE "org.mpris.MediaPlayer2.Player"
#define PROPERTIES_INTERFACE "org.freedesktop.DBus.Properties"
*/
const gchar *mpris_path    = "/org/mpris/MediaPlayer2";
const gchar *mpris_player  = "org.mpris.MediaPlayer2.Player";
const gchar *fdesk_props   = "org.freedesktop.DBus.Properties";
const gchar *mpris_thisname= NULL;
#define MPRIS2_NAME_BASE "org.mpris.MediaPlayer2"

static void
put_mpris_thisname(const char *thisname)
{
    size_t len = sizeof(MPRIS2_NAME_BASE) + strlen(thisname) + 2;
    int    r;
    gchar  *p;

    if ( mpris_thisname != NULL ) {
        free((void *)mpris_thisname);
    }

    p = xmalloc(len);

    r = snprintf(p, len, "%s.%s", MPRIS2_NAME_BASE, thisname);
    p[len - 1] = '\0';

    mpris_thisname = p;
}

static void
alloc_read_buffer(int readfd, char **buf, size_t *bs)
{
    struct stat sb;

    if ( fstat(readfd, &sb) ) {
        *bs = BUFSIZ;
    } else {
        *bs = (size_t)sb.st_blksize;
    }

    *buf = xmalloc(*bs);
}

#if       HAVE_GETDELIM
/* note getdelim vs. getline: the latter would be suitable,
 * but the common use of the name might be a problem; use
 * of the former is just a safe alternative at essentially
 * no cost (they're likely the same code)
 */
static ssize_t
read_line(char **buf, size_t *bs, FILE *fptr)
{
    ssize_t ret;

    if ( *buf == NULL ) {
        alloc_read_buffer(fileno(fptr), buf, bs);
    }

    while ( (ret = getdelim(buf, bs, '\n', fptr)) < 1 ) {
        int e = errno;
        if ( got_common_signal ) {
            return -1;
        } else if ( ferror(fptr) && (e == EAGAIN || e == EINTR) ) {
            clearerr(fptr);
        } else if ( ferror(fptr) ) {
            return -1;
        } else if ( feof(fptr) ) {
            return 0;
        }
        sleep(1);
    }

    return ret;
}
#else  /* HAVE_GETDELIM */
static ssize_t
rd_fgets(char **buf, size_t *bs, FILE *fptr)
{
    char *ret;

    if ( *buf == NULL ) {
        alloc_read_buffer(fileno(fptr), buf, bs);
    }

    while ( (ret = fgets(*buf, *bs, fptr)) == NULL ) {
        int e = errno;
        if ( got_common_signal ) {
        } else if ( ferror(fptr) && (e == EAGAIN || e == EINTR) ) {
            clearerr(fptr);
        } else if ( ferror(fptr) ) {
            return -1;
        } else if ( feof(fptr) ) {
            return 0;
        }
        sleep(1);
    }

    return strlen(*buf);
}

static ssize_t
read_line(char **buf, size_t *bs, FILE *fptr)
{
    ssize_t s = rd_fgets(buf, bs, fptr);

    while ( s > 0 && (*buf)[s - 1] != '\n' ) {
        char  *tbuf = NULL;
        size_t slen = 0;
        ssize_t s2 = rd_fgets(&buf, &slen, fptr);

        if ( s2 > 0 ) {
            /* xrealloc exits on error, so it is no matter
             * that we assign directly to source pointer */
            slen = s;
            s += s2;
            *bs = BUFSIZ + s;
            *buf = xrealloc(*buf, *bs);
            slen = strlcpy((*buf) + slen, tbuf, *bs - slen);
            if ( slen != s2 ) {
                fprintf(stderr, "%s: internal error (strlcpy)\n", prog);
                p_exit(1);
            }
        }

        free(tbuf);

        if ( s2 < 1 ) {
            break;
        }
    }

    return s;
}
#endif /* HAVE_GETDELIM */

static ssize_t
read_line_dat(mpris_data_struct *dat)
{
    return read_line(&dat->buf, &dat->bufsz, dat->fprd);
}

static int
unnl(char *p)
{
    size_t l;
    if ( p == NULL ) return -1;
    l = strlen(p);
    if ( l && --l && p[l] == '\n' ) {
        p[l] = '\0';
        return 1;
    }
    return 0;
}

/* event on read end of client pipe */
static gboolean
on_mpris_fd_read(gint fd, GIOCondition condition, gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    static size_t bufsz = 0;  /* buffer from dat not used, */
    static char  *buf = NULL; /* in case of reentrence */
    static const char  *pfx = "mpris:";
    static const size_t pfxsz = sizeof("mpris:") - 1;

    ssize_t rdlen;
    char    *p;
    const GIOCondition errbits = G_IO_HUP | G_IO_ERR | G_IO_NVAL;

    if ( fd != fileno(mpris_rfp) ) {
        fprintf(stderr, "%s: %s on mpris client read fd unexpected\n",
                prog);

        return FALSE;
    }

    if ( condition & errbits ) {
        GMainLoop *loop = dat->loop;

        fprintf(stderr, "%s: %s on mpris client read fd; quitting\n",
                prog, condition & G_IO_HUP ? "close" : "error");

        g_main_loop_quit(loop);

        return FALSE;
    }

    if ( buf == NULL ) {
        bufsz = MAX(bufsz, 32);
        buf = xmalloc(bufsz);
    }

    rdlen = read_line(&buf, &bufsz, mpris_rfp);
    if ( rdlen < 1 ) {
        /* whether EOF or error, that's it for the other one */
        return FALSE;
    }

    unnl(buf);

    fprintf(stderr, "%s: mpris client read: '%s'\n", prog, buf);

    /* not mpris prefix? */
    if ( strncasecmp(buf, pfx, pfxsz) ) {
        return TRUE;
    }

    p = buf + pfxsz;
    rdlen -= pfxsz;

    if ( S_CI_EQ(p, "on") ) {
        start_mpris_service();
    } else if ( S_CI_EQ(p, "off") ) {
        stop_mpris_service();
    }

    return TRUE;
}

/*
** org.mpris.MediaPlayer2 [base]
*/

/* a handshake proc for all procs that communicate with client */
#define _EXCHGHS_WR_ERR -1
#define _EXCHGHS_RD_ERR -2
#define _EXCHGHS_ALL_OK  0
#define _EXCHGHS_ACKREJ  1
#define _EXCHGHS_ACK_NG  2
static int
_exchange_handshake(mpris_data_struct *dat,
                    const char        *ini,
                    const char        *ack,
                    const char        *property_name)
{
    ssize_t rdlen;
    int ret = _EXCHGHS_ALL_OK;

    fprintf(dat->fpwr, "%s\n", ini);
    fflush(dat->fpwr);
    if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(stderr, "%s error writing to mpris client (b)\n", prog);
        return _EXCHGHS_WR_ERR;
    }

    fprintf(stderr, "%s sent ini '%s' to client\n",
        prog, ini);

    rdlen = read_line_dat(dat);
    if ( rdlen < 1 ) {
        /* whether EOF or error, that's it for the other one */
        fprintf(stderr, "%s unexpected mpris read end (%ld) (b)\n",
            prog, (long int)rdlen);
        return _EXCHGHS_RD_ERR;
    }

    unnl(dat->buf);

    fprintf(stderr, "%s got ack '%s' from client\n",
        prog, dat->buf);

    /* rejected? */
    if ( strcmp(dat->buf, "UNSUPPORTED") == 0 ) {
        fprintf(stderr, "%s mpris client ack for '%s' is '%s'\n",
            prog, ini, dat->buf);
        return _EXCHGHS_ACKREJ;
    }

    /* ack */
    if ( strcmp(dat->buf, ack) ) {
        fprintf(stderr, "%s unexpected mpris client ack '%s'\n",
            prog, dat->buf);
        ret |= _EXCHGHS_ACK_NG;
    }

    fprintf(stderr, "%s writeing '%s' to client\n",
        prog, property_name);

    fprintf(dat->fpwr, "%s\n", property_name);
    fflush(dat->fpwr);
    if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(stderr, "%s error writing to mpris client (c)\n", prog);
        return _EXCHGHS_WR_ERR;
    }

    rdlen = read_line_dat(dat);
    if ( rdlen < 1 ) {
        fprintf(stderr, "%s unexpected mpris read end (%ld) (c)\n",
            prog, (long int)rdlen);
        return _EXCHGHS_RD_ERR;
    }

    unnl(dat->buf);

    return ret;
}

static void
_mpris_call_method(GDBusConnection *connection,
                   const gchar *sender,
                   const gchar *object_path,
                   const gchar *interface_name,
                   const gchar *method_name,
                   GVariant    *parameters,
                   GDBusMethodInvocation *invocation,
                   gpointer    user_data,
                   const char  *ini,
                   const char  *ack)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    char *p, *p2;
    ssize_t rdlen;
    int r;

#define _EXCHGHS_WR_ERR -1
#define _EXCHGHS_RD_ERR -2
#define _EXCHGHS_ALL_OK  0
#define _EXCHGHS_ACKREJ  1
#define _EXCHGHS_ACK_NG  2
    do {
    r = _exchange_handshake(dat, ini, ack, method_name);
    if ( r < 0 ) {
        fprintf(stderr, "%s mpris handshake %s error (b)\n",
            prog, r == _EXCHGHS_WR_ERR ? "write" : "read");
        p2 = r == _EXCHGHS_WR_ERR ? "IO ERROR: w" : "IO ERROR: r";
        break;
    } else if ( r != _EXCHGHS_ALL_OK ) {
        if ( r & _EXCHGHS_ACKREJ ) {
            /* client actively reject and expects no more */
            p2 = "ERROR: handshake rejected";
        } else {
            /* handshake wrong, client expects more */
            p2 = "ERROR: handshake incorrect";
        }
        break;
    }

    p = strchr(dat->buf, _TSEPC);
    if ( p == NULL ) {
        fprintf(stderr, "%s unexpected mpris type (%s) (c)\n",
            prog, dat->buf);
        p2 = "ERROR: format(c)"; break;
    }

    p2 = p++;
    *p2 = '\0';
    p2 = dat->buf;

	/* method takes arguments? */
	if ( S_CI_EQ(p2, "ARGS") ) {
        gsize ix;

        for ( ix = 0; p != NULL; ix++ ) {
            p2 = strsep(&p, _TSEPS);

            if ( *p2 == '\0' ) {
                fprintf(dat->fpwr, "%s\n", "");
            } else if ( S_CS_EQ(p2, "b") ) {
                gboolean v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%s\n",
                        v == TRUE ? "true" : "false");
            } else if ( S_CS_EQ(p2, "y") ) {
                guchar v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%u\n", (unsigned int)v);
            } else if ( S_CS_EQ(p2, "n") ) {
                gint16 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%d\n", (int)v);
            } else if ( S_CS_EQ(p2, "q") ) {
                guint16 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%u\n", (unsigned int)v);
            } else if ( S_CS_EQ(p2, "i") ) {
                gint32 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%d\n", (int)v);
            } else if ( S_CS_EQ(p2, "u") ) {
                guint32 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%u\n", (unsigned int)v);
            } else if ( S_CS_EQ(p2, "x") ) {
                gint64 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%lld\n", (long long)v);
            } else if ( S_CS_EQ(p2, "t") ) {
                guint64 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%llu\n", (unsigned long long)v);
            } else if ( S_CS_EQ(p2, "h") ) {
                gint32 v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%d\n", (int)v);
            } else if ( S_CS_EQ(p2, "d") ) {
                gdouble v;
                g_variant_get_child(parameters, ix, p2, &v);
                fprintf(dat->fpwr, "%f\n", (double)v);
            } else if ( S_CS_EQ(p2, "s") ||
                        S_CS_EQ(p2, "o") ||
                        S_CS_EQ(p2, "g") ) {
                gchar *v;
                g_variant_get_child(parameters, ix, p2, &v);
                if ( v == NULL ) {
                    v = "error";
                }
                fprintf(dat->fpwr, "%s\n", (const char *)v);
                g_free(v);
            }

            fflush(dat->fpwr);
        }

        if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
            fprintf(stderr, "%s error writing to mpris client (d)\n",
                prog);
        }

        rdlen = read_line_dat(dat);
        if ( rdlen < 1 ) {
            fprintf(stderr,
                "%s unexpected mpris read end (%ld) (d)\n",
                prog, (long int)rdlen);
            p2 = "ERROR: read(d)"; break;
        }

        unnl(dat->buf);

        p = strchr(dat->buf, _TSEPC);
        if ( p == NULL ) {
            fprintf(stderr, "%s unexpected mpris type (%s) (d)\n",
                prog, dat->buf);
            p2 = "ERROR: type(d)"; break;
        }

        p2 = p++;
        *p2 = '\0';
        p2 = dat->buf;
	}
    } while ( 0 );

	/* error herein */
    if ( strncmp(p2, "IO ERROR: ", 10) == 0 ) {
		g_dbus_method_invocation_return_error(
            invocation, G_DBUS_ERROR, G_DBUS_ERROR_IO_ERROR,
            "'%s' while performing %s.%s call",
            p2, interface_name, method_name);
	/* error herein */
    } else if ( strncmp(p2, "ERROR: ", 7) == 0 ) {
		g_dbus_method_invocation_return_error(
            invocation, G_DBUS_ERROR, G_DBUS_ERROR_SERVICE_UNKNOWN,
            "Error: internal I/O '%s' while performing %s.%s call",
            p2, interface_name, method_name);
	/* return type and value */
    } else if ( S_CI_EQ(p2, "UNSUPPORTED") ) {
		g_dbus_method_invocation_return_error(
            invocation, G_DBUS_ERROR, G_DBUS_ERROR_NOT_SUPPORTED,
            "Error: method %s.%s not supported",
            interface_name, method_name);
    } else if ( S_CI_EQ(p2, "VOID") ) {
		g_dbus_method_invocation_return_value(invocation, NULL);
	/* TODO: handle return types - before TrackList or Playlists
    } else if (  ) {
    */
    } else {
		g_dbus_method_invocation_return_error(
            invocation, G_DBUS_ERROR, G_DBUS_ERROR_UNKNOWN_METHOD,
            "Error: method %s.%s unknown",
            interface_name, method_name);
	}
}

static GVariant*
_mpris_get_property(GDBusConnection *connection,
                    const gchar *sender,
                    const gchar *object_path,
                    const gchar *interface_name,
                    const char  *property_name,
                    GError      **error,
                    gpointer    user_data,
                    const char  *ini,
                    const char  *ack)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    char *p, *p2;
    ssize_t rdlen;
	GVariant *result = NULL;

    if ( _exchange_handshake(dat, ini, ack, property_name) ) {
        fprintf(stderr, "%s mpris handshake '%s' failure (b)\n",
            prog, ini);
        return NULL;
    }

    p = strchr(dat->buf, _TSEPC);
    if ( p == NULL ) {
        fprintf(stderr, "%s unexpected mpris type (%s) (c)\n",
            prog, dat->buf);
        return NULL;
    }

    p2 = p++;
    *p2 = '\0';
    p2 = dat->buf;

    if ( S_CS_EQ(p2, "b") ) {
        gboolean b = strcasecmp(p, "true") == 0 ? TRUE : FALSE;
		result = g_variant_new_boolean(b);
    } else if ( S_CS_EQ(p2, "s") ) {
		result = g_variant_new_string(p);
    } else if ( S_CS_EQ(p2, "g") ) {
        gdouble d = atof(p);
		result = g_variant_new_double(d);
    } else if ( S_CS_EQ(p2, "as") ) {
		GVariantBuilder *builder =
            g_variant_builder_new(G_VARIANT_TYPE("as"));

        for ( ;; ) {
            rdlen = read_line_dat(dat);
            if ( rdlen < 1 ) {
                fprintf(stderr,
                    "%s unexpected mpris read end (%ld) (d)\n",
                    prog, (long int)rdlen);
                return NULL;
            }

            p2 = dat->buf;
            unnl(dat->buf);

            if ( S_CS_EQ(p2, ":END ARRAY:") ) {
                break;
            }

            g_variant_builder_add(builder, "s", p2);
        }

		result = g_variant_builder_end(builder);
		g_variant_builder_unref(builder);
    }

	return result;
}

static int
_mpris_set_property(GDBusConnection *connection,
                    const gchar *sender,
                    const gchar *object_path,
                    const gchar *interface_name,
                    const gchar *property_name,
                    GVariant    *value,
                    GError      **error,
                    gpointer    user_data,
                    const char  *ini,
                    const char  *ack)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    char *p, *p2;
    ssize_t rdlen;
	int result = 0;

    if ( _exchange_handshake(dat, ini, ack, property_name) ) {
        fprintf(stderr, "%s mpris handshake '%s' failure (b)\n",
            prog, ini);
        return result;
    }

    p = strchr(dat->buf, _TSEPC);
    if ( p == NULL ) {
        fprintf(stderr, "%s unexpected mpris reply '%s' (c)\n",
            prog, dat->buf);
        return result;
    }

    p2 = p++;
    if ( strcmp(p, "ok") ) {
        fprintf(stderr, "%s unexpected mpris property '%s' (c)\n",
            prog, property_name);
        return result;
    }

    *p2 = '\0';
    p2 = dat->buf;

    if ( S_CS_EQ(p2, "b") ) {
        gboolean v;
        g_variant_get(value, "b", &v);
        fprintf(dat->fpwr, "%s\n", v == TRUE ? "true" : "false");
    } else if ( S_CS_EQ(p2, "y") ) {
        guchar v;
        g_variant_get(value, "y", &v);
        fprintf(dat->fpwr, "%u\n", (unsigned int)v);
    } else if ( S_CS_EQ(p2, "n") ) {
        gint16 v;
        g_variant_get(value, "n", &v);
        fprintf(dat->fpwr, "%d\n", (int)v);
    } else if ( S_CS_EQ(p2, "q") ) {
        guint16 v;
        g_variant_get(value, "q", &v);
        fprintf(dat->fpwr, "%u\n", (unsigned int)v);
    } else if ( S_CS_EQ(p2, "i") ) {
        gint32 v;
        g_variant_get(value, "i", &v);
        fprintf(dat->fpwr, "%d\n", (int)v);
    } else if ( S_CS_EQ(p2, "u") ) {
        guint32 v;
        g_variant_get(value, "u", &v);
        fprintf(dat->fpwr, "%u\n", (unsigned int)v);
    } else if ( S_CS_EQ(p2, "x") ) {
        gint64 v;
        g_variant_get(value, "x", &v);
        fprintf(dat->fpwr, "%lld\n", (long long)v);
    } else if ( S_CS_EQ(p2, "t") ) {
        guint64 v;
        g_variant_get(value, "t", &v);
        fprintf(dat->fpwr, "%llu\n", (unsigned long long)v);
    } else if ( S_CS_EQ(p2, "h") ) {
        gint32 v;
        g_variant_get(value, "h", &v);
        fprintf(dat->fpwr, "%d\n", (int)v);
    } else if ( S_CS_EQ(p2, "d") ) {
        gdouble v;
        g_variant_get(value, "d", &v);
        fprintf(dat->fpwr, "%f\n", (double)v);
    } else if ( S_CS_EQ(p2, "s") ) {
        gchar *v;
        g_variant_get(value, "s", &v);
        if ( v == NULL ) {
            v = "error";
        }
        fprintf(dat->fpwr, "%s\n", (const char *)v);
        g_free(v);
    } else {
        return result;
    }

    fflush(dat->fpwr);
    if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(stderr, "%s error writing to mpris client (c)\n",
            prog);
        return result;
    }

    return 1;
}

/*
 * callbacks per interface
 */

/*
** org.mpris.MediaPlayer2 [base]
*/

/* base callbacks */
static void
cb_base_methods(GDBusConnection *connection,
                const gchar *sender,
                const gchar *object_path,
                const gchar *interface_name,
                const gchar *method_name,
                GVariant    *parameters,
                GDBusMethodInvocation *invocation,
                gpointer    user_data)
{
    static const char *ini = "base:method";
    static const char *ack = "method";

    _mpris_call_method(connection,
                       sender,
                       object_path,
                       interface_name,
                       method_name,
                       parameters,
                       invocation,
                       user_data,
                       ini, ack);
}

static GVariant*
cb_base_get_property(GDBusConnection *connection,
                     const gchar *sender,
                     const gchar *object_path,
                     const gchar *interface_name,
                     const char  *property_name,
                     GError      **error,
                     gpointer    user_data)
{
    static const char *ini = "base:getproperty";
    static const char *ack = "getproperty";

    return _mpris_get_property(connection,
                               sender,
                               object_path,
                               interface_name,
                               property_name,
                               error,
                               user_data,
                               ini, ack);
}

static int
cb_base_set_property(GDBusConnection *connection,
                     const gchar *sender,
                     const gchar *object_path,
                     const gchar *interface_name,
                     const gchar *property_name,
                     GVariant    *value,
                     GError      **error,
                     gpointer    user_data)
{
    static const char *ini = "base:setproperty";
    static const char *ack = "setproperty";

    return _mpris_set_property(connection,
                               sender,
                               object_path,
                               interface_name,
                               property_name,
                               value,
                               error,
                               user_data,
                               ini, ack);
}

static const GDBusInterfaceVTable base_interface_vtable = {
	cb_base_methods,
	cb_base_get_property,
	cb_base_set_property
};

/*
** org.mpris.MediaPlayer2.Player [player]
*/

/* player callbacks */
static void
cb_player_methods(GDBusConnection *connection,
                  const gchar *sender,
                  const gchar *object_path,
                  const gchar *interface_name,
                  const gchar *method_name,
                  GVariant    *parameters,
                  GDBusMethodInvocation *invocation,
                  gpointer    user_data)
{
    static const char *ini = "player:method";
    static const char *ack = "method";

    _mpris_call_method(connection,
                       sender,
                       object_path,
                       interface_name,
                       method_name,
                       parameters,
                       invocation,
                       user_data,
                       ini, ack);
}

static GVariant*
cb_player_get_property(GDBusConnection *connection,
                       const gchar *sender,
                       const gchar *object_path,
                       const gchar *interface_name,
                       const char  *property_name,
                       GError      **error,
                       gpointer    user_data)
{
    static const char *ini = "player:getproperty";
    static const char *ack = "getproperty";

    return _mpris_get_property(connection,
                               sender,
                               object_path,
                               interface_name,
                               property_name,
                               error,
                               user_data,
                               ini, ack);
}

static int
cb_player_set_property(GDBusConnection *connection,
                       const gchar *sender,
                       const gchar *object_path,
                       const gchar *interface_name,
                       const gchar *property_name,
                       GVariant    *value,
                       GError      **error,
                       gpointer    user_data)
{
    static const char *ini = "player:setproperty";
    static const char *ack = "setproperty";

    return _mpris_set_property(connection,
                               sender,
                               object_path,
                               interface_name,
                               property_name,
                               value,
                               error,
                               user_data,
                               ini, ack);
}

static const GDBusInterfaceVTable player_interface_vtable = {
	cb_player_methods,
	cb_player_get_property,
	cb_player_set_property
};

static void mp_bus_name_acquired(GDBusConnection *connection,
                                 const gchar *name,
                                 gpointer user_data)
{
    mpris_data_struct  *dat         = (mpris_data_struct *)user_data;
    /* see <interface> blocks in XML desc. (mpris_node_xml) */
	GDBusInterfaceInfo **interfaces = dat->node_info->interfaces;

	g_dbus_connection_register_object(connection,
                                      mpris_path,
                                      interfaces[0],
                                      &base_interface_vtable,
                                      user_data,
                                      NULL, NULL);

	g_dbus_connection_register_object(connection,
                                      mpris_path,
                                      interfaces[1],
                                      &player_interface_vtable,
                                      user_data,
                                      NULL, NULL);
}

static void
mp_bus_acquired(GDBusConnection *connection,
                const gchar *name,
                gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    dat->connection = connection;
    fprintf(stderr, "%s: Acquired data bus '%s' (%s)\n",
            prog, mpris_thisname, name);
}

static void
mp_acquire_failed(GDBusConnection *connection,
                  const gchar *name,
                  gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    dat->connection = NULL;
    fprintf(stderr, "%s: Failed to acquire data bus '%s' (%s)\n",
            prog, mpris_thisname, name);
}


static int
start_mpris_service(void)
{
    put_mpris_thisname(appname);

	mpris_data.node_info = g_dbus_node_info_new_for_xml(mpris_node_xml,
                                                        NULL);

    mpris_data.bus_id = g_bus_own_name(G_BUS_TYPE_SESSION,
                                       mpris_thisname,
                                       G_BUS_NAME_OWNER_FLAGS_REPLACE,
                                       mp_bus_acquired,
                                       mp_bus_name_acquired,
                                       mp_acquire_failed,
                                       (gpointer)&mpris_data,
                                       NULL);

    fprintf(stderr, "%s: MPRIS2 start - name '%s' - bus id %d\n",
            prog, mpris_thisname, mpris_data.bus_id);

    return 1; /* success */
}

static void
stop_mpris_service(void)
{
    if ( mpris_data.bus_id == 0 && mpris_data.node_info == NULL ) {
        fprintf(stderr, "%s: MPRIS2 stop -- NOT started\n", prog);
        return;
    }

	g_bus_unown_name(mpris_data.bus_id);
	g_dbus_node_info_unref(mpris_data.node_info);

    mpris_data.bus_id = 0;
    mpris_data.node_info = NULL;

    fprintf(stderr, "%s: MPRIS2 stop\n", prog);
}

/* XML (blech) description of top node and children,
 * gets passed to g_dbus_node_info_new_for_xml() to
 * buy a GDBusNodeInfo *
 *
 * This is a modification of code found in
 *     https://github.com/Serranya/deadbeef-mpris2-plugin.git
 */
static const char mpris_node_xml[] =
	"<node name='/org/mpris/MediaPlayer2'>"
	"	<interface name='org.mpris.MediaPlayer2'>"
	"		<method name='Raise'/>"
	"		<method name='Quit'/>"
	"		<property access='read'	name='CanQuit'             type='b'/>"
	"		<property access='read'	name='CanRaise'            type='b'/>"
	"		<property access='read'	name='HasTrackList'        type='b'/>"
	"		<property access='read'	name='Identity'            type='s'/>"
	"		<property access='read' name='DesktopEntry'        type='s'/>"
	"		<property access='read'	name='SupportedUriSchemes' type='as'/>"
	"		<property access='read'	name='SupportedMimeTypes'  type='as'/>"
	"	</interface>"
	"	<interface name='org.mpris.MediaPlayer2.Player'>"
	"		<method name='Next'/>"
	"		<method name='Previous'/>"
	"		<method name='Pause'/>"
	"		<method name='PlayPause'/>"
	"		<method name='Stop'/>"
	"		<method name='Play'/>"
	"		<method name='Seek'>"
	"			<arg name='Offset'      type='x'/>"
	"		</method>"
	"		<method name='SetPosition'>"
	"			<arg name='TrackId'     type='o'/>"
	"			<arg name='Position'    type='x'/>"
	"		</method>"
	"		<method name='OpenUri'>"
	"			<arg name='Uri'         type='s'/>"
	"		</method>"
	"		<signal name='Seeked'>"
	"			<arg name='Position'    type='x' direction='out'/>"
	"		</signal>"
	"		<property access='read'	     name='PlaybackStatus' type='s'/>"
	"		<property access='readwrite' name='LoopStatus'     type='s'/>"
	"		<property access='readwrite' name='Rate'           type='d'/>"
	"		<property access='readwrite' name='Shuffle'        type='b'/>"
	"		<property access='read'      name='Metadata'       type='a{sv}'/>"
	"		<property access='readwrite' name='Volume'         type='d'/>"
	"		<property access='read'      name='Position'       type='x'>"
	"			<annotation name='org.freedesktop.DBus.Property.EmitsChangedSignal' value='false'/>"
	"		</property>"
	"		<property access='read'         name='MinimumRate'   type='d'/>"
	"		<property access='read'         name='MaximumRate'   type='d'/>"
	"		<property access='read'         name='CanGoNext'     type='b'/>"
	"		<property access='read'         name='CanGoPrevious' type='b'/>"
	"		<property access='read'         name='CanPlay'       type='b'/>"
	"		<property access='read'         name='CanPause'      type='b'/>"
	"		<property access='read'         name='CanSeek'       type='b'/>"
	"		<property access='read'         name='CanControl'    type='b'>"
	"			<annotation name='org.freedesktop.DBus.Property.EmitsChangedSignal' value='false'/>"
	"		</property>"
	"	</interface>"
	"</node>";

