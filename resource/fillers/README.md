# Split-screen filler pool

Filler footage fills the **bottom half** of the frame to hold attention while
the narration plays.

This directory is one possible pool. The active one is whatever
`split_screen_filler_dir` points at in `config.toml` — currently `videos/`,
which holds multi-hour source videos.

## How a filler is chosen

Two independent random picks happen per task:

1. **Which file** — one video is picked at random from the pool directory.
2. **Which part of it** — a random interval as long as the generated video is
   cut out of that file, skipping the first and last 30 seconds.

The second pick is what makes a single multi-hour source usable forever: a
3-hour video yields thousands of non-overlapping 45-second backgrounds, so no
two uploads share the same footage. The 30-second margins exist because long
videos open with a title card and close with subscribe prompts and black
frames.

If a file is too short for the margins they are dropped but the start is still
randomised; if it is shorter than the narration it starts at 0 and loops.
Implementation: `pick_filler_segment_start()` in `app/services/video.py`.

## Framing

Footage is scaled to fill the panel and **centre-cropped** — never letterboxed,
never stretched. A 1280x720 landscape source cropped into a 1080x960 panel
loses its left and right edges, keeping the middle, where the subject almost
always is.

### Trimming watermarks and bars

Centre-cropping cannot remove a watermark, because watermarks sit near the
middle-bottom where the crop keeps everything. Drop a `crop.json` next to the
source files to trim edges *before* the scale:

```json
{
  "Some Long Video.mp4": { "bottom": 70 },
  "default":             { "bottom": 0 }
}
```

Values are pixels of the source, per edge; missing edges are 0. `default`
applies to any file without its own entry. A bad or missing file just means no
trimming — it never fails a render.

One limit worth knowing: this is static per file. A compilation whose segments
switch between full-frame and pillarboxed content cannot be fixed by one set of
numbers. A fixed watermark can; varying pillarbox padding cannot.

## Audio

Filler audio is **kept at 70% volume by default**, because much of this footage
is ASMR and the sound is part of what holds a viewer. FFmpeg attenuates it while
building the split, and the narration is mixed over it afterwards, so the voice
always sits on top.

The level is set by `_FILLER_KEEP_AUDIO_VOLUME` in `cli.py`. The narration runs
at 1.0, so this value decides how much the ASMR competes with the voice — at
70% it is clearly present rather than a background bed.

Change it with `--split-screen-volume 0.25`, or pass `0` to mute the filler
entirely. Sources without an audio track are detected and skipped, so a silent
gameplay capture will not break the render.

## Configuration

```toml
[app]
split_screen_filler_dir = "videos"
```

Per-run overrides:

```bash
--split-screen-video path/to/clip.mp4   # one specific file
--split-screen-video path/to/dir/       # a different pool
--split-screen-ratio 0.5                # 0.5 = even split (default)
--no-split-screen                       # skip it for this run
```

## Requirements for a source file

- Container: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.flv`
- Any resolution and duration — longer is better, as it means more variety
- Audio is always discarded, so the narration is never fought over
- Landscape sources crop cleanly into the bottom panel

## What is in this directory

Ten short clips from Pexels under its free licence: ebru marbling, acrylic
pour, rolled ice cream, cake frosting, paint mixing, hydraulic press, melting
chocolate, foam texture, liquid marbling and clay smoothing. They are kept as a
licence-clean fallback pool; point `split_screen_filler_dir` here to use them.

Each was reviewed frame by frame before being added, which produced two
selection rules worth more than the search term used:

- **Close-ups only.** Wide shots showing a person working read as stock footage
  and pull attention off the narration.
- **Continuous motion.** The clip is trimmed to the narration length, not to
  its own ending, so it must still be moving wherever the cut lands.

A keyword search guarantees neither — searching "glitter" returned a person
covered in glitter, and "foam" returned a snail. Look at a frame first.

## Sourcing note

Footage ripped from other people's uploads stays their property, and creator
watermarks often travel with it and appear in the output. On YouTube this
invites Content ID claims, which route revenue to the rights holder rather than
to you. Footage explicitly released for reuse, or your own recordings, avoid
that.
