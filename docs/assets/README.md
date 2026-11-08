# Repository media

`le-demo.gif` is the looping README preview; `le-demo.mp4` is the H.264 video
(1128 x 694, approximately 27 seconds, no audio). `le-demo.cast` is the original
asciicast v2 terminal recording, suitable for replay with asciinema.

The recording runs the actual released Linux AMD64 executable, version 1.0.0,
in a real Bash pseudoterminal. Its binary SHA-256 is
`8fba0b1514bd5291e1200cbda6ede46d2eb1d6c111cfc14d4edf8841cc2382d8`.
Typing is scripted and paced for readability. All directories and files are
disposable samples; no personal directory listings are recorded. The exported
JSON was parsed and checked for the expected absolute directory key and nested
filename. The application itself is unmodified.

Commands shown:

```bash
le demo
le demo -rn 2
le demo -r --output-json tree.json
head -n 24 tree.json
```

The final command previews the first 24 lines of the real generated JSON file.

The GIF is rendered using asciinema agg 1.9.0 with the GitHub dark theme,
Consolas text and Segoe UI Emoji. The MP4 is encoded with FFmpeg using H.264,
YUV420P, 24 fps, CRF 18 and fast-start metadata. No output is invented or
replaced in the recording.

To render the supplied recording again:

```bash
agg --renderer resvg --text-font-family Consolas --emoji-font-family "Segoe UI Emoji" --font-size 20 --line-height 1.12 --theme github-dark --fps-cap 12 --idle-time-limit 8 --last-frame-duration 6 le-demo.cast le-demo.gif
ffmpeg -i le-demo.gif -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=0x0d1117,fps=24" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart -an le-demo.mp4
```

Use installed equivalent fonts when replaying on another platform. The GIF,
MP4 and recording are small repository assets and do not require Git LFS.
