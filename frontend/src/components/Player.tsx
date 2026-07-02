import mpegts from "mpegts.js";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { readPrefs, writePrefs } from "@/lib/prefs";
import {
  deleteSubtitle,
  getAudioTracks,
  uploadSubtitle,
  type AudioTrack,
  type LectureItem,
} from "@/api";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

function audioLabel(t: AudioTrack, i: number): string {
  const lang = t.language && t.language !== "und" ? t.language.toUpperCase() : null;
  const base = t.title || lang || `Track ${i + 1}`;
  const ch = t.channels === 2 ? " · 2.0" : t.channels === 6 ? " · 5.1" : t.channels ? ` · ${t.channels}ch` : "";
  return base + ch;
}

export interface PlayerHandle {
  seek: (t: number) => void;
  getCurrentTime: () => number;
}

interface PlayerProps {
  lecture: LectureItem;
  startPosition?: number;
  onProgress?: (positionSec: number, durationSec: number, ended: boolean) => void;
  onEnded?: () => void;
  onNext?: () => void;
  hideAutoplayNext?: boolean;
}

const Player = forwardRef<PlayerHandle, PlayerProps>(function Player(
  { lecture, startPosition = 0, onProgress, onEnded, onNext, hideAutoplayNext = false },
  handleRef,
) {
  const ref = useRef<HTMLVideoElement>(null);
  const lastTick = useRef(0);

  useImperativeHandle(handleRef, () => ({
    seek: (t: number) => {
      const v = ref.current;
      if (!v) return;
      try {
        v.currentTime = t;
        void v.play();
      } catch {
        /* not seekable */
      }
    },
    getCurrentTime: () => ref.current?.currentTime ?? 0,
  }));
  const [err, setErr] = useState(false);
  const [rate, setRate] = useState(() => readPrefs().rate);
  const [autoplay, setAutoplay] = useState(() => readPrefs().autoplayNext);
  const [audioTracks, setAudioTracks] = useState<AudioTrack[]>([]);
  const [audioIndex, setAudioIndex] = useState(0);
  const resumeAt = useRef<{ time: number; playing: boolean } | null>(null);
  const [hasSub, setHasSub] = useState(!!lecture.subtitle);
  const [subVersion, setSubVersion] = useState(0);
  // which subtitle track is showing: -1 = off, else an index into subtitleTracks
  const [subChoice, setSubChoice] = useState(-1);
  const subInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setHasSub(!!lecture.subtitle);
    setSubVersion(0);
    const hasAny = !!lecture.subtitle || (lecture.subtitles?.length ?? 0) > 0;
    setSubChoice(hasAny ? 0 : -1);
  }, [lecture.id, lecture.subtitle, lecture.subtitles]);
  const subtitleUrl = `/api/lectures/${lecture.id}/subtitle?v=${subVersion}`;

  // apply the chosen track to the video's TextTracks (order matches render below)
  const applyTrackModes = (choice: number) => {
    const v = ref.current;
    if (!v) return;
    for (let i = 0; i < v.textTracks.length; i++) {
      v.textTracks[i].mode = i === choice ? "showing" : "disabled";
    }
  };
  const onUploadSub = async (f: File) => {
    try {
      await uploadSubtitle(lecture.id, f);
      setHasSub(true);
      setSubVersion((v) => v + 1);
      setSubChoice(0); // the custom track renders first
      toast.success("Subtitles added");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    }
  };
  const onRemoveSub = async () => {
    try {
      await deleteSubtitle(lecture.id);
      setHasSub(false);
      setSubChoice((lecture.subtitles?.length ?? 0) > 0 ? 0 : -1);
      toast.success("Subtitles removed");
    } catch {
      toast.error("Could not remove subtitles");
    }
  };

  // re-apply track visibility whenever the choice or the available tracks change
  useEffect(() => {
    applyTrackModes(subChoice);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subChoice, hasSub, subVersion, lecture.id, lecture.subtitles]);

  // fetch the file's audio tracks (reset when the lecture changes)
  useEffect(() => {
    setAudioTracks([]);
    setAudioIndex(0);
    resumeAt.current = null;
    if (lecture.playback === "remux" || lecture.playback === "document") return;
    let cancelled = false;
    getAudioTracks(lecture.id)
      .then((t) => !cancelled && setAudioTracks(t))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [lecture.id, lecture.playback]);

  const switchAudio = (n: number) => {
    const v = ref.current;
    resumeAt.current = v ? { time: v.currentTime, playing: !v.paused } : null;
    setAudioIndex(n);
  };

  const changeRate = (r: number) => {
    setRate(r);
    writePrefs({ rate: r });
    if (ref.current) ref.current.playbackRate = r;
  };
  const changeAutoplay = (v: boolean) => {
    setAutoplay(v);
    writePrefs({ autoplayNext: v });
  };
  const onVolume = () => {
    const v = ref.current;
    if (v) writePrefs({ volume: v.volume, muted: v.muted });
  };

  // keyboard shortcuts (ignored while typing in a field)
  useEffect(() => {
    if (lecture.playback === "document") return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const v = ref.current;
      if (!v) return;
      switch (e.key) {
        case " ":
          e.preventDefault();
          if (v.paused) void v.play();
          else v.pause();
          break;
        case "ArrowLeft":
          e.preventDefault();
          v.currentTime = Math.max(0, v.currentTime - 5);
          break;
        case "ArrowRight":
          e.preventDefault();
          v.currentTime = Math.min(v.duration || Infinity, v.currentTime + 5);
          break;
        case "n":
        case "N":
          onNext?.();
          break;
        case "f":
        case "F":
          if (document.fullscreenElement) void document.exitFullscreen();
          else void v.requestFullscreen?.();
          break;
        case "m":
        case "M":
          v.muted = !v.muted;
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lecture.playback, onNext]);

  const mediaUrl =
    lecture.playback === "remux"
      ? `/api/lectures/${lecture.id}/remux`
      : audioIndex > 0
        ? `${lecture.stream}?audio=${audioIndex}`
        : lecture.stream;

  useEffect(() => {
    setErr(false);
    const video = ref.current;
    if (!video || lecture.playback === "document") return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let player: any = null;

    if (lecture.playback === "mpegts" && mpegts.isSupported()) {
      player = mpegts.createPlayer({ type: "mpegts", url: lecture.stream, isLive: false });
      player.attachMediaElement(video);
      player.load();
    } else {
      video.src = mediaUrl;
    }

    return () => {
      if (player) player.destroy();
      else {
        video.removeAttribute("src");
        video.load();
      }
    };
  }, [lecture.id, lecture.playback, lecture.stream, mediaUrl]);

  const handleLoaded = () => {
    const v = ref.current;
    if (!v) return;
    const p = readPrefs();
    v.playbackRate = rate;
    v.volume = p.volume;
    v.muted = p.muted;
    applyTrackModes(subChoice);
    // resuming after an audio-track switch: restore position + play state
    const resume = resumeAt.current;
    if (resume) {
      resumeAt.current = null;
      try {
        v.currentTime = resume.time;
      } catch {
        /* not seekable yet */
      }
      if (resume.playing) void v.play();
      return;
    }
    if (startPosition > 2 && (!v.duration || startPosition < v.duration - 1)) {
      try {
        v.currentTime = startPosition;
      } catch {
        /* not seekable yet */
      }
    }
  };
  const handleTime = () => {
    const v = ref.current;
    if (!v) return;
    const now = Date.now();
    if (now - lastTick.current > 5000) {
      lastTick.current = now;
      onProgress?.(v.currentTime, v.duration || 0, false);
    }
  };
  const flush = () => {
    const v = ref.current;
    if (v) onProgress?.(v.currentTime, v.duration || 0, false);
  };
  const handleEnded = () => {
    const v = ref.current;
    const d = v?.duration || 0;
    onProgress?.(d, d, true);
    if (autoplay) onEnded?.();
  };

  if (lecture.playback === "document") {
    return (
      <div className="space-y-3">
        <iframe
          title={lecture.title}
          src={lecture.stream}
          className="aspect-video w-full rounded-lg border bg-white"
        />
        <Button asChild variant="secondary">
          <a href={lecture.stream} target="_blank" rel="noreferrer">Open document</a>
        </Button>
      </div>
    );
  }

  if (err) {
    return (
      <div className="grid aspect-video w-full place-items-center gap-3 rounded-lg border bg-card text-center">
        <div>
          <p className="text-muted-foreground">Couldn’t play this file in the browser.</p>
          <Button asChild className="mt-3">
            <a href={lecture.stream}>Download</a>
          </Button>
        </div>
      </div>
    );
  }

  // custom/sidecar subtitle (managed via upload controls) + embedded tracks
  const subtitleTracks: { label: string; url: string }[] = [];
  if (hasSub) subtitleTracks.push({ label: "Subtitles", url: subtitleUrl });
  for (const s of lecture.subtitles ?? []) subtitleTracks.push(s);

  return (
    <div className="space-y-2">
      <video
        ref={ref}
        className="aspect-video w-full rounded-lg border bg-black"
        controls
        autoPlay
        onLoadedMetadata={handleLoaded}
        onTimeUpdate={handleTime}
        onPause={flush}
        onSeeked={flush}
        onEnded={handleEnded}
        onVolumeChange={onVolume}
        onError={() => setErr(true)}
      >
        {subtitleTracks.map((t) => (
          <track key={t.url} kind="subtitles" src={t.url} label={t.label} />
        ))}
      </video>
      <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
        {hideAutoplayNext ? (
          <span />
        ) : (
          <label className="flex cursor-pointer items-center gap-2 select-none">
            <Checkbox checked={autoplay} onCheckedChange={(v) => changeAutoplay(v === true)} />
            Autoplay next
          </label>
        )}
        <div className="flex items-center gap-2">
          <input
            ref={subInput}
            type="file"
            accept=".srt,.vtt,.ass,.ssa,.sub"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onUploadSub(f);
              e.currentTarget.value = "";
            }}
          />
          <button type="button" onClick={() => subInput.current?.click()} className="hover:text-foreground">
            {hasSub ? "Replace subs" : "Add subs"}
          </button>
          {hasSub && (
            <button type="button" onClick={() => void onRemoveSub()} className="hover:text-foreground">
              Remove
            </button>
          )}
          {subtitleTracks.length > 0 && (
            <>
              <span>Subtitles</span>
              <select
                value={subChoice}
                onChange={(e) => setSubChoice(Number(e.target.value))}
                className="h-8 max-w-[9rem] rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value={-1}>Off</option>
                {subtitleTracks.map((t, i) => (
                  <option key={t.url} value={i}>{t.label}</option>
                ))}
              </select>
            </>
          )}
          {audioTracks.length > 1 && (
            <>
              <span>Audio</span>
              <select
                value={audioIndex}
                onChange={(e) => switchAudio(Number(e.target.value))}
                className="h-8 max-w-[9rem] rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {audioTracks.map((t, i) => (
                  <option key={i} value={i}>{audioLabel(t, i)}</option>
                ))}
              </select>
            </>
          )}
          <span>Speed</span>
          <select
            value={rate}
            onChange={(e) => changeRate(Number(e.target.value))}
            className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {SPEEDS.map((r) => (
              <option key={r} value={r}>{r}×</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
});

export default Player;
