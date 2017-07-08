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
#include <stdio.h>
/* SIZE_MAX might be in limits.h (BSD), or in stdint.h */
#include <stdint.h> /* TODO: test w/ configure, have alternatives */
#include <stdlib.h>
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

#ifndef   DBUS_GIO_DEBUGFILE
#define   DBUS_GIO_DEBUGFILE "/tmp/wxmav.debug"
#endif /* DBUS_GIO_DEBUGFILE */

/* token separator for multi-token lines */
#define _TSEPC ':'
#define _TSEPS ":"

typedef struct _mpris_data_struct {
    /* glib items */
    GMainLoop         *loop;
    GDBusNodeInfo     *node_info;
    gint              bus_id;
    GDBusConnection   *connection;
    const char        *bus_name;
    /* IO with client */
    char              *buf;
    size_t            bufsz;
    FILE              *fprd;
    FILE              *fpwr;
} mpris_data_struct;

mpris_data_struct mpris_data = {
    NULL, NULL, 0, NULL, NULL,
    NULL, 0, NULL, NULL
};

/* main procedure for dbus gio coprocess */
static int
dbus_gio_main(const dbus_proc_in *in);
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
on_mpris_sig_read(gint fd, GIOCondition condition, gpointer user_data);
/* read a line from a pipe, persistently until '\n' appears */
static ssize_t
read_line(char **buf, size_t *bs, FILE *fptr);\
/* remove trailing '\n' */
static int
unnl(char *p);
/* make a glib variant from a type and value; for complex types
 * (as, etc.) additional lines must be read, hence
 * mpris_data_struct *dat -- type string must be suitable
 * for producing one GVariant -- that is 's' or 'd' or
 * 'aa{sv}' or '(b(oss))' are OK, but e.g. 'a{sv}(ox)' is NG */
static GVariant*
gvar_from_strings(char *type, char *value, mpris_data_struct *dat);
/* make a glib variant from a type and value; complex types
 * (as, etc.) are not permitted -- this is for something like
 * b:true or d:0.5, already split at the colon if from a single
 * string; in any case type should ba a char giving the data
 * type, and value should be a convertible string */
static GVariant*
gvar_from_simple_type(int type, char *value, mpris_data_struct *dat);
/* when client wants arguments -- method invocation, set propery --
 * client calls for them with string "ARGS" and a colon sep'd
 * type string, e.g. 'b:x:a{sv}' -- call this to print args extracted
 * from GVariant 'parameters' sent by glib/gio on FILE * in the
 * data struct 'dat' according to type-string 'types' and
 * return sum of returns from fprintf() or -1 on error
 */
static int
put_args_from_gvar(char *types,
                   GVariant *parameters,
                   mpris_data_struct *dat);

/* MPRIS2 player control */
static int
start_mpris_service(mpris_data_struct *dat);
static void
stop_mpris_service(mpris_data_struct *dat);
static int
signal_mpris_service(mpris_data_struct *dat);

/* global FILE for read end of client pipe */
FILE *mpris_rfp     = NULL;
/* global FILE for writing to client pipe */
FILE *mpris_wfp     = NULL;
/* global FILE for read end of dbus signal pipe */
FILE *mpris_sig_rfp = NULL;
/* global FILE for writing to dbus signal pipe */
FILE *mpris_sig_wfp = NULL;
/* info messages */
FILE *fpinfo;

/* guard reentrency when hadling dbus signal from client */
volatile int reenter_guard = 0;

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

#   if _DEBUG || 0
    fpinfo = fopen(DBUS_GIO_DEBUGFILE, "w");
#   elif 1
    /* stderr goes to main process, through wx event loop
     * to a wxLog* object; but, the volume of messages seems
     * to overwelm the loop, so reserve stderr for urgency */
    fpinfo = stderr;
#   else
    fpinfo = fopen("/dev/null", "w");
#   endif
    setvbuf(fpinfo, NULL, _IOLBF, 0);

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
            fprintf(fpinfo,
              "%s: failed to dup input fd to 1; '%s'\n",
              in->progname, strerror(errno));
        }
        _exit(1);
    }

    if ( dn != 0 && dup2(dn, 0) == -1 ) {
        if ( in->progname != NULL ) {
            fprintf(fpinfo,
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
            fprintf(fpinfo,
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
}

/* signal handler for glib (app arbitrary) quit signals */
static gboolean
on_glib_quit_signal(gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    GMainLoop *loop        = dat->loop;

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

    g_free(param_str);
}

typedef struct _dbus_path_etc {
    const gchar *well_known_name; /*  org.foo.BarDaemon */
    const gchar *object_path;     /* /org/foo/BarDaemon/BazBits */
    const gchar *interface;       /*  org.foo.BarDaemon.BazBits */
    const  char *domain_name;     /*      foo */
} dbus_path_etc;

#define _PUT_DBUS_BY_NAMES(tld, dom, site, respth, resifc) { \
     tld "." dom "." site , \
 "/" tld "/" dom "/" site "/" respth , \
     tld "." dom "." site "." resifc , \
             dom \
    }
#define _PUT_DBUS_PATH_ETC(v) \
_PUT_DBUS_BY_NAMES("org", v, "SettingsDaemon", "MediaKeys", "MediaKeys")

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
    GMainLoop       *loop  = NULL;
    int             outfd  = 1; /* standard output */
    const char      *prg   = in->progname ? prog : NULL;

    loop = g_main_loop_new(NULL, FALSE);
    if ( loop == NULL ) {
        return 1;
    }

    mpris_data.loop = loop;

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        GDBusProxy      *proxy;
        GDBusProxyFlags flags  = 0;
        GError          *error = NULL;
        const char      *nm = path_attempts[i].domain_name;

        proxy = g_dbus_proxy_new_for_bus_sync(
                    G_BUS_TYPE_SESSION,
                    flags,
                    NULL, /* GDBusInterfaceInfo */
                    path_attempts[i].well_known_name,
                    path_attempts[i].object_path,
                    path_attempts[i].interface,
                    NULL, /* GCancellable */
                    &error);

        if ( error != NULL || proxy == NULL ) {
            if ( prg != NULL ) {
                fprintf(fpinfo, "%s: failed proxy for '%s': \"%s\"\n",
                        prg, nm, error == NULL ?
                                 "[unknown]" : (char *)error->message);
            }

            if ( error != NULL ) {
                g_error_free(error);
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
                      (gpointer)&mpris_data);

    if ( mpris_fd_read >= 0 && mpris_fd_write >= 0 ) {
        if ( (mpris_rfp = fdopen(mpris_fd_read, "r")) == NULL ) {
            perror("fdopen(mpris_fd_read, \"r\") (MPRIS2 coproc)");
            p_exit(1);
        }
        if ( (mpris_sig_rfp = fdopen(mpris_fd_sig_read, "r"))
              == NULL ) {
            perror("fdopen(mpris_fd_sig_read, \"r\") (MPRIS2 coproc)");
            fclose(mpris_rfp);
            close(mpris_fd_sig_read);
            p_exit(1);
        }

        mpris_data.fprd = mpris_rfp;

        if ( (mpris_wfp = fdopen(mpris_fd_write, "w")) == NULL ) {
            perror("fdopen(mpris_fd_write, \"w\") (MPRIS2 coproc)");
            fclose(mpris_rfp);
            fclose(mpris_sig_rfp);
            close(mpris_fd_write);
            p_exit(1);
        }
        if ( (mpris_sig_wfp = fdopen(mpris_fd_sig_write, "w"))
              == NULL ) {
            perror("fdopen(mpris_fd_sig_write, \"w\") (MPRIS2 coproc)");
            fclose(mpris_rfp);
            fclose(mpris_wfp);
            fclose(mpris_sig_rfp);
            close(mpris_fd_write);
            p_exit(1);
        }

        mpris_data.fpwr = mpris_wfp;

        setvbuf(mpris_wfp, NULL, _IOLBF, 0);
        setvbuf(mpris_sig_wfp, NULL, _IOLBF, 0);

        /* dbus signals dialogs are initiated by client,
         * so poll that descriptor */
        g_unix_fd_add(mpris_fd_sig_read,
                      G_IO_IN|G_IO_PRI|G_IO_ERR|G_IO_HUP|G_IO_NVAL,
                      on_mpris_sig_read,
                      (gpointer)&mpris_data);
    }

    /* the loop is poised twixt setup and teardown */
    g_main_loop_run(loop);

    for ( i = 0; i < A_SIZE(path_attempts); i++ ) {
        GDBusProxy *proxy = proxy_all[i];

        if ( proxy == NULL ) {
            continue;
        }

        g_dbus_proxy_call(proxy, "ReleaseMediaPlayerKeys",
                          g_variant_new("(s)", in->app_name),
                          G_DBUS_CALL_FLAGS_NO_AUTO_START,
                          -1, NULL, NULL, NULL);

        g_object_unref(proxy);
    }

    /* ensure MPRIS2 support is stopped (should've been called) */
    stop_mpris_service(&mpris_data);

    fclose(mpris_rfp);
    fclose(mpris_wfp);
    fclose(mpris_sig_rfp);
    fclose(mpris_sig_wfp);

    g_main_loop_unref(loop);

    /* if got quit signal (got_common_signal), reraise */
    if ( got_common_signal ) {
        if ( prg != NULL ) {
            fprintf(fpinfo,
                "%s (dbus coproc): caught and re-raising signal %d\n",
                prg, (int)got_common_signal);
        }
        signal((int)got_common_signal, SIG_DFL);
        raise((int)got_common_signal);
    }

    if ( prg != NULL ) {
        fprintf(fpinfo,
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
#ifndef MPRIS2_INST_BASE
#define MPRIS2_INST_BASE "instance"
#endif /* MPRIS2_INST_BASE */

static void
put_mpris_thisname(const char *thisname)
{
    size_t len = sizeof(MPRIS2_NAME_BASE) + sizeof(MPRIS2_INST_BASE);
    int    r;
    gchar  *p;

    if ( mpris_thisname != NULL ) {
        free((void *)mpris_thisname);
    }

    len += strlen(thisname) + _FMT_BUF_PAD;

    p = xmalloc(len);

    /* TODO: when code to check existing owner of this name
     * is ready, this preprocessor conditional must becaome
     * a runtime conditional -- the 'if 0' block running if
     * an instance is found */
#   if 0
    r = snprintf(p, len, "%s.%s.%s%ld",
                 MPRIS2_NAME_BASE, thisname,
                 MPRIS2_INST_BASE, (long int)app_main_pid);
#   else
    r = snprintf(p, len, "%s.%s", MPRIS2_NAME_BASE, thisname);
#   endif

    p[MIN(r, len - 1)] = '\0';

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
                fprintf(fpinfo, "%s: internal error (strlcpy)\n", prog);
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
on_mpris_sig_read(gint fd, GIOCondition condition, gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;
    static size_t bufsz = 0;  /* buffer from dat not used, */
    static char  *buf = NULL; /* in case of reentrence */
    static const char  *pfx = "mpris:";
    static const size_t pfxsz = sizeof("mpris:") - 1;

    ssize_t rdlen;
    char    *p;
    gboolean ret = TRUE;
    const GIOCondition errbits = G_IO_HUP | G_IO_ERR | G_IO_NVAL;

    if ( ++reenter_guard > 1 ) {
        --reenter_guard;
        return ret;
    }

    do { /* breakable block */
        if ( fd != fileno(mpris_sig_rfp) ) {
            fprintf(fpinfo, "%s: on mpris client read: fd unexpected\n",
                    prog);

            ret = FALSE;
            break;
        }

        if ( condition & errbits ) {
            GMainLoop *loop = dat->loop;

            fprintf(fpinfo,
                    "%s: %s on mpris client read fd; quitting\n",
                    prog, condition & G_IO_HUP ? "close" : "error");

            g_main_loop_quit(loop);

            ret = FALSE;
            break;
        }

        if ( buf == NULL ) {
            bufsz = MAX(bufsz, 128);
            buf = xmalloc(bufsz);
        }

        rdlen = read_line(&buf, &bufsz, mpris_sig_rfp);
        if ( rdlen < 1 ) {
            /* whether EOF or error, that's it for the other one */
            ret = FALSE;
            break;
        }

        unnl(buf);

        fprintf(fpinfo, "%s: mpris client read: '%s'\n", prog, buf);

        /* not mpris prefix? */
        if ( strncasecmp(buf, pfx, pfxsz) ) {
            fprintf(fpinfo, "%s: expected prefix '%s' - got \"%s\"\n",
                    prog, pfx, buf);

            ret = TRUE;
            break;
        }

        p = buf + pfxsz;
        rdlen -= pfxsz;

        if ( S_CI_EQ(p, "on") ) {
            start_mpris_service(dat);
        } else if ( S_CI_EQ(p, "off") ) {
            stop_mpris_service(dat);
        } else if ( S_CI_EQ(p, "signal") ) {
            mpris_data_struct ldat;
            int r;

            /* the user_data arg passed here has all the dbus/gio
             * items wanted, but this is a separate IPC pipe pair,
             * so use pertinent file objects and buffer */
            memcpy(&ldat, dat, sizeof(ldat));
            ldat.fprd  = mpris_sig_rfp;
            ldat.fpwr  = mpris_sig_wfp;
            ldat.bufsz = bufsz;
            ldat.buf   = buf;

            r = signal_mpris_service(&ldat);

            /* read calls might realloc() buffer,
             * so don't lose track */
            bufsz = ldat.bufsz;
            buf   = ldat.buf;

            if ( r ) {
                fprintf(fpinfo, "%s: failed signal_mpris_service: %d\n",
                        prog, r);
            }
        }
    } while ( 0 ); /* breakable block */

    --reenter_guard;

    return ret;
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
    int     ret = _EXCHGHS_ALL_OK;

    fprintf(dat->fpwr, "%s\n", ini);
    fflush(dat->fpwr);
    if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(fpinfo, "%s error writing to mpris client (b)\n", prog);
        return _EXCHGHS_WR_ERR;
    }

    fprintf(fpinfo, "%s sent ini '%s' to client\n",
        prog, ini);

    rdlen = read_line_dat(dat);
    if ( rdlen < 1 ) {
        /* whether EOF or error, that's it for the other one */
        fprintf(fpinfo, "%s unexpected mpris read end (%ld) (b)\n",
            prog, (long int)rdlen);
        return _EXCHGHS_RD_ERR;
    }

    unnl(dat->buf);

    fprintf(fpinfo, "%s got ack '%s' from client\n",
        prog, dat->buf);

    /* rejected? */
    if ( strcmp(dat->buf, "UNSUPPORTED") == 0 ) {
        fprintf(fpinfo, "%s mpris client ack for '%s' is '%s'\n",
            prog, ini, dat->buf);
        return _EXCHGHS_ACKREJ;
    }

    /* ack */
    if ( strcmp(dat->buf, ack) ) {
        fprintf(fpinfo, "%s unexpected mpris client ack '%s'\n",
            prog, dat->buf);
        ret |= _EXCHGHS_ACK_NG;
    }

    fprintf(fpinfo, "%s writing '%s' to client\n",
        prog, property_name);

    fprintf(dat->fpwr, "%s\n", property_name);
    fflush(dat->fpwr);
    if ( ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(fpinfo, "%s error writing to mpris client (c)\n", prog);
        return _EXCHGHS_WR_ERR;
    }

    rdlen = read_line_dat(dat);
    if ( rdlen < 1 ) {
        fprintf(fpinfo, "%s unexpected mpris read end (%ld) (c)\n",
            prog, (long int)rdlen);
        return _EXCHGHS_RD_ERR;
    }

    unnl(dat->buf);

    return ret;
}

/* convenience function: get from GVariant with g_variant_get
 * if type matches type (format) string; else, _assume_ the
 * variant is a container type and use g_variant_get_child --
 * note that g_variant_get_child *might crash* the program
 * if passed a variant of simple type --
 * Args:
 *       param      -- pointer to GVariant with data
 *       idx        -- index to use if not a type match
 *       fmt        -- the type (format) string to check against
 *       dest       -- location to receive the value
 */
static void
_get_gvar_one(GVariant *param, gsize idx, const char *fmt, void *dest)
{
    gboolean gb = g_variant_is_of_type(param, G_VARIANT_TYPE(fmt));

    if ( gb ) {
        g_variant_get(param, fmt, dest);
    } else {
        g_variant_get_child(param, idx, fmt, dest);
    }
}

/* when client wants arguments -- method invocation, set propery --
 * client calls for them with string "ARGS" and a colon sep'd
 * type string, e.g. 'b:x:a{sv}' -- call this to print args extracted
 * from GVariant 'parameters' sent by glib/gio on FILE * in the
 * data struct 'dat' according to type-string 'types' and
 * return sum of returns from fprintf() or -1 on error
 */
static int
put_args_from_gvar(char *types,
                   GVariant *parameters,
                   mpris_data_struct *dat)
{
    gsize       ix;
    char        *p;
    size_t      tlen  = strlen(types);
    int         ret   = 0;

    /* copy types string so that we may modify it
     * with a clear conscience */
    p = alloca(++tlen); /* has one extra */
    if ( strlcpy(p, types, tlen) >= tlen ) {
        fprintf(fpinfo, "%s: internal error (H)\n", prog);
        return -1;
    }
    --tlen;

    for ( ix = 0, p = strtok(p, _TSEPS);
          p != NULL;
          ix++, p = strtok(NULL, _TSEPS) ) {
        int r = 0;

        if ( *p == '\0' ) {
            r = fprintf(dat->fpwr, "%s\n", "");
        } else if ( S_CS_EQ(p, "b") ) {
            gboolean v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%s\n",
                    v == TRUE ? "true" : "false");
        } else if ( S_CS_EQ(p, "y") ) {
            guchar v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%u\n", (unsigned int)v);
        } else if ( S_CS_EQ(p, "n") ) {
            gint16 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%d\n", (int)v);
        } else if ( S_CS_EQ(p, "q") ) {
            guint16 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%u\n", (unsigned int)v);
        } else if ( S_CS_EQ(p, "i") ) {
            gint32 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%ld\n", (long int)v);
        } else if ( S_CS_EQ(p, "u") ) {
            guint32 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%lu\n", (unsigned long int)v);
        } else if ( S_CS_EQ(p, "x") ) {
            gint64 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%lld\n", (long long)v);
        } else if ( S_CS_EQ(p, "t") ) {
            guint64 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%llu\n", (unsigned long long)v);
        } else if ( S_CS_EQ(p, "h") ) {
            gint32 v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%ld\n", (long int)v);
        } else if ( S_CS_EQ(p, "d") ) {
            gdouble v;
            _get_gvar_one(parameters, ix, p, &v);
            r = fprintf(dat->fpwr, "%f\n", (double)v);
        } else if ( S_CS_EQ(p, "s") ||
                    S_CS_EQ(p, "o") ||
                    S_CS_EQ(p, "g") ) {
            gchar *v;
            int ok = 0;

            _get_gvar_one(parameters, ix, p, &v);

            if ( v == NULL ) {
                v = "error";
                fprintf(fpinfo, "%s: error getting '%c' param %d\n",
                        prog, *p, (int)ix);
            } else {
                ok = 1;
            }

            r = fprintf(dat->fpwr, "%s\n", (const char *)v);

            if ( ok ) {
                g_free(v);
            }
        }

        if ( r < 0 ) {
            return r;
        }

        ret += r;
        fflush(dat->fpwr);
    }

    return ret;
}

/* make a glib variant from a type and value; complex types
 * (as, etc.) are not permitted -- this is for something like
 * b:true or d:0.5, already split at the colon if from a single
 * string; in any case type should ba a char giving the data
 * type, and value should be a convertible string */
static GVariant*
gvar_from_simple_type(int type, char *value, mpris_data_struct *dat)
{
	GVariant *result = NULL;
    char     *p      = value;

    /* NOTE that for int types, sscanf into types that are wider
     * or at least equal length, then clamp with MAX(MIN())
     */
    if ( type == 'b' ) {
        gboolean b = strcasecmp(p, "true") == 0 ? TRUE : FALSE;
		result = g_variant_new_boolean(b);
    } else if ( type == 's' ||
                type == 'o' ||
                type == 'g' ) {
		gchar pt[2] = {type, '\0'};
        result = g_variant_new(pt, p);
    } else if ( type == 'd' ) {
        gdouble v = atof(p);
		result = g_variant_new_double(v);
    } else if ( type == 'y' ) {
        unsigned int u;
        if ( sscanf(p, "%u", &u) == 1 ) {
            guchar v = (guchar)MIN(u, UINT8_MAX);
            result = g_variant_new_byte(v);
        }
    } else if ( type == 'n' ) {
        int d;
        if ( sscanf(p, "%d", &d) == 1 ) {
            gint16 v = (gint16)MAXMIN(d, INT16_MAX, INT16_MIN);
            result = g_variant_new_int16(v);
        }
    } else if ( type == 'q' ) {
        unsigned int u;
        if ( sscanf(p, "%u", &u) == 1 ) {
            guint16 v = (guint16)MIN(u, UINT16_MAX);
            result = g_variant_new_uint16(v);
        }
    } else if ( type == 'i' ) {
        long int i;
        if ( sscanf(p, "%ld", &i) == 1 ) {
            gint32 v = (gint32)MAXMIN(i, INT32_MAX, INT32_MIN);
            result = g_variant_new_int32(v);
        }
    } else if ( type == 'u' ) {
        unsigned long int u;
        if ( sscanf(p, "%lu", &u) == 1 ) {
            guint32 v = (guint32)MIN(u, UINT32_MAX);
            result = g_variant_new_uint32(v);
        }
    } else if ( type == 'x' ) {
        long long int i;
        if ( sscanf(p, "%lld", &i) == 1 ) {
            gint64 v = (gint64)MAXMIN(i, INT64_MAX, INT64_MIN);
            result = g_variant_new_int64(v);
        }
    } else if ( type == 't' ) {
        unsigned long long int u;
        if ( sscanf(p, "%llu", &u) == 1 ) {
            guint64 v = (guint64)MIN(u, UINT64_MAX);
            result = g_variant_new_uint64(v);
        }
    } else if ( type == 'h' ) {
        long int i;
        if ( sscanf(p, "%ld", &i) == 1 ) {
            gint32 v = (gint32)MAXMIN(i, INT32_MAX, INT32_MIN);
            result = g_variant_new_handle(v);
        }
    } else if ( type == 'v' ) {
		/* special case here: value (p) must be of form:
         * type:[value-or-none-per-type]*/
        GVariant *var;
        char     *t, *t2;

        t = strchr(p, _TSEPC);
        if ( t == NULL ) {
            fprintf(fpinfo, "%s unexpected mpris type (%s) (f)\n",
                prog, p);
            return NULL;
        }

        *t++ = '\0';
        t2   = p;

        var = gvar_from_strings(t2, t, dat);
        if ( var == NULL ) {
            fprintf(fpinfo, "%s rec. gvar_from_strings failed (f)\n",
                prog);
            return NULL;
        }

        result = g_variant_new_variant(var);
    }

    return result;
}

/* make a glib variant from a type and value; for complex types
 * (as, etc.) additional lines must be read, hence
 * mpris_data_struct *dat -- type string must be suitable
 * for producing one GVariant -- that is 's' or 'd' or
 * 'aa{sv}' or '(b(oss))' are OK, but e.g. 'a{sv}(ox)' is NG */
static GVariant*
gvar_from_strings(char *type, char *value, mpris_data_struct *dat)
{
	GVariant *result = NULL;
    char     *p2     = type;
    char     *p      = value;
    size_t   tlen    = strlen(p2);
    ssize_t  rdlen;
    char     *t;

    /* 1st, if type is a single char, hand off to the
     * simple type procedure
     */
    if ( tlen == 1 ) {
        if ( p == NULL || *p == '\0' ) {
            rdlen = read_line_dat(dat);
            if ( rdlen < 1 ) {
                fprintf(fpinfo,
                    "%s unexpected mpris read end (%ld) (d)\n",
                    prog, (long int)rdlen);
                return NULL;
            }

            unnl(dat->buf);
            p = dat->buf;
        }

        result = gvar_from_simple_type(*p2, p, dat);
    }

    if ( result != NULL ) {
        return result;
    }

    if ( tlen < 2 ) {
        fprintf(fpinfo, "%s: internal error (C) p2<2\n", prog);
        return NULL;
    }

    if ( p != NULL && *p == '\0' ) {
        p = NULL;
    }

    /* since type might point into dat->buf, and dat->buf
     * will be refilled, make room and copy type -- if it is not
     * tiny and insignificant on the stack, then there is a big
     * problem elsewhere. */
    t = alloca(++tlen); /* has one extra */
    if ( strlcpy(t, p2, tlen) >= tlen ) {
        fprintf(fpinfo, "%s: internal error (B)\n", prog);
        return NULL;
    }
    --tlen;

    p2 = t++;

    /* array of something */
    if ( *p2 == 'a' ) {
		GVariantBuilder *builder;

        builder = g_variant_builder_new(G_VARIANT_TYPE(p2));

        for ( ;; ) {
            ssize_t  rdlen;
            GVariant *var = NULL;

            if ( p == NULL ) {
                rdlen = read_line_dat(dat);
                if ( rdlen < 1 ) {
                    fprintf(fpinfo,
                        "%s unexpected mpris read end (%ld) (d)\n",
                        prog, (long int)rdlen);
                    return NULL;
                }

                p = dat->buf;
            }

            unnl(p);

            if ( S_CS_EQ(p, ":END ARRAY:") ) {
                break;
            }

            var = gvar_from_strings(t, p, dat);
            g_variant_builder_add_value(builder, var);
            p = NULL;
        }

		result = g_variant_builder_end(builder);
		g_variant_builder_unref(builder);
    /* 'dictionary' type */
    } else if ( *p2 == '{' ) {
        char     *ep;
        GVariant *k, *v;
        int      ccl      = '}';

        if ( (ep = strrchr(t, ccl)) == NULL ) {
            fprintf(fpinfo, "%s: internal error (D,2) '%s'\n", prog, t);
            return NULL;
        }
        if ( *t == '{' || *t == '(' || *t == '\0' ) {
            fprintf(fpinfo, "%s: internal error (D,3) '%s'\n", prog, t);
            return NULL;
        }

        *ep = '\0';

        if ( p == NULL ) {
            rdlen = read_line_dat(dat);
            if ( rdlen < 1 ) {
                fprintf(fpinfo,
                    "%s unexpected mpris read end (%ld) (e)\n",
                    prog, (long int)rdlen);
                return NULL;
            }
            p = dat->buf;
        }

        unnl(p);

        /* key must be a simple type, */
        k = gvar_from_simple_type(*t, p, dat);
        if ( k == NULL ) {
            fprintf(fpinfo, "%s: internal error (D,4) '%s'\n", prog, t);
            return NULL;
        }
        ++t;

        rdlen = read_line_dat(dat);
        if ( rdlen < 1 ) {
            fprintf(fpinfo,
                "%s unexpected mpris read end (%ld) (e)\n",
                prog, (long int)rdlen);
            return NULL;
        }
        p = dat->buf;

        unnl(p);

        /* value needn't be a simple type */
        v = gvar_from_strings(t, p, dat);
        if ( v == NULL ) {
            fprintf(fpinfo, "%s: internal error (D,5)\n", prog);
            return NULL;
        }

        result = g_variant_new_dict_entry(k, v);
    /* 'tuple' type */
    } else if ( *p2 == '(' ) {
        char            *ep;
        GVariant        **ch_vec = NULL;
        gsize           ch_cnt   = 0;
        size_t          ch_asz   = 0, ch_ainc = 4;
        int             ccl      = ')';

        if ( (ep = strrchr(t, ccl)) == NULL ) {
            fprintf(fpinfo, "%s: internal error (D,2) '%s'\n", prog, t);
            return NULL;
        }

        *ep = '\0';

        for ( ; *t != '\0'; t++ ) {
            GVariant *var = NULL;

            if ( p == NULL ) {
                rdlen = read_line_dat(dat);
                if ( rdlen < 1 ) {
                    fprintf(fpinfo,
                        "%s unexpected mpris read end (%ld) (e)\n",
                        prog, (long int)rdlen);
                    return NULL;
                }
                p = dat->buf;
            }

            unnl(p);

            var = gvar_from_strings(t, p, dat);
            if ( var == NULL ) {
                while ( ch_cnt > 0 ) {
                    g_free(ch_vec[--ch_cnt]);
                }
                if ( ch_vec != NULL ) {
                    free(ch_vec);
                }
                return NULL;
            }

            if ( ch_cnt == ch_asz ) {
                ch_asz += ch_ainc;
                ch_vec = xrealloc(ch_vec, sizeof(*ch_vec) * ch_asz);
            }

            ch_vec[ch_cnt++] = var;

            if ( *t == '(' || *t == '{' ) {
                int rtc = *t == '(' ? ')' : '}';
                /* no check: gvar_from_strings() != NULL implies OK */
                t = strrchr(t, rtc);
            }

            p = NULL;
        }

		if ( ch_cnt > 0 ) {
            result = g_variant_new_tuple(ch_vec, ch_cnt);
            free(ch_vec);
		}
    }
    /* TODO other types not handled yet */

    return result;
}

/*
 * general core procs for method invocation, properties get/set,
 * and signal emission
 */

static int
_mpris_emit_signal(const char        *ini,
                   const char        *ack,
                   mpris_data_struct *dat)
{
    int    ret;
    size_t sz;
#   define _ix_object_path 0
#   define _ix_iface_name  1
#   define _ix_signal_name 2
#   define _ix_signal_type 3 /* !!! "property" or "signal" */
#   define _ix_format_str  4
#   define _n_sigparams    5
    gchar  *sigparams[_n_sigparams];

    ret = _exchange_handshake(dat, ini, ack, "signaldata");

    if ( ret != _EXCHGHS_ALL_OK ) {
        return ret;
    }

    memset(sigparams, 0, sizeof(sigparams));

    sigparams[_ix_object_path] = g_strdup(dat->buf);

    do { /* breakable block */
        GVariant *parameters;
        gboolean gret;
        ssize_t  rdlen;
        char     *p, *p2;
        GError   *error = NULL;
        int      br = 0;

        /* get g_dbus_connection_emit_signal parameters
         * interface_name, signal_name, parameter -- earlier param
         * object_path was fetched bu successful _exchange_handshake()
         */
        for ( sz = 1; sz < A_SIZE(sigparams); sz++ ) {
            rdlen = read_line_dat(dat);
            if ( rdlen < 1 ) {
                fprintf(fpinfo,
                    "%s: unexpected read sigparams (%ld) (%lu)\n",
                    prog, (long int)rdlen, (unsigned long)sz);
                ret = (int)sz;
                br = 1; break;
            }

            unnl(dat->buf);
            sigparams[sz] = g_strdup(dat->buf);
        }

        if ( br ) {
            break;
        }

        /* get variant for g_dbus_connection_emit_signal parameters
         */
        p2 = sigparams[_ix_format_str];
        p = strchr(p2, _TSEPC);
        if ( p != NULL ) {
            *p++ = '\0';
        }

        parameters = gvar_from_strings(p2, p, dat);
        if ( parameters == NULL ) {
            fprintf(fpinfo,
                "%s: fail building gvariant '%s' sigparams\n",
                prog, sigparams[_ix_format_str]);
            ret = _n_sigparams;
            break;
        }

        /*
         * Two signal types need handling:
         *  1) a signal defined for the interface in question
         *  2) a signal that a property of the interface changed
         * type 2 is more complicated since it is raised through
         * org.freedesktop.DBus.Properties interface with the
         * PropertiesChanged changed signal, and the MPRIS2
         * interface and its property and new data must be packed
         * into a glib variant as the argument --
         * the property case is handled in this 1st block,
         * the simpler case in the next block.
         */
        if ( S_CS_EQ(sigparams[_ix_signal_type], "property") ) {
            static const gchar *iface_properties =
                                "org.freedesktop.DBus.Properties";
            static const gchar *sname_properties =
                                "PropertiesChanged";
            GVariantBuilder *builder;
            GVariant        *ptuple[3];

            builder = g_variant_builder_new(G_VARIANT_TYPE_ARRAY);
            g_variant_builder_add(builder,
                                  "{sv}",
                                  sigparams[_ix_signal_name],
                                  parameters);

            ptuple[0] = g_variant_new_string(sigparams[_ix_iface_name]);
            ptuple[1] = g_variant_builder_end(builder);
            ptuple[2] = g_variant_new_strv(NULL, 0);

            fprintf(fpinfo, "%s: calling %s(%p, %s, %s, %s, %s, %p)\n",
                            prog,
                            "g_dbus_connection_emit_signal",
                            (void *)dat->connection,
                            "[NULL]",
                            (char *)sigparams[_ix_object_path],
                            (char *)iface_properties,
                            (char *)sigparams[_ix_signal_name],
                            (void *)parameters);
            gret = g_dbus_connection_emit_signal(dat->connection,
                                         NULL,
                                         sigparams[_ix_object_path],
                                         iface_properties,
                                         sname_properties,
                                         g_variant_new_tuple(ptuple,
                                                      A_SIZE(ptuple)),
                                         &error);

            g_variant_builder_unref(builder);

        } else if ( S_CS_EQ(sigparams[_ix_signal_type], "signal") ) {
            fprintf(fpinfo, "%s: calling %s(%p, %s, %s, %s, %s, %p)\n",
                            prog,
                            "g_dbus_connection_emit_signal",
                            (void *)dat->connection,
                            "[NULL]",
                            (char *)sigparams[_ix_object_path],
                            (char *)sigparams[_ix_iface_name],
                            (char *)sigparams[_ix_signal_name],
                            (void *)parameters);
            gret = g_dbus_connection_emit_signal(dat->connection,
                                             NULL,
                                             sigparams[_ix_object_path],
                                             sigparams[_ix_iface_name],
                                             sigparams[_ix_signal_name],
                                             parameters,
                                             &error);
        } else {
            fprintf(fpinfo, "%s: unknown signal type '%s' for '%s'\n",
                            prog,
                            (char *)sigparams[_ix_signal_type],
                            (char *)sigparams[_ix_signal_name]);

            ret = _n_sigparams + 2;
            break;
        }

        if ( error != NULL ) {
            fprintf(fpinfo,
                "%s: error: g_dbus_connection_emit_signal (%d, '%s')\n",
                prog, (int)error->code, (char *)error->message);
            g_error_free(error);
        }
        if ( gret != TRUE ) {
            ret = _n_sigparams + 1;
            break;
        }
    } while ( 0 );

    for ( sz = 0; sz < A_SIZE(sigparams); sz++ ) {
        if ( sigparams[sz] != 0 ) {
            g_free(sigparams[sz]);
        }
    }

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

    if ( ++reenter_guard > 1 ) {
        --reenter_guard;
        /* error code G_DBUS_ERROR_LIMITS_EXCEEDED
         * is the only one I see that looks as if
         * it may be regarded as temporary */
		g_dbus_method_invocation_return_error(
            invocation, G_DBUS_ERROR, G_DBUS_ERROR_LIMITS_EXCEEDED,
            "%s: reenter detected while performing %s.%s call",
            prog, interface_name, method_name);
        return;
    }

    do { /* breakable block */
        r = _exchange_handshake(dat, ini, ack, method_name);
        if ( r < 0 ) {
            fprintf(fpinfo, "%s mpris handshake %s error (b)\n",
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
            fprintf(fpinfo, "%s unexpected mpris type (%s) (c)\n",
                prog, dat->buf);
            p2 = "ERROR: format(c)"; break;
        }

        p2 = p++;
        *p2 = '\0';
        p2 = dat->buf;

        /* method takes arguments? */
        if ( S_CI_EQ(p2, "ARGS") ) {
            int r = put_args_from_gvar(p, parameters, dat);

            if ( r < 0 || ferror(dat->fpwr) || feof(dat->fpwr) ) {
                fprintf(fpinfo, "%s error writing to  client (d)\n",
                    prog);
            }

            rdlen = read_line_dat(dat);
            if ( rdlen < 1 ) {
                fprintf(fpinfo,
                    "%s unexpected mpris read end (%ld) (d)\n",
                    prog, (long int)rdlen);
                p2 = "ERROR: read(d)"; break;
            }

            unnl(dat->buf);

            p = strchr(dat->buf, _TSEPC);
            if ( p == NULL ) {
                fprintf(fpinfo, "%s unexpected mpris type (%s) (d)\n",
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

    --reenter_guard;
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
	GVariant *result = NULL;

    if ( ++reenter_guard > 1 ) {
        --reenter_guard;
        fprintf(fpinfo, "%s reentrence detected at '%s' (count %d)\n",
            prog, "_mpris_get_property", reenter_guard);
        return NULL;
    }

    if ( _exchange_handshake(dat, ini, ack, property_name) ) {
        fprintf(fpinfo, "%s mpris handshake '%s' failure (b)\n",
            prog, ini);
        --reenter_guard;
        return NULL;
    }

    p = strchr(dat->buf, _TSEPC);
    if ( p == NULL ) {
        fprintf(fpinfo, "%s unexpected mpris type (%s) (c)\n",
            prog, dat->buf);
        --reenter_guard;
        return NULL;
    }

    p2 = p++;
    *p2 = '\0';
    p2 = dat->buf;

    result = gvar_from_strings(p2, p, dat);

    --reenter_guard;
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
	int      r, result = 0;

    if ( ++reenter_guard > 1 ) {
        --reenter_guard;
        fprintf(fpinfo, "%s reentrence detected at '%s' (count %d)\n",
            prog, "_mpris_set_property", reenter_guard);
        return 0;
    }

    if ( _exchange_handshake(dat, ini, ack, property_name) ) {
        fprintf(fpinfo, "%s mpris handshake '%s' failure (b)\n",
            prog, ini);
        --reenter_guard;
        return result;
    }

    p = strchr(dat->buf, _TSEPC);
    if ( p == NULL ) {
        fprintf(fpinfo, "%s unexpected mpris reply '%s' (c)\n",
            prog, dat->buf);
        --reenter_guard;
        return result;
    }

    p2 = p++;
    if ( strcmp(p, "ok") ) {
        fprintf(fpinfo, "%s unexpected mpris property '%s' (c)\n",
            prog, property_name);
        --reenter_guard;
        return result;
    }

    *p2 = '\0';
    p2 = dat->buf;

    r = put_args_from_gvar(p2, value, dat);

    fflush(dat->fpwr);
    if ( r < 0 || ferror(dat->fpwr) || feof(dat->fpwr) ) {
        fprintf(fpinfo, "%s error writing to mpris client (c)\n",
            prog);
        --reenter_guard;
        return result;
    }

    --reenter_guard;
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

static void
mp_bus_acquired(GDBusConnection *connection,
                const gchar *name,
                gpointer user_data)
{
    mpris_data_struct  *dat         = (mpris_data_struct *)user_data;
    /* see <interface> blocks in XML desc. (mpris_node_xml) */
	GDBusInterfaceInfo **interfaces = dat->node_info->interfaces;

    dat->connection = connection;

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

    fprintf(fpinfo, "%s: Acquired data bus '%s' (%s)\n",
            prog, dat->bus_name, name);
}

static void
mp_name_acquired(GDBusConnection *connection,
                 const gchar *name,
                 gpointer user_data)
{
    mpris_data_struct  *dat = (mpris_data_struct *)user_data;

    fprintf(fpinfo, "%s: Acquired bus name '%s' (%s)\n",
            prog, dat->bus_name, name);
}

static void
mp_name_lost(GDBusConnection *connection,
             const gchar *name,
             gpointer user_data)
{
    mpris_data_struct *dat = (mpris_data_struct *)user_data;

    dat->connection = NULL;

    fprintf(fpinfo, "%s: Lost bus name '%s' (%s)\n",
            prog, dat->bus_name, name);
}

static int
signal_mpris_service(mpris_data_struct *dat)
{
    static const char *ini = "send:signal";
    static const char *ack = "signal";

    return _mpris_emit_signal(ini, ack, dat);
}

static int
start_mpris_service(mpris_data_struct *dat)
{
    put_mpris_thisname(appname);
    dat->bus_name  = mpris_thisname;

	dat->node_info = g_dbus_node_info_new_for_xml(mpris_node_xml, NULL);

    dat->bus_id    = g_bus_own_name(G_BUS_TYPE_SESSION,
                                    dat->bus_name,
                                    G_BUS_NAME_OWNER_FLAGS_REPLACE,
                                    mp_bus_acquired,
                                    mp_name_acquired,
                                    mp_name_lost,
                                    (gpointer)dat,
                                    NULL);

    fprintf(fpinfo, "%s: MPRIS2 start - name '%s' - bus id %d\n",
            prog, dat->bus_name, dat->bus_id);

    return 1; /* success */
}

static void
stop_mpris_service(mpris_data_struct *dat)
{
    if ( dat->bus_id == 0 && dat->node_info == NULL ) {
        fprintf(fpinfo, "%s: MPRIS2 stop -- NOT started\n", prog);
        return;
    }

    if ( dat->bus_id != 0 ) {
        g_bus_unown_name(dat->bus_id);
    }

    if ( dat->node_info != NULL ) {
        g_dbus_node_info_unref(dat->node_info);
    }

    dat->bus_id    = 0;
    dat->node_info = NULL;

    fprintf(fpinfo, "%s: MPRIS2 stop\n", prog);
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
"		<property access='readwrite' name='Fullscreen'     type='b'/>"
"		<property access='read'	name='CanSetFullscreen'    type='b'/>"
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

