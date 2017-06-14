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

#ifndef _X_AUD_KEY_H_INCL
#define _X_AUD_KEY_H_INCL 1

/* for sig_atomic_t */
#include <signal.h>
/* size_t, etc. */
#include <sys/types.h>
#include <unistd.h>

#undef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#undef MAX
#define MAX(a, b) ((a) > (b) ? (a) : (b))

#define A_SIZE(a) (sizeof(a) / sizeof((a)[0]))

#define TERMINATE_CHARBUF(buf, contentlen) do { \
        buf[MIN(contentlen, sizeof(buf) - 1)] = '\0'; \
    } while (0)

/* memory aid for pipe(2) */
#define PIPE_RFD_INDEX 0
#define PIPE_WFD_INDEX 1

/* prototypes */
ssize_t
input_read(int fd, char *buf, size_t buf_sz, int strip);
ssize_t
client_output(int fd, const void *buf, size_t buf_sz);
ssize_t
client_output_str(int fd, const char *str);
/* system(3) with result message printed on stderr */
int
do_system_call(const char *buf);

/* external global vars */
/* e.g., argv[0] basename */
extern const char *prog;

/* set if common exit signals are caught -- RO! */
extern volatile sig_atomic_t got_common_signal;

#endif /* _X_AUD_KEY_H_INCL */
