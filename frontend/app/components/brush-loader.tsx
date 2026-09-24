"use client";

import { useEffect, useRef, useState } from "react";
import 中 from "@/lib/stroke-data/中.json";
import 事 from "@/lib/stroke-data/事.json";
import 写 from "@/lib/stroke-data/写.json";
import 在 from "@/lib/stroke-data/在.json";
import 排 from "@/lib/stroke-data/排.json";
import 故 from "@/lib/stroke-data/故.json";
import 正 from "@/lib/stroke-data/正.json";
import 队 from "@/lib/stroke-data/队.json";

// Stroke outlines from Make Me a Hanzi via hanzi-writer-data 2.0.1 (Arphic
// Public License, see lib/stroke-data/ARPHICPL.TXT). Only the characters the
// loader writes are vendored, rather than the whole 47 MB data package; add
// a file here before using a new character.
const STROKE_DATA: Record<string, typeof 中> = {
  中,
  事,
  写,
  在,
  排,
  故,
  正,
  队,
};

const PAUSE_BETWEEN_LOOPS_MS = 1500;

function cssColor(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

// A short phrase written stroke by stroke in 田字格 practice squares, on a
// loop, with its pinyin underneath, as a waiting animation. Without
// animation support, or when the reader prefers reduced motion, the
// characters are simply shown. Give it a `key` of the text so a new phrase
// starts a fresh animation.
export function BrushLoader({ text, pinyin }: { text: string; pinyin: string }) {
  const characters = [...text];
  const canvasRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    if (
      typeof window.matchMedia !== "function" ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    const canvases = canvasRefs.current;
    let cancelled = false;
    let pause: ReturnType<typeof setTimeout> | undefined;

    import("hanzi-writer").then(({ default: HanziWriter }) => {
      if (cancelled) {
        return;
      }
      const writers = [...text].map((char, index) =>
        HanziWriter.create(canvases[index]!, char, {
          width: 60,
          height: 60,
          padding: 5,
          showCharacter: false,
          showOutline: true,
          strokeColor: cssColor("--foreground"),
          outlineColor: cssColor("--border"),
          strokeAnimationSpeed: 2,
          delayBetweenStrokes: 80,
          charDataLoader: () => STROKE_DATA[char],
        }),
      );
      setAnimating(true);

      async function writeAll() {
        for (const writer of writers) {
          await writer.hideCharacter({ duration: 0 });
        }
        for (const writer of writers) {
          if (cancelled) {
            return;
          }
          await writer.animateCharacter();
        }
        if (!cancelled) {
          pause = setTimeout(writeAll, PAUSE_BETWEEN_LOOPS_MS);
        }
      }
      void writeAll();
    });

    return () => {
      cancelled = true;
      clearTimeout(pause);
      for (const canvas of canvases) {
        canvas?.replaceChildren();
      }
    };
  }, [text]);

  return (
    <div className="brush-loader" aria-hidden="true">
      <div className="brush-loader-squares">
        {characters.map((char, index) => (
          <span key={index} lang="zh" className="tianzige">
            {!animating && char}
            <span
              ref={(element) => {
                canvasRefs.current[index] = element;
              }}
              className="brush-canvas"
            />
          </span>
        ))}
      </div>
      <p className="brush-loader-pinyin">{pinyin}</p>
    </div>
  );
}
