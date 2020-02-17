







#! /usr/bin/make -f
# POSIX makefile forappname  MSW installer:
# make the MSW installer -- not to be invoked as part of
# normal build, but invoked by hand when MSW binary has been
# built and all things are ready
# 1st non-comment, 1st target w/o dependencies or commands:
.POSIX:

# catalog name: $(NAME).{pot,po,mo}
NAME = WXMav-1.0.0.2-install.exe
NAME64 = mswinstallername64
APPNAME = wxmav
SRC = wxmav.nsi
MACS = ../cdata/cdata.m4

# some utilities used in this script:
# (cp and rm are always forced)
RM = rm -f
CP = cp -f
MV = mv
GREP = grep -F
SED = sed
M4 = m4
MKNSIS = makensis -V4
MKDIR = mkdir

all: $(NAME)
	@P="$$(pwd)"; D="$${P##*/}"; echo $@ made in "$$D" ; exit 0

# do i18 later
#$(NAME) : i18n-sect.in
#	$(M4) $(MACS) i18n-sect.in > i18n-sect
#	$(M4) $(MACS) $(SRC).in > $(SRC)
#	$(MKNSIS) $(SRC)
#	ls -l $@
# for now, w/o i18
$(NAME) :
	$(M4) $(MACS) $(SRC).in > $(SRC)
	$(MKNSIS) $(SRC)
	ls -l $@

make64 $(NAME64) : i18n-sect.in
	$(M4) $(MACS) i18n-sect.in > i18n-sect
	( $(SED) 's,mswinstallername,&64,g' \
		< $(SRC).in > $(SRC).64.in \
		&& $(M4) $(MACS) $(SRC).64.in > $(SRC); \
	S=$$?; $(RM) $(SRC).64.in; \
	exit $$S )
	$(MKNSIS) $(SRC)
	ls -l $(NAME64)

#  SetOutPath "$INSTDIR\en"
#
#  File "../po/en/appname.mo"
#
#  WriteRegStr ${_HK_} "Software\vendorname\appname\appversion\i18n" \
#	"installed en message catalog" "$INSTDIR\en\appname.mo"
i18n-sect.in:
	:> $@; mo="$(APPNAME).mo"; \
	TR='tr / \\' ; \
	for f in ../po/*/$$mo ; do \
		td=$${f%/*}; d=$${td##*/}; \
		printf '\n  SetOutPath "$$INSTDIR\\%s"\n' "$$d" \
			| $$TR >> $@; \
		printf '\n  File "%s"\n' "$$f" \
			| $$TR >> $@; \
		printf \
		'\n  WriteRegStr $${_HK_} "Software\\%s\\%s\\%s\\i18n" \\\n' \
			"GPLFreeSoftwareApplications" "wxmav" "1.0.0.2" \
			| $$TR >> $@; \
		printf \
		'    "installed %s message catalog" "$$INSTDIR\\%s\\%s"\n' \
			"$$d" "$$d" "$$mo" \
			| $$TR >> $@; \
		printf '\n' | $$TR >> $@; \
	done; ls -l $@

install: $(NAME)
	$(MV) $(NAME) ../.. && ls -l ../../$(NAME)

install64: $(NAME64)
	$(MV) $(NAME64) ../.. && ls -l ../../$(NAME64)

uninstall:
	$(RM) ../../$(NAME) ../../$(NAME64)

clean :
	$(RM) $(NAME) $(NAME64) i18n-sect.in i18n-sect

cleanall : clean
	$(RM) $(SRC)

distclean: cleanall
