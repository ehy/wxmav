# if requirements for helper were met (and --without-x no spec'd)
if WITH_X_HELPER
#bin_PROGRAMS=

# to be included in dist:
dist_pkgdata_DATA = LICENSE.gpl,v2 LICENSE.gpl,v3

wxmav_x_helper_LDADD   =
wxmav_x_helper_CFLAGS  =
wxmav_x_helper_LDFLAGS =

# XHELPERNAME is set to wxmav-x-helper with AC_SUBST in configure.ac,
# but automake cannot take the AC substitution as a value for
# libexec_PROGRAMS, so the literal reappears here
libexec_PROGRAMS = wxmav-x-helper

# As above, *_SOURCES requires literals
wxmav_x_helper_SOURCES = x-aud-key-srv.c x-aud-key-srv.h aclocal.m4

if USE_GIO2
wxmav_x_helper_SOURCES+= dbus_gio.h dbus_gio.c
wxmav_x_helper_LDADD  += $(GIO2_LIBS)
wxmav_x_helper_CFLAGS += $(GIO2_CFLAGS)
wxmav_x_helper_LDFLAGS+= $(GIO2_LDFLAGS)
endif

if NEED_GETOPT_C
wxmav_x_helper_SOURCES+=gngetopt.h getopt.c
endif
if NEED_GETOPT_LONG_C
wxmav_x_helper_SOURCES+=getopt1.c
endif

# Note: do not append *_CFLAGS or *_LDFLAGS here, because it was
# necessary to append CFGLAGS and LDFLAGS in the configure script
# for AC_CHECK_LIB on x libs; so, these become redundant
#wxmav_x_helper_CFLAGS = @X_CFLAGS@
#wxmav_x_helper_LDFLAGS = @X_LIBS@

wxmav_x_helper_LDADD += $(X_PRE_LIBS) $(X_EXTRA_LIBS)

# if WITH_X_HELPER
endif

# Python stuff{ed} remains:
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
			-e 's,[@]VERSION[@],$(VERSION),g' \
			-e 's,[@]XHELPERPATH[@],$(libexecdir)/$(XHELPERNAME),g'

python_PYTHON = wxmav_main.py wxmav_mpris2ctl.py
bin_SCRIPTS = wxmav wxmav_control
CLEANFILES = $(bin_SCRIPTS)
EXTRA_DIST = wxmav.in wxmav.pyw wxmav_control.in xdg/* cdata/* msw_pkg/* msw_pynsist/* examples/*

wxmav: wxmav.in Makefile
	$(pyprog_sub) < $(srcdir)/wxmav.in > wxmav
	chmod +x wxmav

wxmav_control: wxmav_control.in Makefile
	$(pyprog_sub) < $(srcdir)/wxmav_control.in > wxmav_control
	chmod +x wxmav_control


if WITH_FRONTEND_XDG
#install-data-local:
#	echo HOOK INVOKED: install-data-local

XDG_INST_ICON = xdg-icon-resource
XDG_INST_MENU = xdg-desktop-menu
XDG_INST_MIME = xdg-mime

XICOARGS = install --noupdate --novendor --size
XICOARGSU= uninstall --noupdate --size
XICOSIZE = 16 24 32 48 64 96 128

XDGRESNAME=wxmav
install-data-hook:
	@echo Installing XDG desktop items: menu entry, icons
	@XII=$$(which $(XDG_INST_ICON)) && XIM=$$(which $(XDG_INST_MENU)) \
	&& XMM=$$(which $(XDG_INST_MIME)) \
	|| { echo cannot find $(XDG_INST_ICON) or $(XDG_INST_MENU); \
		echo will not do xdg icon and menu item install; exit 0; } ; \
	XDG_DATA_DIRS="$(STORE_XDG_DATA_DIRS)"; export XDG_DATA_DIRS; \
	for s in $(XICOSIZE) ; do \
		echo installing icon size $$s; \
		I="$(srcdir)/xdg/$(XDGRESNAME)-$${s}.png"; test -f "$$I" || \
			{ echo icon "$$I" is missing; continue; } ; \
		$$XII $(XICOARGS) $$s  "$$I" $(XDGRESNAME) || \
			{ echo failed installing icon size $$s; true; } ; \
	done; \
	$$XII forceupdate; \
	I="$(srcdir)/xdg/$(XDGRESNAME).desktop"; test -f "$$I" || exit 0; \
	echo XDG_DATA_DIRS contains $$XDG_DATA_DIRS ; \
	XDG_UTILS_DEBUG_LEVEL=3 $$XIM install --novendor "$$I" && \
		$$XIM forceupdate >/dev/null 2>/dev/null || \
			{ echo failed to install "$$I" -- status $$?; true; }


uninstall-local:
	@echo Uninstalling XDG desktop items: menu entry, icons
	@XII=$$(which $(XDG_INST_ICON)) && XIM=$$(which $(XDG_INST_MENU)) \
	&& XMM=$$(which $(XDG_INST_MIME)) \
	|| { echo cannot find $(XDG_INST_ICON) or $(XDG_INST_MENU); \
		echo will not do xdg icon and menu item uninstall; exit 0; } ; \
	XDG_DATA_DIRS="$(STORE_XDG_DATA_DIRS)"; export XDG_DATA_DIRS; \
	I="$(XDGRESNAME).desktop"; \
	$$XIM uninstall "$$I" || \
		{ echo failed to uninstall "$$I"; true; } ; \
	for s in $(XICOSIZE) ; do \
		$$XII $(XICOARGSU) $$s $(XDGRESNAME) || \
			{ echo failed uninstalling icon size $$s; true; } ; \
	done; \
	$$XII forceupdate >/dev/null 2>/dev/null || true

# if WITH_FRONTEND_XDG
endif

#  if you write a self-test script named `chk', uncomment the
#  following and add `chk' to the EXTRA_DIST list
#TESTS=chk

#  install the man pages
#man_MANS=wxmav.1
