#! /bin/sh

I2PY=img2py

I=wxdvdbackup
O=icons.py
T=tmp-"${O}"
X=png
S="16 24 32 48 64"

xs=0

:>"$T"
rm_T() { rm -f "$T"; }
trap rm_T 0

for N in $S ; do
	F=${I}-${N}.${X}
	if test -f "$F" ; then
		"$I2PY" -a -i "$F" "$T" || \
			{
				echo FAILED "$F" 1>&2
				xs=$((xs + 1))
			}
	else
		echo CANNOT FIND "$F" 1>&2
	fi
done

pipest=$?
xs=$((xs + pipest))

sed \
	-e 's/(/("""/' \
	-e 's/)/""")/' \
	-e 's/^[ 	]*"\([^"]\{1,\}\)"/\1/' \
	< "$T" \
	| tr '\r' '\n' \
	> "$O"

pipest=$?
xs=$((xs + pipest))

exit $xs

