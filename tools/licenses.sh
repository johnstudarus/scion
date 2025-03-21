#!/bin/bash

set -e

ROOTDIR=$(dirname "$0")/..
TARGET="${TARGET:-"//:scion"}"

bazel build $TARGET

DSTDIR=${1:-$ROOTDIR/licenses/data}
EXECROOT=$(bazel info execution_root 2>/dev/null)

rm -rf $DSTDIR

# We exclude dependencies named <something>~<something>. These are cannonical
# dependency names; they're redundant and often match a .gitignore entry so
# not included in a commit.

(cd $EXECROOT/external; find -L . -iregex '.*\(LICENSE\|COPYING\).*') | grep -E -v "^./[^/]*~" | while IFS= read -r path ; do
    # skip over node JS stuff, this is only used during build time.
    if [[ "$path" =~ "node_modules" || "$path" =~ "nodejs" || "$path" =~ "rules_license" ]]; then
        continue
    fi
    dst=$DSTDIR/$(dirname $path)
    mkdir -p $dst
    cp $EXECROOT/external/$path $dst
done

# Bazel tools are used only for building.
# We don't need these licenses to be distributed with the containers.
rm -rf $DSTDIR/bazel_tools

# These are not actual licenses.
rm -rf $DSTDIR/com_github_spf13_cobra/cobra
rm -rf $DSTDIR/com_github_uber_jaeger_client_go/scripts
rm -rf $DSTDIR/com_github_uber_jaeger_lib/scripts
rm -rf $DSTDIR/com_github_prometheus_procfs/scripts
rm -rf $DSTDIR/org_uber_go_zap/checklicense.sh
rm -rf $DSTDIR/org_golang_x_tools/gopls/
rm -rf $DSTDIR/org_golang_x_tools/internal/lsp/cmd/usage/licenses.hlp
rm -rf $DSTDIR/com_github_google_certificate_transparency_go/scripts
rm -rf $DSTDIR/python3_10_x86_64-unknown-linux-gnu/
rm -rf $DSTDIR/aspect_bazel_lib/
rm -rf $DSTDIR/aspect_rules_js/
rm -rf $DSTDIR/npm__*/
find $DSTDIR/ -name "*.go" -type f -delete
find $DSTDIR/ -path "*/testdata/*" -type f -delete
