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
#include <string.h>
#include <unistd.h>

typedef struct dbus_gio_proc_data_out {
    pid_t   proc_pid;
    int     fd_rd;    /* read end of pipe, only assigned if fd_wr */
                      /* is not given (i.e. < 0) in */
                      /* dbus_gio_proc_data_in.fd_wr */
    int     err_no;   /* 0 if success, else errno */
} dbus_proc_out;

typedef struct dbus_gio_proc_data_in {
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

