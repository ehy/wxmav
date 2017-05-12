#! /usr/bin/make -f
# POSIX makefile for epspline common data files:
# not to be invoked as part of
# normal build, but invoked by hand when change is
# made in macros
# 1st non-comment, 1st target w/o dependencies or commands:
.POSIX:

NAME = cdata
MACS = $(NAME).m4
#HDR = ../src/$(NAME).h
#HDRIN = ./$(NAME).h.in
#VER = ../version.sh
#VERIN = ./version.sh.in
MKM = ../msw_pkg/Makefile
MKMIN = ../msw_pkg/Makefile.in
# Xorg desktop file
#XDMIN = ./desktopmime.in
#XDM = ../epspline.xdgmime.xml
#XDFIN = ./desktopfile.in
#XDF = ../epspline.desktop

# some utilities used in this script:
# (cp and rm are always forced)
RM = rm -f
CP = cp -f
MV = mv
M4 = m4
MKDIR = mkdir

all: $(HDR) $(VER) $(XDM) $(XDF) $(MKM)
	@P="$$(pwd)"; D="$${P##*/}"; echo $@ made in "$$D" ; exit 0

force:
	touch $(MACS) && $(MAKE) all

#$(HDR) : $(MACS) $(HDRIN)
#	$(M4) $(MACS) $(HDRIN) > $@
#	ls -l $@
#
#$(VER) : $(MACS) $(VERIN)
#	$(M4) $(MACS) $(VERIN) > $@
#	ls -l $@
#
#$(XDM) : $(MACS) $(XDMIN)
#	$(M4) $(MACS) $(XDMIN) > $@
#	ls -l $@
#
#$(XDF) : $(MACS) $(XDFIN)
#	$(M4) $(MACS) $(XDFIN) > $@
#	ls -l $@

$(MKM) : $(MACS) $(MKMIN)
	$(M4) $(MACS) $(MKMIN) > $@
	ls -l $@

install: all

uninstall:

clean :

cleanall : clean

distclean: cleanall
