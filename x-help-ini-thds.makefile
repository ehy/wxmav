#
#.POSIX:

# with .POSIX, c99 might expand from default $(CC),
# but these sources are c89 -- set CC to cc, and if
# necessary use CC=c89 (or your choice) on command line
CC=cc

# preferrably a BSD-ish install program (including GNU)
# -- some systems (Sun) might have a 'ginstall'
INSTALL_PROG = install
INSTALL_OPTS = -c -s -m 555 -o 0 -g 0
INSTALL_DIR  = /usr/local/bin
INSTALL_LDIR = /usr/local/lib

XHELPER    = x-aud-key-srv
XHELPER_SRC= $(XHELPER).c
XHELPER_OBJ= $(XHELPER).o

SHARED_NAM = x-help-ini-thds
SHARED_LIB = lib$(SHARED_NAM).so
SHARED_SRC = $(SHARED_NAM).c
SHARED_OBJ = $(SHARED_NAM).o

ALL_BIN    = $(XHELPER) $(SHARED_LIB)
ALL_OBJ    = $(XHELPER_OBJ) $(SHARED_OBJ)

# X libs and includes are traditionally in /usr/X11{,R6,R7}/,
# but some systems differ (e.g., several GNU/Linux)
#INCLUDES = -I/usr/X11/include
INCLUDES = -I/usr/include/X11
#LDFLAGS  = -L/usr/X11/lib
LDFLAGS  = -L/usr/lib64
LDLIBS   = -lX11

#XHDEFS = -DHAVE_XEXT=1 -DHAVE_XSSAVEREXT=0
XHDEFS = -DHAVE_XEXT=1 -DHAVE_XSSAVEREXT=1
XHELPER_INCLUDES = $(INCLUDES)
XHELPER_LDFLAGS  = $(LDFLAGS)
#XHELPER_LDLIBS   = $(LDLIBS) -lXext
XHELPER_LDLIBS   = $(LDLIBS) -lXext -lXss

# for optional helper shared lib:
# modern gcc (or clang) should not need anything like
# -Wl,-init,_xits_init since the in the source the init
# function has __attribute__((constructor)) (if defined(__GNUC__))
# but if the tools are not gcc it will be necessary to
# provide the the correct switches to:
# a) build a share library suitable for LD_PRELOAD (or equivalent)
# b) specify _xits_init as an automatically called constructor
PFLAGS   = -fPIC -shared
#PFLAGS   = -fPIC -shared -Wl,-init,_xits_init

SHARED_INCLUDES = $(INCLUDES)
SHARED_LDFLAGS  = $(LDFLAGS)
SHARED_LDLIBS   = $(LDLIBS)

def default: $(XHELPER)

all: def $(SHARED_LIB)

$(XHELPER_OBJ) : $(XHELPER_SRC)
	$(CC) $(CFLAGS) $(XHDEFS) $(XHELPER_INCLUDES) -c -o $(XHELPER_OBJ) \
		$(XHELPER_SRC)

$(XHELPER) : $(XHELPER_OBJ)
	$(CC) -o $(XHELPER) $(XHELPER_OBJ) \
		$(XHELPER_LDFLAGS) $(XHELPER_LDLIBS)


$(SHARED_OBJ) : $(SHARED_SRC)
	$(CC) $(CFLAGS) $(PFLAGS) $(SHARED_INCLUDES) -c -o $(SHARED_OBJ) \
		$(SHARED_SRC)

$(SHARED_LIB) : $(SHARED_OBJ)
	$(CC) $(PFLAGS) -o $(SHARED_LIB) $(SHARED_OBJ) \
		$(SHARED_LDFLAGS) $(SHARED_LDLIBS)


install: def
	$(INSTALL_PROG) $(INSTALL_OPTS) $(XHELPER) $(INSTALL_DIR)

install_shared: $(SHARED_LIB)
	$(INSTALL_PROG) $(INSTALL_OPTS) $(SHARED_LIB) $(INSTALL_LDIR)

install_all: install install_shared


clean:
	rm -f $(ALL_BIN) $(ALL_OBJ) core $(XHELPER).core
