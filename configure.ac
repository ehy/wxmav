dnl Process this file with autoconf to produce a configure script.

dnl Every other copy of the package version number gets its value from here
AC_INIT([cprec], [0.4.1])

dnl EH: some [ ... deleted ... ] decided that autoconf should preach
dnl and fail rather than just work, so this shell parameter is
dnl needed on OpenIndiana (maybe all Sun) -- must preceed automake
AS_IF([test rm != am_arrogance],
[
ACCEPT_INFERIOR_RM_PROGRAM=yes
export ACCEPT_INFERIOR_RM_PROGRAM
], [
ACCEPT_INFERIOR_RM_PROGRAM=yes
export ACCEPT_INFERIOR_RM_PROGRAM
])

AM_INIT_AUTOMAKE([-Wall -Werror])

dnl create a config.h file (Automake will add -DHAVE_CONFIG_H)
AC_CONFIG_HEADERS(config.h)

AC_SUBST(VERSION)

ISODATE=`date +%Y-%m-%d`
AC_SUBST(ISODATE)

dnl We want these before the checks, so the checks can modify their values.
dnl (found in fetchmail configure.in)
test x"$CFLAGS" = x && CFLAGS="-O2"; AC_SUBST(CFLAGS)
test x"$CXXFLAGS" = x && CXXFLAGS="-O2"; AC_SUBST(CXXFLAGS)
dnl test x"$LDFLAGS" = x && LDFLAGS=-s; AC_SUBST(LDFLAGS)

AC_CANONICAL_HOST

dnl Ensure use of large file support
AC_SYS_LARGEFILE
dnl Check file names
AC_SYS_LONG_FILE_NAMES

dnl arg to allow disabling of linking libdvdread
AC_ARG_WITH([libdvdread], AS_HELP_STRING([--with-libdvdread],
  [link with -ldvdread (or ARG) (the default is to use runtime loading,
   which is better, where possible)]),,
  [with_libdvdread=no])

dnl dd-dvd made optional
AC_ARG_ENABLE([dd-dvd],
	AS_HELP_STRING([--disable-dd-dvd],
		 [do not build dd-dvd, the simple dvd filesystem backup program (C++)]),
	[case "${enableval}" in
	yes) enable_dd_dvd=true ;;
	no)  enable_dd_dvd=false ;;
	*) AC_MSG_ERROR([bad value ${enableval} for --enable-dd-dvd]) ;;
	esac],[enable_dd_dvd=true])
AM_CONDITIONAL([WITH_DD_DVD], [test x$enable_dd_dvd = xtrue])

dnl Version 0.2.1, wxPython front end
AC_ARG_ENABLE([wxpy-frontend],
	AS_HELP_STRING([--disable-wxpy-frontend],
		 [do not install the wxPython graphical backup frontend program:
          requires Python 2.7 (not 3.x), wxPython, growisofs, dvd+rw-mediainfo,
          dvd+rw-format (the latter three from the same package "dvd+rw-tools"
          or maybe "growisofs"), genisoimage or mkisofs, and cprec and dd-dvd
          from this package (--disable-dd-dvd will disable this frontend
          application too)
         ]),
	[case "${enableval}" in
	yes) enable_frontend=true ;;
	no)  enable_frontend=false ;;
	*) AC_MSG_ERROR([bad value ${enableval} for --enable-wxpy-frontend]) ;;
	esac],[enable_frontend=true])
AM_CONDITIONAL([WITH_FRONTEND], [test x$enable_frontend = xtrue])

dnl Version 0.2.1, wxPython front end -- install xdg items?
AC_ARG_ENABLE([wxpy-frontend-xdg],
	AS_HELP_STRING([--disable-wxpy-frontend-xdg],
		 [do not install the 'desktop' items (icons, menu, etc.) for the
          wxPython graphical backup frontend program (--enable-wxpy-frontend) --
          requires xdg-icon-resource, xdg-desktop-menu, xdg-mime
          (from package possibly named "xdg-utils") -- installation will
          *not* fail if those programs fail or are absent
         ]),
	[case "${enableval}" in
	yes) enable_frontend_xdg=true ;;
	no)  enable_frontend_xdg=false ;;
	*) AC_MSG_ERROR([bad value ${enableval} for --enable-wxpy-frontend-xdg]) ;;
	esac],[enable_frontend_xdg=true])
AM_CONDITIONAL([WITH_FRONTEND_XDG], [test x$enable_frontend_xdg = xtrue])

dnl Checks for programs.
AC_PROG_INSTALL
AC_PROG_CC
AC_PROG_CXX
AC_C_INLINE

dnl Checks for libraries.
# libdvdread check
if test x"$with_libdvdread" = xyes; then
# libdvdread enabled
#  Now it gets ugly^Hier. Many OS's might offer dvdread with a 3rd party
#  package system, but the installation directories might not be in
#  the default search path of the compiler and linker. Or it might be
#  'hand' installed anywhere. But it must be found. There seems to be
#  no autoconf magic for this, and all the 'googling' I could stand was
#  little help. Therefore shell script is resorted to.
#
_search_hack_prefix_list="/usr/local /opt/local /opt /usr/pkg"
_search_hack_headers_list="include/dvdread/dvd_reader.h"
_search_hack_libraries_list="lib/libdvdread.so lib/libdvdread.a"

for _search_hack_prefix in $_search_hack_prefix_list
do
  for _search_hack_var in $_search_hack_headers_list
  do
    if test -f "${_search_hack_prefix}/${_search_hack_var}"
    then
    	_search_hack_header="${_search_hack_prefix}/${_search_hack_var}"
	break
    fi
  done
  if test X"$_search_hack_header" != X
  then
    CFLAGS="$CFLAGS -I${_search_hack_prefix}/include"
    CXXFLAGS="$CXXFLAGS -I${_search_hack_prefix}/include"
    break
  fi
done

for _search_hack_prefix in $_search_hack_prefix_list
do
  for _search_hack_var in $_search_hack_libraries_list
  do
    if test -f "${_search_hack_prefix}/${_search_hack_var}"
    then
    	_search_hack_library="${_search_hack_prefix}/${_search_hack_var}"
	break
    fi
  done
  if test X"$_search_hack_library" != X
  then
    LDFLAGS="$LDFLAGS -L${_search_hack_prefix}/lib"
    break
  fi
done

AC_CHECK_LIB(dvdread, DVDVersion, AC_DEFINE([HAVE_DVDVERSION], [1], ["Got DVDVersion"]))
AC_CHECK_LIB(dvdread, DVDReadBlocks,
  AC_CHECK_LIB(dvdread, UDFFindFile,,
	AC_MSG_ERROR([libdvdread function UDFFindFile not found -- try a static library build])),
AC_MSG_ERROR([libdvdread function DVDReadBlocks not found -- not good at all]))

else
# libdvdread not enabled
if test x"$with_libdvdread" = x || test x"$with_libdvdread" = xno; then
AC_MSG_NOTICE(Skipping check for libdvdread: --with-libdvdread not given)
AC_CHECK_LIB(dl, dlsym)
else
#  Here user has given a specific library argument; will assume such a user
#  will have set -I and -L as necessary.
AC_MSG_NOTICE(Skipping check for libdvdread: using --with-libdvdread=ARG)
LIBS="$with_libdvdread $LIBS"
AC_DEFINE([HAVE_LIBDVDREAD], [1])
fi
fi
# end libdvdread check

dnl Checks for header files.
AC_HEADER_STDC
AC_HEADER_DIRENT
AC_CHECK_HEADERS(getopt.h unistd.h sys/param.h sys/time.h time.h sys/mkdev.h sys/sysmacros.h string.h memory.h fcntl.h dirent.h sys/ndir.h ndir.h alloca.h locale.h error.h errno.h limits.h sys/resource.h ctype.h stdarg.h varargs.h dlfcn.h)

dnl  this jm_* was provided by an older autogen, and now causes
dnl  warning noise with newer auto* tools: do without it and watch
dnl  for reports from any old system users
dnl jm_CHECK_TYPE_STRUCT_UTIMBUF

AC_HEADER_MAJOR
AC_STRUCT_TM
AC_STRUCT_ST_BLOCKS
AC_FUNC_ALLOCA
AC_FUNC_FSEEKO
AC_FUNC_CLOSEDIR_VOID
AC_CHECK_FUNCS(mkfifo vprintf doprnt seekdir telldir getrlimit pathconf getpagesize sysconf strlcpy mmap lstat readlink realpath symlink lchown lchmod lutimes utimes error dlsym posix_memalign getfsfile endfsent getmntinfo setmntent getmntent endmntent mknod getopt getopt_long)

dnl getopt{,_long}
AM_CONDITIONAL([NEED_GETOPT_C], [test x$ac_cv_func_getopt != xyes && test x$ac_cv_func_getopt != xtrue])
AM_CONDITIONAL([NEED_GETOPT_LONG_C], [test x$ac_cv_func_getopt_long != xyes && test x$ac_cv_func_getopt_long != xtrue])

dnl Checks for typedefs, structures, and compiler characteristics.
AC_C_CONST
AC_TYPE_SIZE_T
AC_TYPE_SSIZE_T
AC_TYPE_UID_T
AC_CHECK_SIZEOF(char*, 4)

dnl Checks for library functions.

dnl subdir configures
AC_CONFIG_SUBDIRS(lib_misc wxdvdbackuppkg)

dnl Version 0.2.1, wxPython front end
if test x"$enable_frontend" = xtrue; then
AM_PATH_PYTHON([2.7],, [:])
dnl AM_CONDITIONAL([HAVE_PYTHON], [test X"$PYTHON" != X:])
if test X"$PYTHON" = X: ; then
AC_MSG_ERROR([a suitable Python was not found -- use --disable-wxpy-frontend to install without the Python graphical frontend])
elif ! $PYTHON -c 'import wx' >/dev/null 2>&1 ; then
AC_MSG_ERROR([wxPython (wxWidgets python package) was not found -- use --disable-wxpy-frontend to install without the Python graphical frontend])
else
# EH: AM_PATH_PYTHON sets pkgpythondir to $PACKAGE -- override that
pkgpythondir=\${pythondir}/wxdvdbackuppkg
fi
dnl END Version 0.2.1, wxPython front end
fi

dnl this was original from autopackage: AC_OUTPUT(Makefile cprec.lsm cprec.spec)
AC_OUTPUT(Makefile)
