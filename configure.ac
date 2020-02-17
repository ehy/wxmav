dnl Process this file with autoconf to produce a configure script.

dnl Every other copy of the package version number gets its value from here
AC_INIT([wxmav], [1.0.0.2])

dnl Name for the X helper program (reason for most of this script)
AC_SUBST([XHELPERNAME], [wxmav-x-helper])
dnl Name for the X helper program source
AC_SUBST([XHELPERSOURCE], [x-aud-key-srv.c])

dnl EH: prevent configure/automake being conservative on finding
dnl an rm command that does not satisfy a posix test -- this
dnl has happened on OpenIndiana, and the following makes things work:
dnl intitial test condition is probably always true
AS_IF([test rm != am_please_work_portably],
[
ACCEPT_INFERIOR_RM_PROGRAM=yes
export ACCEPT_INFERIOR_RM_PROGRAM
], [
ACCEPT_INFERIOR_RM_PROGRAM=yes
export ACCEPT_INFERIOR_RM_PROGRAM
])

AM_INIT_AUTOMAKE([-Wall -Werror])

dnl autoheader template, macro indication of pkg-config gio-2.0
AH_TEMPLATE([HAVE_GIO20], [Define if pkg-config --cflags gio-2.0,
    pkg-config --libs gio-2.0 succeed])

dnl create a config.h file (Automake will add -DHAVE_CONFIG_H)
AC_CONFIG_HEADERS(config.h)

AC_SUBST(VERSION)

ISODATE=`date +%Y-%m-%d`
AC_SUBST(ISODATE)

dnl We want these before the checks, so the checks can modify their values.
dnl (found in fetchmail configure.in)
test x"$CFLAGS" = x && CFLAGS="-O"; AC_SUBST(CFLAGS)
test x"$CXXFLAGS" = x && CXXFLAGS="-O"; AC_SUBST(CXXFLAGS)
dnl test x"$LDFLAGS" = x && LDFLAGS=-s; AC_SUBST(LDFLAGS)

AC_CANONICAL_HOST

dnl Ensure use of large file support (not needed presently)
dnl AC_SYS_LARGEFILE
dnl Check file names
AC_SYS_LONG_FILE_NAMES

dnl Configure option: install xdg items?
AC_ARG_ENABLE([xdg-setup-items],
    AS_HELP_STRING([--disable-xdg-setup-items],
         [do not install the 'desktop' items (icons, menu, etc.) for
          the program -- installation of these items
          requires xdg-icon-resource, xdg-desktop-menu, xdg-mime
          (from package possibly named "xdg-utils") -- installation will
          *not* fail if those programs fail or are absent
         ]),
    [case "${enableval}" in
    yes) enable_frontend_xdg=true ;;
    no)  enable_frontend_xdg=false ;;
    *) AC_MSG_ERROR([bad value ${enableval} for --enable-xdg-setup-items]) ;;
    esac],[enable_frontend_xdg=true])
AM_CONDITIONAL([WITH_FRONTEND_XDG], [test x$enable_frontend_xdg = xtrue])

dnl WRT xdg items: scripts such as xdg-desktop-menu check env
dnl for XDG_DATA_DIRS, and provide defaults if not found; but,
dnl the scripts defaults might not be right, and doing su/sudo
dnl make install very well might strip XDG_DATA_DIRS from the
dnl environment -- so try to record configure-time $XDG_DATA_DIRS
dnl value so it is available to the xdg* {,un}install rule.
AC_SUBST([STORE_XDG_DATA_DIRS], [$XDG_DATA_DIRS])

dnl Checks for programs.
AC_PROG_INSTALL
AC_PROG_CC
dnl AC_PROG_CXX
dnl AC_C_INLINE
dnl automake 1.11 on OpenBSD is *demanding* AM_PROG_CC_C_O
AM_PROG_CC_C_O

# proc to warn that the X requiement unsatisfied and
# helper will not be installed
_no_helper_warning () {
    test X"$no_x" = Xyes && {
    AC_MSG_WARN([X Window System headers path or libraries path
    were not found: please use configure options:
    --with-x --x-includes=<X path>/include --x-libraries=<X path>/lib
    or, the X helper program will not be built or installed --
    that means that multimedia keys (play/pause, stop, next, previous)
    will not be available, and the screensaver will not be suspended
    for video playing.
    ])
    }
}

dnl Check for X (maybe disable use of xmkmf?)
dnl XMKMF=false
AC_PATH_X
_no_helper_warning

# Presently the only compiled program is the X-helper, and
# if X was not found by now, remaining C related checks are
# not needed (but the final Python checks are);
if test X"$no_x" != Xyes ; then

test X = X"$x_includes" || {
    # add to CPPFLAGS here even though $X_CFLAG from AC_PATH_XTRA
    # is used below - $X_CFLAG is documented as *compiler* flags
    # leaving the possibility of something unsuitable for cpp,
    # therefore $X_CFLAG is added to CFLAGS; but, without the X
    # path in CPPFLAGS the configure script complains that headers
    # are not usable by the preprocessor - if this results in
    # redundant compiler args, it should be harmless
    CPPFLAGS="$CPPFLAGS -I$x_includes"
    AC_MSG_RESULT([X paths: headers $x_includes])
}
test X = X"$x_libraries" || {
    # do not add to LDFLAGS here, since $X_LIBS from AC_PATH_XTRA
    # should suffice
    #LDFLAGS="$LDFLAGS-L$x_libraries"
    AC_MSG_RESULT([X paths: libs $x_libraries])
}

dnl Checks for X include and lib paths
AC_PATH_XTRA
test X = X"$X_CFLAGS" || {
    AC_MSG_RESULT([X_CFLAGS: $X_CFLAGS])
    CFLAGS="$CFLAGS $X_CFLAGS"
}
test X = X"$X_LIBS" || {
    AC_MSG_RESULT([X_LIBS: $X_LIBS])
    LDFLAGS="$LDFLAGS $X_LIBS"
}

dnl Checks for libraries.

AC_CHECK_LIB([X11], [XPending], [],
[no_x=yes; _no_helper_warning], [])
fi # if test X"$no_x" != Xyes

# can continue X checks?
# IF test X"$no_x" != Xyes
if test X"$no_x" != Xyes ; then
AC_CHECK_LIB([Xext], [DPMSInfo], [],
    [_missing_ext_dmps=yes], [-lX11])

AC_CHECK_LIB([Xss], [XScreenSaverSuspend], [],
    [_missing_ext_xss=yes], [-lX11])


dnl Checks for header files.
AC_HEADER_STDC

AC_CHECK_HEADERS(getopt.h)
dnl autoconf info doc says 'blank-separated argument list';
dnl hence, the repeats:
AC_CHECK_HEADERS(unistd.h sys/param.h string.h poll.h locale.h,
    [], [
    no_x=yes;
    AC_MSG_WARN([
    C header $ac_header is missing; the X helper program
    cannot be built - screen-saver control and multimedia
    keys will not work, but $PACKAGE should work])
    break
    ])
test X"$no_x" = Xyes || {
    AC_CHECK_HEADERS(errno.h limits.h sys/types.h sys/wait.h,
        [], [
        no_x=yes;
        AC_MSG_WARN([
        C header $ac_header is missing; the X helper program
        cannot be built - screen-saver control and multimedia
        keys will not work, but $PACKAGE should work])
        break
        ])
    test X"$no_x" = Xyes || {
        AC_CHECK_HEADERS(X11/X.h X11/Xlib.h X11/Xutil.h X11/keysym.h X11/XF86keysym.h,
            [], [
            no_x=yes;
            AC_MSG_WARN([
            C header $ac_header is missing; the X helper program
            cannot be built - screen-saver control and multimedia
            keys will not work, but $PACKAGE should work])
            break
            ])
    } # test X"$no_x" = Xyes ||
} # test X"$no_x" = Xyes ||
fi # if test X"$no_x" != Xyes

# can continue X checks?
if test X"$no_x" != Xyes ; then

AC_CHECK_HEADERS([X11/extensions/scrnsaver.h],[], [],
[[#include <X11/Xlib.h>
]])
AC_CHECK_HEADERS([X11/extensions/dpms.h],[], [],
[[#include <X11/Xlib.h>
]])

AC_CHECK_FUNCS(getopt getopt_long setlocale strlcpy getdelim)
dnl autoconf info doc says
dnl '... each FUNCTION enumerated in the blank-or-newline-separated ...'
dnl but newlines are raising syntax errors; hence, the repeats:
AC_CHECK_FUNCS(fork pipe fcntl poll system waitpid chdir,
    [], [
    no_x=yes;
    AC_MSG_WARN([
    C function $ac_func missing; the X helper program
    cannot be built - screen-saver control and multimedia
    keys will not work, but $PACKAGE should work])
    break
    ])
test X"$no_x" = Xyes || {
    AC_CHECK_FUNCS(strtoul strcasecmp snprintf strrchr signal,
        [], [
        no_x=yes;
        AC_MSG_WARN([
        C function $ac_func is missing; the X helper program
        cannot be built - screen-saver control and multimedia
        keys will not work, but $PACKAGE should work])
        break
        ])
    test X"$no_x" = Xyes || {
        : # futurama
        dnl AC_CHECK_FUNCS(-more funcs go here-,
        dnl     [], [
        dnl     no_x=yes;
        dnl     AC_MSG_WARN([
        dnl     C function $ac_func is missing; the X helper program
        dnl     cannot be built - screen-saver control and multimedia
        dnl     keys will not work, but $PACKAGE should work])
        dnl     break
        dnl     ])
    } # test X"$no_x" = Xyes ||
} # test X"$no_x" = Xyes ||

fi # if test X"$no_x" != Xyes

# can continue X checks?
if test X"$no_x" != Xyes ; then
AC_FUNC_ALLOCA
dnl getopt{,_long}
AM_CONDITIONAL([NEED_GETOPT_C], [test x$ac_cv_func_getopt != xyes && test x$ac_cv_func_getopt != xtrue])
AM_CONDITIONAL([NEED_GETOPT_LONG_C], [test x$ac_cv_func_getopt_long != xyes && test x$ac_cv_func_getopt_long != xtrue])

dnl check here for gio/dbus and anything else placed in x-helper --
dnl even if X headers/libs might not be strictly needed.
dnl
dnl Now, checks for pkg-config; 1st acoording to comments in
dnl share/aclocal/pkg.m4, installed by pkgconfig package --
dnl check version of these macros (for development):
dnl UPDATE: OpenBSD (at least 6.1, 6.2, don\'t know 1st version)
dnl has pkg-config hack in base system, and *no* pkgconfig in
dnl ports packages -- and as of 6.2 pkg-config --version reports
dnl 0.27.1 -- so adjust minimum version from 0.29 to 0.27 for
dnl development on OpenBSD -- but watch this elsewhere --
dnl no, test fails regardless, just remove this test
#m4_ifndef([PKG_PREREQ],
#    [m4_fatal([must install pkg-config 0.27 or later before running autoconf/autogen])])
#PKG_PREREQ(0.27)
dnl Now, set the PKG_CONFIG variable to first in path -- optional
dnl version arg defaults to 0.9.0
PKG_PROG_PKG_CONFIG
if test X = X"$PKG_CONFIG"; then
    tst_pkgconf_ok=no
else
    tst_pkgconf_ok=yes
fi
# if $PKG_CONFIG is OK, proceed with further package checks:
if test X"$tst_pkgconf_ok" = Xyes ; then
    dnl check gio-2.0 for dbus+glib hacks
    PKG_CHECK_MODULES([GIO2], [gio-2.0], [
      AC_DEFINE([HAVE_GIO20], [1])
      tst_gio_ok=yes
    ],[tst_gio_ok=no])
    # if gio/dbus is OK
    if test X"$tst_gio_ok" = Xyes ; then
    :
    # else if gio/dbus is OK
    else
      AC_MSG_WARN([
      Cannot use dbus for media keys, MPRIS2, screensaver control etc.])
    # end if gio/dbus is OK
    fi
# end if X"$tst_pkgconf_ok" = Xyes
fi

dnl Checks for typedefs, structures, and compiler characteristics.
AC_C_CONST
AC_TYPE_SIZE_T
AC_TYPE_SSIZE_T
AC_CHECK_SIZEOF(char*, 4)

# ELSE test X"$no_x" != Xyes
else

# must define conditionals tested in *.am
AM_CONDITIONAL([NEED_GETOPT_C], [test X = Y])
AM_CONDITIONAL([NEED_GETOPT_LONG_C], [test X = Y])

# END test X"$no_x" != Xyes
fi

AM_CONDITIONAL([WITH_X_HELPER], [test X"$no_x" != Xyes])
AM_CONDITIONAL([USE_GIO2], [test X"$tst_gio_ok" = Xyes])

dnl subdir configures
dnl AC_CONFIG_SUBDIRS(lib_misc wxmavpkg)

dnl wxPython runs better with Python
AM_PATH_PYTHON([2.7],, [:])
dnl AM_CONDITIONAL([HAVE_PYTHON], [test X"$PYTHON" != X:])

# Test python check result, and wx version
if test X"$PYTHON" = X: ; then
    AC_MSG_ERROR([
    did not find a suitable Python - Python 2.7 or greater needed])
fi

# if python was found, then test suitable wx module
dnl NOTE:
dnl in configure.ac this entire function must be enclosed in
dnl brackets to quote it, since the here-doc contains brackets
[_py_test_wx_ok () {
    _PY="$1"
    "$_PY" <<"NIK"
try:
    import wx
except ImportError:
    print("wxPython module not found: import exception")
    exit(1)

v = int(wx.VERSION[0])
if v < 3:
    print("wxPython version {} found, *need* 3 or greater".format(v))
    exit(1)

print("good, found wxPython version '{}'".format(wx.version()))
exit(0)
NIK

    return $?
}]

dnl Python seems OK; now check wx module
AC_MSG_CHECKING([for wxPython presence and version])
_PYCHECKRES=`_py_test_wx_ok "$PYTHON" 2>&1`
_py_test_wx_ok_status=$?
AC_MSG_RESULT([$_PYCHECKRES])
if ! test $_py_test_wx_ok_status = 0 ; then
    AC_MSG_ERROR([
    sorry, $PACKAGE requires wxPython with wxWidgets 3.x or greater])
else
    # EH: AM_PATH_PYTHON sets pkgpythondir to $PACKAGE -- override that
    pkgpythondir=\${pythondir}/wxmavpkg
fi
dnl END wxPython

AC_OUTPUT(Makefile)
