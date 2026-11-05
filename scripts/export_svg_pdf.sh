#!/bin/sh
# Outlined vector PDF from a figure SVG: text becomes paths, geometry stays vector.
# Three steps: rsvg-convert -> pdftocairo -> rsvg-convert (text becomes paths).
set -eu
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "usage: $0 <figure.svg> [out.pdf]" >&2
    exit 2
fi
svg=$1
out=${2:-${svg%.svg}.pdf}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rsvg-convert -f pdf -o "$work/input.pdf" "$svg"
pdftocairo -svg "$work/input.pdf" "$work/outlined.svg"
# 72 dpi keeps pdftocairo's point-unit page size (85 mm = 240.945 pt).
rsvg-convert --dpi-x 72 --dpi-y 72 -f pdf -o "$out" "$work/outlined.svg"
pdfinfo "$out" | sed -n 's/^Page size:/page size:/p'
fonts=$(pdffonts "$out" | tail -n +3 | grep -c . || true)
if [ "$fonts" -ne 0 ]; then
    echo "warning: $fonts font(s) still referenced; text is not fully outlined" >&2
fi
printf '%s -> %s\n' "$svg" "$out"
