#! /bin/sh
#
# When sources are from repo, e.g. git and repo excludes
# the several generated autoblech files, the poor hapless
# soul attempting to make the source useful will have to
# jump through hoops.  This script might, for the lucky,
# be a gentle nudge toward one such hoop.
#
# License inherited from enclosing/including source package.
#

PROG=${0##*/}

: ${ALLDIRS:="lib_misc ."}

e2 () { printf '%s: %s\n' "$PROG" "$*" 1>&2; }
fail () { e2 "$@"; exit 1; }

spew_fail_blech () {
	# subsequent kludges fail in absence
	# of precedent kludges which also
	# fail yet produce and leave files
	# on which subsequent kludges depend
	autoconf -f >/dev/null 2>&1 || test 0 -eq 0
	autoreconf -f >/dev/null 2>&1 || test 0 -eq 0
	autoheader -f >/dev/null 2>&1 || test 0 -eq 0
	automake --add-missing -f >/dev/null 2>&1 || test 0 -eq 0
	automake -f >/dev/null 2>&1 || test 0 -eq 0

	return 0
}

spew_blech () {
	e2 Attempting expected failure  autospew in \""$PWD"\"

	spew_fail_blech

	e2 Attempting autospew in \""$PWD"\"

	autoheader && automake --add-missing \
	&& automake && autoconf \
	&& e2 Wow, looks like success in \""$PWD"\"
}

finagle () {
	( cd "$1" && spew_blech ) || \
		fail failed to finagle the kludge in \""$1"\"
}

for D in $ALLDIRS ; do
	finagle "$D"
done

