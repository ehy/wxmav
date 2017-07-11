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
#define MINMAX(v, min, max) \
    ((v) >= (min) && (v) <= (max) ? (v) : ((v) < (min) ? (min) : (max)))
#define MAXMIN(v, max, min) MINMAX(v, min, max)

#define A_SIZE(a) (sizeof(a) / sizeof((a)[0]))

#define TERMINATE_CHARBUF(buf, contentlen) do { \
        buf[MIN(contentlen, sizeof(buf) - 1)] = '\0'; \
    } while (0)

/* 64 bit decimal with sign can be 20 chars -- so lets use 32 */
#define _FMT_BUF_PAD 32

/* string equivalence - Case Sensitive */
#define S_CS_EQ(s1, s2) (strcmp(s1, s2) == 0)
/* string equivalence - Case Insensitive */
#define S_CI_EQ(s1, s2) (strcasecmp(s1, s2) == 0)

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
/*
 * utility: if the modest memory requirements here
 * cannot be met, simply report and exit
 */
void *
xcalloc(size_t nmemb, size_t szmemb);
#define xmalloc(sz) xcalloc(sz, 1)
void *
xrealloc(void *ptr, size_t sz);
void *
xstrdup(const char *s);
/*
 * alloca() is desirable for some small allocations, but it
 * is merely widely available, not standard; so, where unavailable
 * or broken, or where this code is compiled by a zealous
 * alloca hater . . .
 */
#if HAVE_ALLOCA && ! ALLOCA_GO_AWAY
#   define LALLOC(sz)  alloca(sz)
    /* of course sane use of these macros demand that
     * unallocation macro must occur on any path to return --
     * the odd block for do-while should silence gcc set but not
     * used warning w/o '-Wunused-but-set-variable' */
#   define LAFREE(ptr) do { ptr = ptr; } while (0)

    /* and, this ugly nest of includes right outta autoconf.info: */
    #ifdef STDC_HEADERS
    # include <stdlib.h>
    # include <stddef.h>
    #else
    # ifdef HAVE_STDLIB_H
    #  include <stdlib.h>
    # endif
    #endif
    #ifdef HAVE_ALLOCA_H
    # include <alloca.h>
    #elif !defined alloca
    # ifdef __GNUC__
    #  define alloca __builtin_alloca
    # elif defined _AIX
    #  define alloca __alloca
    # elif defined _MSC_VER
    #  include <malloc.h>
    #  define alloca _alloca
    # elif !defined HAVE_ALLOCA
    #  ifdef  __cplusplus
    extern "C"
    #  endif
    void *alloca (size_t);
    # endif
    #endif
#else
#   define LALLOC(sz)  xmalloc(sz)
#   define LAFREE(ptr) free(ptr)
#endif

#if ! HAVE_STRLCPY
size_t
strlcpy(char* dst, const char* src, size_t cnt);
#endif /* ! HAVE_STRLCPY */

/* external global vars */
/* e.g., argv[0] basename */
extern const char *prog;

/* p_exit should be assigned exit in main(), and _exit in the
 * entry procedure of coprocesses, and any func. that exits
 * use p_exit */
extern void (*p_exit)(int);

/* name of application being served, passed by argument; */
/* if not given, then prog is used */
extern const char *appname;

/* set if common exit signals are caught -- RO! */
extern volatile sig_atomic_t got_common_signal;

/* for MPRIS2 support (if available) */
extern int mpris_fd_read;
extern int mpris_fd_write;
extern int mpris_fd_sig_read;
extern int mpris_fd_sig_write;

/* store parent pid for child coprocess */
extern pid_t app_main_pid;

#endif /* _X_AUD_KEY_H_INCL */
