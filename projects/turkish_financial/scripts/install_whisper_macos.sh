#!/usr/bin/env bash
set -euo pipefail

# This installer is intentionally host-native. It never runs in Docker and only
# writes beneath the directory explicitly selected by the operator.
: "${WHISPER_CPP_DIR:?Set WHISPER_CPP_DIR to an absolute install directory first}"
case "$WHISPER_CPP_DIR" in
  /*) ;;
  *) echo "WHISPER_CPP_DIR must be an absolute path" >&2; exit 2 ;;
esac

for dependency in cmake git ffmpeg yt-dlp; do
  command -v "$dependency" >/dev/null || {
    echo "Missing $dependency. Install it first (for example: brew install cmake ffmpeg yt-dlp)." >&2
    exit 2
  }
done

if [ "$(uname -m)" != "arm64" ]; then
  echo "This installer is for Apple Silicon. Open a native terminal (not Rosetta) and run it again." >&2
  exit 2
fi

mkdir -p "$(dirname "$WHISPER_CPP_DIR")"

if [ ! -d "$WHISPER_CPP_DIR/.git" ]; then
  git clone https://github.com/ggml-org/whisper.cpp.git "$WHISPER_CPP_DIR"
fi

# Some Macs still have an Intel Homebrew CMake under /usr/local.  CMake itself
# can run under Rosetta, but the generated compiler commands must target arm64;
# otherwise ggml combines an x86 target with Apple-M1 CPU flags and fails.
CC=/usr/bin/clang CXX=/usr/bin/clang++ cmake \
  -S "$WHISPER_CPP_DIR" \
  -B "$WHISPER_CPP_DIR/build" \
  -DGGML_METAL=ON \
  -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build "$WHISPER_CPP_DIR/build" --config Release -j 4
"$WHISPER_CPP_DIR/models/download-ggml-model.sh" small

echo "Installed native Whisper. Run the collector with:"
printf '%s\n' \
  "  projects/turkish_financial/scripts/youtube_to_text.py \\" \
  "    --whisper-bin $WHISPER_CPP_DIR/build/bin/whisper-cli \\" \
  "    --whisper-model $WHISPER_CPP_DIR/models/ggml-small.bin"
