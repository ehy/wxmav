bin_PROGRAMS=cprec

cprec_SOURCES=cprec.c cprec.h apue_ftw.c apue_ftw.h cpf.c cpf.h
cprec_SOURCES+=vd_cpf.c vd_cpf.h ino.c ino.h block_hash.c block_hash.h
cprec_SOURCES+=meta_set.h meta_set.c path_set.h path_set.c walk.h walk.c
cprec_SOURCES+=dl_drd.h dl_drd.c cprec.1 xmalloc.c xmalloc.h
cprec_SOURCES+=hdr_cfg.h system.h aclocal.m4

if NEED_GETOPT_C
cprec_SOURCES+=gngetopt.h getopt.c
endif
if NEED_GETOPT_LONG_C
cprec_SOURCES+=getopt1.c
endif

if WITH_DD_DVD
bin_PROGRAMS+= dd-dvd
dd_dvd_SOURCES=dd-dvd.cc dl_drd.h dl_drd.c vd_cpf.c vd_cpf.h dd-dvd.1
dd_dvd_LDADD = lib_misc/lib_misc.a
if NEED_GETOPT_C
dd_dvd_SOURCES+=gngetopt.h getopt.c
endif
if NEED_GETOPT_LONG_C
dd_dvd_SOURCES+=getopt1.c
endif
endif

#  uncomment the following if cprec requires the math library
#cprec_LDADD=-lm
cprec_LDADD = lib_misc/lib_misc.a

# commented see below
#EXTRA_DIST=cprec.lsm.in cprec.spec.in cprec.texinfo

SUBDIRS = lib_misc wxdvdbackuppkg

AM_CPPFLAGS = -I$(srcdir)/lib_misc

# Version 0.2.1: wxPython front end -- requires dd-dvd
pyprog_sub = sed \
			-e 's,[@]PYTHON[@],$(PYTHON),g' \
			-e 's,[@]PYTHON_VERSION[@],$(PYTHON_VERSION),g' \
			-e 's,[@]PYTHON_PREFIX[@],$(PYTHON_PREFIX),g' \
			-e 's,[@]PYTHON_EXEC_PREFIX[@],$(PYTHON_EXEC_PREFIX),g' \
			-e 's,[@]PYTHON_PLATFORM[@],$(PYTHON_PLATFORM),g' \
			-e 's,[@]pythondir[@],$(pythondir),g' \
			-e 's,[@]pkgpythondir[@],$(pkgpythondir),g' \
			-e 's,[@]pyexecdir[@],$(pyexecdir),g' \
			-e 's,[@]pkgpyexecdir[@],$(pkgpyexecdir),g' \
			-e 's,[@]PACKAGE[@],$(PACKAGE),g' \
			-e 's,[@]VERSION[@],$(VERSION),g'

if WITH_DD_DVD
if WITH_FRONTEND
#if HAVE_PYTHON

python_PYTHON = wxDVDBackup.py
#pkgpython_PYTHON = wxdvdbackuppkg/*.py
bin_SCRIPTS = wxDVDBackup
CLEANFILES = $(bin_SCRIPTS)
EXTRA_DIST = wxDVDBackup.in xdg/*

wxDVDBackup: wxDVDBackup.in Makefile
	$(pyprog_sub) < $(srcdir)/wxDVDBackup.in > wxDVDBackup
	chmod +x wxDVDBackup


if WITH_FRONTEND_XDG
#install-data-local:
#	echo HOOK INVOKED: install-data-local

XDG_INST_ICON = xdg-icon-resource
XDG_INST_MENU = xdg-desktop-menu
XDG_INST_MIME = xdg-mime

XICOARGS = install --noupdate --novendor --size
XICOARGSU= uninstall --noupdate --size
XICOSIZE = 16 24 32 48 64 96 128

XDGRESNAME=wxdvdbackup
install-data-hook:
	@echo Installing XDG desktop items: menu entry, icons
	@XII=$$(which $(XDG_INST_ICON)) && XIM=$$(which $(XDG_INST_MENU)) \
	&& XMM=$$(which $(XDG_INST_MIME)) \
	|| { echo cannot find $(XDG_INST_ICON) or $(XDG_INST_MENU); \
		echo will not do xdg icon and menu item install; exit 0; } ; \
	for s in $(XICOSIZE) ; do \
		I="$(srcdir)/xdg/$(XDGRESNAME)-$${s}.png"; test -f "$$I" || \
			{ echo icon "$$I" is missing; continue; } ; \
		$$XII $(XICOARGS) $$s  "$$I" $(XDGRESNAME) || \
			{ echo failed installing icon size $$s; true; } ; \
	done; \
	$$XII forceupdate; \
	I="$(srcdir)/xdg/$(XDGRESNAME).desktop"; test -f "$$I" || exit 0; \
	$$XIM install --novendor "$$I" || \
		{ echo failed to install "$$I"; true; }


uninstall-local:
	@echo Uninstalling XDG desktop items: menu entry, icons
	@XII=$$(which $(XDG_INST_ICON)) && XIM=$$(which $(XDG_INST_MENU)) \
	&& XMM=$$(which $(XDG_INST_MIME)) \
	|| { echo cannot find $(XDG_INST_ICON) or $(XDG_INST_MENU); \
		echo will not do xdg icon and menu item uninstall; exit 0; } ; \
	I="$(XDGRESNAME).desktop"; \
	$$XIM uninstall "$$I" || \
		{ echo failed to uninstall "$$I"; true; } ; \
	for s in $(XICOSIZE) ; do \
		$$XII $(XICOARGSU) $$s $(XDGRESNAME) || \
			{ echo failed uninstalling icon size $$s; true; } ; \
	done; \
	$$XII forceupdate || true

# if WITH_FRONTEND_XDG
endif

# if HAVE_PYTHON
#endif
# if WITH_FRONTEND
endif
# if WITH_DD_DVD
endif

#  if you write a self-test script named `chk', uncomment the
#  following and add `chk' to the EXTRA_DIST list
#TESTS=chk

#  build and install the .info pages
# EH: 1-13: disable .info until time to write it;
# note that presently cprec.info seems absent
# from any *clean target -- must fix that if
# this is re-enabled.
#info_TEXINFOS = cprec.texinfo
#cprec_TEXINFOS = gpl.texinfo

#  install the man pages
man_MANS=cprec.1
if WITH_DD_DVD
man_MANS+=dd-dvd.1
endif
