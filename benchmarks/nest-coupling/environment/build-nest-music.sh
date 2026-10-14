#!/bin/sh
# Build MUSIC 1.2.1 and NEST 3.10.0 (MPI + MUSIC + OpenMP) into one conda prefix with Apple clang.
#
# Usage: build-nest-music.sh PREFIX WORK NEST_SDIST MUSIC_ARCHIVE [JOBS]
#   PREFIX         conda environment that already holds the libraries (Open MPI 5.0.10, LLVM OpenMP,
#                  GSL 2.8, Boost 1.88, libtool, CMake 3.29.6, Python 3.11, NumPy, Cython, autotools)
#   WORK           new working directory (must not exist) for sources, build trees and logs
#   NEST_SDIST     nest_simulator-3.10.0.tar.gz from PyPI
#   MUSIC_ARCHIVE  MUSIC 1.2.1 GitHub tag archive
# Nothing outside PREFIX and WORK is written. Each step logs to WORK/logs.
set -eu

PREFIX=$1 WORK=$2 NEST_SDIST=$3 MUSIC_ARCHIVE=$4 JOBS=${5:-8}
NEST_SHA256=8fbd7df4a3e941784d4b1d5825ded234bdc915238faac0982c62e4cb80134d52
MUSIC_SHA256=7bf8160ba4f261b8fa14bf8ceab318912b8b8d8a1d8e653c6fbdd45eb27a51c7

[ ! -e "$WORK" ] || { echo "WORK must not exist yet: $WORK" >&2; exit 2; }
mkdir -p "$WORK/logs" "$WORK/shim" "$WORK/src"
check() { [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" = "$2" ] || { echo "digest mismatch: $1" >&2; exit 2; }; }
check "$NEST_SDIST" "$NEST_SHA256"
check "$MUSIC_ARCHIVE" "$MUSIC_SHA256"

# The environment's tools first; MUSIC's autogen.sh calls glibtoolize on macOS.
ln -sf "$PREFIX/bin/libtoolize" "$WORK/shim/glibtoolize"
export PATH="$WORK/shim:$PREFIX/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# Apple clang with the macOS SDK C++ library, as in Engram's NEST 3.10 builds. NEST 3.10.0 does
# not compile against conda-forge libc++ 22 (std::less on boost::tuple in heap algorithms), and
# MUSIC must share NEST's C++ runtime. -nostdlib++ plus the SDK stub keeps PREFIX/lib/libc++ out.
SDK=$(xcrun --show-sdk-path)
export CC=/usr/bin/clang CXX=/usr/bin/clang++
export OMPI_CC="$CC" OMPI_CXX="$CXX"
STDLIB="-nostdlib++ $SDK/usr/lib/libc++.1.tbd"
export LDFLAGS="$STDLIB -Wl,-rpath,$PREFIX/lib"
# libtool drops -nostdlib++ for MUSIC's shared library; the SDK directory must therefore come
# before PREFIX/lib in the MPI wrapper's own linker flags, which MUSIC's configure reads.
export OMPI_LDFLAGS="-L$SDK/usr/lib -L$PREFIX/lib -Wl,-rpath,$PREFIX/lib"
unset PYTHONPATH PYTHONHOME CPPFLAGS

# MUSIC
cd "$WORK/src" && tar -xzf "$MUSIC_ARCHIVE"
cd MUSIC-1.2.1
./autogen.sh > "$WORK/logs/music-autogen.log" 2>&1
# configure keys its Open MPI branch on the name mpiCC; that branch takes the compile and link
# flags from PREFIX/bin/mpicxx -showme (PATH) and enables MUSIC's own test suite.
./configure --prefix="$PREFIX" MPI_CXX=mpiCC \
  PYTHON="$PREFIX/bin/python" > "$WORK/logs/music-configure.log" 2>&1
make -j"$JOBS" > "$WORK/logs/music-make.log" 2>&1
make install > "$WORK/logs/music-install.log" 2>&1

# NEST
cd "$WORK/src" && tar -xzf "$NEST_SDIST"
cmake -S nest_simulator-3.10.0 -B nest-build \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_BUILD_TYPE=Release -Dwith-optimize=-O2 \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_OSX_SYSROOT="$SDK" \
  -DCMAKE_EXE_LINKER_FLAGS="$LDFLAGS" -DCMAKE_SHARED_LINKER_FLAGS="$LDFLAGS" \
  -DCMAKE_MODULE_LINKER_FLAGS="$LDFLAGS" \
  -DOpenMP_C_FLAGS="-Xpreprocessor -fopenmp" -DOpenMP_CXX_FLAGS="-Xpreprocessor -fopenmp" \
  -DOpenMP_C_LIB_NAMES=omp -DOpenMP_CXX_LIB_NAMES=omp -DOpenMP_omp_LIBRARY="$PREFIX/lib/libomp.dylib" \
  -DOpenMP_C_INCLUDE_DIR="$PREFIX/include" -DOpenMP_CXX_INCLUDE_DIR="$PREFIX/include" \
  -DMPI_HOME="$PREFIX" \
  -DPython_EXECUTABLE="$PREFIX/bin/python" \
  -Dwith-python=ON -Dwith-mpi=ON -Dwith-music="$PREFIX" -Dwith-openmp=ON \
  -Dwith-gsl="$PREFIX" -Dwith-boost="$PREFIX" -Dwith-ltdl="$PREFIX" \
  -DCMAKE_PREFIX_PATH="$PREFIX" > "$WORK/logs/nest-configure.log" 2>&1
cmake --build nest-build --parallel "$JOBS" > "$WORK/logs/nest-build.log" 2>&1
cmake --install nest-build > "$WORK/logs/nest-install.log" 2>&1
# Every installed MUSIC and NEST binary must use the system C++ runtime, never PREFIX/lib/libc++.
for f in "$PREFIX/lib/libmusic.dylib" "$PREFIX/bin/music" \
         "$PREFIX/lib/python3.11/site-packages/nest/nestkernel_api.so"; do
  if otool -L "$f" | grep -q '@rpath/libc++'; then echo "wrong C++ runtime: $f" >&2; exit 3; fi
done
echo "build complete"
