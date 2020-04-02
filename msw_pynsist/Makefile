







#! /usr/bin/make -f
# POSIX makefile forappname  MSW installer:
# make the MSW installer -- not to be invoked as part of
# normal build, but invoked by hand when MSW binary has been
# built and all things are ready
# 1st non-comment, 1st target w/o dependencies or commands:
.POSIX:

# catalog name: $(NAME).{pot,po,mo}
NAME = $(OUTDIR)/WXMav-1.0.0.3-install-all.exe
NAME64 = $(OUTDIR)/mswinstallerembedname64
APPNAME = wxmav
SRC = wxmav.nsist
TPL = installer_template.nsi
MACS = ../cdata/cdata.m4
LNSRCS = ../wxmav.pyw ../wxmav_main.py
BLDDIR = build
OUTDIR = $(BLDDIR)/nsis

# some utilities used in this script:
# (cp and rm are always forced)
RM = rm -f
RMR= $(RM) -r
CP = cp -f
LN = ln
LS = ls
LNS= $(LN) -s
LSL= $(LS) -l
MV = mv
MKDIR = mkdir
GREP = grep -F
SED = sed
M4 = m4
PYTHON = python3
PYNSIS = /usr/bin/pynsist
MKNSIS = $(PYTHON) $(PYNSIS)

all: $(NAME)
	@P="$$(pwd)"; D="$${P##*/}"; echo $@ made in "$$D" ; exit 0

# do i18 later
#$(NAME) : i18n-sect.in
#	$(M4) $(MACS) i18n-sect.in > i18n-sect
#	$(M4) $(MACS) $(SRC).in > $(SRC)
#	$(MKNSIS) $(SRC)
#	ls -l $@
# for now, w/o i18
$(NAME) : symlinks
	$(M4) $(MACS) $(TPL).in > $(TPL)
	$(M4) $(MACS) $(SRC).in > $(SRC)
	$(MKNSIS) $(SRC)
	ls -l $@

make64 $(NAME64) : i18n-sect.in
	$(M4) $(MACS) i18n-sect.in > i18n-sect
	( $(SED) 's,mswinstallerembedname,&64,g' \
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
			"GPLFreeSoftwareApplications" "wxmav" "1.0.0.3" \
			| $$TR >> $@; \
		printf \
		'    "installed %s message catalog" "$$INSTDIR\\%s\\%s"\n' \
			"$$d" "$$d" "$$mo" \
			| $$TR >> $@; \
		printf '\n' | $$TR >> $@; \
	done; ls -l $@

install: $(NAME)
	S="$(NAME)"; T=../../$${S##*/}; \
	$(MV) "$$S" "$$T" && ls -l "$$T"

install64: $(NAME64)
	S="$(NAME64)"; T=../../$${S##*/}; \
	$(MV) "$$S" "$$T" && ls -l "$$T"

uninstall:
	$(RM) ../../$(NAME) ../../$(NAME64)

symlinks:
	@echo making symbolic links for $(LNSRCS)
	@for S in $(LNSRCS) ; do \
		test -f "$$S" || { echo MISSING "$$S"; exit 1; } ; \
		T=$${S##*/} ; test -h "$$T" && $(RM) "$$T" ; \
		test -e "$$T" && { echo ERROR: "$$T" exists; exit 1; } ; \
		$(LNS) "$$S" "$$T" || { echo FAILED linking "$$S"; exit 1; } ; \
		$(LSL) "$$T" ; \
	done

clean_symlinks:
	@echo removing symbolic links to $(LNSRCS)
	@for S in $(LNSRCS) ; do \
		T=$${S##*/} ; test -h "$$T" && $(RM) "$$T" ; \
	done ; \
	exit 0

clean : clean_symlinks
	$(RMR) $(NAME) $(NAME64) i18n-sect.in i18n-sect

cleanall : clean
	$(RMR) $(SRC) $(TPL) $(BLDDIR)

distclean: cleanall
