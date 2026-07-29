# Local YouTube to text (macOS / Apple Silicon)

This is the deliberately small, local-only collection path for finance videos:

```text
new public YouTube video -> Turkish caption -> local Whisper small -> PostgreSQL
```

It does not use Firecrawl, AVGRAB, a cloud speech API, or a background model service.
The model is loaded only while the command is running, one video is handled at a time,
and temporary audio is deleted when each video completes.

## One-time host setup

The finance Docker services must already be running. Install host tools once:

```bash
brew install cmake ffmpeg yt-dlp
export WHISPER_CPP_DIR="/absolute/path/you/choose/whisper.cpp"
projects/turkish_financial/scripts/install_whisper_macos.sh
```

The installer builds `whisper.cpp` with Metal enabled and downloads the multilingual
`small` model. It uses about 850 MiB for the model, making it the default safe choice
on the 32 GB M1 Max when other applications are active.

If an earlier run reports both `x86 detected` and `unknown target CPU 'apple-m1'`,
rerun the installer after updating this project. The installer explicitly reconfigures
the build for `arm64`, including when an older Intel Homebrew CMake is first on `PATH`.

## Collect new videos

Run this from the repository root:

```bash
projects/turkish_financial/scripts/youtube_to_text.py \
  --whisper-bin "$WHISPER_CPP_DIR/build/bin/whisper-cli" \
  --whisper-model "$WHISPER_CPP_DIR/models/ggml-small.bin"
```

The script reads the configured `YOUTUBE_CHANNELS` through the running finance
container. Pass one or more `--channel https://www.youtube.com/@example/videos`
arguments to override that list for a one-off collection.

It caches by YouTube `video_id` in PostgreSQL:

- a stored transcript is never downloaded or transcribed again;
- a blocked or unavailable video is retried no more than once every 24 hours;
- only new videos are processed;
- audio and subtitle files exist only in a temporary host directory and are removed
  after each video.

After each local run, the saved transcripts are analysed in the finance container
without contacting YouTube again. Detected BIST ticker mentions create/update the
per-video YouTube sentiment and the ticker's daily YouTube and combined scores. The
dashboard completion message reports how many ticker mentions and score rows changed.

## If YouTube blocks anonymous requests

Use a browser session you control. This reads cookies directly from that local browser;
the script does not write them to the database, project files, or API logs.

```bash
projects/turkish_financial/scripts/youtube_to_text.py \
  --cookies-from-browser chrome \
  --whisper-bin "$WHISPER_CPP_DIR/build/bin/whisper-cli" \
  --whisper-model "$WHISPER_CPP_DIR/models/ggml-small.bin"
```

Use `safari`, `firefox`, or another browser name supported by your installed `yt-dlp`
instead of `chrome` when appropriate. Keep the browser profile local and do not commit
or share exported cookies.

## Run it from the dashboard

Install the lightweight local runner once. It binds only to localhost port 8765 and
does not load Whisper until the dashboard starts a run:

    projects/turkish_financial/scripts/install_youtube_runner_macos.sh

Open http://127.0.0.1:8000/ui, choose public access or your local browser session,
then click **Run local video transcription**. The button disables itself while one job
is active, so it cannot run two collectors concurrently.

Use **Stop safely** to terminate the current local collector. Completed videos remain
cached; an incomplete video is not saved. The dashboard also lists its YouTube
sources. Adding or removing a channel creates the local-only file
`.local/youtube-sources.json`, which affects the next run without changing a public
API or storing browser cookies. **Use project defaults** deletes that local override
and returns to `YOUTUBE_CHANNELS` / the project defaults.
