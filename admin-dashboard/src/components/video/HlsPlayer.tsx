"use client";
import React, { useEffect, useRef } from "react";
import Hls from "hls.js";

type HlsPlayerProps = {
  src: string;
  autoPlay?: boolean;
  muted?: boolean;
  controls?: boolean;
  poster?: string;
  className?: string;
};

export default function HlsPlayer({ src, autoPlay = true, muted = true, controls = true, poster, className }: HlsPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    const canNativePlay = video.canPlayType("application/vnd.apple.mpegurl");

    if (canNativePlay) {
      // Safari и iOS могут проигрывать HLS нативно
      video.src = src;
    } else if (Hls.isSupported()) {
      const hls = new Hls({
        // Небольшие безопасные дефолты
        enableWorker: true,
        lowLatencyMode: true,
      });
      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);

      const onError = (event: any, data: any) => {
        if (data?.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              break;
          }
        }
      };
      hls.on(Hls.Events.ERROR, onError);
    } else {
      // Fallback: просто пытаемся установить src — некоторые браузеры могут поддерживать
      video.src = src;
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [src]);

  return (
    <video
      ref={videoRef}
      className={className || "w-full h-auto rounded-lg bg-black"}
      poster={poster}
      autoPlay={autoPlay}
      muted={muted}
      controls={controls}
      playsInline
    />
  );
}