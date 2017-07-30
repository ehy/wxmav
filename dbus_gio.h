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

#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

/* do: request multimedia keys over dbus */
#ifndef DO_DBUS_KEYS
#define DO_DBUS_KEYS 1
#endif

/* do: try screensaver control over dbus */
#ifndef DO_DBUS_SSAVERS
#define DO_DBUS_SSAVERS 1
#endif

/* do: support the MPRIS2 player control spec (over dbus) */
#ifndef DO_MPRIS2
#define DO_MPRIS2 1
#endif

typedef struct _dbus_gio_proc_data_out {
    pid_t   proc_pid;
    int     fd_rd;    /* read end of pipe, only assigned if fd_wr */
                      /* is not given (i.e. < 0) in */
                      /* dbus_gio_proc_data_in.fd_wr */
    int     err_no;   /* 0 if success, else errno */
} dbus_proc_out;

typedef struct _dbus_gio_proc_data_in {
    int     quit_sig; /* if > 0 handle this signal as quit command */
    int     *def_sig; /* signals to be set to default */
    size_t  num_sig;  /* count in def_sig */
    int     fd_wr;    /* for proc stdout; if < 0 */
                      /* then pipe() is called and read end */
                      /* is put in dbus_gio_proc_data_out.fd_rd */
                      /* (else it will be -1) */
    const
    char    *progname;/* for info messages on stderr; */
                      /* if NULL, no messages */
    const
    char    *app_name;/* name of the application this process serves, */
                      /* required by some methods called over dbus */
} dbus_proc_in;

/*
 * start (fork) coprocess to handle glib2 gio loop for
 * dbus signals (e.g., keys that some X desktop envs grab
 * and dole out through dbus) -- and MPRIS2 dbus hackery --
 * args in and out are described above; arg av may be NULL,
 * else it should be argv from main, so that the coprocess may
 * alter argv[0] in an informative way (if that is supported by
 * the system)
 */
int
start_dbus_coproc(const dbus_proc_in *in,
                  dbus_proc_out *out,
                  char **av);

/*
 * invoke Inhibit method on dbus screensaver object:
 * pass application name in appname, reason for inhibit
 * in reason (e.g., "A/V medium playing"), and address of pointer
 * to 32 bit unsigned integers in ppcookie to receive the cookies
 * that must be passed to the uninhibit method --
 * returns 0 on success else non-zero
 * -- NOTE ppcookie is not terminated -- consider it opaque
 */
int
dbus_inhibit_screensaver(const char *app_name,
                         const char *reason,
                         uint32_t   **ppcookie);

/*
 * invoke UnInhibit method on dbus screensaver object:
 * pass the pcookie assigned by *successful* call to
 * dbus_inhibit_screensaver --
 * returns 0 on success else non-zero
 */
int
dbus_uninhibit_screensaver(uint32_t *pcookie);

/* the above procedures have external visibility, but
 * to be useful to a separate process, provide trigger
 * signals
 */
#ifndef   DBUS_UNINHIBIT_SCREENSAVER_SIGNAL
#define   DBUS_UNINHIBIT_SCREENSAVER_SIGNAL SIGUSR1
#endif /* DBUS_UNINHIBIT_SCREENSAVER_SIGNAL */

#ifndef   DBUS_INHIBIT_SCREENSAVER_SIGNAL
#define   DBUS_INHIBIT_SCREENSAVER_SIGNAL SIGUSR2
#endif /* DBUS_INHIBIT_SCREENSAVER_SIGNAL */
