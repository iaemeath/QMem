#!/bin/bash
set -e
echo 'Building Mojo Binary...'
export PATH=/home/iaemeath/mojo-env/bin:$PATH
cd /home/iaemeath/code/QMem

mojo build src/mcp_server.mojo -o release/qmem_mcp

echo 'Preparing packaging directory...'
rm -rf release_pkg
mkdir -p release_pkg/QMem_V1.1

cp -r release/* release_pkg/QMem_V1.1/
cp -r python release_pkg/QMem_V1.1/

rm -f release_pkg/QMem_V1.1/core_memory.db

echo 'Compressing...'
cd release_pkg
tar -czvf qmem_v1.1.tar.gz QMem_V1.1/

echo 'Creating GitHub Release...'
cd /home/iaemeath/code/QMem
gh release create v1.1 release_pkg/qmem_v1.1.tar.gz --title 'QMem v1.1 (V3.0 Architecture)' --notes 'This release contains the V3.0 Hybrid Proxy Architecture (Plan 10) compiled binary and required ONNX/SQLite FFI extensions.'
echo 'Done!'
