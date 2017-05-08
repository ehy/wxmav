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

#include <stdint.h>
#if DEBUG
#include <string.h>
#include <unistd.h>
#endif /* DEBUG */
#include <X11/X.h>
#include <X11/Xlib.h>

/* X11 'Status' is typedef or macro int */
static Status x_help_ini_thds_callstatus = 0;

extern Status
get_x_help_ini_thds_callstatus(void);

Status
get_x_help_ini_thds_callstatus(void)
{
    return x_help_ini_thds_callstatus;
}

/*
 * This debug stuff is just an ugly way to make sure
 * the init func is getting called, so do not compile
 * with DEBUG!=0, and pretend you don't see this.
 */
#if DEBUG
static const char _x_help_ini_thds_hstr[] = "0123456789abcdef";
static void
_x_help_ini_thds_puth(char *p)
{
    unsigned i;
    const unsigned sz = sizeof(x_help_ini_thds_callstatus);
    
    for ( i = 1; i <= sz; i++ ) {
        unsigned b;
        
        b = (x_help_ini_thds_callstatus >> (sz - i)) & 0xFFllu;
        
        *p++ = _x_help_ini_thds_hstr[(b >> 4) & 0xFu];
        *p++ = _x_help_ini_thds_hstr[b & 0xFu];
    }
}


#define _HS_P1 "XInitThreads STATUS: 0"
#define _HS_P2 "x                \n"

#endif /* DEBUG */

#if defined(__GNUC__)
static void _xits_init(void) __attribute__((constructor));
#else  /* defined(__GCC__) */
extern void _xits_init(void);
#warning "NOT GCC, so make sure link editor args will use init func!"
#endif /* defined(__GCC__) */

void
_xits_init(void)
{
#if DEBUG
    char bogostr[] = _HS_P1 _HS_P2;
    
    x_help_ini_thds_callstatus = XInitThreads();

    _x_help_ini_thds_puth(bogostr + sizeof(_HS_P1));

    write(1, bogostr, strlen(bogostr));
#else  /* DEBUG */
    x_help_ini_thds_callstatus = XInitThreads();
#endif /* DEBUG */
}
